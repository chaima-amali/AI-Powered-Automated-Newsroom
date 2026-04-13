"""
scraper/feed_collector.py
--------------------------
Fetch RSS/Atom entries for a single source.
Returns a list of raw feed entries (dicts with title, link, published, etc.)
Does NOT hit article URLs — that is the parser's job.

FIXES applied vs original:
  - FIX 1: BeautifulSoup import moved to module top-level.
  - FIX 2: _resolve_google_url() is now actually CALLED inside the loop.
            The function existed before but was never used — Google News URLs
            were stored as-is (news.google.com/rss/articles/CBMi...)
            instead of being followed to the real article URL.
  - FIX 3: rss_content is now cleared for Google News entries.
            Google News RSS summary contains HTML fragments (img tags, etc.)
            that were being stored in the DB as raw HTML. Since we now resolve
            to the real article URL, we let the parser fetch clean content.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import feedparser
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# ── Google News URL resolver ───────────────────────────────────────────────────

def _resolve_google_url(url: str) -> str:
    """
    Google News RSS gives redirect URLs like:
      news.google.com/rss/articles/CBMiRkFV...

    These redirect to the real article on the newspaper's website.
    We follow the redirect chain to get the actual article URL so the
    parser can extract clean text from the real page.

    Example:
      IN:  https://news.google.com/rss/articles/CBMiRkFV...
      OUT: https://www.lesoirdalgerie.com/actualites/some-article-title
    """
    if "news.google.com" not in url:
        return url  # Not a Google URL — return unchanged

    try:
        resp = requests.get(
            url,
            timeout=10,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )
        real_url = resp.url
        # Only use the resolved URL if it actually left Google's domain
        if "news.google.com" not in real_url:
            logger.debug("Google URL resolved: %s → %s", url[:60], real_url[:80])
            return real_url
    except Exception as e:
        logger.debug("Could not resolve Google URL %s: %s", url[:60], e)

    return url  # Fallback: return original if resolution fails


# ── Main feed fetcher ──────────────────────────────────────────────────────────

def fetch_feed_entries(source: dict) -> list[dict]:
    """
    Parse an RSS feed and return normalised entry dicts.
    Empty list on failure (errors are logged, not raised — caller decides).
    """
    rss_url = source.get("rss_url")
    if not rss_url:
        logger.info("No RSS URL for '%s', skipping feed step", source["name"])
        return []

    try:
        feed = feedparser.parse(rss_url, agent="NewsroomAI/1.0")

        if feed.bozo and not feed.entries:
            logger.warning("Malformed feed for '%s': %s", source["name"], feed.bozo_exception)
            return []

        is_google_news = "news.google.com" in rss_url

        entries = []
        for entry in feed.entries:
            link = entry.get("link") or entry.get("id")
            if not link:
                continue

            # FIX 2: Actually resolve Google News redirect URLs to real article URLs
            if is_google_news:
                link = _resolve_google_url(link)

            title = entry.get("title", "").strip() or None

            # FIX 3: For Google News sources, do NOT use rss_content.
            # Google News RSS summaries contain raw HTML fragments (<img>, <p> tags)
            # that are NOT the full article — they are just a teaser snippet.
            # Since we now have the real article URL, let the parser fetch
            # clean content directly from the newspaper's website.
            rss_content = None
            if not is_google_news:
                if "content" in entry and entry.content:
                    html = entry.content[0].get("value", "")
                    rss_content = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
                elif "summary" in entry:
                    rss_content = entry.summary

            # Published date
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass

            entries.append({
                "title":        title,
                "url":          link,
                "published_at": published,
                "rss_content":  rss_content,
                "author":       entry.get("author"),
                "tags":         [t.term for t in entry.get("tags", [])],
                "image_url":    _entry_image(entry),
            })

        logger.info("Feed '%s': %d entries", source["name"], len(entries))
        return entries

    except Exception as e:
        logger.error("Failed to fetch feed '%s' (%s): %s", source["name"], rss_url, e)
        return []


# ── Image extractor helper ─────────────────────────────────────────────────────

def _entry_image(entry) -> Optional[str]:
    """Extract thumbnail/enclosure image from feed entry."""
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url")
    if hasattr(entry, "media_content") and entry.media_content:
        return entry.media_content[0].get("url")
    for enc in getattr(entry, "enclosures", []):
        if enc.get("type", "").startswith("image/"):
            return enc.get("href")
    return None