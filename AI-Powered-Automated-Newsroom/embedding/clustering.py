"""
embedding/clustering.py
------------------------
Cluster article embeddings with DBSCAN (cosine metric).

Why DBSCAN?
  - No need to specify K in advance (unlike K-Means).
  - Naturally marks outliers as cluster -1 (noise).
  - Works well with cosine-distance on L2-normalised vectors.

Since vectors from generator.py are already L2-normalised,
cosine distance = 1 - dot_product, which maps neatly onto
DBSCAN's eps threshold.

Tune via environment variables:
    DBSCAN_EPS          (float, default 0.20)   — max cosine distance for a point to
                                                                                                be considered a neighbour
    DBSCAN_MIN_SAMPLES  (int,   default 2)       — min cluster size
"""

from __future__ import annotations

import logging
import os
from collections import deque

import numpy as np
from sklearn.cluster import DBSCAN

logger = logging.getLogger(__name__)

# ── Tuneable parameters ────────────────────────────────────────────────────────
_EPS: float = float(os.environ.get("DBSCAN_EPS", 0.70))
_MIN_SAMPLES: int = int(os.environ.get("DBSCAN_MIN_SAMPLES", 2))
_MIN_PAIRWISE_SIMILARITY: float = float(os.environ.get("CLUSTER_MIN_PAIRWISE_SIMILARITY", 0.82))


def cluster_embeddings(
    embeddings: np.ndarray,
    eps: float | None = None,
    min_samples: int | None = None,
    metric: str = "cosine",
) -> np.ndarray:
    """
    Run DBSCAN on a 2-D array of L2-normalised vectors.

    DBSCAN expects a distance metric. We pass metric='cosine' so distances
    are in [0, 2]; eps=0.25 means articles within 12.5° cosine angle are
    neighbours.

    Noise points receive label -1. Callers may choose to leave cluster_id
    as NULL or map -1 → NULL in the DB.

    Args:
        embeddings : np.ndarray shape (N, D), float32, L2-normalised
        eps: The maximum distance between two samples for one to be considered as in the neighborhood of the other.
        min_samples: The number of samples in a neighborhood for a point to be considered as a core point.
        metric: The metric to use when calculating distance between instances in a feature array.

    Returns:
        np.ndarray shape (N,), integer labels from -1 (noise) to K-1
    """
    if embeddings.ndim != 2 or embeddings.shape[1] == 0:
        logger.warning("Cannot cluster empty or invalid embeddings array.")
        return np.array([-1] * embeddings.shape[0], dtype=np.int32)

    if embeddings.shape[0] == 0:
        return np.array([], dtype=np.int32)

    effective_eps = eps if eps is not None else _EPS
    effective_min_samples = min_samples if min_samples is not None else _MIN_SAMPLES

    if embeddings.shape[0] < effective_min_samples:
        logger.info(
            "Only %d row(s), below min_samples=%d; assigning noise labels.",
            embeddings.shape[0],
            effective_min_samples,
        )
        return np.full(embeddings.shape[0], -1, dtype=np.int32)

    logger.info(
        "Running DBSCAN with eps=%s, min_samples=%s, metric=%s",
        effective_eps,
        effective_min_samples,
        metric,
    )
    db = DBSCAN(
        eps=effective_eps,
        min_samples=effective_min_samples,
        metric=metric,
        n_jobs=-1,
    )
    db.fit(embeddings)
    return db.labels_.astype(np.int32)


def _pairwise_cosine_similarity(embeddings: np.ndarray) -> np.ndarray:
    if embeddings.shape[0] == 0:
        return np.empty((0, 0), dtype=np.float32)
    normalized = embeddings.astype(np.float32, copy=False)
    norms = np.linalg.norm(normalized, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    normalized = normalized / norms
    return normalized @ normalized.T


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


def refine_cluster_labels(
    embeddings: np.ndarray,
    labels: np.ndarray,
    source_keys: list[str] | None = None,
    min_pairwise_similarity: float | None = None,
    min_samples: int | None = None,
) -> np.ndarray:
    """Split weak DBSCAN clusters into tighter coherence-based components.

    The initial DBSCAN pass can still merge stories inside broad tag buckets.
    This refinement step keeps only components whose internal cosine similarity
    stays above a stricter threshold, and demotes weak fragments to noise.
    """
    embeddings = np.asarray(embeddings, dtype=np.float32)
    labels = np.asarray(labels, dtype=np.int32)
    if embeddings.ndim != 2 or len(labels) == 0:
        return labels.astype(np.int32)

    if embeddings.shape[0] != labels.shape[0]:
        raise ValueError("embeddings and labels must have the same number of rows")

    effective_min_samples = int(min_samples if min_samples is not None else _MIN_SAMPLES)
    effective_threshold = float(min_pairwise_similarity if min_pairwise_similarity is not None else _MIN_PAIRWISE_SIMILARITY)

    refined = np.full(labels.shape[0], -1, dtype=np.int32)
    next_label = 0

    for cluster_label in sorted(set(int(item) for item in labels if int(item) != -1)):
        indices = np.where(labels == cluster_label)[0]
        cluster_embeddings = embeddings[indices]
        if len(indices) < effective_min_samples:
            continue

        similarity = _pairwise_cosine_similarity(cluster_embeddings)
        if len(indices) <= 2:
            mean_similarity = float(similarity[np.triu_indices(len(indices), k=1)].mean()) if len(indices) > 1 else 0.0
            if len(indices) >= effective_min_samples and mean_similarity >= effective_threshold:
                refined[indices] = next_label
                next_label += 1
            continue

        components = _connected_components(similarity, effective_threshold)
        kept_any = False
        for component in components:
            if len(component) < effective_min_samples:
                continue
            component_indices = indices[np.array(component, dtype=np.int32)]
            component_embeddings = embeddings[component_indices]
            component_similarity = _pairwise_cosine_similarity(component_embeddings)
            if component_similarity.shape[0] > 1:
                upper = component_similarity[np.triu_indices(component_similarity.shape[0], k=1)]
                if upper.size and float(upper.mean()) < effective_threshold:
                    continue
            unique_sources = {source_keys[index] for index in component_indices} if source_keys else None
            if unique_sources is not None and len(unique_sources) < 2:
                continue
            refined[component_indices] = next_label
            next_label += 1
            kept_any = True

        if not kept_any:
            logger.info(
                "Cluster %d failed coherence check (n=%d, threshold=%.2f) and was dropped as noise.",
                cluster_label,
                len(indices),
                effective_threshold,
            )

    return refined
