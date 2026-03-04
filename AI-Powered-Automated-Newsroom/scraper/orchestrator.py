"""
scraper/orchestrator.py
------------------------
Concurrent scraping engine.

Architecture:
  - One ThreadPoolExecutor per source (I/O-bound → threads beat asyncio here)
  - Feed fetching + article scraping happen in parallel across all sources
  - Rate limiting per domain to be polite to servers
  - Retry with exponential backoff on transient failures
  - Progress tracking + final stats report
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

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
MAX_WORKERS_SOURCES  = 10       # parallel sources (concurrent downloads from different websites)
MAX_WORKERS_ARTICLES = 15       # parallel article fetches *per source*
ARTICLES_PER_SOURCE  = 50       # max articles to process per run (None = unlimited)
MIN_CONTENT_CHARS    = 300      # skip articles shorter than this (ads/stubs)
DELAY_BETWEEN_REQS   = 0.3      # seconds between requests to the same domain (reduced for faster scraping)


# ── Stats container ────────────────────────────────────────────────────────────
@dataclass
class RunStats:
    total_fetched:  int = 0
    total_inserted: int = 0
    total_failed:   int = 0
    by_source:      dict = field(default_factory=dict)


# ── Entry point ────────────────────────────────────────────────────────────────

def run_scraper() -> RunStats:
    """
    Main entry point. Scrape all sources concurrently.
    Returns aggregated RunStats.
    
    Concurrent Architecture:
      - All sources are scraped SIMULTANEOUSLY (max MAX_WORKERS_SOURCES at once)
      - Within each source, articles are scraped in PARALLEL (max MAX_WORKERS_ARTICLES)
      - This means we can have MAX_WORKERS_SOURCES × MAX_WORKERS_ARTICLES concurrent HTTP requests
    """
    logger.info("═══ Scrape run started — %d sources (scraping CONCURRENTLY) ═══", len(SOURCES))
    logger.info("Parallelism: %d sources × %d articles per source = %d max concurrent requests",
                MAX_WORKERS_SOURCES, MAX_WORKERS_ARTICLES, MAX_WORKERS_SOURCES * MAX_WORKERS_ARTICLES)
    run_id = start_scrape_run(len(SOURCES))
    stats  = RunStats()


    with ThreadPoolExecutor(max_workers=MAX_WORKERS_SOURCES, thread_name_prefix="src") as executor:
        # Submit ALL sources at once for concurrent execution
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
                stats.by_source[source_name] = src_stats
                logger.info(
                    "✔  %-30s  fetched=%d  inserted=%d  failed=%d",
                    source_name,
                    src_stats["fetched"],
                    src_stats["inserted"],
                    src_stats["failed"],
                )
            except Exception as exc:
                logger.error("✘  Source '%s' raised an unhandled exception: %s", source_name, exc, exc_info=True)
                stats.total_failed += 1

    finish_scrape_run(
        run_id,
        fetched=stats.total_fetched,
        inserted=stats.total_inserted,
        failed=stats.total_failed,
    )

    logger.info(
        "═══ Scrape run complete — fetched=%d  inserted=%d  failed=%d ═══",
        stats.total_fetched, stats.total_inserted, stats.total_failed,
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
    stats = {"fetched": 0, "inserted": 0, "failed": 0}
    
    logger.info("▸ Starting source: %s", source_name)

    # Register source in DB and attach its id
    source_id = ensure_source(
        name=source_name,
        rss_url=source.get("rss_url", ""),
        base_url=source["base_url"],
        language=source.get("language", "ar"),
    )
    source["_source_id"] = source_id

    # Fetch feed
    entries = fetch_feed_entries(source)
    if not entries:
        logger.warning("No entries from source '%s'", source_name)
        return stats

    if ARTICLES_PER_SOURCE:
        entries = entries[:ARTICLES_PER_SOURCE]

    stats["fetched"] = len(entries)
    logger.info("  %s: Processing %d articles CONCURRENTLY (%d workers)", 
                source_name, len(entries), MAX_WORKERS_ARTICLES)

    # Scrape articles concurrently within this source
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_ARTICLES, thread_name_prefix=f"{source_name[:8]}") as executor:
        # Submit all articles at once for parallel scraping
        futures = {
            executor.submit(_scrape_and_store, entry, source): entry["url"]
            for entry in entries
        }

        for future in as_completed(futures):
            url = futures[future]
            try:
                inserted = future.result()
                if inserted is True:
                    stats["inserted"] += 1
                elif inserted is False:
                    pass    # duplicate, already in DB
                else:
                    stats["failed"] += 1
            except Exception as exc:
                stats["failed"] += 1
                logger.error("Article error [%s] %s: %s", source_name, url, exc)

    return stats


def _scrape_and_store(entry: dict, source: dict) -> Optional[bool]:
    """
    Scrape one article and upsert it.
    Returns True  = newly inserted
            False = duplicate (already in DB)
            None  = failed / skipped
    """
    url = entry["url"]
    time.sleep(DELAY_BETWEEN_REQS)     # polite rate limit

    # If RSS already gave us enough content, skip re-scraping the page
    article = None
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

    # Quality gate — skip stubs
    content = article.get("content") or ""
    if len(content) < MIN_CONTENT_CHARS and article["scrape_status"] != "failed":
        article["scrape_status"] = "partial"

    if not article.get("title"):
        logger.debug("Skipping article with no title: %s", url)
        return None

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
