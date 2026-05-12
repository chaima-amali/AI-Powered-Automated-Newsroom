"""
summarizer/preprocessor.py
───────────────────────────
Phase: Language Detection & Transformation

Responsibilities:
  1. Detect the language of each article in the cluster
  2. Translate all non-English articles → English
     (AR → EN via Helsinki-NLP/opus-mt-ar-en)
     (FR → EN via Helsinki-NLP/opus-mt-fr-en)
  3. Concatenate articles using centroid-ranked, title-weighted strategy
  4. Return a clean English string ready for any summarizer

Why Helsinki-NLP MarianMT:
  - Free, offline, no API key
  - Separate models per language pair = better quality than one-size-fits-all
  - ~300 MB per model, cached after first download
  - Good enough for meaning transfer on short news snippets (title + 300 chars)

Why translate to English first:
  - BART-large-CNN and PEGASUS are the strongest news summarizers available
    and both only support English input
  - Avoids maintaining separate AR/FR model paths
  - ROUGE evaluation is most reliable in English
  - Translating the final 2-sentence summary back (if needed) is much more
    reliable than translating full articles
"""

from __future__ import annotations

import re
import logging
from typing import Optional

import numpy as np
from langdetect import detect, LangDetectException
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from transformers import MarianMTModel, MarianTokenizer

logger = logging.getLogger(__name__)

# ── Embedding model (shared with embedding pipeline — reuse if already loaded)
_EMBED_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_embed_model: Optional[SentenceTransformer] = None

# ── Translation model cache (lazy load — only load what we need)
_translation_models: dict[str, tuple[MarianTokenizer, MarianMTModel]] = {}

MARIAN_MODELS = {
    "ar": "Helsinki-NLP/opus-mt-ar-en",
    "fr": "Helsinki-NLP/opus-mt-fr-en",
    "de": "Helsinki-NLP/opus-mt-de-en",   # future-proofing
    "es": "Helsinki-NLP/opus-mt-es-en",   # future-proofing
}


def _get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        logger.info("Loading embedding model: %s", _EMBED_MODEL_NAME)
        _embed_model = SentenceTransformer(_EMBED_MODEL_NAME)
    return _embed_model


def _get_translation_model(lang: str) -> Optional[tuple[MarianTokenizer, MarianMTModel]]:
    """Lazy-load translation model for a given source language."""
    if lang == "en":
        return None  # no translation needed
    if lang not in MARIAN_MODELS:
        logger.warning("No translation model for lang=%s — keeping original text", lang)
        return None
    if lang not in _translation_models:
        model_name = MARIAN_MODELS[lang]
        logger.info("Loading translation model: %s", model_name)
        tok = MarianTokenizer.from_pretrained(model_name)
        mdl = MarianMTModel.from_pretrained(model_name)
        _translation_models[lang] = (tok, mdl)
    return _translation_models[lang]


def detect_language(text: str) -> str:
    """Detect language of text. Returns ISO 639-1 code. Defaults to 'en' on failure."""
    try:
        return detect(text[:500])  # langdetect only needs first ~500 chars
    except LangDetectException:
        return "en"


def clean_text(text: str) -> str:
    """Strip HTML tags, normalize whitespace, remove lone punctuation lines."""
    text = re.sub(r"<[^>]+>", " ", text)           # strip HTML
    text = re.sub(r"http\S+", "", text)              # strip URLs
    text = re.sub(r"\s+", " ", text)                 # collapse whitespace
    text = text.strip()
    return text


def translate_to_english(text: str, src_lang: str, max_length: int = 512) -> str:
    """
    Translate text from src_lang to English.
    Returns original text if lang is already English or no model available.
    """
    if src_lang == "en":
        return text

    result = _get_translation_model(src_lang)
    if result is None:
        return text

    tok, mdl = result
    # Truncate to avoid OOM on very long texts
    words = text.split()
    if len(words) > 300:
        text = " ".join(words[:300])

    try:
        tokens = tok([text], return_tensors="pt", truncation=True, max_length=max_length, padding=True)
        translated_ids = mdl.generate(**tokens, max_length=max_length)
        return tok.decode(translated_ids[0], skip_special_tokens=True)
    except Exception as e:
        logger.error("Translation failed (lang=%s): %s", src_lang, e)
        return text  # fallback to original


def prepare_articles(articles: list[dict]) -> list[dict]:
    """
    For each article:
      1. Clean text
      2. Detect language
      3. Translate title + content to English
    Returns enriched article dicts with keys:
      lang_detected, title_en, content_en
    """
    enriched = []
    for a in articles:
        title = clean_text(a.get("title", ""))
        content = clean_text(a.get("content", ""))

        lang = a.get("lang") or detect_language(title + " " + content[:200])

        title_en = translate_to_english(title, lang)
        content_en = translate_to_english(content, lang)

        enriched.append({
            **a,
            "lang_detected": lang,
            "title_en": title_en,
            "content_en": content_en,
        })
        logger.debug("Article '%s': lang=%s → EN", title[:40], lang)

    return enriched


def concatenate_for_summarization(
    articles: list[dict],
    centroid: Optional[np.ndarray] = None,
    max_tokens: int = 900,
    sentences_per_article: int = 2,
) -> str:
    """
    Centroid-ranked, extractive-compressed concatenation.

    Strategy (in order of priority):
      1. If centroid is provided: rank articles by cosine similarity to it
      2. Extract best `sentences_per_article` sentences per article
      3. Concatenate title + extracted sentences per article
      4. Stop when token budget is reached

    Why this order:
      - Most topically central articles appear first = survive truncation
      - Per-article sentence extraction = equal representation
      - Token budget = safe for both BART (1024) and mT5 (512)
    """
    model = _get_embed_model()

    # ── Step 1: rank articles by centroid similarity ──────────────────────
    if centroid is not None:
        texts = [a["title_en"] + " " + a["content_en"][:300] for a in articles]
        embeddings = model.encode(texts)
        scores = cosine_similarity(embeddings, [centroid]).flatten()
        ranked = [a for _, a in sorted(zip(scores, articles), key=lambda x: -x[0])]
    else:
        ranked = articles  # use DB order if no centroid

    # ── Step 2: build concatenated string within token budget ─────────────
    parts = []
    total_tokens = 0

    for a in ranked:
        content = a["content_en"]
        title = a["title_en"]

        # Extract best sentences from this article
        sentences = [s.strip() for s in content.split(".") if len(s.strip()) > 20]
        if sentences:
            sent_embeddings = model.encode(sentences)
            doc_vec = model.encode([title])
            sent_scores = cosine_similarity(sent_embeddings, doc_vec).flatten()
            top_idx = sorted(np.argsort(sent_scores)[-sentences_per_article:])
            best = ". ".join(sentences[i] for i in top_idx)
        else:
            best = content[:300]

        snippet = f"{title}. {best}"
        approx_tokens = int(len(snippet.split()) * 1.3)

        if total_tokens + approx_tokens > max_tokens:
            break

        parts.append(snippet)
        total_tokens += approx_tokens

    result = " ".join(parts)
    logger.info(
        "Concatenated %d/%d articles → ~%d tokens",
        len(parts), len(articles), total_tokens
    )
    return result
