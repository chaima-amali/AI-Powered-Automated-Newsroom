"""
db/repository.py
-----------------
All database read/write operations for articles and scrape runs.
No SQL lives outside this file.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from db.connection import get_cursor

logger = logging.getLogger(__name__)


# ── Scrape Run helpers ─────────────────────────────────────────────────────────

def start_scrape_run(total_sources: int) -> int:
    """Insert a new scrape_run row and return its id."""
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO scrape_runs (total_sources, run_status)
            VALUES (%s, 'running')
            RETURNING id
            """,
            (total_sources,),
        )
        return cur.fetchone()[0]


def finish_scrape_run(run_id: int, fetched: int, inserted: int, failed: int, status: str = "completed") -> None:
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE scrape_runs
               SET finished_at   = NOW(),
                   total_fetched  = %s,
                   total_inserted = %s,
                   total_failed   = %s,
                   run_status     = %s
             WHERE id = %s
            """,
            (fetched, inserted, failed, status, run_id),
        )


# ── Article helpers ────────────────────────────────────────────────────────────

def upsert_article(article: dict) -> bool:
    """
    Insert article; skip silently on URL conflict.
    Returns True if a new row was inserted, False if it already existed.
    """
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO articles (
                title, content, summary, author, language,
                source_id, source_name, url, section,
                published_at, tags, image_url, word_count,
                is_paywalled, scrape_status, error_message
            ) VALUES (
                %(title)s, %(content)s, %(summary)s, %(author)s, %(language)s,
                %(source_id)s, %(source_name)s, %(url)s, %(section)s,
                %(published_at)s, %(tags)s, %(image_url)s, %(word_count)s,
                %(is_paywalled)s, %(scrape_status)s, %(error_message)s
            )
            ON CONFLICT (url) DO NOTHING
            RETURNING id
            """,
            article,
        )
        row = cur.fetchone()
        return row is not None


def get_source_id(source_name: str) -> Optional[int]:
    with get_cursor() as cur:
        cur.execute("SELECT id FROM sources WHERE name = %s", (source_name,))
        row = cur.fetchone()
        return row[0] if row else None


def ensure_source(name: str, rss_url: str, base_url: str, language: str = "ar") -> int:
    """Insert source if it doesn't exist; return its id."""
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO sources (name, rss_url, base_url, language)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET rss_url = EXCLUDED.rss_url
            RETURNING id
            """,
            (name, rss_url, base_url, language),
        )
        return cur.fetchone()[0]


# ── Embedding pipeline helpers ─────────────────────────────────────────────────

def fetch_unprocessed_articles(batch_size: int = 256, after_id: int = 0) -> list[dict]:
    """
    Return a batch of articles where:
        - is_processed = FALSE
        - scrape_status = 'success'

    Uses keyset pagination on id so the scan is stable and efficient.

    Args:
        batch_size : maximum rows to fetch in this call
        after_id   : fetch rows with id > after_id

    Returns:
        List of dicts [{id, title, content, summary, article_date}, ...]
    """
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """
            SELECT
                id,
                title,
                content,
                                summary,
                COALESCE(published_at::date, scraped_at::date) AS article_date
              FROM articles
             WHERE is_processed = FALSE
               AND scrape_status = 'success'
               AND id > %s
             ORDER BY id
             LIMIT %s
            """,
            (after_id, batch_size),
        )
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def count_unprocessed_articles() -> int:
    """Return the total number of articles yet to be embedded."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
              FROM articles
             WHERE is_processed = FALSE
               AND scrape_status = 'success'
            """
        )
        return cur.fetchone()[0]


def bulk_update_embeddings_and_clusters(records: list[dict]) -> None:
    """
    Atomically update embedding + cluster_id + is_processed for a batch
    of articles.

    Each record must have keys: id, embedding, cluster_id.

    Uses psycopg2 executemany with a temporary VALUES list for efficiency —
    avoids N individual round-trips.

    Args:
        records : list of dicts [{id, embedding, cluster_id, article_date}, ...]
    """
    if not records:
        return

    # 1. Insert/update the clusters table first
    cluster_dates = {}
    for record in records:
        cid = record.get("cluster_id")
        if cid is not None and cid != -1:
            if cid not in cluster_dates:
                cluster_dates[cid] = record.get("article_date")

    if cluster_dates:
        with get_cursor() as cur:
            for cluster_id, article_date in cluster_dates.items():
                cur.execute(
                    """
                    INSERT INTO clusters (cluster_id, article_date)
                    VALUES (%s, %s)
                    ON CONFLICT (cluster_id) DO UPDATE
                    SET article_count = (SELECT COUNT(*) FROM articles WHERE cluster_id = %s)
                    """,
                    (cluster_id, article_date, cluster_id),
                )

    # Build parameter tuples
    # embedding is stored as a Python list so psycopg2 can cast it to vector
    params = [
        (
            r["embedding"],          # list[float] → cast to vector in SQL
            r["cluster_id"],         # int or None for noise points
            r["id"],                 # WHERE id = %s
        )
        for r in records
    ]

    with get_cursor() as cur:
        cur.executemany(
            """
            UPDATE articles
               SET embedding     = %s::vector,
                   cluster_id    = %s,
                   is_processed  = TRUE,
                   updated_at    = NOW()
             WHERE id = %s
            """,
            params,
        )

    logger.info("bulk_update_embeddings_and_clusters: updated %d rows", len(records))


def get_cluster_info(cluster_id: int) -> dict | None:
    """Fetch metadata about a cluster."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT * FROM clusters WHERE cluster_id = %s",
            (cluster_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def get_articles_in_cluster(cluster_id: int) -> list[dict]:
    """Fetch all articles in a given cluster."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """
            SELECT id, title, content, cluster_id, is_processed
              FROM articles
             WHERE cluster_id = %s
             ORDER BY id
            """,
            (cluster_id,),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def fetch_processed_article_samples(limit: int = 5) -> list[dict]:
    """Return a small sample of processed articles for verification output."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """
            SELECT id, cluster_id, embedding, COALESCE(published_at::date, scraped_at::date) AS article_date
              FROM articles
             WHERE is_processed = TRUE
             ORDER BY id
             LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]
