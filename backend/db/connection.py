"""
db/connection.py (v2)
---------------------
Thread-safe PostgreSQL connection pool using psycopg2.

FIXES vs v1:
  1. sslmode was hardcoded to "require" — fails on local Postgres without SSL.
     Now reads SSL_MODE env var (default: "prefer" for local-friendly behavior).
  2. _build_dsn() raised RuntimeError if any var missing — now raises clearly
     on connection attempt, not at import time, so app starts in degraded mode.
  3. No graceful degradation — DB failure crashed the whole app at startup.
     Now has_db_settings() + try/except in lifespan allows API to run read-only.
  4. Socket test was done with hardcoded 5s timeout; now respects env var.
  5. Pool exhaustion retry loop used sleep(0.1*attempt) — could wait 4+ seconds;
     capped at 0.5s per wait.

ARCHITECTURE NOTE:
  Use get_cursor(dict_cursor=True) for SELECT rows as dicts.
  Use get_conn() when you need the raw connection (e.g., execute_values).
"""

import logging
import os
import socket
import time
from contextlib import contextmanager
from typing import Optional

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from psycopg2.pool import PoolError

logger = logging.getLogger(__name__)

_pool: Optional[pool.ThreadedConnectionPool] = None


def _env(*names: str, default: Optional[str] = None) -> Optional[str]:
    for name in names:
        v = os.environ.get(name)
        if v:
            return v
    return default


def has_db_settings() -> bool:
    """Return True when all required DB env vars are present."""
    return all(
        _env(*pair) for pair in (
            ("DB_HOST", "PGHOST"),
            ("DB_USER", "PGUSER"),
            ("DB_PASSWORD", "PGPASSWORD"),
            ("DB_NAME", "PGDATABASE"),
        )
    )


def _build_dsn() -> dict:
    host     = _env("DB_HOST", "PGHOST")
    user     = _env("DB_USER", "PGUSER")
    password = _env("DB_PASSWORD", "PGPASSWORD")
    dbname   = _env("DB_NAME", "PGDATABASE")
    port     = int(_env("DB_PORT", "PGPORT", default="5432"))
    sslmode  = _env("DB_SSLMODE", default="prefer")   # BUG FIX: was hardcoded "require"

    missing = [k for k, v in [("DB_HOST", host), ("DB_USER", user),
                                ("DB_PASSWORD", password), ("DB_NAME", dbname)] if not v]
    if missing:
        raise RuntimeError(
            f"Missing DB environment variables: {missing}\n"
            f"Create a .env file with DB_HOST, DB_USER, DB_PASSWORD, DB_NAME.\n"
            f"Working directory: {os.getcwd()}"
        )

    return dict(
        dbname=dbname, user=user, password=password,
        host=host, port=port,
        sslmode=sslmode,
        connect_timeout=int(_env("DB_CONNECT_TIMEOUT", default="15")),
        options="-c statement_timeout=30000",
    )


def init_pool(minconn: Optional[int] = None, maxconn: Optional[int] = None) -> None:
    """
    Create the global connection pool. Safe to call multiple times.
    Must be called AFTER load_dotenv().
    """
    global _pool
    if _pool is not None:
        return

    _min = minconn or int(os.environ.get("DB_POOL_MINCONN", "1"))
    _max = maxconn or int(os.environ.get("DB_POOL_MAXCONN", "10"))
    _min = max(1, _min)
    _max = max(_min, _max)

    dsn = _build_dsn()

    # Quick TCP reachability test — fail fast with a clear message
    try:
        timeout = int(os.environ.get("DB_CONNECT_TEST_TIMEOUT", "5"))
        with socket.create_connection((dsn["host"], dsn["port"]), timeout=timeout):
            pass
    except Exception as e:
        raise RuntimeError(
            f"Cannot reach database at {dsn['host']}:{dsn['port']} — {e}\n"
            f"Check that PostgreSQL is running and DB_HOST/DB_PORT are correct."
        ) from e

    _pool = pool.ThreadedConnectionPool(_min, _max, **dsn)
    logger.info(
        "✅ DB pool ready  host=%s  db=%s  user=%s  pool=%d..%d",
        dsn["host"], dsn["dbname"], dsn["user"], _min, _max,
    )


def close_pool() -> None:
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        logger.info("DB pool closed")


@contextmanager
def get_conn():
    """
    Yield a raw psycopg2 connection from the pool.
    Commits on success, rolls back on exception, always returns to pool.
    """
    global _pool
    if _pool is None:
        init_pool()

    conn = None
    last_exc: Optional[Exception] = None
    retries = int(os.environ.get("DB_POOL_ACQUIRE_RETRIES", "30"))
    backoff  = float(os.environ.get("DB_POOL_ACQUIRE_BACKOFF_SEC", "0.1"))

    for attempt in range(retries):
        try:
            conn = _pool.getconn()
            break
        except PoolError as e:
            last_exc = e
            wait = min(backoff * (attempt + 1), 0.5)   # BUG FIX: was capped at 1.0, now 0.5
            logger.warning("Pool busy (%d/%d) — retry in %.2fs", attempt + 1, retries, wait)
            time.sleep(wait)

    if conn is None:
        raise RuntimeError(
            f"DB pool exhausted after {retries} retries. Raise DB_POOL_MAXCONN in .env."
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
    """
    Yield a cursor. Commit/rollback handled automatically.
    Use dict_cursor=True to get rows as dicts instead of tuples.
    """
    factory = RealDictCursor if dict_cursor else None
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=factory) if factory else conn.cursor()
        try:
            yield cur
        finally:
            cur.close()
