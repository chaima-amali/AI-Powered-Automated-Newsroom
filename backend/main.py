"""
main.py (v2) — Manual pipeline runner.
See api_main.py for the FastAPI server.

uvicorn api_main:app --host 0.0.0.0 --port 8000

Usage:
    python main.py                     # run all 4 stages
    python main.py --stage scraper
    python main.py --stage embedding
    python main.py --stage summarizer
    python main.py --stage rewriter
    python main.py --health            # check DB + feeds only
"""
import argparse
import logging
import sys
import time
from typing import Callable

from dotenv import load_dotenv
load_dotenv()

from utils.logging_config import setup_logging, stage_banner

setup_logging()
logger = logging.getLogger("main")

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[94m"; BOLD = "\033[1m"; RST = "\033[0m"


def banner(msg: str) -> None:
    print(f"\n{BOLD}{B}{'═'*60}{RST}\n{BOLD}{B}  {msg}{RST}\n{BOLD}{B}{'═'*60}{RST}")


def ok(msg: str)   -> None: print(f"  {G}✔{RST}  {msg}")
def err(msg: str)  -> None: print(f"  {R}✘{RST}  {msg}")
def info(msg: str) -> None: print(f"  {Y}▸{RST}  {msg}")


def _run_stage(name: str, fn: Callable) -> tuple[bool, float, object]:
    stage_banner(name, "start")
    t0 = time.time()
    try:
        result  = fn()
        elapsed = time.time() - t0
        stage_banner(name, "done")
        return True, elapsed, result
    except Exception as exc:
        elapsed = time.time() - t0
        stage_banner(name, "failed")
        logger.exception("Stage '%s' raised exception", name)
        return False, elapsed, exc


STAGES: dict[str, tuple[Callable, str]] = {
    "scraper": (
        lambda: __import__("pipeline.scraper.orchestrator", fromlist=["run_scraper"]).run_scraper(),
        "🕷️  Scraper    — RSS feeds + article parsing",
    ),
    "embedding": (
        lambda: __import__("pipeline.embedding.pipeline", fromlist=["run_embedding_pipeline"]).run_embedding_pipeline(),
        "🧠  Embedding  — vectors + DBSCAN clustering",
    ),
    "summarizer": (
        lambda: __import__("pipeline.summarizer.pipeline", fromlist=["run_summarization_pipeline"]).run_summarization_pipeline(),
        "📝  Summarizer — extractive/hybrid/LLM per cluster",
    ),
    "rewriter": (
        lambda: __import__("pipeline.rewriter.pipeline", fromlist=["run_rewriter_pipeline"]).run_rewriter_pipeline(),
        "✍️  Rewriter   — LLM → publication-ready articles",
    ),
}


def run_all() -> None:
    banner("AI Newsroom — Full Pipeline Run")
    total_start = time.time()
    results: list[tuple[str, bool, float, object]] = []

    for name, (fn, desc) in STAGES.items():
        info(desc)
        success, elapsed, result = _run_stage(name, fn)
        results.append((name, success, elapsed, result))
        if success:
            ok(f"'{name}' done in {elapsed:.1f}s — {result}")
        else:
            err(f"'{name}' FAILED after {elapsed:.1f}s — {result}")

    total = time.time() - total_start
    banner("Summary")
    for name, success, elapsed, result in results:
        sym = f"{G}✔{RST}" if success else f"{R}✘{RST}"
        print(f"  {sym}  {name:<12}  {'OK    ' if success else 'FAILED'}  {elapsed:6.1f}s")
    print(f"\n  Total: {BOLD}{total:.1f}s{RST}\n")

    if not all(s for _, s, _, _ in results):
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Newsroom Pipeline Runner")
    parser.add_argument("--stage", choices=[*STAGES.keys(), "all"], default="all")
    parser.add_argument("--health", action="store_true", help="Check DB + feeds only")
    args = parser.parse_args()

    if args.health:
        from utils.health_check import check_env_vars, check_db_connection, check_db_schema
        banner("Health Check")
        check_env_vars()
        check_db_connection()
        check_db_schema()
        return

    try:
        from db.connection import init_pool, has_db_settings
        if has_db_settings():
            init_pool()
        else:
            err("No DB credentials in .env — DB writes will fail.")
    except Exception as e:
        err(f"DB init failed: {e}")
        sys.exit(1)

    if args.stage == "all":
        run_all()
    else:
        fn, desc = STAGES[args.stage]
        info(desc)
        success, elapsed, result = _run_stage(args.stage, fn)
        if success:
            ok(f"Done in {elapsed:.1f}s — {result}")
        else:
            err(f"Failed — {result}")
            sys.exit(1)


if __name__ == "__main__":
    main()
