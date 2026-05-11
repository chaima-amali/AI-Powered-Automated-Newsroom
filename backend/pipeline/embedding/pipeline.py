"""End-to-end embedding and clustering pipeline for daily news articles.

Key changes vs previous version
────────────────────────────────
1. Articles are grouped by DATE ONLY before clustering.
   The old code grouped by (date, tag) which prevented cross-tag story discovery.
   Now all articles from the same day are clustered together; tags only act as
   a soft similarity boost inside NewsClust.

2. DBSCAN replaced with NewsClust (centroid-based online clustering).
   See embedding/clustering.py for the full explanation.

3. `build_text()` no longer injects tags into the embedding text.
   Tags are passed separately to the clustering step as soft signals.

4. Embedding model is LaBSE by default (cross-lingual, no prefix needed).
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import DefaultDict, Iterable, List, Optional

import numpy as np
from sklearn.decomposition import PCA

from db.repository import (
    bulk_update_embeddings_and_clusters,
    count_unprocessed_articles,
    fetch_processed_article_samples,
    fetch_unprocessed_articles,
)
from embedding.clustering import cluster_articles
from embedding.generator import build_text, embed_texts, get_effective_model_version

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
_FETCH_BATCH: int = int(os.environ.get("EMBEDDING_FETCH_BATCH", "256"))
_ENCODE_BATCH: int = int(os.environ.get("EMBEDDING_ENCODE_BATCH", "64"))
_ALLOWED_LANGUAGES = tuple(
    lang.strip().lower()
    for lang in os.environ.get("EMBEDDING_LANGUAGES", "ar,fr,en").split(",")
    if lang.strip()
)
_REPORT_DIR = Path(os.environ.get("EMBEDDING_REPORT_DIR", "artifacts"))

# Clustering parameters (see NewsClust for full documentation)
_SIMILARITY_THRESHOLD: float = float(
    os.environ.get("CLUSTER_SIMILARITY_THRESHOLD", "0.72")
)
_TAG_OVERLAP_BONUS: float = float(os.environ.get("CLUSTER_TAG_OVERLAP_BONUS", "0.04"))
_MIN_CLUSTER_SIZE: int = int(os.environ.get("CLUSTER_MIN_SIZE", "2"))
_MAX_CLUSTER_SIZE: int = int(os.environ.get("MAX_CLUSTER_SIZE", "20"))


# ── Date helpers ───────────────────────────────────────────────────────────────

def _resolve_target_date(process_date: date | str | None) -> date | None:
    if process_date is None:
        return datetime.utcnow().date()
    if isinstance(process_date, str) and process_date.strip() in {"*", "all", "ALL"}:
        return None
    if isinstance(process_date, date):
        return process_date
    return datetime.strptime(process_date, "%Y-%m-%d").date()


def _article_date_key(row: dict) -> Optional[str]:
    raw = row.get("article_date")
    if raw is None:
        return None
    if hasattr(raw, "isoformat"):
        return raw.isoformat()
    return str(raw)


def _pick_source_key(row: dict) -> str:
    source_name = str(row.get("source_name") or "").strip().lower()
    if source_name:
        return source_name
    source_id = row.get("source_id")
    return f"source:{source_id}" if source_id is not None else "unknown"


# ── Fetching ───────────────────────────────────────────────────────────────────

def _iter_batches(process_date: date | None) -> Iterable[list[dict]]:
    after_id = 0
    while True:
        batch = fetch_unprocessed_articles(
            batch_size=_FETCH_BATCH,
            after_id=after_id,
            target_date=process_date,
            allowed_languages=_ALLOWED_LANGUAGES,
        )
        if not batch:
            break
        yield batch
        after_id = int(batch[-1]["id"])


# ── Embedding ──────────────────────────────────────────────────────────────────

def _parse_existing_embedding(value: object) -> Optional[List[float]]:
    if value is None:
        return None
    if isinstance(value, np.ndarray):
        return value.astype(np.float32).tolist()
    if isinstance(value, list):
        return [float(v) for v in value]
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and text.endswith("]"):
            inner = text[1:-1].strip()
            if not inner:
                return []
            return [float(p.strip()) for p in inner.split(",")]
    return None


def _ensure_embeddings(records: list[dict]) -> None:
    """Compute embeddings for records that don't already have one."""
    model_version = get_effective_model_version()
    to_embed_idx = [i for i, r in enumerate(records) if r["embedding"] is None]

    if to_embed_idx:
        texts = [records[i]["combined_text_source"] for i in to_embed_idx]
        vectors = embed_texts(texts, batch_size=_ENCODE_BATCH)
        for list_pos, record_idx in enumerate(to_embed_idx):
            records[record_idx]["embedding"] = vectors[list_pos].tolist()
            records[record_idx]["embedding_model_version"] = model_version


# ── Clustering ─────────────────────────────────────────────────────────────────

def _cluster_date_group(rows: list[dict], next_cluster_id: int) -> tuple[list[dict], int]:
    """
    Embed and cluster all articles from a single calendar date.

    All articles share the same date_key, so the date hard-constraint is
    satisfied trivially.  Tags are passed to NewsClust as soft signals.

    Returns
    -------
    records : list[dict]
        Each record has all original fields plus:
        - embedding, embedding_model_version
        - cluster_id (int | None)
        - cluster_label (int, -1 = unassigned)
    next_cluster_id : int
        Updated global cluster counter.
    """
    model_version = get_effective_model_version()
    records: list[dict] = []

    for row in rows:
        existing_emb = _parse_existing_embedding(row.get("embedding"))
        records.append(
            {
                "id": int(row["id"]),
                "title": row.get("title") or "",
                "tags": row.get("tags") or [],
                "article_date": row.get("article_date"),
                "source_key": _pick_source_key(row),
                "embedding": existing_emb,
                "cluster_id": None,
                "cluster_label": -1,
                "embedding_model_version": model_version,
                "combined_text_source": build_text(
                    row.get("title") or "",
                    row.get("content"),
                    row.get("summary"),
                    row.get("tags"),
                ),
            }
        )

    _ensure_embeddings(records)

    if len(records) < 2:
        return records, next_cluster_id

    # Need at least 2 distinct sources to form meaningful clusters
    unique_sources = {r["source_key"] for r in records}
    if len(unique_sources) < 2:
        logger.info(
            "Date group has only 1 source (%s) — skipping clustering",
            next(iter(unique_sources), "unknown"),
        )
        return records, next_cluster_id

    article_ids = [r["id"] for r in records]
    embeddings = np.array([r["embedding"] for r in records], dtype=np.float32)
    date_keys = [str(_article_date_key(r) or "unknown") for r in records]
    tags_list = [list(r["tags"]) if r["tags"] else None for r in records]

    labels = cluster_articles(
        article_ids=article_ids,
        embeddings=embeddings,
        date_keys=date_keys,
        tags_list=tags_list,
        threshold=_SIMILARITY_THRESHOLD,
        tag_overlap_bonus=_TAG_OVERLAP_BONUS,
        min_cluster_size=_MIN_CLUSTER_SIZE,
    )

    # Map local labels → globally unique cluster IDs
    local_to_global: dict[int, int] = {}
    for record, label in zip(records, labels):
        local_label = int(label)
        record["cluster_label"] = local_label
        if local_label == -1:
            record["cluster_id"] = None
            continue
        if local_label not in local_to_global:
            local_to_global[local_label] = next_cluster_id
            next_cluster_id += 1
        record["cluster_id"] = local_to_global[local_label]

    return records, next_cluster_id


# ── Cluster size capping ───────────────────────────────────────────────────────

def _cap_cluster_sizes(records: list[dict], max_cluster_size: int = _MAX_CLUSTER_SIZE) -> None:
    """Split oversized clusters into chunks (preserves chronological order)."""
    if max_cluster_size <= 0:
        return

    grouped: DefaultDict[int, list[dict]] = defaultdict(list)
    for r in records:
        if r.get("cluster_id") is not None:
            grouped[int(r["cluster_id"])].append(r)

    if not grouped:
        return

    next_id = max(grouped.keys()) + 1
    for cluster_id in sorted(grouped.keys()):
        cluster_records = grouped[cluster_id]
        if len(cluster_records) <= max_cluster_size:
            continue
        cluster_records.sort(
            key=lambda item: (str(item.get("article_date") or ""), int(item["id"]))
        )
        for chunk_idx in range(0, len(cluster_records), max_cluster_size):
            if chunk_idx == 0:
                continue
            for r in cluster_records[chunk_idx : chunk_idx + max_cluster_size]:
                r["cluster_id"] = next_id
            next_id += 1


# ── Reporting ──────────────────────────────────────────────────────────────────

def _save_cluster_scatter_chart(records: list[dict], output_path: Path) -> Optional[Path]:
    if not records or len(records) < 2:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        embeddings = np.array([r["embedding"] for r in records], dtype=np.float32)
        labels = np.array([r["cluster_label"] for r in records], dtype=np.int32)
        projection = PCA(n_components=2).fit_transform(embeddings)

        fig, ax = plt.subplots(figsize=(9, 6))
        for label in sorted(set(int(l) for l in labels)):
            pts = projection[labels == label]
            if label == -1:
                ax.scatter(pts[:, 0], pts[:, 1], s=30, marker="x", color="grey", label="noise")
            else:
                ax.scatter(pts[:, 0], pts[:, 1], s=30, label=f"cluster {label}")
        ax.set_title("Embedding cluster projection (PCA)")
        ax.set_xlabel("PC 1")
        ax.set_ylabel("PC 2")
        ax.legend(loc="best", fontsize=7)
        fig.tight_layout()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150)
        plt.close(fig)
        return output_path
    except Exception:
        logger.exception("Failed to save scatter chart")
        return None


def _print_cluster_preview(all_records: list[dict]) -> None:
    """Print a debug preview of cluster assignments with titles."""
    by_cluster: DefaultDict[int, list[str]] = defaultdict(list)
    for r in all_records:
        cid = r.get("cluster_id")
        if cid is not None:
            by_cluster[int(cid)].append(r["title"])

    if not by_cluster:
        print("No clusters formed.")
        return

    print(f"\nFormed {len(by_cluster)} cluster(s):")
    for cid in sorted(by_cluster.keys()):
        titles = by_cluster[cid]
        print(f"  Cluster {cid}  ({len(titles)} articles)")
        for t in titles[:5]:
            print(f"    · {t}")
        if len(titles) > 5:
            print(f"    … and {len(titles) - 5} more")


# ── Main pipeline entry-point ──────────────────────────────────────────────────

def run_pipeline(process_date: date | str | None = None) -> dict:
    """Run the complete embedding and clustering workflow for one day."""
    started = time.perf_counter()
    target_date = _resolve_target_date(process_date)

    total_pending = count_unprocessed_articles(
        target_date=target_date,
        allowed_languages=_ALLOWED_LANGUAGES,
    )
    if total_pending == 0:
        logger.info("No pending articles for date=%s", target_date)
        return {
            "processed": 0,
            "date_groups": 0,
            "elapsed_seconds": 0.0,
            "target_date": str(target_date),
            "scatter_report": None,
        }

    # ── Step 1: Collect and group by DATE only ─────────────────────────────────
    # We deliberately do NOT pre-group by tag here.  Tags are only a soft hint
    # inside NewsClust.  Pre-grouping by tag was the primary cause of the
    # inconsistent clusters in the previous version.
    grouped_by_date: DefaultDict[str, list[dict]] = defaultdict(list)
    fetch_batches = 0

    for batch in _iter_batches(target_date):
        for row in batch:
            date_key = _article_date_key(row)
            if date_key is None:
                logger.debug("Skipping article id=%s with no article_date", row.get("id"))
                continue
            grouped_by_date[date_key].append(row)
        fetch_batches += 1

    logger.info(
        "Fetched %d articles across %d date(s) in %d batch(es)",
        total_pending,
        len(grouped_by_date),
        fetch_batches,
    )

    # ── Step 2: Embed + cluster per date bucket ────────────────────────────────
    next_cluster_id = 0
    all_records: list[dict] = []

    for date_key in sorted(grouped_by_date.keys()):
        rows = sorted(grouped_by_date[date_key], key=lambda r: int(r["id"]))
        logger.info(
            "Processing date=%s  articles=%d", date_key, len(rows)
        )
        records, next_cluster_id = _cluster_date_group(rows, next_cluster_id)
        all_records.extend(records)

    # ── Step 3: Cap oversized clusters ────────────────────────────────────────
    _cap_cluster_sizes(all_records)

    # ── Step 4: Persist to DB ──────────────────────────────────────────────────
    bulk_update_embeddings_and_clusters(all_records)

    # ── Step 5: Reporting ──────────────────────────────────────────────────────
    scatter_path = _save_cluster_scatter_chart(
        all_records, _REPORT_DIR / "cluster_scatter_pca.png"
    )
    _print_cluster_preview(all_records)

    elapsed = round(time.perf_counter() - started, 2)
    summary = {
        "processed": len(all_records),
        "date_groups": len(grouped_by_date),
        "clusters_formed": next_cluster_id,
        "fetch_batches": fetch_batches,
        "target_date": str(target_date),
        "elapsed_seconds": elapsed,
        "scatter_report": str(scatter_path) if scatter_path else None,
    }
    logger.info("Embedding pipeline complete: %s", summary)
    return summary


def run_embedding_pipeline(process_date: date | str | None = None) -> dict:
    """Backward-compatible alias for CLI entry-point."""
    return run_pipeline(process_date=process_date)
