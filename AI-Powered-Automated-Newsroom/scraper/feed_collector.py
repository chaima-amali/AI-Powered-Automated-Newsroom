"""
scraper/feed_collector.py
--------------------------
Fetch RSS/Atom entries for a single source.
Returns a list of raw feed entries (dicts with title, link, published, etc.)
Does NOT hit article URLs — that is the parser's job.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import feedparser

logger = logging.getLogger(__name__)

# feedparser is synchronous but very fast for feed XML — no need to async it.

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

        entries = []
        for entry in feed.entries:
            link = entry.get("link") or entry.get("id")
            if not link:
                continue

            title = entry.get("title", "").strip() or None

            # RSS inline content (some feeds embed full HTML)
            rss_content = None
            if "content" in entry and entry.content:
                from bs4 import BeautifulSoup
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
                "rss_content":  rss_content,   # may replace scraping if long enough
                "author":       entry.get("author"),
                "tags":         [t.term for t in entry.get("tags", [])],
                "image_url":    _entry_image(entry),
            })

        logger.info("Feed '%s': %d entries", source["name"], len(entries))
        return entries

    except Exception as e:
        logger.error("Failed to fetch feed '%s' (%s): %s", source["name"], rss_url, e)
        return []


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
