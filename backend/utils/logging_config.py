"""
utils/logging_config.py (v2)
-----------------------------
Structured logging with:
  - Console output with color-coded levels
  - File handler rotating at 10 MB
  - Pipeline stage markers visible in logs
  - Optional JSON output for log aggregation

IMPROVEMENTS vs v1:
  1. Added rotating file handler (was single-file, could grow unbounded)
  2. Added color support on terminal for easier reading
  3. Silenced more noisy libraries (httpx, PIL, urllib3)
  4. Added structured_log() helper for machine-readable pipeline events
"""
import json
import logging
import logging.handlers
import os
import sys
import time
from pathlib import Path


# ── ANSI colors ───────────────────────────────────────────────────────────────
_COLORS = {
    "DEBUG":    "\033[90m",   # grey
    "INFO":     "\033[37m",   # white
    "WARNING":  "\033[33m",   # yellow
    "ERROR":    "\033[31m",   # red
    "CRITICAL": "\033[35m",   # magenta
}
_RESET = "\033[0m"
_BOLD  = "\033[1m"


class _ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, "")
        msg   = super().format(record)
        return f"{color}{msg}{_RESET}"


def setup_logging(level: str | None = None) -> None:
    log_level = level or os.environ.get("LOG_LEVEL", "INFO").upper()
    log_dir   = Path("logs")
    log_dir.mkdir(exist_ok=True)

    fmt       = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    date_fmt  = "%Y-%m-%d %H:%M:%S"

    # Console handler with colors
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_ColorFormatter(fmt=fmt, datefmt=date_fmt))

    # Rotating file handler — 10 MB per file, keep 5 files
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "pipeline.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=date_fmt))

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        handlers=[console, file_handler],
        force=True,
    )

    # Silence noisy libraries
    for lib in (
        "httpx", "httpcore", "urllib3", "filelock",
        "transformers", "sentence_transformers",
        "apscheduler.scheduler", "PIL", "matplotlib",
    ):
        logging.getLogger(lib).setLevel(logging.WARNING)

    logging.getLogger("pipeline").info("Logging initialized — level=%s", log_level)


def stage_banner(stage: str, action: str = "start") -> None:
    """Print a prominent stage separator to the terminal."""
    symbol = "▶" if action == "start" else "✅" if action == "done" else "❌"
    sep    = "═" * 60
    msg    = f"{symbol} STAGE [{stage.upper()}] {action.upper()}"
    logger = logging.getLogger("pipeline.stage")
    logger.info(sep)
    logger.info(msg)
    logger.info(sep)


def structured_log(stage: str, event: str, **kwargs) -> None:
    """
    Emit a machine-readable JSON log line for external log aggregators.
    Also triggers the SSE broadcaster if available.
    """
    payload = {
        "ts": time.time(),
        "stage": stage,
        "event": event,
        **kwargs,
    }
    logging.getLogger(f"pipeline.{stage}").info("EVENT %s", json.dumps(payload, ensure_ascii=False))

    # Broadcast to SSE if registered
    try:
        import builtins
        fn = getattr(builtins, "_newsroom_broadcast", None)
        if fn:
            fn(event, payload)
    except Exception:
        pass
