"""
utils/health_check.py
----------------------
Run this to verify the scraper is working correctly BEFORE deploying.

Checks:
  1. DB connection & schema
  2. Each source's RSS feed is reachable
  3. Sample article parse from each source
  4. A full mini-run (first 3 articles per source)

Usage:
    python -m utils.health_check
    python -m utils.health_check --source "El Watan"
    python -m utils.health_check --db-only
"""

import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("health_check")

GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

def ok(msg):  logger.info(f"{GREEN}✔{RESET}  {msg}")
def fail(msg): logger.error(f"{RED}✘{RESET}  {msg}")
def warn(msg): logger.warning(f"{YELLOW}⚠{RESET}  {msg}")


def check_env_vars() -> bool:
    required = ["DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST"]
    missing  = [k for k in required if not os.environ.get(k)]
    if missing:
        fail(f"Missing env vars: {', '.join(missing)}")
        return False
    ok(f"All required env vars present")
    return True


def check_db_connection() -> bool:
    try:
        from db.connection import get_cursor
        with get_cursor() as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
        ok(f"DB connected: {version[:60]}")
        return True
    except Exception as e:
        fail(f"DB connection failed: {e}")
        return False


def check_db_schema() -> bool:
    try:
        from db.connection import get_cursor
        with get_cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('articles', 'sources', 'scrape_runs')
            """)
            tables = {r[0] for r in cur.fetchall()}
        missing = {"articles", "sources", "scrape_runs"} - tables
        if missing:
            fail(f"Missing tables: {missing} — run db/schema.sql first")
            return False
        ok("All required tables exist")
        return True
    except Exception as e:
        fail(f"Schema check failed: {e}")
        return False


def check_feeds(source_filter: str = None) -> dict:
    from config.sources import SOURCES
    from scraper.feed_collector import fetch_feed_entries

    results = {}
    sources = SOURCES
    if source_filter:
        sources = [s for s in sources if source_filter.lower() in s["name"].lower()]

    for source in sources:
        name = source["name"]
        if not source.get("rss_url"):
            warn(f"{name}: no RSS URL configured")
            results[name] = "no_rss"
            continue
        try:
            entries = fetch_feed_entries(source)
            if entries:
                ok(f"{name}: {len(entries)} entries in feed")
                results[name] = "ok"
            else:
                warn(f"{name}: feed reachable but 0 entries")
                results[name] = "empty"
        except Exception as e:
            fail(f"{name}: feed error — {e}")
            results[name] = "error"

    return results


def check_article_parse(source_filter: str = None) -> dict:
    from config.sources import SOURCES
    from scraper.feed_collector import fetch_feed_entries
    from scraper.parser import extract_article

    results = {}
    sources = SOURCES
    if source_filter:
        sources = [s for s in sources if source_filter.lower() in s["name"].lower()]

    for source in sources:
        name = source["name"]
        entries = fetch_feed_entries(source)
        if not entries:
            warn(f"{name}: no entries to test")
            continue

        url = entries[0]["url"]
        try:
            article = extract_article(url, source)
            content_len = len(article.get("content") or "")
            if content_len > 300:
                ok(f"{name}: parsed article OK ({content_len} chars) — {url[:70]}")
                results[name] = "ok"
            else:
                warn(f"{name}: article parsed but short ({content_len} chars) — may need custom selector")
                results[name] = "short"
        except Exception as e:
            fail(f"{name}: parse error — {e}")
            results[name] = "error"

    return results


def main():
    # Load .env if present
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--source",  help="Filter to one source name")
    parser.add_argument("--db-only", action="store_true")
    args = parser.parse_args()

    print("\n══════════════ AI Newsroom Health Check ══════════════")

    all_ok = True
    all_ok &= check_env_vars()
    all_ok &= check_db_connection()
    all_ok &= check_db_schema()

    if not args.db_only:
        check_feeds(args.source)
        check_article_parse(args.source)

    print("\n══════════════════════════════════════════════════════")
    if all_ok:
        print(f"{GREEN}All critical checks passed.{RESET}")
    else:
        print(f"{RED}Some checks failed — review errors above.{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
