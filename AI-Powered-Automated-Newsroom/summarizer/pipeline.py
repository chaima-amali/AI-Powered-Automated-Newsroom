"""
summarizer/pipeline.py
───────────────────────
Main orchestration: pulls clusters from Supabase, summarizes each,
writes results back.

Mirrors the pattern of run_embedding_pipeline.py in your project root.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from db.connection import get_cursor
from dotenv import load_dotenv

from .router import route_and_summarize

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def fetch_unsummarized_clusters() -> list[dict]:
    with get_cursor(dict_cursor=True) as cur:
        cur.execute("""
            SELECT c.cluster_id, c.tag, c.article_date, c.article_count
            FROM clusters c
            LEFT JOIN summaries s ON c.cluster_id = s.cluster_id
            WHERE s.cluster_id IS NULL AND c.article_count > 0
        """)
        return cur.fetchall()

def fetch_articles_for_cluster(cluster_id: int) -> list[dict]:
    with get_cursor(dict_cursor=True) as cur:
        cur.execute("""
            SELECT title, content,
                   source_name  AS source,
                   language     AS lang,
                   url
            FROM articles
            WHERE cluster_id = %s
        """, (cluster_id,))
        return cur.fetchall()

def write_summary(cluster_id: int, result: dict) -> None:
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO summaries (cluster_id, summary_text, summary_lang, summary_model, strategy)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (cluster_id) DO UPDATE SET
                summary_text = EXCLUDED.summary_text,
                summary_model = EXCLUDED.summary_model,
                strategy = EXCLUDED.strategy,
                summarized_at = NOW()
        """, (
            cluster_id,
            result["summary_text"],
            result["summary_lang"],
            result["summary_model"],
            result["strategy"],
        ))

def run_summarization_pipeline(limit: int = None) -> None:
    """
    Main entry point. Summarizes all unsummarized clusters.

    Args:
        limit: process only first N clusters (useful for testing)
    """

    # ❌ no Supabase client anymore
    clusters = fetch_unsummarized_clusters()

    if limit:
        clusters = clusters[:limit]

    logger.info("Starting summarization pipeline for %d clusters", len(clusters))

    success, failed = 0, 0

    for cluster in clusters:
        cluster_id = cluster["cluster_id"]
        tag = cluster.get("tag", "")

        try:
            # fetch articles via psycopg2
            articles = fetch_articles_for_cluster(cluster_id)

            if not articles:
                logger.warning("Cluster %d has no articles — skipping", cluster_id)
                continue

            result = route_and_summarize(
                articles=articles,
                cluster_tag=tag,
                centroid=None,  # keep if you compute/store it later
            )

            # write summary via psycopg2
            write_summary(cluster_id, result)

            success += 1

        except Exception as e:
            logger.error("Failed cluster %d: %s", cluster_id, e)
            failed += 1

    logger.info("Pipeline done. Success: %d | Failed: %d", success, failed)

if __name__ == "__main__":
    run_summarization_pipeline()
