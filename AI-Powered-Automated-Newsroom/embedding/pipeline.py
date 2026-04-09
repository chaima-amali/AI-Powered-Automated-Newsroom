"""
embedding/pipeline.py
----------------------
Orchestrates the full embedding + clustering pipeline.

The pipeline now works in date groups so articles published on the same day
are clustered together. This keeps clusters date-local, which matches the
newsroom use case and makes the result easier to reason about.
"""

from __future__ import annotations

import ast
import logging
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Generator

import numpy as np

from db.repository import (
    bulk_update_embeddings_and_clusters,
    count_unprocessed_articles,
    fetch_processed_article_samples,
    fetch_unprocessed_articles,
)
from db.connection import get_cursor
from embedding.clustering import cluster_embeddings
from embedding.generator import build_text, embed_texts

logger = logging.getLogger(__name__)

# ── Tuneable knobs (override via environment variables) ────────────────────────
_FETCH_BATCH: int = int(os.environ.get("EMBEDDING_FETCH_BATCH", 256))
_ENCODE_BATCH: int = int(os.environ.get("EMBEDDING_ENCODE_BATCH", 64))
_WRITE_BATCH: int = 128
_REPORT_PATH = Path(os.environ.get("EMBEDDING_CLUSTER_REPORT", "artifacts/cluster_report.png"))


def _iter_batches() -> Generator[list[dict], None, None]:
    """Yield successive batches of unprocessed articles using id keyset pagination."""
    after_id = 0
    while True:
        batch = fetch_unprocessed_articles(batch_size=_FETCH_BATCH, after_id=after_id)
        if not batch:
            break
        yield batch
        after_id = batch[-1]["id"]


def _article_date_key(row: dict) -> str:
    article_date = row.get("article_date")
    if article_date is None:
        return "unknown-date"
    if hasattr(article_date, "isoformat"):
        return article_date.isoformat()
    return str(article_date)


def _preview_embedding(embedding: object) -> list[float]:
    if isinstance(embedding, str):
        try:
            parsed = ast.literal_eval(embedding)
        except Exception:
            return []
        if isinstance(parsed, list):
            return [float(value) for value in parsed[:3]]
        return []
    if isinstance(embedding, np.ndarray):
        return [float(value) for value in embedding[:3].tolist()]
    if isinstance(embedding, (list, tuple)):
        return [float(value) for value in list(embedding)[:3]]
    return []


def _write_records(records: list[dict]) -> None:
    for start in range(0, len(records), _WRITE_BATCH):
        chunk = records[start : start + _WRITE_BATCH]
        bulk_update_embeddings_and_clusters(chunk)
        logger.info(
            "DB write %d/%d articles committed",
            min(start + _WRITE_BATCH, len(records)),
            len(records),
        )


def _upsert_cluster_summaries(records: list[dict]) -> None:
    cluster_counts: dict[int, int] = defaultdict(int)
    cluster_dates: dict[int, str] = {}

    for record in records:
        cluster_id = record["cluster_id"]
        if cluster_id is None:
            continue
        cluster_id = int(cluster_id)
        cluster_counts[cluster_id] += 1
        cluster_dates[cluster_id] = record["article_date"]

    if not cluster_counts:
        return

    with get_cursor() as cur:
        for cluster_id, count in cluster_counts.items():
            cur.execute(
                """
                INSERT INTO clusters (cluster_id, article_date, article_count)
                VALUES (%s, %s, %s)
                ON CONFLICT (cluster_id) DO UPDATE
                SET article_date = EXCLUDED.article_date,
                    article_count = EXCLUDED.article_count,
                    created_at = NOW()
                """,
                (cluster_id, cluster_dates[cluster_id], count),
            )


def _build_cluster_report(processed_by_date: dict[str, list[dict]]) -> Path | None:
    if not processed_by_date:
        return None

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    date_keys = sorted(processed_by_date.keys())
    cluster_ids = sorted(
        {
            int(record["cluster_id"])
            for records in processed_by_date.values()
            for record in records
            if record["cluster_id"] is not None
        }
    )

    if not cluster_ids:
        cluster_ids = []

    matrix: list[list[int]] = []
    labels: list[str] = []

    for date_key in date_keys:
        counts: dict[int, int] = defaultdict(int)
        for record in processed_by_date[date_key]:
            counts[int(record["cluster_label"])] += 1

        row = [counts.get(cluster_id, 0) for cluster_id in cluster_ids]
        if counts.get(-1):
            row.append(counts[-1])
        matrix.append(row)
        labels.append(date_key)

    if not matrix:
        return None

    column_labels = [f"C{cluster_id}" for cluster_id in cluster_ids]
    if any(-1 == int(record["cluster_label"]) for records in processed_by_date.values() for record in records):
        column_labels.append("Outlier")

    data = np.array(matrix, dtype=float)

    fig_width = max(8, len(column_labels) * 1.1)
    fig_height = max(4, len(labels) * 0.7)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    image = ax.imshow(data, cmap="Blues", aspect="auto")
    ax.set_xticks(range(len(column_labels)))
    ax.set_xticklabels(column_labels, rotation=45, ha="right")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.set_xlabel("Cluster ID")
    ax.set_ylabel("Article date")
    ax.set_title("Cluster distribution by article date")
    fig.colorbar(image, ax=ax, label="Article count")

    for row_index in range(data.shape[0]):
        for col_index in range(data.shape[1]):
            value = int(data[row_index, col_index])
            if value:
                ax.text(col_index, row_index, str(value), ha="center", va="center", color="black", fontsize=8)

    fig.tight_layout()
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(_REPORT_PATH, dpi=180)
    plt.close(fig)
    logger.info("Cluster report saved to %s", _REPORT_PATH)
    return _REPORT_PATH


def _print_verification(processed_records: list[dict]) -> None:
    samples = fetch_processed_article_samples(limit=5)
    print("Processed article samples:")
    for sample in samples:
        preview = _preview_embedding(sample.get("embedding"))
        print(
            f"  id={sample['id']} cluster_id={sample['cluster_id']} embedding[:3]={preview}"
        )

    cluster_titles: dict[int, list[str]] = defaultdict(list)
    for record in processed_records:
        cluster_id = record["cluster_id"]
        if cluster_id == -1:
            continue
        if cluster_id is None:
            continue
        cluster_id = int(cluster_id)
        cluster_titles[cluster_id].append(record["title"])

    print("Cluster titles:")
    for cluster_id in sorted(cluster_titles):
        print(f"  cluster {cluster_id}:")
        for title in cluster_titles[cluster_id]:
            print(f"    - {title}")


def run_pipeline() -> dict:
    """Execute the full embedding + clustering pipeline."""
    t0 = time.perf_counter()

    total_pending = count_unprocessed_articles()
    if total_pending == 0:
        logger.info("No unprocessed articles found — pipeline complete")
        return {
            "processed": 0,
            "batches": 0,
            "date_groups": 0,
            "elapsed_seconds": 0.0,
            "report_path": None,
        }

    logger.info("Articles to process: %d  (fetch_batch=%d)", total_pending, _FETCH_BATCH)

    articles_by_date: DefaultDict[str, list[dict]] = defaultdict(list)
    fetch_batches = 0

    for batch in _iter_batches():
        for row in batch:
            articles_by_date[_article_date_key(row)].append(row)
        fetch_batches += 1
        logger.info(
            "Fetched batch %d  (%d rows, %d total date groups)",
            fetch_batches,
            len(batch),
            len(articles_by_date),
        )

    processed_by_date: dict[str, list[dict]] = {}
    all_processed_records: list[dict] = []
    next_cluster_id = 0

    for date_key in sorted(articles_by_date.keys()):
        date_rows = sorted(articles_by_date[date_key], key=lambda row: row["id"])
        logger.info("Processing %s with %d article(s)", date_key, len(date_rows))

        texts = [build_text(row["title"], row.get("content"), row.get("summary")) for row in date_rows]
        vectors = embed_texts(texts, batch_size=_ENCODE_BATCH)
        labels = cluster_embeddings(vectors)

        local_to_global: dict[int, int] = {}
        records: list[dict] = []
        for row, vector, local_label in zip(date_rows, vectors, labels):
            local_label = int(local_label)
            if local_label == -1:
                global_cluster_id = None
            else:
                if local_label not in local_to_global:
                    local_to_global[local_label] = next_cluster_id
                    next_cluster_id += 1
                global_cluster_id = local_to_global[local_label]

            records.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "embedding": vector.tolist(),
                    "cluster_id": global_cluster_id,
                    "cluster_label": local_label,
                    "article_date": date_key,
                }
            )

        _write_records(records)
        _upsert_cluster_summaries(records)
        processed_by_date[date_key] = records
        all_processed_records.extend(records)

    report_path = _build_cluster_report(processed_by_date)
    _print_verification(all_processed_records)

    elapsed = time.perf_counter() - t0
    summary = {
        "processed": len(all_processed_records),
        "batches": fetch_batches,
        "date_groups": len(processed_by_date),
        "elapsed_seconds": round(elapsed, 2),
        "report_path": str(report_path) if report_path else None,
    }
    logger.info(
        "Pipeline complete — processed=%d  batches=%d  date_groups=%d  elapsed=%.1fs",
        summary["processed"],
        summary["batches"],
        summary["date_groups"],
        summary["elapsed_seconds"],
    )
    if report_path:
        logger.info("Cluster report written to %s", report_path)
    return summary
