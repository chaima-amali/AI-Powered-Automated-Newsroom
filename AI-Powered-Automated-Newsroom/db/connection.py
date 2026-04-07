"""
db/connection.py
----------------
Thread-safe PostgreSQL connection pool using psycopg2.
Reads credentials from environment variables (never hardcoded).

FIXES applied vs original:
  - FIX 1 (SECURITY): Removed all credential hints from comments.
                      The original file had the real Supabase password
                      written in a comment. Even though the value itself
                      came from the environment, the comment was visible
                      to anyone with repo access and in git history.
"""

import os
import logging
import time
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from psycopg2.pool import PoolError

logger = logging.getLogger(__name__)

# ── singleton connection pool ──────────────────────────────────────────────────
_pool: pool.ThreadedConnectionPool | None = None

# Pool tuning (override in .env if needed)
DB_POOL_MINCONN = int(os.environ.get("DB_POOL_MINCONN", 2))
DB_POOL_MAXCONN = int(os.environ.get("DB_POOL_MAXCONN", 15))
DB_POOL_ACQUIRE_RETRIES = int(os.environ.get("DB_POOL_ACQUIRE_RETRIES", 40))
DB_POOL_ACQUIRE_BACKOFF_SEC = float(os.environ.get("DB_POOL_ACQUIRE_BACKOFF_SEC", 0.1))


def _build_dsn() -> dict:
    return {
        # FIX 1: Removed credential hints from all comments.
        # Values come exclusively from environment variables — see .env file.
        "dbname":          os.environ["DB_NAME"],
        "user":            os.environ["DB_USER"],
        "password":        os.environ["DB_PASSWORD"],
        "host":            os.environ["DB_HOST"],
        "port":            int(os.environ.get("DB_PORT", 5432)),
        "connect_timeout": 10,
        "options":         "-c statement_timeout=30000",
    }


def init_pool(minconn: int | None = None, maxconn: int | None = None) -> None:
    """Create the global connection pool. Call once at startup."""
    global _pool
    if _pool is None:
        minconn = DB_POOL_MINCONN if minconn is None else minconn
        maxconn = DB_POOL_MAXCONN if maxconn is None else maxconn
        if minconn < 1:
            minconn = 1
        if maxconn < minconn:
            maxconn = minconn
        _pool = pool.ThreadedConnectionPool(minconn, maxconn, **_build_dsn())
        logger.info("DB connection pool initialised (min=%d, max=%d)", minconn, maxconn)


def close_pool() -> None:
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        logger.info("DB connection pool closed")


@contextmanager
def get_conn():
    """Yield a connection from the pool, auto-return on exit."""
    if _pool is None:
        init_pool()
    conn = None
    last_exc: Exception | None = None

    for attempt in range(DB_POOL_ACQUIRE_RETRIES):
        try:
            conn = _pool.getconn()
            break
        except PoolError as exc:
            last_exc = exc
            wait = min(DB_POOL_ACQUIRE_BACKOFF_SEC * (attempt + 1), 1.0)
            logger.warning(
                "DB pool busy (attempt %d/%d). Retrying in %.2fs",
                attempt + 1,
                DB_POOL_ACQUIRE_RETRIES,
                wait,
            )
            time.sleep(wait)

    if conn is None:
        raise RuntimeError(
            "DB connection pool exhausted after retries. "
            "Increase DB_POOL_MAXCONN or reduce scraper concurrency."
        ) from last_exc

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


@contextmanager
def get_cursor(dict_cursor: bool = False):
    """Yield a cursor; handles commit/rollback automatically."""
    factory = RealDictCursor if dict_cursor else None
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=factory) if factory else conn.cursor()
        try:
            yield cur
        finally:
            cur.close()
