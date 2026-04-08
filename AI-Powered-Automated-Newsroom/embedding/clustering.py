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
  DBSCAN_EPS          (float, default 0.25)   — max cosine distance for a point to
                                                be considered a neighbour
  DBSCAN_MIN_SAMPLES  (int,   default 3)       — min cluster size
"""

from __future__ import annotations

import logging
import os

import numpy as np
from sklearn.cluster import DBSCAN

logger = logging.getLogger(__name__)

# ── Tuneable parameters ────────────────────────────────────────────────────────
_EPS: float = float(os.environ.get("DBSCAN_EPS", 0.25))
_MIN_SAMPLES: int = int(os.environ.get("DBSCAN_MIN_SAMPLES", 3))


def cluster_embeddings(embeddings: np.ndarray) -> np.ndarray:
    """
    Run DBSCAN on a 2-D array of L2-normalised vectors.

    DBSCAN expects a distance metric. We pass metric='cosine' so distances
    are in [0, 2]; eps=0.25 means articles within 12.5° cosine angle are
    neighbours.

    Noise points receive label -1. Callers may choose to leave cluster_id
    as NULL or map -1 → NULL in the DB.

    Args:
        embeddings : np.ndarray shape (N, 384), float32, L2-normalised

    Returns:
        np.ndarray shape (N,) of int cluster labels
    """
    n = len(embeddings)

    if n == 0:
        logger.warning("cluster_embeddings called with empty array — nothing to do")
        return np.array([], dtype=np.int32)

    if n < _MIN_SAMPLES:
        # Not enough points for DBSCAN to form any cluster; mark all as noise
        logger.warning(
            "Only %d articles — fewer than min_samples=%d. All assigned to noise (-1).",
            n,
            _MIN_SAMPLES,
        )
        return np.full(n, -1, dtype=np.int32)

    logger.info(
        "DBSCAN  n_samples=%d  eps=%.3f  min_samples=%d",
        n,
        _EPS,
        _MIN_SAMPLES,
    )

    db = DBSCAN(
        eps=_EPS,
        min_samples=_MIN_SAMPLES,
        metric="cosine",
        algorithm="brute",   # exact; use 'ball_tree' for very large sets
        n_jobs=-1,           # use all CPU cores
    )
    labels: np.ndarray = db.fit_predict(embeddings)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = int((labels == -1).sum())
    logger.info(
        "Clustering complete — %d clusters  %d noise points",
        n_clusters,
        n_noise,
    )
    return labels.astype(np.int32)
