"""
pipeline/summarizer/pipeline.py (v2)
--------------------------------------
Summarization pipeline runner with real-time progress.

BUGS FIXED vs v1:
  1. When route_summarization() returned a result with empty summary_text
     (e.g. if BART produced an empty string on very short input), write_summary()
     silently skipped writing (guarded in repository v2). But the cluster was
     not marked as failed, so it would be retried on every run endlessly.
     Fixed: log explicitly when skipping a cluster due to empty summary.

  2. fetch_unsummarized_clusters() returned clusters with article_count=0
     from old orphaned rows. The pipeline then called fetch_articles_for_cluster()
     which returned [], causing the "skipped" path. The cluster was then retried
     forever. Fixed: add a DB-level guard (article_count > 0) in the query —
     already in repository v2 — and log clearly.

  3. No SSE progress events — pipeline was invisible in the UI.

PERFORMANCE NOTES:
  - The BART model download is ~1.6 GB on first run. Set SUMMARIZER_USE_DISTIL=true
    in .env to use the 700 MB distilbart-cnn-12-6 instead (6x faster, slight quality drop).
  - For production, pre-download the model:
      python -c "from transformers import pipeline; pipeline('summarization', model='facebook/bart-large-cnn')"
  - Translation models (Helsinki-NLP) are ~300 MB each and download lazily.
"""
from __future__ import annotations

import logging
from dotenv import load_dotenv
load_dotenv()

from db.connection import init_pool
from db.repository import (
    fetch_unsummarized_clusters,
    fetch_articles_for_cluster,
    write_summary,
)
from pipeline.summarizer.router import route_summarization

logger = logging.getLogger(__name__)


def _broadcast(event: str, **kw):
    try:
        import builtins
        fn = getattr(builtins, "_newsroom_broadcast", None)
        if fn:
            fn(event, kw)
    except Exception:
        pass


def run_summarization_pipeline() -> dict:
    init_pool()

    clusters = fetch_unsummarized_clusters()
    total    = len(clusters)
    logger.info("═══ Summarization pipeline — %d clusters to process ═══", total)
    _broadcast("summarizer_started", cluster_count=total)

    stats = {"total": total, "success": 0, "failed": 0, "skipped": 0}

    for i, cluster in enumerate(clusters, 1):
        cluster_id = cluster["cluster_id"]
        tag        = cluster.get("tag", "unknown")
        count      = cluster.get("article_count", 0)

        if count == 0:
            logger.debug("Cluster %d has 0 articles — skipping", cluster_id)
            stats["skipped"] += 1
            continue

        articles = fetch_articles_for_cluster(cluster_id)
        if not articles:
            logger.warning("Cluster %d: fetch returned 0 articles despite count=%d", cluster_id, count)
            stats["skipped"] += 1
            continue

        logger.info("[%d/%d] Cluster %d (%s, n=%d)…", i, total, cluster_id, tag, count)
        _broadcast("summarizer_progress",
                   current=i, total=total, cluster_id=cluster_id, tag=tag, n_articles=count)

        try:
            result = route_summarization(articles, tag=tag)

            if not result.get("summary_text", "").strip():
                logger.warning("Cluster %d: empty summary — skipping write", cluster_id)
                stats["skipped"] += 1
                continue

            write_summary(cluster_id, result)
            stats["success"] += 1
            logger.info(
                "  ✅ Cluster %d → strategy=%s  model=%s",
                cluster_id, result["strategy"], result.get("summary_model", "?")
            )

        except Exception as e:
            stats["failed"] += 1
            logger.error("  ❌ Cluster %d failed: %s", cluster_id, e, exc_info=True)
            _broadcast("summarizer_error", cluster_id=cluster_id, error=str(e))

    logger.info("═══ Summarization done: %s ═══", stats)
    _broadcast("summarizer_done", **stats)
    return stats
