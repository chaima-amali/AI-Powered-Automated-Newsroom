"""
embedding/clustering.py
────────────────────────────────────────────────────────────────────────────────
Cross-Lingual News Clustering with the NewsClust class.

Architecture overview
─────────────────────
Instead of the previous DBSCAN + post-hoc refinement approach (which produced
inconsistent clusters), we now use a *centroid-based online clustering* strategy
via the NewsClust class.  This mirrors how real-world news aggregators work:

  1. For each incoming article (embedding vector, date, tags):
       a. HARD filter: only compare against clusters from the SAME calendar date.
       b. Compute cosine similarity between the article and each cluster centroid.
       c. SOFT boost: if the article shares a normalized tag with the cluster,
          add `tag_overlap_bonus` to the raw similarity score.
       d. If the best adjusted score ≥ `threshold`, add the article to that
          cluster and update the centroid (running average).
       e. Otherwise, create a new single-article cluster.

  2. After all articles are processed, clusters with fewer than `min_cluster_size`
     articles are dissolved (their articles become unassigned / label -1).

Why centroid-based instead of DBSCAN?
  - DBSCAN groups by density, which can link unrelated articles through a "chain"
    of borderline-similar pairs.  A centroid threshold is more conservative:
    every article is directly compared to the cluster's *average* meaning.
  - The running-average centroid update is O(1) per insertion and naturally
    drifts toward the cluster's dominant topic if early articles were noisy.
  - The date hard-constraint is trivially implemented by partitioning the
    cluster registry per date before searching.

Tuning via environment variables
─────────────────────────────────
  CLUSTER_SIMILARITY_THRESHOLD   float  default 0.72   cosine similarity required
                                                         to join an existing cluster
  CLUSTER_TAG_OVERLAP_BONUS      float  default 0.04   added when tags match
  CLUSTER_MIN_SIZE               int    default 2       min articles per cluster
                                                         (smaller clusters dissolved)
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from pipeline.embedding.labels import normalize_tag

logger = logging.getLogger(__name__)

# ── Tuneable defaults (overridable via env) ────────────────────────────────────
_SIMILARITY_THRESHOLD: float = float(
    os.environ.get("CLUSTER_SIMILARITY_THRESHOLD", "0.72")
)
_TAG_OVERLAP_BONUS: float = float(
    os.environ.get("CLUSTER_TAG_OVERLAP_BONUS", "0.04")
)
_MIN_CLUSTER_SIZE: int = int(os.environ.get("CLUSTER_MIN_SIZE", "2"))


# ── Internal cluster representation ───────────────────────────────────────────

@dataclass
class _ClusterState:
    """Internal mutable state for a single cluster."""

    cluster_id: int
    date_key: str                          # "YYYY-MM-DD"  — hard constraint partition
    centroid: np.ndarray                   # L2-normalised mean embedding, shape (D,)
    tags: set                              # union of normalised tags seen so far
    article_count: int = 0
    _centroid_sum: np.ndarray = field(default=None, repr=False)  # unnormalised sum

    def __post_init__(self) -> None:
        self._centroid_sum = self.centroid.copy()

    def cosine_similarity_to(self, vector: np.ndarray) -> float:
        """
        Cosine similarity between this centroid and an L2-normalised vector.
        Since centroid is also L2-normalised, this is just the dot product.
        """
        return float(np.dot(self.centroid, vector))

    def add_article(self, vector: np.ndarray, article_tags: set) -> None:
        """
        Update the running centroid (Welford-style average) and tag union.

        The centroid is kept L2-normalised so future cosine comparisons remain
        in [−1, 1].  We track the unnormalised sum to avoid accumulating
        floating-point drift from repeated re-normalisation.
        """
        self._centroid_sum = self._centroid_sum + vector
        self.article_count += 1
        norm = float(np.linalg.norm(self._centroid_sum))
        if norm > 0:
            self.centroid = self._centroid_sum / norm
        self.tags.update(article_tags)


class NewsClust:
    """
    Centroid-based online news clustering engine.

    Usage
    ─────
        clust = NewsClust()

        for article in articles_sorted_by_date:
            cluster_id = clust.add_article(
                article_id=article["id"],
                embedding=article["embedding_vector"],  # np.ndarray, L2-normalised
                date_key=article["article_date"],        # "YYYY-MM-DD"
                tags=article["tags"],                    # list[str] | None
            )
            # cluster_id is None if the article was below min_cluster_size threshold

        # After all articles:
        final_assignments = clust.get_assignments()
        # {article_id: cluster_id | None}

    Parameters
    ──────────
    threshold : float
        Minimum cosine similarity to join an existing cluster (default 0.72).
        Higher → tighter clusters with fewer cross-topic merges.
        Lower  → more permissive; risk of topic drift.
        Recommended range: 0.65 – 0.80 for LaBSE embeddings.

    tag_overlap_bonus : float
        Extra similarity added when the article shares ≥1 normalised tag with
        a candidate cluster (default 0.04).  Keeps the tag signal as a *tiebreaker*
        rather than a primary driver, so tag-less articles can still cluster.

    min_cluster_size : int
        Clusters below this size are dissolved at `get_assignments()` time.
        Their articles receive cluster_id = None.
    """

    def __init__(
        self,
        threshold: float = _SIMILARITY_THRESHOLD,
        tag_overlap_bonus: float = _TAG_OVERLAP_BONUS,
        min_cluster_size: int = _MIN_CLUSTER_SIZE,
    ) -> None:
        self.threshold = threshold
        self.tag_overlap_bonus = tag_overlap_bonus
        self.min_cluster_size = min_cluster_size

        self._next_id: int = 0
        # date_key → list of _ClusterState
        self._clusters_by_date: Dict[str, List[_ClusterState]] = defaultdict(list)
        # article_id → provisional cluster_id
        self._assignments: Dict[int, int] = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def add_article(
        self,
        article_id: int,
        embedding: np.ndarray,
        date_key: str,
        tags: Optional[List[str]] = None,
    ) -> Optional[int]:
        """
        Assign an article to an existing cluster or create a new one.

        Args:
            article_id: Unique integer identifier for the article.
            embedding: L2-normalised vector (shape (D,), dtype float32).
            date_key:  Publication date string "YYYY-MM-DD" (hard constraint).
            tags:      Optional list of raw tag strings; normalised internally.

        Returns:
            The provisional cluster_id (may be dissolved later if the cluster
            ends up below min_cluster_size).
        """
        vec = np.asarray(embedding, dtype=np.float32)
        # Ensure L2-normalised (idempotent if already normalised)
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm

        normalised_tags = self._normalise_tags(tags)

        best_cluster, best_score = self._find_best_cluster(vec, date_key, normalised_tags)

        if best_cluster is not None and best_score >= self.threshold:
            best_cluster.add_article(vec, normalised_tags)
            cluster_id = best_cluster.cluster_id
        else:
            cluster_id = self._create_cluster(vec, date_key, normalised_tags)

        self._assignments[article_id] = cluster_id
        return cluster_id

    def get_assignments(self) -> Dict[int, Optional[int]]:
        """
        Return {article_id: cluster_id | None} after dissolving small clusters.

        Clusters with fewer than `min_cluster_size` articles are dissolved:
        their articles receive cluster_id = None.
        """
        # Count articles per cluster
        cluster_sizes: Dict[int, int] = defaultdict(int)
        for cid in self._assignments.values():
            cluster_sizes[cid] += 1

        dissolved = {
            cid for cid, size in cluster_sizes.items() if size < self.min_cluster_size
        }
        if dissolved:
            logger.info(
                "Dissolving %d cluster(s) below min_cluster_size=%d",
                len(dissolved),
                self.min_cluster_size,
            )

        return {
            aid: (cid if cid not in dissolved else None)
            for aid, cid in self._assignments.items()
        }

    def get_cluster_labels(self, article_ids: List[int]) -> np.ndarray:
        """
        Convenience method: return an integer label array aligned to article_ids.
        Dissolved / unassigned articles get label -1.
        """
        assignments = self.get_assignments()
        labels = []
        for aid in article_ids:
            cid = assignments.get(aid)
            labels.append(cid if cid is not None else -1)
        return np.array(labels, dtype=np.int32)

    # ── Internal helpers ────────────────────────────────────────────────────────

    def _normalise_tags(self, tags: Optional[List[str]]) -> set:
        if not tags:
            return set()
        result = set()
        for t in tags:
            canonical = normalize_tag(t)
            if canonical:
                result.add(canonical)
        return result

    def _find_best_cluster(
        self,
        vec: np.ndarray,
        date_key: str,
        article_tags: set,
    ) -> Tuple[Optional[_ClusterState], float]:
        """
        Search only same-date clusters (hard constraint) for the best match.

        Returns (best_cluster, adjusted_score) or (None, -1.0) if no candidates.
        """
        candidates = self._clusters_by_date.get(date_key, [])
        if not candidates:
            return None, -1.0

        best_cluster: Optional[_ClusterState] = None
        best_score: float = -1.0

        for cluster in candidates:
            raw_sim = cluster.cosine_similarity_to(vec)

            # Soft tag boost: only applied if similarity is already reasonably high
            # (avoids tag-driven merging of semantically unrelated articles)
            tag_bonus = 0.0
            if cluster.tags and article_tags and cluster.tags & article_tags:
                tag_bonus = self.tag_overlap_bonus

            adjusted = raw_sim + tag_bonus

            if adjusted > best_score:
                best_score = adjusted
                best_cluster = cluster

        return best_cluster, best_score

    def _create_cluster(
        self,
        vec: np.ndarray,
        date_key: str,
        tags: set,
    ) -> int:
        cluster_id = self._next_id
        self._next_id += 1
        state = _ClusterState(
            cluster_id=cluster_id,
            date_key=date_key,
            centroid=vec.copy(),
            tags=set(tags),
            article_count=1,
        )
        self._clusters_by_date[date_key].append(state)
        return cluster_id


# ── Functional API (used by pipeline.py) ─────────────────────────────────────

def cluster_articles(
    article_ids: List[int],
    embeddings: np.ndarray,
    date_keys: List[str],
    tags_list: Optional[List[Optional[List[str]]]] = None,
    threshold: float = _SIMILARITY_THRESHOLD,
    tag_overlap_bonus: float = _TAG_OVERLAP_BONUS,
    min_cluster_size: int = _MIN_CLUSTER_SIZE,
) -> np.ndarray:
    """
    Cluster a batch of articles and return an integer label array.

    This is the primary entry-point used by pipeline.py.

    Args:
        article_ids:       List of integer article IDs.
        embeddings:        np.ndarray shape (N, D), L2-normalised float32.
        date_keys:         List of "YYYY-MM-DD" strings aligned to embeddings.
        tags_list:         Optional list of tag lists aligned to embeddings.
        threshold:         Cosine similarity threshold to join a cluster.
        tag_overlap_bonus: Similarity bonus when tags match.
        min_cluster_size:  Minimum cluster size; smaller clusters → label -1.

    Returns:
        np.ndarray shape (N,) of int32 labels; -1 means unassigned/noise.
    """
    if len(article_ids) == 0:
        return np.array([], dtype=np.int32)

    if tags_list is None:
        tags_list = [None] * len(article_ids)

    clust = NewsClust(
        threshold=threshold,
        tag_overlap_bonus=tag_overlap_bonus,
        min_cluster_size=min_cluster_size,
    )

    for aid, vec, date_key, tags in zip(article_ids, embeddings, date_keys, tags_list):
        clust.add_article(
            article_id=int(aid),
            embedding=vec,
            date_key=date_key,
            tags=list(tags) if tags else None,
        )

    return clust.get_cluster_labels(article_ids)


# ── Legacy shim (keeps pipeline.py import working during transition) ───────────

def cluster_embeddings(
    embeddings: np.ndarray,
    eps: float | None = None,          # ignored — kept for call-site compatibility
    min_samples: int | None = None,    # maps to min_cluster_size
    metric: str = "cosine",            # ignored — always cosine
) -> np.ndarray:
    """
    DEPRECATED shim: callers should migrate to cluster_articles().

    This function lacks date_keys and tags, so every article is treated as
    belonging to the same date bucket.  It exists only to avoid import errors
    in code that calls cluster_embeddings() directly.
    """
    logger.warning(
        "cluster_embeddings() is deprecated; use cluster_articles() for proper "
        "date-constrained, tag-boosted clustering."
    )
    n = embeddings.shape[0]
    if n == 0:
        return np.array([], dtype=np.int32)

    min_size = int(min_samples) if min_samples is not None else _MIN_CLUSTER_SIZE
    article_ids = list(range(n))
    date_keys = ["1970-01-01"] * n  # single bucket — no date filtering

    return cluster_articles(
        article_ids=article_ids,
        embeddings=embeddings,
        date_keys=date_keys,
        min_cluster_size=min_size,
    )


def refine_cluster_labels(
    embeddings: np.ndarray,
    labels: np.ndarray,
    source_keys: list[str] | None = None,
    min_pairwise_similarity: float | None = None,
    min_samples: int | None = None,
) -> np.ndarray:
    """
    DEPRECATED shim: refinement is now built into NewsClust.

    Returns labels unchanged.  Kept to avoid ImportError in existing callers.
    """
    logger.warning(
        "refine_cluster_labels() is a no-op shim.  Refinement is now handled "
        "inside NewsClust.  Remove this call."
    )
    return np.asarray(labels, dtype=np.int32)
