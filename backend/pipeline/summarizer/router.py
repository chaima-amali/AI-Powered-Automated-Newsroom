"""
summarizer/router.py
─────────────────────
Decides which summarization strategy to apply per cluster.

Decision table:
┌─────────────────────────────────────┬──────────────────────────────┐
│ Condition                           │ Strategy                     │
├─────────────────────────────────────┼──────────────────────────────┤
│ cluster size == 1                   │ extractive_only (3 sentences)│
│ cluster size 2-4, any tag           │ hybrid (BART)                │
│ cluster size >= 5, tag = political  │ llm (OpenRouter/Groq)        │
│ cluster size >= 5, other tags       │ hybrid (BART)                │
│ LLM fails / no API key              │ hybrid (BART) as fallback    │
└─────────────────────────────────────┴──────────────────────────────┘

The LLM-for-politics decision is valid because:
  - Neutrality is hardest to guarantee in political topics
  - Political clusters are a minority of daily volume
  - Token cost is manageable (see llm.py for analysis)
  - Free tier models (Mistral-7B, LLaMA-3.1-8B) are sufficient quality
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import numpy as np

from .preprocessor import prepare_articles, concatenate_for_summarization
from .hybrid import hybrid_summarize, extractive_only
from .llm import llm_summarize, is_political

logger = logging.getLogger(__name__)


def route_summarization(
    articles: list[dict],
    cluster_tag: str = "",
    centroid: Optional[np.ndarray] = None,
    force_strategy: Optional[str] = None,  # "hybrid" | "llm" | "extractive"
    tag: str = "",  # alias for cluster_tag for backward compatibility
) -> dict:
    """
    Full pipeline: preprocess → route → summarize → return result dict.

    Args:
        articles:        Raw article dicts from DB (title, content, lang, source)
        cluster_tag:     The cluster's tag field from Supabase (used for LLM routing)
        centroid:        Cluster centroid embedding (from embedding step, optional)
        force_strategy:  Override routing logic (useful for testing)
        tag:             Alias for cluster_tag (for backward compatibility)

    Returns:
        {
            "summary_text":  str,
            "summary_model": str,   # model/strategy identifier
            "summary_lang":  str,   # always "en" in this pipeline
            "strategy":      str,   # "hybrid" | "llm" | "extractive"
        }
    """
    # Handle the tag alias
    if tag:
        cluster_tag = tag

    if not articles:
        return {
            "summary_text": "",
            "summary_model": "none",
            "summary_lang": "en",
            "strategy": "none",
        }

    # ── Phase 1: Language Detection & Translation ──────────────────────────
    logger.info("Preprocessing %d articles (cluster_tag=%s)", len(articles), cluster_tag)
    enriched = prepare_articles(articles)

    # ── Phase 2: Concatenation ─────────────────────────────────────────────
    english_text = concatenate_for_summarization(
        enriched,
        centroid=centroid,
        max_tokens=900,
        sentences_per_article=2,
    )

    # ── Phase 3: Routing ───────────────────────────────────────────────────
    n = len(articles)

    if force_strategy:
        strategy = force_strategy
    elif n == 1:
        strategy = "extractive"
    elif is_political(cluster_tag) and n >= 5:
        strategy = "llm"
    else:
        strategy = "hybrid"

    logger.info("Routing: n_articles=%d tag=%s → strategy=%s", n, cluster_tag, strategy)

    # ── Phase 4: Summarization ─────────────────────────────────────────────
    summary_text = ""
    summary_model = ""

    if strategy == "extractive":
        summary_text = extractive_only(english_text, top_k=3)
        summary_model = "extractive/paraphrase-multilingual-MiniLM-L12-v2"

    elif strategy == "llm":
        try:
            summary_text = llm_summarize(enriched)
            provider = os.getenv("LLM_PROVIDER", "openrouter")
            model = os.getenv("LLM_MODEL", "mistralai/mistral-7b-instruct")
            summary_model = f"llm/{provider}/{model}"
        except Exception as e:
            logger.warning("LLM failed, falling back to hybrid: %s", e)
            summary_text = hybrid_summarize(english_text)
            summary_model = "hybrid/bart-large-cnn (llm-fallback)"
            strategy = "hybrid"

    else:  # hybrid (default)
        use_distil = os.getenv("SUMMARIZER_USE_DISTIL", "false").lower() == "true"
        summary_text = hybrid_summarize(english_text, use_distil=use_distil)
        model_name = "sshleifer/distilbart-cnn-12-6" if use_distil else "facebook/bart-large-cnn"
        summary_model = f"hybrid/{model_name}"

    return {
        "summary_text": summary_text,
        "summary_model": summary_model,
        "summary_lang": "en",
        "strategy": strategy,
    }
