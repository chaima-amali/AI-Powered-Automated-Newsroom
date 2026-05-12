"""
pipeline/scraper/image_downloader.py
--------------------------------------
Downloads and stores article images locally.
Images are resized to max 1200px wide and converted to JPEG to save storage.

Usage:
    from pipeline.scraper.image_downloader import download_image, ImageDownloader
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "./media"))
MAX_WIDTH   = 1200
MAX_SIZE_MB = 5
TIMEOUT     = 10

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 NewsroomAI/1.0"
    retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://",  HTTPAdapter(max_retries=retry))
    return s


_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = _make_session()
    return _session


def _image_path(article_id: int, pub_date: Optional[datetime] = None) -> Path:
    """Return the local storage path for an article image."""
    dt = pub_date or datetime.utcnow()
    folder = MEDIA_ROOT / "images" / str(dt.year) / f"{dt.month:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{article_id}.jpg"


def _resize_and_save(raw_bytes: bytes, dest: Path) -> None:
    """Resize image to max MAX_WIDTH px wide, save as JPEG. Falls back to raw save."""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
        if img.width > MAX_WIDTH:
            ratio = MAX_WIDTH / img.width
            img = img.resize((MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS)
        img.save(dest, "JPEG", quality=85, optimize=True)
    except ImportError:
        # Pillow not installed — save raw bytes
        dest.write_bytes(raw_bytes)
    except Exception as e:
        logger.warning("Image resize failed (%s); saving raw bytes", e)
        dest.write_bytes(raw_bytes)


def download_image(
    image_url: str,
    article_id: int,
    pub_date: Optional[datetime] = None,
) -> Optional[str]:
    """
    Download an article image, resize it, and store locally.

    Returns the local file path (str) on success, None on failure.
    """
    if not image_url:
        return None

    # Basic URL validation
    parsed = urlparse(image_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        logger.debug("Skipping invalid image URL: %s", image_url)
        return None

    dest = _image_path(article_id, pub_date)

    # Skip if already downloaded
    if dest.exists():
        return str(dest)

    try:
        resp = _get_session().get(image_url, timeout=TIMEOUT, stream=True)
        resp.raise_for_status()

        # Validate content type
        ct = resp.headers.get("Content-Type", "").split(";")[0].strip()
        if ct not in ALLOWED_CONTENT_TYPES:
            logger.debug("Skipping non-image content-type '%s' for %s", ct, image_url)
            return None

        # Validate size
        raw = resp.content
        if len(raw) > MAX_SIZE_MB * 1024 * 1024:
            logger.debug("Image too large (%.1f MB) at %s", len(raw) / 1e6, image_url)
            return None

        _resize_and_save(raw, dest)
        logger.debug("Image saved: %s (%d KB)", dest, len(raw) // 1024)
        return str(dest)

    except requests.exceptions.Timeout:
        logger.debug("Image download timeout: %s", image_url)
    except requests.exceptions.HTTPError as e:
        logger.debug("Image HTTP error %s: %s", e.response.status_code, image_url)
    except Exception as e:
        logger.debug("Image download failed (%s): %s", type(e).__name__, image_url)

    return None


class ImageDownloader:
    """
    Batch image downloader for use in the pipeline.
    Tracks success/failure stats per run.
    """

    def __init__(self):
        self.downloaded = 0
        self.failed     = 0
        self.skipped    = 0

    def process(self, article_id: int, image_url: Optional[str],
                pub_date: Optional[datetime] = None) -> Optional[str]:
        if not image_url:
            self.skipped += 1
            return None

        path = download_image(image_url, article_id, pub_date)
        if path:
            self.downloaded += 1
        else:
            self.failed += 1
        return path

    def log_stats(self) -> None:
        logger.info(
            "Image downloads: %d OK | %d failed | %d skipped",
            self.downloaded, self.failed, self.skipped,
        )
