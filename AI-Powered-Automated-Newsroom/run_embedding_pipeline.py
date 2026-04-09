"""
run_embedding_pipeline.py
--------------------------
CLI entry point for the local embedding + clustering pipeline.

Usage examples:
    python run_embedding_pipeline.py                    # one-shot run
    python run_embedding_pipeline.py --schedule 1440   # run every 24 h (minutes)
    python run_embedding_pipeline.py --dry-run         # count pending, no DB writes

Environment variables (set in .env):
    DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
    EMBEDDING_MODEL         (default: sentence-transformers/all-MiniLM-L6-v2)
    EMBEDDING_FETCH_BATCH   (default: 256)  rows fetched from DB per iteration
    EMBEDDING_ENCODE_BATCH  (default: 64)   sentences per model forward pass
    EMBEDDING_MAX_WORDS     (default: 500)  words used per article
    DBSCAN_EPS              (default: 0.25) cosine distance threshold
    DBSCAN_MIN_SAMPLES      (default: 3)    minimum cluster size
"""

import argparse
import logging
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()  # must happen before any db imports

from db.connection import close_pool, has_db_settings, init_pool
from db.repository import count_unprocessed_articles
from utils.logging_config import setup_logging


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(
        description="AI Newsroom — Local Embedding & Clustering Pipeline"
    )
    parser.add_argument(
        "--schedule",
        type=int,
        metavar="MINUTES",
        help="Run repeatedly every N minutes (omit for a single run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the number of pending articles and exit without processing",
    )
    args = parser.parse_args()

    # ── Validate required env vars ─────────────────────────────────────────────
    if not has_db_settings():
        logger.critical(
            "Missing required database environment variables — check your .env file."
        )
        sys.exit(1)

    # ── Dry-run mode ───────────────────────────────────────────────────────────
    if args.dry_run:
        init_pool()
        pending = count_unprocessed_articles()
        close_pool()
        logger.info("DRY RUN — articles pending embedding: %d", pending)
        return

    # ── Import pipeline here so the model isn't loaded during --dry-run ───────
    from embedding.pipeline import run_pipeline

    init_pool()

    try:
        if args.schedule:
            logger.info(
                "Scheduler mode — running every %d minutes", args.schedule
            )
            while True:
                run_pipeline()
                logger.info(
                    "Sleeping %d minutes until next run…", args.schedule
                )
                time.sleep(args.schedule * 60)
        else:
            summary = run_pipeline()
            logger.info("Summary: %s", summary)
    except KeyboardInterrupt:
        logger.info("Interrupted by user — shutting down gracefully.")
    except Exception:
        logger.exception("Unhandled exception in embedding pipeline")
        sys.exit(1)
    finally:
        close_pool()


if __name__ == "__main__":
    main()
