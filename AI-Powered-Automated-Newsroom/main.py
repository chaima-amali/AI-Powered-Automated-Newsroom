
import argparse
import logging
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()  # Load .env file before anything else

from db.connection import close_pool, init_pool
from scraper.orchestrator import run_scraper
from utils.logging_config import setup_logging


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(description="AI Newsroom — Web Scraper")
    parser.add_argument("--schedule", type=int, metavar="MINUTES",
                        help="Run repeatedly every N minutes (omit for one-shot run)")
    parser.add_argument("--sources", nargs="+", metavar="SOURCE",
                        help="Only run specific sources by name (partial match OK)")
    args = parser.parse_args()

    # Validate required env vars early
    required_env = ["DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST"]
    missing = [k for k in required_env if not os.environ.get(k)]
    if missing:
        logger.critical("Missing required environment variables: %s", ", ".join(missing))
        logger.critical("Copy .env.example → .env and fill in your credentials.")
        sys.exit(1)

    init_pool()

    # Filter sources if requested
    if args.sources:
        from config.sources import SOURCES
        import scraper.orchestrator as orch
        query = [s.lower() for s in args.sources]
        orch.SOURCES = [s for s in SOURCES if any(q in s["name"].lower() for q in query)]
        logger.info("Filtered to %d source(s): %s",
                    len(orch.SOURCES), [s["name"] for s in orch.SOURCES])

    try:
        if args.schedule:
            logger.info("Scheduler mode: running every %d minutes", args.schedule)
            while True:
                run_scraper()
                logger.info("Sleeping %d minutes until next run…", args.schedule)
                time.sleep(args.schedule * 60)
        else:
            run_scraper()
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        close_pool()


if __name__ == "__main__":
    main()
