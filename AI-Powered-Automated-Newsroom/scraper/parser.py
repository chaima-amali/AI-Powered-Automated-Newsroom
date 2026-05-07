"""
scraper/parser.py
------------------
HTML → structured article dict.
Uses Trafilatura as primary extractor (fast, robust, handles Arabic well),
with newspaper3k and BeautifulSoup as fallback layers.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── HTTP session (shared, keep-alive) ─────────────────────────────────────────
_session: Optional[requests.Session] = None

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
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
    return _session


# ── Core extractor ─────────────────────────────────────────────────────────────

def extract_article(url: str, source_config: dict) -> dict:
    """
    Download and parse an article page.
    Returns a dict ready for upsert_article().
    
    Extraction strategy:
      1. Trafilatura (primary - fast, robust, great Arabic support)
      2. newspaper3k (fallback if Trafilatura fails)
      3. BeautifulSoup with selectors (last resort)
    """
    result = _empty_article(url, source_config)

    try:
        # ── 1. Try Trafilatura (BEST - actively maintained, great extraction) ──
        try:
            import trafilatura
            
            resp = get_session().get(url, timeout=15)
            resp.raise_for_status()
            
            # Extract with metadata
            extracted = trafilatura.extract(
                resp.text,
                include_comments=False,
                include_tables=True,
                output_format='json',
                url=url
            )
            
            if extracted:
                import json
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

        # ── 2. Try newspaper3k (fallback) ──
        try:
            from newspaper import Article as NpArticle

            np_article = NpArticle(url, language=source_config.get("language", "ar"))
            np_article.download()
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

        # ── 3. BeautifulSoup fallback ──────────────────────────────────────
        if 'resp' not in locals():
            resp = get_session().get(url, timeout=15)
            resp.raise_for_status()
            
        soup = BeautifulSoup(resp.text, "html.parser")

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

        result["content"]      = content_text
        result["scrape_status"] = "success" if content_text else "partial"

        # try to pick up author from meta tags
        if not result["author"]:
            result["author"] = _meta_author(soup)

        # try published date from meta tags
        if not result["published_at"]:
            result["published_at"] = _meta_date(soup)

        if content_text:
            result["word_count"] = len(content_text.split())

    except requests.exceptions.HTTPError as e:
        result["scrape_status"] = "failed"
        result["error_message"] = f"HTTP {e.response.status_code}"
        logger.warning("HTTP error scraping %s: %s", url, e)

    except requests.exceptions.Timeout:
        result["scrape_status"] = "failed"
        result["error_message"] = "Timeout"
        logger.warning("Timeout scraping %s", url)

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
        from dateutil import parser as dp
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
                from dateutil import parser as dp
                return dp.parse(tag["content"])
            except Exception:
                pass
    return None


def _infer_section(url: str) -> Optional[str]:
    """Try to extract section from URL path, e.g. /politique/... → politique"""
    path = urlparse(url).path.strip("/")
    parts = [p for p in path.split("/") if p and len(p) > 2 and not p.isdigit()]
    return parts[0] if parts else None
