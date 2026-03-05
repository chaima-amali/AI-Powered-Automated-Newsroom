"""
db/connection.py
----------------
Thread-safe PostgreSQL connection pool using psycopg2.
Reads credentials from environment variables (never hardcoded).
"""

import os
import logging
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

# ── singleton connection pool ──────────────────────────────────────────────────
_pool: pool.ThreadedConnectionPool | None = None

def _build_dsn() -> dict:
    return {
        "dbname":   os.environ["DB_NAME"],        # set to: postgres
        "user":     os.environ["DB_USER"],         # set to: postgres
        "password": os.environ["DB_PASSWORD"],     # set to: zi/v_S*7AwRB54b
        "host":     os.environ["DB_HOST"],         # set to: db.utjltiuyvevuqtiimocq.supabase.co
        "port":     int(os.environ.get("DB_PORT", 5432)),
        "connect_timeout": 10,
        "options":  "-c statement_timeout=30000",
    }

def init_pool(minconn: int = 2, maxconn: int = 10) -> None:
    """Create the global connection pool. Call once at startup."""
    global _pool
    if _pool is None:
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
    conn = _pool.getconn()
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
