"""
scraper/sitemap_collector.py
-----------------------------
Layer 2 of the discovery pipeline: News Sitemap (48h coverage).

Strategy:
  1. Try /news-sitemap.xml first (Google News Sitemap format)
  2. Fall back to /sitemap.xml and filter <news:publication_date> ≤ 48h
  3. Fall back to sitemap index → enumerate children → filter recent entries
  4. If all fail → return empty list (Layer 3 / category pages will compensate)

Design decisions:
  - Only articles with <news:publication_date> within last 48h are returned
  - Articles without a <news:publication_date> are SKIPPED (can't verify recency)
  - Malformed sitemaps are handled gracefully — errors logged, not raised
  - Multiple sitemap indexes are supported (recursive, up to depth=2)
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SITEMAP_TIMEOUT = 20          # seconds
MAX_SITEMAP_INDEX_DEPTH = 2   # prevent infinite recursion on nested indexes
WINDOW_HOURS = 48             # only articles published within this window


# ── Public entry point ─────────────────────────────────────────────────────────

def fetch_sitemap_urls(source: dict) -> list[dict]:
    """
    Return a list of recent article dicts from the source's news sitemap.
    Each dict: { url, title, published_at, keywords, discovered_from='sitemap' }

    Priority order:
      1. base_url/news-sitemap.xml
      2. base_url/sitemap.xml  (parse as news sitemap or index)
      3. Sitemap URLs declared in robots.txt
    """
    base_url = source["base_url"].rstrip("/")
    candidates = [
        f"{base_url}/news-sitemap.xml",
        f"{base_url}/sitemap.xml",
    ]

    # Also check robots.txt for Sitemap: directives
    robots_sitemaps = _parse_robots_sitemaps(base_url)
    candidates.extend(robots_sitemaps)

    # Deduplicate while preserving order
    seen = set()
    unique_candidates = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique_candidates.append(c)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)

    for sitemap_url in unique_candidates:
        entries = _try_sitemap(sitemap_url, cutoff, depth=0)
        if entries:
            logger.info(
                "Sitemap '%s': found %d recent articles from %s",
                source["name"], len(entries), sitemap_url,
            )
            for e in entries:
                e["discovered_from"] = "sitemap"
                e["source_name"] = source["name"]
                e["language"] = source.get("language", "ar")
            return entries

    logger.info("Sitemap '%s': no usable sitemap found, Layer 3 will compensate", source["name"])
    return []


# ── Sitemap fetcher ────────────────────────────────────────────────────────────

def _try_sitemap(url: str, cutoff: datetime, depth: int) -> list[dict]:
    """Fetch a sitemap URL, auto-detect type, return recent article entries."""
    if depth > MAX_SITEMAP_INDEX_DEPTH:
        logger.debug("Max sitemap index depth reached at %s", url)
        return []

    xml = _fetch_xml(url)
    if not xml:
        return []

    soup = BeautifulSoup(xml, "xml")

    # Detect sitemap index (contains <sitemap> tags with <loc>)
    if soup.find("sitemapindex") or soup.find("sitemap"):
        return _parse_sitemap_index(soup, cutoff, depth)

    # Otherwise treat as a URL set
    return _parse_urlset(soup, cutoff)


def _parse_sitemap_index(soup: BeautifulSoup, cutoff: datetime, depth: int) -> list[dict]:
    """
    Parse a sitemap index file.
    Only follow children that EITHER:
      a) have 'news' in their URL (likely news sitemaps), OR
      b) have a <lastmod> within the 48h window
    This avoids crawling massive archive sitemaps.
    """
    all_entries = []

    for sitemap_tag in soup.find_all("sitemap"):
        loc = sitemap_tag.find("loc")
        lastmod = sitemap_tag.find("lastmod")
        if not loc:
            continue

        child_url = loc.get_text(strip=True)

        # Filter: only follow recent or news-labeled sitemaps
        is_news_sitemap = "news" in child_url.lower()
        is_recent = False
        if lastmod:
            try:
                lm_date = _parse_date(lastmod.get_text(strip=True))
                is_recent = lm_date and lm_date >= cutoff
            except Exception:
                pass

        if is_news_sitemap or is_recent:
            child_entries = _try_sitemap(child_url, cutoff, depth + 1)
            all_entries.extend(child_entries)

    return all_entries


def _parse_urlset(soup: BeautifulSoup, cutoff: datetime) -> list[dict]:
    """
    Parse a URL set sitemap.
    For each <url>:
      - Extract <loc>, <news:publication_date> (or <lastmod>), <news:title>, <news:keywords>
      - Only include articles where date >= cutoff
      - Skip entries with no parseable date (can't verify recency)
    """
    entries = []

    for url_tag in soup.find_all("url"):
        loc = url_tag.find("loc")
        if not loc:
            continue

        article_url = loc.get_text(strip=True)

        # Skip obvious non-article URLs
        if _is_junk_url(article_url):
            continue

        # Try <news:publication_date> first, then <lastmod>
        pub_date = None
        news_pub = url_tag.find("news:publication_date") or url_tag.find("publication_date")
        if news_pub:
            pub_date = _parse_date(news_pub.get_text(strip=True))
        if not pub_date:
            lastmod = url_tag.find("lastmod")
            if lastmod:
                pub_date = _parse_date(lastmod.get_text(strip=True))

        # CRITICAL: skip if no date — we cannot verify 48h recency
        if not pub_date:
            continue

        # CRITICAL: skip if older than cutoff
        if pub_date < cutoff:
            continue

        # Extract <news:title> and <news:keywords>
        title = None
        news_title = url_tag.find("news:title") or url_tag.find("title")
        if news_title:
            title = news_title.get_text(strip=True)

        keywords = None
        news_kw = url_tag.find("news:keywords") or url_tag.find("keywords")
        if news_kw:
            keywords = [k.strip() for k in news_kw.get_text().split(",") if k.strip()]

        entries.append({
            "url":          article_url,
            "title":        title,
            "published_at": pub_date,
            "tags":         keywords,
        })

    return entries


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fetch_xml(url: str) -> Optional[str]:
    """Fetch a URL and return response text, or None on failure."""
    try:
        resp = requests.get(
            url,
            timeout=SITEMAP_TIMEOUT,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; NewsroomAI/1.0; +https://newsroom.dz)",
                "Accept": "application/xml,text/xml,*/*",
            },
        )
        if resp.status_code == 404:
            logger.debug("Sitemap 404: %s", url)
            return None
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.Timeout:
        logger.debug("Sitemap timeout: %s", url)
        return None
    except Exception as e:
        logger.debug("Sitemap fetch error %s: %s", url, e)
        return None


def _parse_robots_sitemaps(base_url: str) -> list[str]:
    """Extract Sitemap: directives from robots.txt."""
    robots_url = f"{base_url}/robots.txt"
    try:
        resp = requests.get(robots_url, timeout=10, headers={"User-Agent": "NewsroomAI/1.0"})
        if resp.status_code != 200:
            return []
        urls = []
        for line in resp.text.splitlines():
            if line.lower().startswith("sitemap:"):
                sitemap_url = line.split(":", 1)[1].strip()
                if sitemap_url.startswith("http"):
                    urls.append(sitemap_url)
        return urls
    except Exception:
        return []


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse ISO 8601 date string to timezone-aware datetime."""
    if not date_str:
        return None
    try:
        from dateutil import parser as dp
        dt = dp.parse(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


# Common URL patterns that are NOT articles
_JUNK_PATTERNS = re.compile(
    r"/(tag|tags|author|auteur|category|categorie|page|search|recherche|media|photo|video|galerie)/",
    re.IGNORECASE,
)


def _is_junk_url(url: str) -> bool:
    """Return True if the URL is clearly not an article (tag, author, category pages, etc.)."""
    path = urlparse(url).path
    if _JUNK_PATTERNS.search(path):
        return True
    # Skip URLs with no path depth (homepage, section roots)
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) < 1:
        return True
    return False
