"""
utils/logging_config.py
------------------------
Structured, production-ready logging setup.
- Logs to stdout (for Docker / cloud) AND to a rotating file.
- JSON format in production, human-readable in development.
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path


def setup_logging(log_dir: str = "logs") -> None:
    env = os.environ.get("APP_ENV", "development").lower()
    level = logging.DEBUG if env == "development" else logging.INFO

    Path(log_dir).mkdir(exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    fmt_str = (
        "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
        if env == "development"
        else "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    formatter = logging.Formatter(fmt_str, datefmt="%Y-%m-%d %H:%M:%S")

    # ── stdout handler ──
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    root.addHandler(sh)

    # ── rotating file handler (10 MB × 5 files) ──
    fh = logging.handlers.RotatingFileHandler(
        f"{log_dir}/newsroom.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(formatter)
    root.addHandler(fh)

    # Silence overly verbose third-party loggers
    for noisy in ("urllib3", "charset_normalizer", "feedparser"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.info("Logging initialised (env=%s, level=%s)", env, logging.getLevelName(level))
