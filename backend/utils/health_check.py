"""
utils/health_check.py (v2)
IMPROVEMENTS: checks new v4 schema tables, pgvector ext, LLM keys, table counts.
"""
from __future__ import annotations
import argparse, logging, os, sys

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("health_check")
G="\033[92m"; R="\033[91m"; Y="\033[93m"; RST="\033[0m"
def ok(m):   logger.info(f"{G}✔{RST}  {m}")
def fail(m): logger.error(f"{R}✘{RST}  {m}")
def warn(m): logger.warning(f"{Y}⚠{RST}  {m}")

def check_env_vars() -> bool:
    required = ["DB_NAME","DB_USER","DB_PASSWORD","DB_HOST"]
    missing  = [k for k in required if not os.environ.get(k)]
    if missing:
        fail(f"Missing required env vars: {', '.join(missing)}")
        fail("Copy backend/.env.example to backend/.env and fill in the values.")
        return False
    ok("All required env vars present")
    has_llm = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("GROQ_API_KEY")
    if not has_llm:
        warn("No LLM API key found — rewriter falls back to extractive output.")
    else:
        ok("LLM API key configured")
    return True

def check_db_connection() -> bool:
    try:
        from db.connection import init_pool, get_cursor
        init_pool()
        with get_cursor() as cur:
            cur.execute("SELECT version()")
            v = cur.fetchone()[0]
        ok(f"DB connected: {v[:60]}")
        return True
    except Exception as e:
        fail(f"DB connection failed: {e}")
        fail("Tip: Check DB_HOST, DB_PORT, DB_SSLMODE in .env")
        return False

def check_db_schema() -> bool:
    REQUIRED = {"articles","sources","scrape_runs","clusters","summaries",
                "published_articles","article_cluster","pipeline_jobs","users"}
    try:
        from db.connection import get_cursor
        with get_cursor() as cur:
            cur.execute("SELECT 1 FROM pg_extension WHERE extname='vector'")
            if not cur.fetchone():
                fail("pgvector extension not installed. Run: CREATE EXTENSION vector;")
                return False
            ok("pgvector extension OK")
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            existing = {r[0] for r in cur.fetchall()}
        missing = REQUIRED - existing
        if missing:
            fail(f"Missing tables: {sorted(missing)}")
            fail("Run: psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f db/schema.sql")
            return False
        ok(f"All {len(REQUIRED)} required tables present")
        return True
    except Exception as e:
        fail(f"Schema check failed: {e}")
        return False

def check_feeds(source_filter=None) -> bool:
    from config.sources import SOURCES
    from pipeline.scraper.feed_collector import fetch_feed_entries
    sources = [s for s in SOURCES if not source_filter or source_filter.lower() in s["name"].lower()]
    all_ok = True
    for src in sources:
        if not src.get("rss_url"): warn(f"{src['name']}: no RSS URL"); continue
        try:
            entries = fetch_feed_entries(src)
            if entries: ok(f"{src['name']}: {len(entries)} entries")
            else: warn(f"{src['name']}: 0 entries"); all_ok = False
        except Exception as e:
            fail(f"{src['name']}: {e}"); all_ok = False
    return all_ok

def check_article_parse(source_filter=None) -> bool:
    from config.sources import SOURCES
    from pipeline.scraper.feed_collector import fetch_feed_entries
    from pipeline.scraper.parser import extract_article
    sources = [s for s in SOURCES if not source_filter or source_filter.lower() in s["name"].lower()][:3]
    all_ok = True
    for src in sources:
        entries = fetch_feed_entries(src)
        if not entries: warn(f"{src['name']}: no entries"); continue
        try:
            art = extract_article(entries[0]["url"], src)
            n   = len(art.get("content") or "")
            if n > 300: ok(f"{src['name']}: parsed OK ({n} chars)")
            else: warn(f"{src['name']}: short ({n} chars)")
        except Exception as e:
            fail(f"{src['name']}: {e}"); all_ok = False
    return all_ok

def check_pipeline_tables_populated() -> None:
    from db.connection import get_cursor
    try:
        with get_cursor(dict_cursor=True) as cur:
            cur.execute("""SELECT
                (SELECT COUNT(*) FROM articles) AS articles,
                (SELECT COUNT(*) FROM articles WHERE is_processed) AS embedded,
                (SELECT COUNT(*) FROM clusters) AS clusters,
                (SELECT COUNT(*) FROM summaries) AS summaries,
                (SELECT COUNT(*) FROM published_articles WHERE status='published') AS published""")
            row = cur.fetchone()
        print("\n  Pipeline table counts:")
        for k,v in row.items(): print(f"    {k:<14} {v:>8}")
    except Exception as e:
        warn(f"Could not read table counts: {e}")

def main():
    try:
        from dotenv import load_dotenv; load_dotenv()
    except ImportError: pass
    p = argparse.ArgumentParser()
    p.add_argument("--source"); p.add_argument("--db-only", action="store_true")
    args = p.parse_args()
    print("\n══════════ AI Newsroom Health Check v2 ══════════\n")
    r = {"env": check_env_vars(), "db_conn": check_db_connection()}
    if r["db_conn"]:
        r["schema"] = check_db_schema()
        if r.get("schema"): check_pipeline_tables_populated()
    if not args.db_only:
        print("\n── Feed checks ──")
        r["feeds"] = check_feeds(args.source)
        if r.get("feeds"):
            print("\n── Parse checks ──")
            r["parse"] = check_article_parse(args.source)
    print("\n═══════════════════════════════════════════════")
    if all(r.values()): print(f"{G}All checks passed.{RST}\n")
    else:
        failed = [k for k,v in r.items() if not v]
        print(f"{R}Failed: {', '.join(failed)}{RST}\n"); sys.exit(1)

if __name__ == "__main__": main()
