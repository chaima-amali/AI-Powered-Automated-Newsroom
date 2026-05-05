"""
run_summarization_pipeline.py
-------------------------------
CLI entry point for the summarization pipeline.

Usage:
    python run_summarization_pipeline.py           # summarize all pending clusters
    python run_summarization_pipeline.py --limit 5 # test: summarize first 5 clusters only
    python run_summarization_pipeline.py --schedule 60  # run every 60 minutes
"""

import argparse
import logging
import sys
import time

from dotenv import load_dotenv
load_dotenv()

from utils.logging_config import setup_logging


def main():
    setup_logging()
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(description="AI Newsroom — Summarization Pipeline")
    parser.add_argument("--limit", type=int, help="Only process first N clusters (for testing)")
    parser.add_argument("--schedule", type=int, metavar="MINUTES",
                        help="Run repeatedly every N minutes")
    args = parser.parse_args()

    from summarizer.pipeline import run_summarization_pipeline

    try:
        if args.schedule:
            logger.info("Scheduler mode: running every %d minutes", args.schedule)
            while True:
                run_summarization_pipeline(limit=args.limit)
                logger.info("Sleeping %d minutes...", args.schedule)
                time.sleep(args.schedule * 60)
        else:
            run_summarization_pipeline(limit=args.limit)
    except KeyboardInterrupt:
        logger.info("Interrupted.")
    except Exception:
        logger.exception("Unhandled exception in summarization pipeline")
        sys.exit(1)


if __name__ == "__main__":
    main()