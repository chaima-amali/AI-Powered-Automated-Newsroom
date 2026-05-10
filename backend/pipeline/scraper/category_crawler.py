"""
scraper/category_crawler.py
----------------------------
Layer 3 of the discovery pipeline: Category Pages + Pagination (Safety Net).

Purpose:
  Catch articles missed by RSS (dropped entries) or sitemap (delayed updates,
  missing publication_date, malformed XML). This layer is the final safety net
  that guarantees near-100% coverage.

Strategy:
  1. For each source, crawl its configured category paths (/politique, /sport, etc.)
  2. Extract article links from the category listing page
  3. Follow pagination (up to MAX_PAGES) to catch more articles
  4. Filter links through URL validation rules to exclude junk pages
  5. Return only URLs not already known (deduplication happens upstream)

Anti-duplication:
  This layer DOES NOT scrape article content — it only discovers URLs.
  The orchestrator cross-references these URLs with known_urls before scraping.

Pagination logic:
  Sites use different patterns:
    - ?page=2 (query param, most WP-based Algerian sites)
    - /page/2/ (WordPress path-based)
    - /?p=2    (some custom CMSs)
  We try the most common patterns and stop when:
    - No new URLs found on a page (duplicate detection)
    - Max page limit reached
    - HTTP error or timeout
"""

import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlparse, urlencode, parse_qsl, urlunsplit, urlsplit

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MAX_PAGES = 5              # per category — enough to cover 24-48h of production
PAGE_TIMEOUT = 15          # seconds
MIN_ARTICLE_LINKS = 3      # if a page has fewer links than this, stop paginating

# Anchor tags to skip: these patterns indicate non-article links
_JUNK_URL_RE = re.compile(
    r"/(tag|tags|author|auteur|category|categorie|page|search|login|register|"
    r"contact|about|inscription|connexion|profil|media|photo|video|galerie|"
    r"publicite|advertis|newsletter|rss|feed|sitemap)(/|$|\?)",
    re.IGNORECASE,
)

# Minimum path depth for article URLs (e.g. /sport/le-match-2026 = depth 2)
MIN_PATH_DEPTH = 2


# ── Public entry point ─────────────────────────────────────────────────────────

def fetch_category_urls(source: dict, known_urls: set[str]) -> list[str]:
    """
    Discover article URLs from category/section pages for a source.

    Args:
        source:     source config dict (needs base_url + categories list)
        known_urls: set of URLs already discovered by RSS or sitemap layers
                    — these are SKIPPED to avoid redundant scraping

    Returns:
        List of new article URLs not present in known_urls.
    """
    base_url = source["base_url"].rstrip("/")
    categories = source.get("categories", _default_categories())
    session = _make_session()

    discovered: set[str] = set()

    for cat_path in categories:
        cat_url = f"{base_url}/{cat_path.strip('/')}"
        cat_urls = _crawl_category(cat_url, base_url, session)
        for url in cat_urls:
            if url not in known_urls:
                discovered.add(url)

    new_urls = list(discovered)
    if new_urls:
        logger.info(
            "Category crawler '%s': %d new URLs (beyond RSS+sitemap)",
            source["name"], len(new_urls),
        )
    return new_urls


# ── Category page crawler ──────────────────────────────────────────────────────

def _crawl_category(category_url: str, base_url: str, session: requests.Session) -> set[str]:
    """
    Crawl a category listing page and its subsequent pages.
    Returns a set of article URLs found across all pages.
    """
    all_urls: set[str] = set()
    prev_count = -1

    for page_num in range(1, MAX_PAGES + 1):
        page_url = _build_page_url(category_url, page_num)
        links = _extract_links(page_url, base_url, session)

        if not links:
            logger.debug("Category page empty or failed: %s", page_url)
            break

        # Stop when no new links are being added (pagination exhausted)
        before = len(all_urls)
        all_urls.update(links)
        after = len(all_urls)

        if after == before and page_num > 1:
            logger.debug("No new links on page %d of %s — stopping", page_num, category_url)
            break

        if len(links) < MIN_ARTICLE_LINKS:
            break

    return all_urls


def _extract_links(page_url: str, base_url: str, session: requests.Session) -> set[str]:
    """
    Fetch a page and extract candidate article hrefs.
    Applies URL filtering to exclude junk (tags, authors, media, etc.)
    """
    html = _fetch_page(page_url, session)
    if not html:
        return set()

    soup = BeautifulSoup(html, "html.parser")
    base_domain = urlparse(base_url).netloc
    links: set[str] = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue

        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)

        # Only same-domain articles
        if parsed.netloc != base_domain:
            continue

        # Normalise: drop fragment, strip tracking params
        clean_url = _normalize_url(full_url)

        # Filter junk
        if _is_junk_url(clean_url):
            continue

        # Require minimum path depth
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(path_parts) < MIN_PATH_DEPTH:
            continue

        links.add(clean_url)

    return links


# ── Pagination URL builder ─────────────────────────────────────────────────────

def _build_page_url(category_url: str, page_num: int) -> str:
    """
    Build the URL for page N of a category listing.
    Tries WordPress-style path pagination (/page/N/) for page > 1.
    Page 1 returns the base category URL unchanged.
    """
    if page_num == 1:
        return category_url

    # WordPress path-based: /politique/page/2/
    # Most Algerian sites use WordPress, this covers ~80% of cases
    base = category_url.rstrip("/")
    return f"{base}/page/{page_num}/"


# ── Helpers ────────────────────────────────────────────────────────────────────

_TRACKING_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "igshid", "mc_cid", "mc_eid", "ref", "source",
}


def _normalize_url(url: str) -> str:
    """Strip tracking params and fragment from URL."""
    try:
        parts = urlsplit(url.strip())
        query_pairs = [
            (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in _TRACKING_KEYS
        ]
        from urllib.parse import urlencode
        clean_query = urlencode(query_pairs, doseq=True)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, clean_query, ""))
    except Exception:
        return url


def _is_junk_url(url: str) -> bool:
    path = urlparse(url).path
    return bool(_JUNK_URL_RE.search(path))


def _fetch_page(url: str, session: requests.Session) -> Optional[str]:
    try:
        resp = session.get(url, timeout=PAGE_TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.debug("Category page fetch error %s: %s", url, e)
        return None


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ar,fr;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    })
    return s


def _default_categories() -> list[str]:
    """Default Algerian news site category paths to crawl."""
    return [
        "actualite", "actualites", "politique", "economie", "societe",
        "sport", "culture", "international", "region", "medias",
        "sante", "education", "justice", "securite",
    ]
