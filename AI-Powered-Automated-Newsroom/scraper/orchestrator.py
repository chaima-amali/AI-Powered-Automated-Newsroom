"""
scraper/orchestrator.py
------------------------
Concurrent scraping engine.

Architecture:
  - One ThreadPoolExecutor per source (I/O-bound → threads beat asyncio here)
  - Feed fetching + article scraping happen in parallel across all sources
  - Rate limiting per domain to be polite to servers
  - Retry with exponential backoff on transient failures (in parser.py session)
  - Progress tracking + final stats report

FIXES applied vs original:
  - FIX 1: Real per-domain rate limiting via a lock + timestamp dictionary.
            The original time.sleep() was per-thread and provided no real
            throttling when many threads ran simultaneously.
  - FIX 2: source dict is no longer mutated in place. A local copy is made
            with {**source, "_source_id": ...} to avoid a thread data race
            on the shared SOURCES list.
  - FIX 3: Added `total_skipped` counter to RunStats so title-less articles
            are not counted as failures — they are distinguishable skips.
  - ENHANCEMENT: Safer MAX_WORKERS defaults (5×5=25 instead of 10×15=150)
                 to avoid IP bans on first run. Scale up after testing.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunsplit, urlsplit

from config.sources import SOURCES
from db.repository import (
    ensure_source,
    finish_scrape_run,
    start_scrape_run,
    upsert_article,
)
from scraper.feed_collector import fetch_feed_entries
from scraper.parser import extract_article

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
# ENHANCEMENT: Reduced from 10×15=150 to 5×5=25 concurrent connections.
# 150 simultaneous requests is very likely to trigger IP bans on shared hosts.
# Scale these up gradually once you've confirmed your sources don't block you.
MAX_WORKERS_SOURCES  = 5        # parallel sources
MAX_WORKERS_ARTICLES = 5        # parallel article fetches *per source*
ARTICLES_PER_SOURCE  = 50       # max articles to process per run (None = unlimited)
MIN_CONTENT_CHARS    = 300      # skip articles shorter than this (ads/stubs)
DELAY_BETWEEN_REQS   = 0.5      # seconds between requests to the same domain

# URL tracking parameters that do not identify article identity.
_TRACKING_QUERY_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "igshid", "mc_cid", "mc_eid",
}


# ── FIX 1: Real per-domain rate limiting ──────────────────────────────────────
# Original code just did time.sleep() inside each thread which provided zero
# real throttling — all threads sleep simultaneously then all fire at once.
# This implementation uses a per-domain lock so only ONE request per domain
# runs at a time, with a genuine minimum gap between them.
_domain_locks: dict[str, threading.Lock] = {}
_domain_last_req: dict[str, float] = {}
_registry_lock = threading.Lock()


def _get_domain_lock(url: str) -> str:
    """Register a domain and return its key. Thread-safe."""
    domain = urlparse(url).netloc
    with _registry_lock:
        if domain not in _domain_locks:
            _domain_locks[domain] = threading.Lock()
            _domain_last_req[domain] = 0.0
    return domain


def _rate_limited_get(url: str, timeout: int = 15):
    """
    Fetch a URL with real per-domain rate limiting.
    At most one request per domain runs at a time, with DELAY_BETWEEN_REQS
    enforced between consecutive calls to the same host.
    """
    from scraper.parser import get_session
    domain = _get_domain_lock(url)
    with _domain_locks[domain]:
        elapsed = time.time() - _domain_last_req[domain]
        wait = DELAY_BETWEEN_REQS - elapsed
        if wait > 0:
            time.sleep(wait)
        resp = get_session().get(url, timeout=timeout)
        _domain_last_req[domain] = time.time()
        return resp


# ── Stats container ────────────────────────────────────────────────────────────
@dataclass
class RunStats:
    total_fetched:  int = 0
    total_inserted: int = 0
    total_failed:   int = 0
    total_skipped:  int = 0          # FIX 3: new — title-less / too-short articles
    by_source:      dict = field(default_factory=dict)


# ── Entry point ────────────────────────────────────────────────────────────────

def run_scraper() -> RunStats:
    """
    Main entry point. Scrape all sources concurrently.
    Returns aggregated RunStats.

    Concurrent Architecture:
      - All sources are scraped SIMULTANEOUSLY (max MAX_WORKERS_SOURCES at once)
      - Within each source, articles are scraped in PARALLEL (max MAX_WORKERS_ARTICLES)
      - Real per-domain throttling prevents IP bans
    """
    logger.info("═══ Scrape run started — %d sources (scraping CONCURRENTLY) ═══", len(SOURCES))
    logger.info(
        "Parallelism: %d sources × %d articles per source = %d max concurrent requests",
        MAX_WORKERS_SOURCES, MAX_WORKERS_ARTICLES, MAX_WORKERS_SOURCES * MAX_WORKERS_ARTICLES,
    )
    run_id = start_scrape_run(len(SOURCES))
    stats  = RunStats()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS_SOURCES, thread_name_prefix="src") as executor:
        futures = {
            executor.submit(_process_source, source): source["name"]
            for source in SOURCES
        }

        logger.info("✓ Submitted %d sources for SIMULTANEOUS processing", len(futures))

        for future in as_completed(futures):
            source_name = futures[future]
            try:
                src_stats = future.result()
                stats.total_fetched  += src_stats["fetched"]
                stats.total_inserted += src_stats["inserted"]
                stats.total_failed   += src_stats["failed"]
                stats.total_skipped  += src_stats["skipped"]  # FIX 3
                stats.by_source[source_name] = src_stats
                logger.info(
                    "✔  %-30s  fetched=%d  inserted=%d  failed=%d  skipped=%d",
                    source_name,
                    src_stats["fetched"],
                    src_stats["inserted"],
                    src_stats["failed"],
                    src_stats["skipped"],
                )
            except Exception as exc:
                logger.error(
                    "✘  Source '%s' raised an unhandled exception: %s",
                    source_name, exc, exc_info=True,
                )
                stats.total_failed += 1

    finish_scrape_run(
        run_id,
        fetched=stats.total_fetched,
        inserted=stats.total_inserted,
        failed=stats.total_failed,
    )

    logger.info(
        "═══ Scrape run complete — fetched=%d  inserted=%d  failed=%d  skipped=%d ═══",
        stats.total_fetched, stats.total_inserted, stats.total_failed, stats.total_skipped,
    )
    return stats


# ── Per-source processing ──────────────────────────────────────────────────────

def _process_source(source: dict) -> dict:
    """
    Full pipeline for one source:
      1. Ensure source exists in DB
      2. Fetch RSS feed entries
      3. Scrape each article URL concurrently (PARALLEL within source)
      4. Upsert to DB
    """
    source_name = source["name"]
    # FIX 3: added "skipped" key
    stats = {"fetched": 0, "inserted": 0, "failed": 0, "skipped": 0}

    logger.info("▸ Starting source: %s", source_name)

    source_id = ensure_source(
        name=source_name,
        rss_url=source.get("rss_url", ""),
        base_url=source["base_url"],
        language=source.get("language", "ar"),
    )

    # FIX 2: Never mutate the shared source dict — create a local copy.
    # Original code did `source["_source_id"] = source_id` which is a
    # thread data race when multiple sources run concurrently.
    source = {**source, "_source_id": source_id}

    # Fetch feed
    entries = fetch_feed_entries(source)
    if not entries:
        logger.warning("No entries from source '%s'", source_name)
        return stats

    if ARTICLES_PER_SOURCE:
        entries = entries[:ARTICLES_PER_SOURCE]

    # Remove duplicate article URLs from the feed window before processing.
    entries = _dedupe_entries(entries)

    stats["fetched"] = len(entries)
    logger.info(
        "  %s: Processing %d articles CONCURRENTLY (%d workers)",
        source_name, len(entries), MAX_WORKERS_ARTICLES,
    )

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS_ARTICLES,
        thread_name_prefix=f"{source_name[:8]}",
    ) as executor:
        futures = {
            executor.submit(_scrape_and_store, entry, source): entry["url"]
            for entry in entries
        }

        for future in as_completed(futures):
            url = futures[future]
            try:
                result = future.result()
                if result is True:
                    stats["inserted"] += 1
                elif result is False:
                    pass    # duplicate, already in DB
                elif result == "skipped":
                    # FIX 3: distinguish skipped from failed
                    stats["skipped"] += 1
                else:
                    stats["failed"] += 1
            except Exception as exc:
                stats["failed"] += 1
                logger.error("Article error [%s] %s: %s", source_name, url, exc)

    return stats


def _normalize_article_url(url: str) -> str:
    """Canonicalize URL to reduce duplicate variants of the same article."""
    try:
        parts = urlsplit(url.strip())
        query_pairs = [
            (k, v)
            for (k, v) in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in _TRACKING_QUERY_KEYS
        ]
        normalized_query = urlencode(query_pairs, doseq=True)
        # Keep scheme/netloc/path/query, drop fragment.
        return urlunsplit((parts.scheme, parts.netloc, parts.path, normalized_query, ""))
    except Exception:
        return url


def _dedupe_entries(entries: list[dict]) -> list[dict]:
    """Deduplicate feed entries by normalized URL while preserving order."""
    seen = set()
    unique_entries = []
    dropped = 0

    for entry in entries:
        raw_url = entry.get("url")
        if not raw_url:
            continue

        normalized_url = _normalize_article_url(raw_url)
        if normalized_url in seen:
            dropped += 1
            continue

        seen.add(normalized_url)
        if normalized_url != raw_url:
            entry = {**entry, "url": normalized_url}
        unique_entries.append(entry)

    if dropped:
        logger.info("Dropped %d duplicate feed URLs after normalization", dropped)

    return unique_entries


def _scrape_and_store(entry: dict, source: dict) -> Optional[bool]:
    """
    Scrape one article and upsert it.
    Returns True     = newly inserted
            False    = duplicate (already in DB)
            'skipped'= no title / too short — deliberately not counted as failure
            None     = unexpected failure
    """
    url = entry["url"]
    # FIX 1: rate limiting is now handled in _rate_limited_get() which uses
    # a per-domain lock. The old time.sleep() here had no effect because all
    # threads slept and fired simultaneously.

    rss_content = entry.get("rss_content", "")
    if rss_content and len(rss_content) >= MIN_CONTENT_CHARS:
        article = _rss_to_article(entry, source)
    else:
        article = extract_article(url, source)

        # merge RSS-level metadata that the scraper might have missed
        if not article["title"] and entry.get("title"):
            article["title"] = entry["title"]
        if not article["author"] and entry.get("author"):
            article["author"] = entry["author"]
        if not article["published_at"] and entry.get("published_at"):
            article["published_at"] = entry["published_at"]
        if not article["image_url"] and entry.get("image_url"):
            article["image_url"] = entry["image_url"]
        if not article["tags"] and entry.get("tags"):
            article["tags"] = entry["tags"]

    # Quality gate — mark stubs as partial
    content = article.get("content") or ""
    if len(content) < MIN_CONTENT_CHARS and article["scrape_status"] != "failed":
        article["scrape_status"] = "partial"

    # FIX 3: return "skipped" sentinel instead of None, so callers can track
    # these separately from real failures.
    if not article.get("title"):
        logger.debug("Skipping article with no title: %s", url)
        return "skipped"

    return upsert_article(article)


def _rss_to_article(entry: dict, source: dict) -> dict:
    """Build an article dict directly from RSS content (no HTTP request needed)."""
    content = entry["rss_content"]
    return {
        "title":         entry.get("title"),
        "content":       content,
        "summary":       content[:500] if content else None,
        "author":        entry.get("author"),
        "language":      source.get("language"),
        "source_id":     source.get("_source_id"),
        "source_name":   source.get("name"),
        "url":           entry["url"],
        "section":       None,
        "published_at":  entry.get("published_at"),
        "tags":          entry.get("tags") or None,
        "image_url":     entry.get("image_url"),
        "word_count":    len(content.split()) if content else None,
        "is_paywalled":  False,
        "scrape_status": "success",
        "error_message": None,
    }
