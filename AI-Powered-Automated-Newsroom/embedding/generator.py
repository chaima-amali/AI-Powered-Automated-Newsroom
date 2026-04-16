"""Embedding generation and text preparation utilities."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import List

import numpy as np
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Model configuration ────────────────────────────────────────────────────────
_MODEL_NAME: str = "intfloat/multilingual-e5-base"
_DB_VECTOR_DIM: int = int(os.environ.get("EMBEDDING_VECTOR_DIM", "768"))
_BACKEND: str = os.environ.get("EMBEDDING_BACKEND", "sentence-transformers").strip().lower()

# ── Singleton model instance ───────────────────────────────────────────────────
_model: object | None = None
_MODEL_OUTPUT_DIM: int | None = None


class _FallbackSentenceTransformer:
    """Deterministic local fallback used when sentence-transformers is unavailable."""

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self.device = "cpu"

    def encode(
        self,
        texts: List[str],
        batch_size: int = 64,
        show_progress_bar: bool = False,
        normalize_embeddings: bool = True,
        convert_to_numpy: bool = True,
    ) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row_index, text in enumerate(texts):
            for token in text.lower().split():
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                bucket = int.from_bytes(digest[:4], "little") % self.dimension
                vectors[row_index, bucket] += 1.0

        if normalize_embeddings:
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            vectors = vectors / norms

        if convert_to_numpy:
            return vectors
        return vectors.tolist()


def get_model() -> object:
    """
    Return the globally shared SentenceTransformer instance.
    Lazily loads the model on first call; reuses it thereafter.
    Thread-safe read after first load (GIL protects object reference assignment).
    """
    global _model
    global _MODEL_OUTPUT_DIM
    if _model is None:
        logger.info("Loading embedding model: %s", _MODEL_NAME)
        if _BACKEND != "sentence-transformers":
            logger.warning(
                "Using deterministic fallback embeddings (EMBEDDING_BACKEND=%s)",
                _BACKEND,
            )
            _model = _FallbackSentenceTransformer(_DB_VECTOR_DIM)
            _MODEL_OUTPUT_DIM = _DB_VECTOR_DIM
        else:
            try:
                from sentence_transformers import SentenceTransformer
            except ModuleNotFoundError:
                logger.warning(
                    "sentence-transformers is not installed; using deterministic fallback embeddings"
                )
                _model = _FallbackSentenceTransformer(_DB_VECTOR_DIM)
                _MODEL_OUTPUT_DIM = _DB_VECTOR_DIM
            else:
                _model = SentenceTransformer(_MODEL_NAME)
                _MODEL_OUTPUT_DIM = int(_model.get_sentence_embedding_dimension())
        logger.info(
            "Model loaded. model_dim=%s  db_vector_dim=%d  device=%s",
            _MODEL_OUTPUT_DIM,
            _DB_VECTOR_DIM,
            getattr(_model, "device", "cpu"),
        )
    return _model


def _align_dimension(vectors: np.ndarray) -> np.ndarray:
    """Pad or truncate model vectors to match the DB vector dimension."""
    if vectors.ndim != 2:
        return vectors

    current_dim = int(vectors.shape[1])
    if current_dim == _DB_VECTOR_DIM:
        return vectors

    if current_dim > _DB_VECTOR_DIM:
        logger.warning(
            "Embedding dim %d > DB dim %d; truncating vectors",
            current_dim,
            _DB_VECTOR_DIM,
        )
        return vectors[:, :_DB_VECTOR_DIM]

    pad_width = _DB_VECTOR_DIM - current_dim
    logger.info(
        "Embedding dim %d < DB dim %d; zero-padding vectors",
        current_dim,
        _DB_VECTOR_DIM,
    )
    return np.pad(vectors, ((0, 0), (0, pad_width)), mode="constant")


def _extract_first_paragraph(content: str) -> str:
    """Extract first paragraph or first 2-3 non-empty lines from content."""
    if not content:
        return ""

    raw_text = BeautifulSoup(content, "lxml").get_text("\n")
    collapsed = re.sub(r"\r\n?", "\n", raw_text)
    collapsed = re.sub(r"\n{3,}", "\n\n", collapsed)
    paragraph_candidates = [chunk.strip() for chunk in re.split(r"\n{2,}", collapsed) if chunk.strip()]
    if paragraph_candidates:
        lead = paragraph_candidates[0]
    else:
        lead = collapsed.strip()

    lines = [line.strip() for line in lead.split("\n") if line.strip()]
    if lines:
        return _clean_text(" ".join(lines[:3]))
    return _clean_text(lead)


def _clean_text(text: str | None) -> str:
    """Remove HTML and normalize whitespace while preserving language characters."""
    if not text:
        return ""
    # BeautifulSoup safely strips tags from partially malformed HTML snippets.
    stripped = BeautifulSoup(text, "lxml").get_text(" ")
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped.strip()


def build_text(
    title: str,
    content: str | None,
    summary: str | None = None,
    tags: list[str] | tuple[str, ...] | None = None,
) -> str:
    """Construct required embedding input: title + '. ' + title + '. ' + first paragraph."""
    clean_title = _clean_text(title)
    first_paragraph = _extract_first_paragraph(content or "")
    if not first_paragraph:
        first_paragraph = _clean_text(summary)

    if clean_title and first_paragraph:
        return f"{clean_title}. {clean_title}. {first_paragraph}"
    if clean_title:
        return f"{clean_title}. {clean_title}"
    return first_paragraph


def embed_texts(texts: List[str], batch_size: int = 64) -> np.ndarray:
    """
    Encode a list of texts into L2-normalized sentence vectors.

    Returns:
        np.ndarray of shape (len(texts), EMBEDDING_VECTOR_DIM), dtype=float32
    """
    if not texts:
        return np.empty((0, _DB_VECTOR_DIM), dtype=np.float32)

    model = get_model()

    logger.debug("Encoding %d texts  batch_size=%d", len(texts), batch_size)
    vectors: np.ndarray = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,   # L2-normalise → cosine sim == dot product
        convert_to_numpy=True,
    )
    vectors = vectors.astype(np.float32)
    vectors = _align_dimension(vectors)
    return vectors.astype(np.float32)
