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

def fetch_unprocessed_articles(batch_size: int = 256, offset: int = 0) -> list[dict]:
    """
    Return a batch of articles where:
      - is_processed = FALSE
      - scrape_status = 'success'

    Returns a list of dicts with keys: id, title, content.
    Uses LIMIT/OFFSET for cursor-style batching without loading the full table.

    Args:
        batch_size : maximum rows to fetch in this call
        offset     : row offset for pagination

    Returns:
        List of dicts [{id, title, content}, ...]
    """
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """
            SELECT id, title, content
              FROM articles
             WHERE is_processed = FALSE
               AND scrape_status = 'success'
             ORDER BY id          -- stable order for reproducible batching
             LIMIT %s OFFSET %s
            """,
            (batch_size, offset),
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
        records : list of dicts [{id, embedding, cluster_id}, ...]
    """
    if not records:
        return

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
