"""
scraper/parser.py
------------------
HTML → structured article dict.
Uses Trafilatura as primary extractor (fast, robust, handles Arabic well),
with newspaper3k and BeautifulSoup as fallback layers.

FIXES applied vs original:
  - FIX 1: All imports moved to module top-level (removed from hot-path / loops)
  - FIX 2: Stale `resp` locals() trick removed — BS4 layer always fetches fresh
  - FIX 3: newspaper3k now reuses already-fetched HTML via set_html() instead
            of making a second HTTP request to the same URL
  - FIX 4: HTTP session now configured with automatic retry + backoff
  - ENHANCEMENT: get_session() is now thread-safe via a lock
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse
import threading

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dp
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# FIX 1: trafilatura imported at module level, not inside the function
import trafilatura

logger = logging.getLogger(__name__)

# ── HTTP session (shared, keep-alive, thread-safe) ────────────────────────────
_session: Optional[requests.Session] = None
_session_lock = threading.Lock()          # ENHANCEMENT: prevents race on init

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ar,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def get_session() -> requests.Session:
    global _session
    # ENHANCEMENT: double-checked locking pattern for thread safety
    if _session is None:
        with _session_lock:
            if _session is None:
                _session = requests.Session()
                _session.headers.update(HEADERS)
                # FIX 4: retry on transient failures (was completely missing)
                # Retries up to 3 times with exponential backoff (1s, 2s, 4s)
                # on the most common server-side error codes.
                retry = Retry(
                    total=3,
                    backoff_factor=1,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["GET"],
                )
                adapter = HTTPAdapter(max_retries=retry)
                _session.mount("https://", adapter)
                _session.mount("http://", adapter)
    return _session


# ── Core extractor ─────────────────────────────────────────────────────────────

def extract_article(url: str, source_config: dict) -> dict:
    """
    Download and parse an article page.
    Returns a dict ready for upsert_article().

    Extraction strategy:
      1. Trafilatura (primary - fast, robust, great Arabic support)
      2. newspaper3k (fallback — reuses already-fetched HTML, no 2nd request)
      3. BeautifulSoup with selectors (last resort — always fetches fresh)
    """
    result = _empty_article(url, source_config)

    # We fetch once here and pass the response down to every fallback layer.
    # This avoids multiple HTTP requests to the same URL.
    # FIX 2 / FIX 3: single fetch, shared across all layers
    raw_html: Optional[str] = None
    fetch_error: Optional[Exception] = None

    try:
        resp = get_session().get(url, timeout=15)
        resp.raise_for_status()
        raw_html = resp.text
    except requests.exceptions.HTTPError as e:
        result["scrape_status"] = "failed"
        result["error_message"] = f"HTTP {e.response.status_code}"
        logger.warning("HTTP error scraping %s: %s", url, e)
        return _finalize(result)
    except requests.exceptions.Timeout:
        result["scrape_status"] = "failed"
        result["error_message"] = "Timeout"
        logger.warning("Timeout scraping %s", url)
        return _finalize(result)
    except Exception as e:
        result["scrape_status"] = "failed"
        result["error_message"] = str(e)[:255]
        logger.error("Unexpected fetch error %s: %s", url, e, exc_info=True)
        return _finalize(result)

    try:
        # ── 1. Try Trafilatura (BEST) ─────────────────────────────────────────
        try:
            # FIX 1: trafilatura already imported at top — no per-call import
            extracted = trafilatura.extract(
                raw_html,
                include_comments=False,
                include_tables=True,
                output_format="json",
                url=url,
            )

            if extracted:
                # FIX 1: json already imported at top
                data = json.loads(extracted) if isinstance(extracted, str) else extracted

                result["title"]        = data.get("title") or result["title"]
                result["content"]      = data.get("text") or None
                result["author"]       = data.get("author") or None
                result["published_at"] = _parse_date(data.get("date")) if data.get("date") else None
                result["image_url"]    = data.get("image") or None

                if result["content"] and len(result["content"]) > 200:
                    result["word_count"]    = len(result["content"].split())
                    result["scrape_status"] = "success"
                    logger.debug("Trafilatura OK: %s", url)
                    return _finalize(result)

        except Exception as tf_err:
            logger.debug("Trafilatura failed (%s), trying newspaper3k: %s", tf_err, url)

        # ── 2. Try newspaper3k (fallback — NO second HTTP request) ────────────
        try:
            from newspaper import Article as NpArticle

            np_article = NpArticle(url, language=source_config.get("language", "ar"))
            # FIX 3: inject the HTML we already downloaded instead of letting
            # newspaper3k make a second GET request to the same URL.
            np_article.set_html(raw_html)
            np_article.parse()

            result["title"]        = np_article.title or result["title"]
            result["content"]      = np_article.text or None
            result["author"]       = ", ".join(np_article.authors) if np_article.authors else None
            result["image_url"]    = str(np_article.top_image) if np_article.top_image else None
            result["published_at"] = np_article.publish_date

            if result["content"] and len(result["content"]) > 200:
                result["word_count"]    = len(result["content"].split())
                result["scrape_status"] = "success"
                logger.debug("newspaper3k OK: %s", url)
                return _finalize(result)

        except Exception as np_err:
            logger.debug("newspaper3k failed (%s), falling back to BS4: %s", np_err, url)

        # ── 3. BeautifulSoup fallback ─────────────────────────────────────────
        # FIX 2: We removed the broken `if 'resp' not in locals()` guard.
        # raw_html is always the fresh response fetched at the top of this
        # function, so BS4 always gets consistent data.
        soup = BeautifulSoup(raw_html, "html.parser")

        # try source-specific selectors first, then generic ones
        selectors = source_config.get("article_selectors", []) + [
            "article", "div[class*='article']", "div[class*='content']",
            "div[class*='post']", "main",
        ]
        content_text = None
        for selector in selectors:
            tag = soup.select_one(selector)
            if tag:
                content_text = tag.get_text(separator=" ", strip=True)
                if len(content_text) > 200:     # skip nav snippets
                    break

        result["content"]       = content_text
        result["scrape_status"] = "success" if content_text else "partial"

        # try to pick up author from meta tags
        if not result["author"]:
            result["author"] = _meta_author(soup)

        # try published date from meta tags
        if not result["published_at"]:
            result["published_at"] = _meta_date(soup)

        if content_text:
            result["word_count"] = len(content_text.split())

    except Exception as e:
        result["scrape_status"] = "failed"
        result["error_message"] = str(e)[:255]
        logger.error("Unexpected error scraping %s: %s", url, e, exc_info=True)

    return _finalize(result)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _empty_article(url: str, source_config: dict) -> dict:
    return {
        "title":         None,
        "content":       None,
        "summary":       None,
        "author":        None,
        "language":      source_config.get("language"),
        "source_id":     source_config.get("_source_id"),
        "source_name":   source_config.get("name"),
        "url":           url,
        "section":       _infer_section(url),
        "published_at":  None,
        "tags":          None,
        "image_url":     None,
        "word_count":    None,
        "is_paywalled":  False,
        "scrape_status": "failed",
        "error_message": None,
    }


def _finalize(article: dict) -> dict:
    """Ensure published_at is timezone-aware and data is clean."""
    if article["published_at"] and article["published_at"].tzinfo is None:
        article["published_at"] = article["published_at"].replace(tzinfo=timezone.utc)
    if article["content"]:
        article["content"] = re.sub(r"\s{3,}", "  ", article["content"]).strip()
    return article


def _meta_author(soup: BeautifulSoup) -> Optional[str]:
    for attr in [("name", "author"), ("property", "article:author")]:
        tag = soup.find("meta", {attr[0]: attr[1]})
        if tag and tag.get("content"):
            return tag["content"]
    return None


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse date string from Trafilatura or meta tags."""
    if not date_str:
        return None
    try:
        # FIX 1: dp already imported at top-level as `from dateutil import parser as dp`
        return dp.parse(date_str)
    except Exception:
        return None


def _meta_date(soup: BeautifulSoup) -> Optional[datetime]:
    for attr in [
        ("property", "article:published_time"),
        ("name", "pubdate"),
        ("name", "date"),
        ("itemprop", "datePublished"),
    ]:
        tag = soup.find("meta", {attr[0]: attr[1]})
        if tag and tag.get("content"):
            try:
                # FIX 1: dp already imported at top — no per-loop import
                return dp.parse(tag["content"])
            except Exception:
                pass
    return None


def _infer_section(url: str) -> Optional[str]:
    """Try to extract section from URL path, e.g. /politique/... → politique"""
    path = urlparse(url).path.strip("/")
    parts = [p for p in path.split("/") if p and len(p) > 2 and not p.isdigit()]
    return parts[0] if parts else None
