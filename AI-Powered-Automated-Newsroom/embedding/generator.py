"""
embedding/generator.py
-----------------------
Local embedding generation using sentence-transformers.

Model : sentence-transformers/all-MiniLM-L6-v2
Output: 384-dimensional float32 vectors

The SentenceTransformer model is loaded ONCE (singleton) to avoid
re-loading weights on every batch call — essential for production.
"""

from __future__ import annotations

import logging
import os
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ── Model configuration ────────────────────────────────────────────────────────
# Override via env: EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
_MODEL_NAME: str = os.environ.get(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
_EMBEDDING_DIM: int = 384  # dimension for all-MiniLM-L6-v2

# ── Singleton model instance ───────────────────────────────────────────────────
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """
    Return the globally shared SentenceTransformer instance.
    Lazily loads the model on first call; reuses it thereafter.
    Thread-safe read after first load (GIL protects object reference assignment).
    """
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", _MODEL_NAME)
        _model = SentenceTransformer(_MODEL_NAME)
        logger.info(
            "Model loaded. Embedding dim=%d  device=%s",
            _EMBEDDING_DIM,
            _model.device,
        )
    return _model


def _extract_first_paragraph(content: str) -> str:
    """
    Extract the first non-empty paragraph from article content.

    News articles scraped from the web use newlines (\n or \n\n) to separate
    paragraphs.  The first non-empty paragraph is the lead/lede — the
    sentence or two that summarises the whole story, structurally similar
    to a heading.  This gives the model the most signal-dense text.

    Strategy:
      1. Split on double newlines first (common in cleaned article text).
      2. Fall back to single newlines if nothing useful is found.
      3. Return the first chunk that has at least 3 words.
    """
    for separator in ("\n\n", "\n"):
        parts = [p.strip() for p in content.split(separator)]
        for part in parts:
            if len(part.split()) >= 3:   # skip single-word artefacts
                return part
    # Last resort: return whatever is there
    return content.strip()


def build_text(title: str, content: str | None) -> str:
    """
    Construct the input text for embedding:
      "{title}. {first paragraph of content}"

    Using the first paragraph (lead sentence) rather than a fixed word count
    gives the model the most semantically dense snippet — the part of a news
    article that best captures its topic, similar to a headline + standfirst.
    """
    title = (title or "").strip()
    content = (content or "").strip()

    if content:
        first_para = _extract_first_paragraph(content)
        return f"{title}. {first_para}"
    return title


def embed_texts(texts: List[str], batch_size: int = 64) -> np.ndarray:
    """
    Encode a list of strings into L2-normalised embedding vectors.

    Args:
        texts      : list of input strings (pre-built with build_text)
        batch_size : sentences per forward pass (tune to your GPU/CPU RAM)

    Returns:
        np.ndarray of shape (len(texts), 384), dtype=float32
    """
    if not texts:
        return np.empty((0, _EMBEDDING_DIM), dtype=np.float32)

    model = get_model()

    logger.debug("Encoding %d texts  batch_size=%d", len(texts), batch_size)
    vectors: np.ndarray = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,   # L2-normalise → cosine sim == dot product
        convert_to_numpy=True,
    )
    return vectors.astype(np.float32)
