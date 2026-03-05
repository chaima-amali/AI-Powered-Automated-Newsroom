"""
embedding/pipeline.py
----------------------
Orchestrates the full embedding + clustering pipeline:

  1. Count unprocessed articles.
  2. Stream them in configurable batches (no full-table load).
  3. Build input text (title + first 500 words of content).
  4. Encode with the local sentence-transformer model.
  5. Run DBSCAN clustering over the *full* batch of new embeddings.
  6. Write embeddings + cluster_id + is_processed=true back to Postgres.

Design decisions for production:
  - Batched DB reads    → constant memory regardless of dataset size.
  - Single model load   → amortises GPU/CPU warm-up across all batches.
  - Atomic DB writes    → executemany, no partial updates.
  - Idempotent          → re-running skips already-processed articles.
  - Configurable        → all tuneable knobs come from env vars.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Generator

import numpy as np

from db.repository import (
    bulk_update_embeddings_and_clusters,
    count_unprocessed_articles,
    fetch_unprocessed_articles,
)
from embedding.clustering import cluster_embeddings
from embedding.generator import build_text, embed_texts

logger = logging.getLogger(__name__)

# ── Tuneable knobs (override via environment variables) ────────────────────────
_FETCH_BATCH   : int = int(os.environ.get("EMBEDDING_FETCH_BATCH",   256))
_ENCODE_BATCH  : int = int(os.environ.get("EMBEDDING_ENCODE_BATCH",  64))
# Input text strategy: title + first paragraph (lead sentence).
# See embedding/generator.py → build_text() for extraction logic.


def _iter_batches() -> Generator[list[dict], None, None]:
    """
    Yield successive batches of unprocessed articles from the DB.

    Uses LIMIT/OFFSET so only `_FETCH_BATCH` rows live in memory at once.
    """
    offset = 0
    while True:
        batch = fetch_unprocessed_articles(batch_size=_FETCH_BATCH, offset=offset)
        if not batch:
            break
        yield batch
        offset += len(batch)


def run_pipeline() -> dict:
    """
    Execute the full embedding + clustering pipeline.

    Returns a summary dict:
        {processed: int, batches: int, elapsed_seconds: float}
    """
    t0 = time.perf_counter()

    total_pending = count_unprocessed_articles()
    if total_pending == 0:
        logger.info("No unprocessed articles found — pipeline complete")
        return {"processed": 0, "batches": 0, "elapsed_seconds": 0.0}

    logger.info("Articles to process: %d  (fetch_batch=%d)", total_pending, _FETCH_BATCH)

    # ── Collect ALL new embeddings before clustering ───────────────────────────
    # DBSCAN needs the full matrix to assign globally consistent cluster labels.
    # Each "fetch batch" is encoded independently; embeddings accumulate in a list.
    all_ids: list[int]         = []
    all_vectors: list[np.ndarray] = []

    batches_done = 0
    for batch in _iter_batches():
        texts = [build_text(row["title"], row["content"])
                 for row in batch]
        ids   = [row["id"] for row in batch]

        vectors = embed_texts(texts, batch_size=_ENCODE_BATCH)  # (N, 384) float32

        all_ids.extend(ids)
        all_vectors.append(vectors)
        batches_done += 1

        logger.info(
            "Encoded batch %d  (%d articles, cumulative %d)",
            batches_done,
            len(batch),
            len(all_ids),
        )

    # Stack into one contiguous matrix
    embeddings_matrix: np.ndarray = np.vstack(all_vectors)   # (total, 384)
    logger.info(
        "Embedding matrix shape=%s  dtype=%s",
        embeddings_matrix.shape,
        embeddings_matrix.dtype,
    )

    # ── Cluster ───────────────────────────────────────────────────────────────
    labels = cluster_embeddings(embeddings_matrix)   # shape (total,) int32

    # ── Build update records ──────────────────────────────────────────────────
    records: list[dict] = []
    for art_id, vec, label in zip(all_ids, embeddings_matrix, labels):
        records.append(
            {
                "id":         art_id,
                "embedding":  vec.tolist(),          # list[float] for psycopg2
                "cluster_id": int(label) if label != -1 else None,  # noise → NULL
            }
        )

    # ── Persist in DB-sized write batches ─────────────────────────────────────
    write_batch = _FETCH_BATCH
    for start in range(0, len(records), write_batch):
        chunk = records[start : start + write_batch]
        bulk_update_embeddings_and_clusters(chunk)
        logger.info(
            "DB write %d/%d articles committed",
            min(start + write_batch, len(records)),
            len(records),
        )

    elapsed = time.perf_counter() - t0
    summary = {
        "processed":       len(all_ids),
        "batches":         batches_done,
        "elapsed_seconds": round(elapsed, 2),
    }
    logger.info(
        "Pipeline complete — processed=%d  batches=%d  elapsed=%.1fs",
        summary["processed"],
        summary["batches"],
        summary["elapsed_seconds"],
    )
    return summary
