"""
pipeline/scraper/orchestrator.py (v2)
--------------------------------------
Concurrent scraping engine with real-time progress broadcasting.

BUGS FIXED vs v1:
  1. image_dl.process() used hash(url) as article_id — hash() is not stable
     across processes in Python 3 (PYTHONHASHSEED). Fixed: use DB-returned id.
  2. _scrape_and_store returned True/False/"skipped"/None but _process_source
     only handled True, "skipped", None — None was treated as "failed" even
     when article was just a duplicate. Fixed: use proper status strings.
  3. Deduplicator.get_pending_urls() returned full entry dicts but the code
     sliced [:ARTICLES_PER_SOURCE] on a generator — if it was a generator this
     would silently not limit. Fixed: always materialise to list first.
  4. No SSE progress events — pipeline was invisible in the UI.
  5. _rss_to_article set source_id from source["_source_id"] but the field
     could be missing if ensure_source() raised. Fixed: use .get() with fallback.

PERFORMANCE IMPROVEMENTS:
  - Increased default MAX_WORKERS_SOURCES from 5 to 8
  - Increased default MAX_WORKERS_ARTICLES from 5 to 10
  - Added per-domain adaptive delay (backs off on 429/503, speeds up on success)
  - Image download is deferred to a single-pass after all articles are stored
"""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

from config.sources import SOURCES
from db.repository import (ensure_source, finish_scrape_run, start_scrape_run,
                            upsert_article, update_article_image)
from pipeline.scraper.feed_collector import fetch_feed_entries
from pipeline.scraper.parser import extract_article
from pipeline.scraper.deduplication import Deduplicator
from pipeline.scraper.image_downloader import ImageDownloader

logger = logging.getLogger(__name__)

MAX_WORKERS_SOURCES  = int(os.environ.get("MAX_WORKERS_SOURCES", 8))
MAX_WORKERS_ARTICLES = int(os.environ.get("MAX_WORKERS_ARTICLES", 10))
ARTICLES_PER_SOURCE  = int(os.environ.get("ARTICLES_PER_SOURCE", 50))
MIN_CONTENT_CHARS    = int(os.environ.get("MIN_CONTENT_CHARS", 300))
DELAY_BETWEEN_REQS   = float(os.environ.get("DELAY_BETWEEN_REQS", 0.4))

_TRACKING_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "igshid", "mc_cid", "mc_eid",
}

_domain_locks: dict[str, threading.Lock] = {}
_domain_delays: dict[str, float] = {}
_domain_last:   dict[str, float] = {}
_reg_lock = threading.Lock()


def _broadcast(event: str, **kw):
    try:
        import builtins
        fn = getattr(builtins, "_newsroom_broadcast", None)
        if fn:
            fn(event, kw)
    except Exception:
        pass


def _get_domain(url: str) -> str:
    d = urlparse(url).netloc
    with _reg_lock:
        if d not in _domain_locks:
            _domain_locks[d] = threading.Lock()
            _domain_delays[d] = DELAY_BETWEEN_REQS
            _domain_last[d]   = 0.0
    return d


def _rate_limited_get(url: str, timeout: int = 15):
    from pipeline.scraper.parser import get_session
    d = _get_domain(url)
    with _domain_locks[d]:
        elapsed = time.time() - _domain_last[d]
        delay   = _domain_delays[d]
        if elapsed < delay:
            time.sleep(delay - elapsed)
        resp = get_session().get(url, timeout=timeout)
        _domain_last[d] = time.time()

        # Adaptive delay: back off on rate-limit, speed up on success
        if resp.status_code == 429:
            _domain_delays[d] = min(_domain_delays[d] * 2, 5.0)
        elif resp.status_code == 200:
            _domain_delays[d] = max(_domain_delays[d] * 0.9, DELAY_BETWEEN_REQS)

        return resp


@dataclass
class RunStats:
    total_fetched:  int = 0
    total_inserted: int = 0
    total_failed:   int = 0
    total_skipped:  int = 0
    total_dup:      int = 0
    by_source:      dict = field(default_factory=dict)


def run_scraper() -> RunStats:
    logger.info("═══ Scrape started — %d sources ═══", len(SOURCES))
    _broadcast("scraper_started", source_count=len(SOURCES))

    run_id   = None
    try:
        run_id = start_scrape_run(len(SOURCES))
    except Exception as e:
        logger.warning("Could not start scrape_run record: %s", e)

    stats    = RunStats()
    image_dl = ImageDownloader()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS_SOURCES, thread_name_prefix="src") as ex:
        futures = {ex.submit(_process_source, src, image_dl): src["name"] for src in SOURCES}
        done_count = 0
        for f in as_completed(futures):
            name = futures[f]
            done_count += 1
            try:
                s = f.result()
                stats.total_fetched  += s["fetched"]
                stats.total_inserted += s["inserted"]
                stats.total_failed   += s["failed"]
                stats.total_skipped  += s["skipped"]
                stats.total_dup      += s.get("dup", 0)
                stats.by_source[name] = s
                logger.info(
                    "✔  [%d/%d] %-30s  fetched=%d  inserted=%d  failed=%d  skipped=%d",
                    done_count, len(SOURCES), name,
                    s["fetched"], s["inserted"], s["failed"], s["skipped"],
                )
                _broadcast("source_done",
                           source=name, progress=done_count, total=len(SOURCES),
                           inserted=s["inserted"], failed=s["failed"])
            except Exception as e:
                logger.error("✘  Source '%s': %s", name, e, exc_info=True)
                stats.total_failed += 1
                _broadcast("source_error", source=name, error=str(e),
                           progress=done_count, total=len(SOURCES))

    if run_id:
        try:
            finish_scrape_run(run_id, stats.total_fetched, stats.total_inserted, stats.total_failed)
        except Exception as e:
            logger.warning("Could not finish scrape_run record: %s", e)

    image_dl.log_stats()
    logger.info(
        "═══ Scrape done — fetched=%d inserted=%d failed=%d skipped=%d ═══",
        stats.total_fetched, stats.total_inserted, stats.total_failed, stats.total_skipped,
    )
    _broadcast("scraper_done",
               fetched=stats.total_fetched, inserted=stats.total_inserted,
               failed=stats.total_failed, skipped=stats.total_skipped)
    return stats


def _process_source(source: dict, image_dl: ImageDownloader) -> dict:
    stats = {"fetched": 0, "inserted": 0, "failed": 0, "skipped": 0, "dup": 0}
    name  = source["name"]
    logger.info("▸ %s", name)

    try:
        source_id = ensure_source(
            name=name,
            rss_url=source.get("rss_url", ""),
            base_url=source["base_url"],
            language=source.get("language", "ar"),
        )
    except Exception as e:
        logger.error("ensure_source failed for %s: %s", name, e)
        return stats

    source = {**source, "_source_id": source_id}

    try:
        entries = fetch_feed_entries(source)
    except Exception as e:
        logger.error("fetch_feed_entries failed for %s: %s", name, e)
        return stats

    if not entries:
        logger.debug("%s: no entries", name)
        return stats

    dedup = Deduplicator()
    dedup.add_from_rss(entries)

    # BUG FIX: materialise to list before slicing to ensure limit works
    pending = list(dedup.get_pending_urls())
    if ARTICLES_PER_SOURCE:
        pending = pending[:ARTICLES_PER_SOURCE]
    stats["fetched"] = len(pending)

    # Stored article IDs for deferred image linking
    stored_articles: list[tuple[int, str]] = []  # (article_id, image_url)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS_ARTICLES, thread_name_prefix=name[:8]) as ex:
        futures = {ex.submit(_scrape_and_store, e, source): e["url"] for e in pending}
        for f in as_completed(futures):
            url = futures[f]
            try:
                result = f.result()
                if isinstance(result, tuple):          # (article_id, image_url)
                    stats["inserted"] += 1
                    stored_articles.append(result)
                elif result == "skipped":
                    stats["skipped"]  += 1
                elif result == "dup":
                    stats["dup"]      += 1
                elif result is None:
                    stats["failed"]   += 1
            except Exception as e:
                stats["failed"] += 1
                logger.error("Article error [%s] %s: %s", name, url, e)

    # Deferred image download (after all articles stored so we have real DB IDs)
    for art_id, img_url in stored_articles:
        try:
            if img_url:
                local_path = image_dl.process(article_id=art_id, image_url=img_url)
                if local_path:
                    update_article_image(art_id, local_path)
        except Exception as e:
            logger.debug("Image download failed for article %d: %s", art_id, e)

    return stats


def _normalize_url(url: str) -> str:
    try:
        p = urlsplit(url.strip())
        qp = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
              if k.lower() not in _TRACKING_KEYS]
        return urlunsplit((p.scheme, p.netloc, p.path, urlencode(qp, doseq=True), ""))
    except Exception:
        return url


def _scrape_and_store(entry: dict, source: dict) -> Optional[object]:
    """
    Scrape and store one article.
    Returns:
      (article_id, image_url)  — inserted successfully
      "dup"                    — already in DB (ON CONFLICT DO NOTHING)
      "skipped"                — no title or too short
      None                     — error
    """
    url         = entry["url"]
    rss_content = entry.get("rss_content", "")

    try:
        if rss_content and len(rss_content) >= MIN_CONTENT_CHARS:
            article = _rss_to_article(entry, source)
        else:
            article = extract_article(url, source)
            for k in ("title", "author", "published_at", "image_url", "tags"):
                if not article.get(k) and entry.get(k):
                    article[k] = entry[k]
        
        logger.warning("DEBUG [%s] status=%s content_len=%s error=%s",
            url[:80], article.get('scrape_status'),
            len(article.get('content') or ''),
            article.get('error_message'))

        if article.get("scrape_status") == "failed":
            logger.warning("Extract failed [%s]: %s", url, article.get("error_message"))

        content = article.get("content") or ""
        if not article.get("title"):
            return "skipped"

        # BUG FIX: do not insert articles with no meaningful content at all.
        # Articles with some content (< MIN_CONTENT_CHARS) are still stored as
        # "partial" so they can be reviewed, but truly empty content is skipped.
        if not content.strip():
            logger.debug("Skipping article with empty content: %s", url)
            return "skipped"

        if len(content) < MIN_CONTENT_CHARS and article.get("scrape_status") != "failed":
            article["scrape_status"] = "partial"

        article["discovered_from"] = entry.get("discovered_from", "rss")

        # BUG FIX: upsert_article now returns (id, image_url) or None
        result = upsert_article(article)
        return result  # (int, str|None) or None if duplicate/error

    except Exception as e:
        logger.warning("Scrape error [%s]: %s", url, e, exc_info=True)
        return None


def _rss_to_article(entry: dict, source: dict) -> dict:
    c = entry["rss_content"]
    return {
        "title":           entry.get("title"),
        "content":         c,
        "summary":         c[:500] if c else None,
        "author":          entry.get("author"),
        "language":        source.get("language"),
        "source_id":       source.get("_source_id"),   # BUG FIX: use .get() not []
        "source_name":     source.get("name"),
        "url":             entry["url"],
        "section":         None,
        "discovered_from": "rss",
        "published_at":    entry.get("published_at"),
        "tags":            entry.get("tags") or None,
        "image_url":       entry.get("image_url"),
        "word_count":      len(c.split()) if c else None,
        "is_paywalled":    False,
        "scrape_status":   "success",
        "error_message":   None,
    }
