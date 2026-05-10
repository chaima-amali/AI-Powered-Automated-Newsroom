"""End-to-end embedding and clustering pipeline for daily news articles."""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import DefaultDict, Iterable

import numpy as np
from sklearn.decomposition import PCA

from db.repository import (
    bulk_update_embeddings_and_clusters,
    count_unprocessed_articles,
    fetch_processed_article_samples,
    fetch_unprocessed_articles,
)
from pipeline.embedding.clustering import cluster_embeddings, refine_cluster_labels
from pipeline.embedding.generator import build_text, embed_texts, get_effective_model_version
from pipeline.embedding.labels import pick_primary_tag_value

logger = logging.getLogger(__name__)

_FETCH_BATCH: int = int(os.environ.get("EMBEDDING_FETCH_BATCH", 256))
_ENCODE_BATCH: int = int(os.environ.get("EMBEDDING_ENCODE_BATCH", 64))
_ALLOWED_LANGUAGES = tuple(
    lang.strip().lower()
    for lang in os.environ.get("EMBEDDING_LANGUAGES", "ar,fr").split(",")
    if lang.strip()
)
_REPORT_DIR = Path(os.environ.get("EMBEDDING_REPORT_DIR", "artifacts"))
_MIN_PAIRWISE_SIMILARITY: float = float(os.environ.get("CLUSTER_MIN_PAIRWISE_SIMILARITY", 0.82))
_TOPIC_MERGE_SIMILARITY: float = float(os.environ.get("TOPIC_MERGE_SIMILARITY", 0.88))
_MAX_CLUSTER_SIZE: int = int(os.environ.get("MAX_CLUSTER_SIZE", 20))


def _resolve_target_date(process_date: date | str | None) -> date | None:
    if process_date is None:
        # Default to daily runs for today's publication date.
        return datetime.utcnow().date()
    if isinstance(process_date, str) and process_date.strip() in {"*", "all", "ALL"}:
        return None
    if isinstance(process_date, date):
        return process_date
    return datetime.strptime(process_date, "%Y-%m-%d").date()


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


def _article_date_key(row: dict) -> str:
    raw = row.get("article_date")
    if hasattr(raw, "isoformat"):
        return raw.isoformat()
    return str(raw)


def _pick_source_key(row: dict) -> str:
    source_name = str(row.get("source_name") or "").strip().lower()
    if source_name:
        return source_name
    source_id = row.get("source_id")
    if source_id is None:
        return "unknown"
    return f"source:{source_id}"


def _parse_existing_embedding(value: object) -> list[float] | None:
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
            return [float(part.strip()) for part in inner.split(",")]
    return None


def _build_group_records(rows: list[dict], next_cluster_id: int) -> tuple[list[dict], int]:
    model_version = get_effective_model_version()
    texts_to_embed: list[str] = []
    ids_to_embed: list[int] = []
    records: list[dict] = []

    for row in rows:
        existing_embedding = _parse_existing_embedding(row.get("embedding"))
        record = {
            "id": int(row["id"]),
            "title": row.get("title") or "",
            "tag": row["group_tag"],
            "article_date": row["group_date"],
            "source_key": _pick_source_key(row),
            "embedding": existing_embedding,
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
        records.append(record)

        if existing_embedding is None:
            texts_to_embed.append(record["combined_text_source"])
            ids_to_embed.append(record["id"])

    if texts_to_embed:
        vectors = embed_texts(texts_to_embed, batch_size=_ENCODE_BATCH)
        for article_id, vector in zip(ids_to_embed, vectors):
            for record in records:
                if record["id"] == article_id:
                    record["embedding"] = vector.tolist()
                    break

    if len(records) < 2:
        labels = np.full(len(records), -1, dtype=np.int32)
    else:
        unique_sources = {record["source_key"] for record in records}
        if len(unique_sources) < 2:
            # Enforce multi-source requirement for level-2 clusters.
            labels = np.full(len(records), -1, dtype=np.int32)
        else:
            embeddings = np.array([record["embedding"] for record in records], dtype=np.float32)
            labels = cluster_embeddings(embeddings, min_samples=2)
            labels = refine_cluster_labels(
                embeddings,
                labels,
                source_keys=[record["source_key"] for record in records],
                min_pairwise_similarity=_MIN_PAIRWISE_SIMILARITY,
                min_samples=2,
            )

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


def _cluster_centroid(vectors: list[list[float]]) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float32)
    centroid = matrix.mean(axis=0)
    norm = float(np.linalg.norm(centroid))
    if norm == 0.0:
        return centroid
    return centroid / norm


def _connected_components(similarity: np.ndarray, threshold: float) -> list[list[int]]:
    n = similarity.shape[0]
    visited = np.zeros(n, dtype=bool)
    components: list[list[int]] = []

    for start in range(n):
        if visited[start]:
            continue
        queue: deque[int] = deque([start])
        visited[start] = True
        component: list[int] = []

        while queue:
            node = queue.popleft()
            component.append(node)
            neighbors = np.where(similarity[node] >= threshold)[0]
            for neighbor in neighbors:
                if not visited[neighbor]:
                    visited[neighbor] = True
                    queue.append(int(neighbor))

        components.append(component)

    return components


def _assign_global_topic_cluster_ids(records: list[dict]) -> None:
    provisional_ids = sorted(
        {
            int(record["cluster_id"])
            for record in records
            if record.get("cluster_id") is not None
        }
    )
    if not provisional_ids:
        return

    vectors_by_cluster: dict[int, list[list[float]]] = defaultdict(list)
    for record in records:
        cluster_id = record.get("cluster_id")
        if cluster_id is None:
            continue
        vectors_by_cluster[int(cluster_id)].append(record["embedding"])

    centroids = np.vstack([_cluster_centroid(vectors_by_cluster[cid]) for cid in provisional_ids]).astype(np.float32)
    centroid_similarity = centroids @ centroids.T
    components = _connected_components(centroid_similarity, _TOPIC_MERGE_SIMILARITY)

    remap: dict[int, int] = {}
    next_global_id = 0
    for component in components:
        component_cluster_ids = [provisional_ids[index] for index in component]
        for old_id in component_cluster_ids:
            remap[old_id] = next_global_id
        next_global_id += 1

    for record in records:
        if record.get("cluster_id") is None:
            continue
        record["cluster_id"] = remap[int(record["cluster_id"])]


def _cap_cluster_sizes(records: list[dict], max_cluster_size: int | None = None) -> None:
    max_size = _MAX_CLUSTER_SIZE if max_cluster_size is None else int(max_cluster_size)
    if max_size <= 0:
        return

    grouped_records: DefaultDict[int, list[dict]] = defaultdict(list)
    for record in records:
        cluster_id = record.get("cluster_id")
        if cluster_id is None:
            continue
        grouped_records[int(cluster_id)].append(record)

    if not grouped_records:
        return

    next_cluster_id = max(grouped_records.keys()) + 1
    for cluster_id in sorted(grouped_records.keys()):
        cluster_records = grouped_records[cluster_id]
        if len(cluster_records) <= max_size:
            continue

        cluster_records.sort(key=lambda item: (str(item.get("article_date") or ""), int(item["id"])))
        for chunk_index in range(0, len(cluster_records), max_size):
            chunk = cluster_records[chunk_index : chunk_index + max_size]
            if chunk_index == 0:
                continue
            for record in chunk:
                record["cluster_id"] = next_cluster_id
            next_cluster_id += 1


def _save_cluster_distribution_chart(records: list[dict], output_path: Path) -> Path | None:
    if not records:
        return None

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    counts: DefaultDict[str, DefaultDict[str, int]] = defaultdict(lambda: defaultdict(int))
    for record in records:
        date_key = str(record["article_date"])
        tag_key = str(record["tag"])
        counts[date_key][tag_key] += 1

    dates = sorted(counts.keys())
    tags = sorted({tag for per_date in counts.values() for tag in per_date.keys()})
    matrix = np.array([[counts[d].get(t, 0) for t in tags] for d in dates], dtype=float)

    fig, ax = plt.subplots(figsize=(max(7, len(tags) * 1.1), max(4, len(dates) * 0.7)))
    image = ax.imshow(matrix, cmap="YlGnBu", aspect="auto")
    ax.set_xticks(range(len(tags)))
    ax.set_xticklabels(tags, rotation=45, ha="right")
    ax.set_yticks(range(len(dates)))
    ax.set_yticklabels(dates)
    ax.set_xlabel("Tag")
    ax.set_ylabel("Article date")
    ax.set_title("Processed article counts by date and tag")
    fig.colorbar(image, ax=ax, label="Article count")

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return output_path


def _save_cluster_scatter_chart(records: list[dict], output_path: Path) -> Path | None:
    if not records:
        return None

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    embeddings = np.array([record["embedding"] for record in records], dtype=np.float32)
    labels = np.array([record["cluster_label"] for record in records], dtype=np.int32)

    if len(records) < 2:
        return None

    projection = PCA(n_components=2).fit_transform(embeddings)

    fig, ax = plt.subplots(figsize=(9, 6))
    unique_labels = sorted(set(int(label) for label in labels))
    for label in unique_labels:
        points = projection[labels == label]
        if label == -1:
            ax.scatter(points[:, 0], points[:, 1], s=36, marker="x", label="noise")
        else:
            ax.scatter(points[:, 0], points[:, 1], s=36, label=f"cluster {label}")

    ax.set_title("Embedding cluster projection (PCA)")
    ax.set_xlabel("PC 1")
    ax.set_ylabel("PC 2")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return output_path


def _print_verification(processed_records: list[dict]) -> None:
    samples = fetch_processed_article_samples(limit=8)
    print("Processed samples from Supabase articles table:")
    for sample in samples:
        emb = sample.get("embedding")
        emb_preview = emb[:3] if isinstance(emb, list) else str(emb)[:40]
        print(
            f"  id={sample['id']} cluster_id={sample['cluster_id']} tag={sample.get('cluster_tag')} "
            f"model={sample.get('embedding_model_version')} embedding[:3]={emb_preview}"
        )

    by_cluster: DefaultDict[int, list[str]] = defaultdict(list)
    for record in processed_records:
        cluster_id = record.get("cluster_id")
        if cluster_id is None:
            continue
        by_cluster[int(cluster_id)].append(record["title"])

    print("\nCluster topic preview:")
    for cluster_id in sorted(by_cluster.keys()):
        print(f"  cluster {cluster_id}")
        for title in by_cluster[cluster_id][:5]:
            print(f"    - {title}")


def run_pipeline(process_date: date | str | None = None) -> dict:
    """Run the complete embedding and clustering workflow."""
    started = time.perf_counter()
    target_date = _resolve_target_date(process_date)

    total_pending = count_unprocessed_articles(
        target_date=target_date,
        allowed_languages=_ALLOWED_LANGUAGES,
    )
    if total_pending == 0:
        logger.info("No pending Arabic/French articles for date=%s", target_date)
        return {
            "processed": 0,
            "groups": 0,
            "elapsed_seconds": 0.0,
            "target_date": str(target_date),
            "distribution_report": None,
            "scatter_report": None,
        }

    grouped: DefaultDict[tuple[str, str], list[dict]] = defaultdict(list)
    fetch_batches = 0
    for batch in _iter_batches(target_date):
        for row in batch:
            tag = pick_primary_tag_value(row.get("tags"))
            if tag is None and row.get("tags") is not None:
                continue
            row["group_tag"] = tag or "untagged"
            published_at_date = row.get("article_date")
            if published_at_date is None:
                continue
            row["group_date"] = _article_date_key({"article_date": published_at_date})
            grouped[(row["group_date"], row["group_tag"])] .append(row)
        fetch_batches += 1

    next_cluster_id = 0
    all_records: list[dict] = []

    for group_key in sorted(grouped.keys()):
        date_key, tag_key = group_key
        rows = sorted(grouped[group_key], key=lambda item: int(item["id"]))
        logger.info("Clustering group date=%s tag=%s with %d article(s)", date_key, tag_key, len(rows))
        records, next_cluster_id = _build_group_records(rows, next_cluster_id)
        all_records.extend(records)

    _assign_global_topic_cluster_ids(all_records)
    _cap_cluster_sizes(all_records)
    bulk_update_embeddings_and_clusters(all_records)

    distribution_path = _save_cluster_distribution_chart(
        all_records,
        _REPORT_DIR / "cluster_distribution_heatmap.png",
    )
    scatter_path = _save_cluster_scatter_chart(
        all_records,
        _REPORT_DIR / "cluster_scatter_pca.png",
    )
    _print_verification(all_records)

    elapsed = round(time.perf_counter() - started, 2)
    summary = {
        "processed": len(all_records),
        "groups": len(grouped),
        "fetch_batches": fetch_batches,
        "target_date": str(target_date),
        "elapsed_seconds": elapsed,
        "distribution_report": str(distribution_path) if distribution_path else None,
        "scatter_report": str(scatter_path) if scatter_path else None,
    }
    logger.info("Embedding pipeline complete: %s", summary)
    return summary


def run_embedding_pipeline(process_date: date | str | None = None) -> dict:
    """Backward-compatible alias used by the CLI entry point."""
    return run_pipeline(process_date=process_date)