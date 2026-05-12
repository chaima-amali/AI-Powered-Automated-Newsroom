"""
summarizer/hybrid.py
─────────────────────
Approach 1: Hybrid Summarizer (Extractive → Abstractive)

Pipeline:
  [English text from preprocessor]
       ↓
  [KeyBERT / sentence-level extraction]   ← selects most central sentences
       ↓
  Compressed English input (~100-150 tokens)
       ↓
  [facebook/bart-large-cnn]               ← abstractive generation
       ↓
  Final English summary (2-3 sentences)

Why BART-large-CNN:
  - Fine-tuned on CNN/DailyMail: closest available training domain to
    your Algerian news corpus (same journalistic style)
  - Consistently outperforms mT5 on English news summarization
  - Handles up to 1024 tokens input
  - No GPU required (slow but functional on CPU)
  - Widely benchmarked — easy to evaluate with ROUGE

Why extractive first:
  - BART's quality degrades on long, noisy input
  - Extractive step selects the most informative sentences, so BART
    receives a clean, focused input rather than raw concatenation
  - Reduces hallucination: model works on curated facts, not gaps
  - Reuses the same embedding model already loaded in preprocessor
    (no extra memory cost)

distilbart-cnn-12-6 is included as a CPU-friendly fallback:
  - 6x faster than bart-large-cnn
  - Acceptable quality for demos / low-resource environments




python -m pip install transformers==4.41.2 sentence-transformers torch nltk sacremoses sentencepiece
  pip uninstall transformers -y

  pip install transformers==4.41.2 sentencepiece sacremoses
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import nltk
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from transformers import pipeline as hf_pipeline, Pipeline

# Download NLTK sentence tokenizer models (if not already present)
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt")

logger = logging.getLogger(__name__)

# ── Model options ──────────────────────────────────────────────────────────
BART_LARGE = "facebook/bart-large-cnn"       # best quality (~1.6 GB)
BART_DISTIL = "sshleifer/distilbart-cnn-12-6" # faster CPU option (~700 MB)

_bart_pipelines: Dict[str, Pipeline] = {}
_embed_model: Optional[SentenceTransformer] = None

_EMBED_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def _get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(_EMBED_MODEL_NAME)
    return _embed_model


def _get_bart(use_distil: bool = False) -> Pipeline:
    model_name = BART_DISTIL if use_distil else BART_LARGE

    if model_name not in _bart_pipelines:
        logger.info("Loading BART model: %s", model_name)
        _bart_pipelines[model_name] = hf_pipeline(
            "summarization",
            model=model_name,
            tokenizer=model_name,
        )
    return _bart_pipelines[model_name]


# ── Extractive step ────────────────────────────────────────────────────────

def extractive_compress(text: str, top_k: int = 6) -> str:
    """
    Select top-k sentences from text by cosine similarity to document centroid.

    top_k=6 is chosen to give ~100-150 tokens of input to BART,
    well within its 1024-token limit and enough for coherent generation.
    """
    model = _get_embed_model()

    sentences = [s.strip() for s in nltk.sent_tokenize(text) if len(s.strip()) > 20]
    if len(sentences) <= top_k:
        return text  # already short enough

    embeddings = model.encode(sentences)
    centroid = embeddings.mean(axis=0, keepdims=True)
    scores = cosine_similarity(embeddings, centroid).flatten()

    # Preserve original sentence order (not score order) for coherence
    top_indices = sorted(np.argsort(scores)[-top_k:])
    compressed = ". ".join(sentences[i] for i in top_indices) + "."

    logger.debug(
        "Extractive: %d sentences → %d sentences (%d words)",
        len(sentences), top_k, len(compressed.split())
    )
    return compressed


# ── Abstractive step ───────────────────────────────────────────────────────

def abstractive_generate(text: str, use_distil: bool = False) -> str:
    """
    Run BART on the (already compressed) English text.
    max_length=130 / min_length=40 chosen for 2-3 sentence news digests.
    """
    bart = _get_bart(use_distil=use_distil)

    # BART tokenizer limit
    words = text.split()
    if len(words) > 700:
        text = " ".join(words[:700])

    try:
        result = bart(
            text,
            max_length=130,
            min_length=40,
            do_sample=False,
            num_beams=4,
            no_repeat_ngram_size=3,
            early_stopping=True,
        )
        return result[0]["summary_text"]
    except Exception as e:
        logger.error("BART generation failed: %s", e)
        # Fallback: return first 2 sentences of extractive output
        sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 20]
        return ". ".join(sentences[:2]) + "."


# ── Public API ─────────────────────────────────────────────────────────────

def hybrid_summarize(
    english_text: str,
    top_k_sentences: int = 6,
    use_distil: bool = False,
) -> str:
    """
    Full hybrid pipeline: extractive compression → abstractive generation.

    Args:
        english_text:     Pre-translated, concatenated English text from preprocessor
        top_k_sentences:  Number of sentences to select in extractive step
        use_distil:       Use distilbart (faster) instead of bart-large-cnn

    Returns:
        2-3 sentence English news digest
    """
    # Step 1: extractive compression
    compressed = extractive_compress(english_text, top_k=top_k_sentences)

    # Step 2: abstractive generation on compressed input
    summary = abstractive_generate(compressed, use_distil=use_distil)

    return summary


def extractive_only(english_text: str, top_k: int = 3) -> str:
    """
    Pure extractive summarization (no generation).
    Useful for single-article clusters, offline fallback, or unit tests.
    """
    sentences = [s.strip() for s in english_text.split(".") if len(s.strip()) > 20]
    if len(sentences) <= top_k:
        return english_text

    model = _get_embed_model()
    embeddings = model.encode(sentences)
    centroid = embeddings.mean(axis=0, keepdims=True)
    scores = cosine_similarity(embeddings, centroid).flatten()
    top_indices = sorted(np.argsort(scores)[-top_k:])
    return ". ".join(sentences[i] for i in top_indices) + "."
