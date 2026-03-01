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
