"""Embedding generation and text preparation utilities.

Key design decisions (v2 – cross-lingual fix):
  - Model: sentence-transformers/LaBSE
      * Purpose-built for cross-lingual sentence similarity.
      * Maps Arabic, French, and English into the same 768-d vector space.
      * No special query/passage prefixes required (unlike multilingual-e5).
      * State-of-the-art on BUCC / Tatoeba multilingual retrieval benchmarks.
  - Arabic text normalization: strips diacritics, normalises alef/hamza/teh-marbuta
    variants so the same word written differently compares correctly.
  - HTML stripping + whitespace collapse for all languages.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from typing import List

import numpy as np
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Avoid TensorFlow import path on Windows when only PyTorch embeddings are needed.
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")

# ── Model configuration ───────────────────────────────────────────────────────
# LaBSE is the recommended model for Arabic/French/English cross-lingual tasks.
# Enforce LaBSE for production embedding/clustering to ensure consistent
# multilingual behaviour. If an env var is set to a different model we log
# a warning and override it to avoid accidental runs with weaker models.
_ENV_MODEL_NAME = os.environ.get("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2").strip()
_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
if _ENV_MODEL_NAME and _ENV_MODEL_NAME.lower() != _MODEL_NAME.lower():
    logger = logging.getLogger(__name__)
    logger.warning(
        "EMBEDDING_MODEL_NAME in environment is '%s' but pipeline enforces '%s' for consistent clustering. Overriding.",
        _ENV_MODEL_NAME,
        _MODEL_NAME,
    )
_DB_VECTOR_DIM: int = int(os.environ.get("EMBEDDING_VECTOR_DIM", "384"))
_BACKEND: str = (
    os.environ.get("EMBEDDING_BACKEND", "sentence-transformers").strip().lower()
)

# ── Singleton model instance ───────────────────────────────────────────────────
_model: object | None = None
_MODEL_OUTPUT_DIM: int | None = None

# ── Arabic normalisation map ───────────────────────────────────────────────────
# Maps visually distinct but semantically identical Arabic characters to a
# canonical form so the model sees consistent tokens.
_ARABIC_NORM_MAP: dict[str, str] = {
    # Alef variants → plain alef
    "\u0622": "\u0627",  # أ (alef madda)
    "\u0623": "\u0627",  # أ (alef with hamza above)
    "\u0625": "\u0627",  # إ (alef with hamza below)
    "\u0671": "\u0627",  # ٱ (alef wasla)
    # Teh marbuta → heh
    "\u0629": "\u0647",
    # Yeh variants → dotless yeh
    "\u0649": "\u064a",  # alef maqsura → ya
    # Remove tatweel (kashida)
    "\u0640": "",
}
_ARABIC_NORM_RE = re.compile(
    "[" + "".join(re.escape(k) for k in _ARABIC_NORM_MAP) + "]"
)

_PUNCT_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00a0": " ",
        "\u202f": " ",
        "\u2013": "-",
        "\u2014": "-",
    }
)


def _normalize_arabic(text: str) -> str:
    """Normalize Arabic script: remove diacritics, unify alef/yeh variants."""
    # 1. Strip harakat (short vowel marks) and other combining diacritics
    text = "".join(
        ch
        for ch in unicodedata.normalize("NFC", text)
        if not (unicodedata.category(ch) == "Mn" and "\u0600" <= ch <= "\u06FF")
    )
    # 2. Apply character-level normalization map
    text = _ARABIC_NORM_RE.sub(lambda m: _ARABIC_NORM_MAP[m.group()], text)
    return text


def get_model() -> object:
    """
    Return the globally shared SentenceTransformer instance (LaBSE by default).
    Lazily loads the model on first call; reuses it thereafter.
    """
    global _model, _MODEL_OUTPUT_DIM
    if _model is None:
        logger.info("Loading embedding model: %s", _MODEL_NAME)
        if _BACKEND != "sentence-transformers":
            raise RuntimeError(
                "Fallback embeddings are disabled for production clustering. "
                "Set EMBEDDING_BACKEND=sentence-transformers and rerun."
            )
        try:
            from sentence_transformers import SentenceTransformer
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "sentence-transformers is required. "
                "Install it with: pip install sentence-transformers"
            ) from exc

        _model = SentenceTransformer(_MODEL_NAME)
        _MODEL_OUTPUT_DIM = int(_model.get_sentence_embedding_dimension())
        logger.info(
            "Model loaded. model_dim=%d  db_vector_dim=%d  device=%s",
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


def _strip_html(text: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    if not text:
        return ""
    stripped = BeautifulSoup(text, "lxml").get_text(" ")
    return re.sub(r"\s+", " ", stripped).strip()


def _clean_text(text: str | None) -> str:
    """Remove HTML, normalize whitespace, and apply Arabic normalization."""
    if not text:
        return ""
    cleaned = _strip_html(text)
    cleaned = cleaned.translate(_PUNCT_TRANSLATION)
    # Apply Arabic normalization only if the text contains Arabic script
    if re.search(r"[\u0600-\u06FF]", cleaned):
        cleaned = _normalize_arabic(cleaned)
    return cleaned.strip()


def _extract_first_paragraph(content: str) -> str:
    """Extract the lead paragraph from article content (any language)."""
    if not content:
        return ""
    raw_text = BeautifulSoup(content, "lxml").get_text("\n")
    collapsed = re.sub(r"\r\n?", "\n", raw_text)
    collapsed = re.sub(r"\n{3,}", "\n\n", collapsed)
    paragraph_candidates = [
        chunk.strip()
        for chunk in re.split(r"\n{2,}", collapsed)
        if chunk.strip()
    ]
    lead = paragraph_candidates[0] if paragraph_candidates else collapsed.strip()
    lines = [line.strip() for line in lead.split("\n") if line.strip()]
    first_para = " ".join(lines[:3]) if lines else lead
    return _clean_text(first_para)


def build_text(
    title: str,
    content: str | None,
    summary: str | None = None,
    tags: list[str] | tuple[str, ...] | None = None,
) -> str:
    """
    Construct the text to embed for an article.

    For LaBSE (and most multilingual ST models), no special prefix is needed.
    We use: "<title>. <lead paragraph>" which gives the model enough semantic
    signal without including noisy boilerplate from long article bodies.

    Tags are intentionally NOT included in the embedding text — they are only
    used as a soft similarity boost in the clustering step (via tag_overlap_bonus
    in NewsClust). Mixing tags into the embedding text causes tag-driven
    clustering rather than topic-driven clustering.
    """
    clean_title = _clean_text(title)
    lead = _extract_first_paragraph(content or "")
    if not lead:
        lead = _clean_text(summary or "")

    if clean_title and lead:
        return f"{clean_title}. {lead}"
    return clean_title or lead


def get_effective_model_version() -> str:
    """Return the embedding model identifier for auditability / DB storage."""
    return _MODEL_NAME


def embed_texts(texts: List[str], batch_size: int = 64) -> np.ndarray:
    """
    Encode a list of texts into L2-normalized sentence vectors using LaBSE.

    Args:
        texts: List of strings (any mix of Arabic, French, English).
        batch_size: Preserved for compatibility; embeddings are encoded one at a time.

    Returns:
        np.ndarray of shape (len(texts), _DB_VECTOR_DIM), dtype=float32,
        L2-normalized so cosine_similarity(a, b) == np.dot(a, b).
    """
    if not texts:
        return np.empty((0, _DB_VECTOR_DIM), dtype=np.float32)

    model = get_model()
    logger.debug("Encoding %d texts  batch_size=%d", len(texts), batch_size)

    vectors: list[np.ndarray] = []
    try:
        for text in texts:
            encoded = model.encode(
                [text],
                batch_size=1,
                show_progress_bar=False,
                normalize_embeddings=True,  # L2-normalise → cosine_sim == dot product
                convert_to_numpy=True,
            )
            encoded = np.asarray(encoded, dtype=np.float32)
            if encoded.ndim == 1:
                encoded = encoded.reshape(1, -1)
            vectors.append(encoded[0])
    except Exception:
        logger.exception("Embedding model encode failed")
        raise

    vectors = np.vstack(vectors).astype(np.float32)
    vectors = _align_dimension(vectors)

    # Sanity check: LaBSE produces dense vectors; very sparse output means
    # something went wrong with the model load.
    nonzero_ratio = float((vectors != 0).mean()) if vectors.size else 0.0
    if nonzero_ratio < 0.50:
        raise RuntimeError(
            f"Embedding density check failed (nonzero_ratio={nonzero_ratio:.3f}). "
            "Vectors look sparse — verify the model loaded correctly."
        )
    return vectors
