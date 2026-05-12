"""
scraper/deduplication.py
-------------------------
Layer 4: Cross-source deduplication intelligence.

Three levels of deduplication:
  1. URL normalization       — same article, different tracking params / fragments
  2. Canonical URL detection — <link rel="canonical"> points to the true URL
  3. Cross-layer merging     — RSS vs sitemap vs category discovered same article
                               → merge metadata, keep best source

This module is stateless within a run — it operates on in-memory sets.
DB-level deduplication is handled by the `ON CONFLICT (url) DO NOTHING`
constraint in repository.upsert_article().

Usage:
    from scraper.deduplication import Deduplicator

    dedup = Deduplicator()
    dedup.add_from_rss(rss_entries)
    dedup.add_from_sitemap(sitemap_entries)
    dedup.add_from_categories(category_urls)

    to_scrape = dedup.get_pending_urls()
"""

import logging
import re
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunsplit

logger = logging.getLogger(__name__)

# Query parameters that do NOT identify article identity
_TRACKING_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "igshid", "mc_cid", "mc_eid",
    "ref", "source", "from", "via",
}

# Query parameters that DO identify article identity (e.g. ?p=12345)
_IDENTITY_KEYS = {"p", "id", "article_id", "post_id"}


def normalize_url(url: str) -> str:
    """
    Canonical URL normalization:
      - Strip tracking query params (utm_*, fbclid, etc.)
      - Lowercase scheme and netloc
      - Remove trailing slash from path (except root)
      - Drop fragment (#section)
      - Preserve identity query params (?p=12345)
    """
    try:
        url = url.strip()
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        netloc = parts.netloc.lower()

        # Normalize path
        path = parts.path
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")

        # Filter query params
        query_pairs = [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in _TRACKING_KEYS
        ]
        clean_query = urlencode(sorted(query_pairs), doseq=True)  # sort for stability

        return urlunsplit((scheme, netloc, path, clean_query, ""))
    except Exception:
        return url


class Deduplicator:
    """
    In-memory deduplication across all three discovery layers for a single run.

    Internal state:
      _seen_normalized: set of normalized URLs already registered
      _url_metadata:    normalized_url → best metadata dict we have so far
      _discovery_order: normalized_url → which layer discovered it first
    """

    def __init__(self):
        self._seen_normalized: set[str] = set()
        self._url_metadata: dict[str, dict] = {}
        self._discovery_order: dict[str, str] = {}

        # Stats
        self.rss_count = 0
        self.sitemap_count = 0
        self.category_count = 0
        self.duplicate_count = 0

    # ── Add methods ────────────────────────────────────────────────────────────

    def add_from_rss(self, entries: list[dict]) -> int:
        """Register RSS feed entries. Returns count of new unique URLs added."""
        return self._add_batch(entries, layer="rss")

    def add_from_sitemap(self, entries: list[dict]) -> int:
        """Register sitemap entries. Returns count of new unique URLs added."""
        return self._add_batch(entries, layer="sitemap")

    def add_from_categories(self, urls: list[str]) -> int:
        """
        Register category-crawled URLs (no metadata, just URLs).
        Returns count of new unique URLs added.
        """
        entries = [{"url": u} for u in urls]
        return self._add_batch(entries, layer="category")

    def _add_batch(self, entries: list[dict], layer: str) -> int:
        added = 0
        for entry in entries:
            raw_url = entry.get("url")
            if not raw_url:
                continue

            norm = normalize_url(raw_url)

            if norm in self._seen_normalized:
                self.duplicate_count += 1
                # Merge metadata: prefer RSS/sitemap metadata over category
                self._merge_metadata(norm, entry, layer)
                continue

            self._seen_normalized.add(norm)
            self._url_metadata[norm] = {**entry, "url": norm, "discovered_from": layer}
            self._discovery_order[norm] = layer
            added += 1

        if layer == "rss":
            self.rss_count += added
        elif layer == "sitemap":
            self.sitemap_count += added
        else:
            self.category_count += added

        return added

    def _merge_metadata(self, norm: str, new_entry: dict, layer: str) -> None:
        """
        When the same URL is seen from multiple layers, merge metadata.
        Priority: RSS > sitemap > category (RSS has best real-time metadata).
        """
        existing = self._url_metadata.get(norm, {})
        existing_layer = self._discovery_order.get(norm, "category")

        layer_priority = {"rss": 0, "sitemap": 1, "category": 2}
        if layer_priority.get(layer, 9) < layer_priority.get(existing_layer, 9):
            # New layer has higher priority — overwrite most fields but keep url
            merged = {**new_entry, "url": norm, "discovered_from": existing_layer}
            self._url_metadata[norm] = merged
        else:
            # Fill in missing fields from the new entry
            for key, val in new_entry.items():
                if key != "url" and val and not existing.get(key):
                    existing[key] = val

    # ── Query methods ──────────────────────────────────────────────────────────

    def get_pending_urls(self) -> list[dict]:
        """
        Return all unique article metadata dicts, sorted by discovered_from layer
        (RSS first for freshness, then sitemap, then category).
        """
        layer_order = {"rss": 0, "sitemap": 1, "category": 2}
        return sorted(
            self._url_metadata.values(),
            key=lambda e: layer_order.get(e.get("discovered_from", "category"), 9),
        )

    def is_known(self, url: str) -> bool:
        return normalize_url(url) in self._seen_normalized

    def add_db_known(self, db_urls: list[str]) -> None:
        """Pre-populate with URLs already in the database to skip re-scraping."""
        for url in db_urls:
            self._seen_normalized.add(normalize_url(url))

    def stats(self) -> dict:
        return {
            "rss_new":      self.rss_count,
            "sitemap_new":  self.sitemap_count,
            "category_new": self.category_count,
            "duplicates_merged": self.duplicate_count,
            "total_unique": len(self._seen_normalized),
        }

    def log_stats(self) -> None:
        s = self.stats()
        logger.info(
            "Deduplication stats — RSS: %d new | Sitemap: %d new | "
            "Category: %d new | Merged duplicates: %d | Total unique: %d",
            s["rss_new"], s["sitemap_new"], s["category_new"],
            s["duplicates_merged"], s["total_unique"],
        )
