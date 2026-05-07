"""
summarizer/llm.py
──────────────────
Approach 2: LLM-Based Summarizer (OpenRouter or Groq)

Used for: political news category (tag = "politics" / "سياسة" / "politique")

Why LLMs for political news specifically:
  ─────────────────────────────────────────
  Political articles require:
    1. Neutrality: LLMs can be explicitly instructed to avoid partisan framing.
       BART has no such instruction mechanism — it inherits biases from CNN/DailyMail.
    2. Nuance: Political summaries often require understanding context
       (who said what, in what capacity) which BART frequently gets wrong.
    3. Entity accuracy: Names of officials, ministries, parties must be exact.
       LLMs are much better at preserving named entities correctly.

  The cost argument:
    - Free tier of OpenRouter/Groq: ~millions of tokens/month for small models
    - Political clusters are typically 5-10 articles max per day
    - At ~500 tokens per cluster input, political summarization uses
      ~5000 tokens/day → well within free tier limits
    - All other categories (sports, economy, culture) use the free BART model

Supported providers:
  ─────────────────────────────────────────
  OpenRouter (recommended for class project):
    - Aggregates 100+ models under one API key
    - Free models: mistralai/mistral-7b-instruct, google/gemma-3-4b-it
    - Base URL: https://openrouter.ai/api/v1
    - Compatible with OpenAI SDK

  Groq (recommended for speed):
    - Extremely fast inference (LPU hardware)
    - Free tier: llama-3.1-8b-instant, mixtral-8x7b-32768
    - Base URL: https://api.groq.com/openai/v1
    - Compatible with OpenAI SDK

Both use the OpenAI-compatible chat completions API,
so the same code works for both — just swap the base_url and api_key.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── Provider configuration ─────────────────────────────────────────────────
# Set these in your .env file:
#   LLM_PROVIDER=openrouter   (or "groq")
#   OPENROUTER_API_KEY=sk-or-...
#   GROQ_API_KEY=gsk_...

PROVIDER_CONFIGS = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "default_model": "mistralai/mistral-7b-instruct",   # free tier
        "extra_headers": {
            "HTTP-Referer": "https://github.com/AI-Powered-Automated-Newsroom",
            "X-Title": "AI Newsroom Pipeline",
        },
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "default_model": "llama-3.1-8b-instant",            # free tier
        "extra_headers": {},
    },
}

# ── Prompt templates ───────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a neutral news digest editor.
Your task is to summarize a cluster of news articles into a concise, factual, 
2-3 sentence digest.

Rules:
- Be strictly neutral — no opinion, no editorial framing
- Preserve all named entities exactly (people, places, organizations)
- Write in clear, journalistic English
- Do not start with "The articles discuss" or similar meta-phrases
- Output ONLY the summary, nothing else"""

USER_PROMPT_TEMPLATE = """Here are {n} news articles on the same topic. 
Write a 2-3 sentence neutral English digest:

{articles_text}

Summary:"""


def _build_articles_text(articles: list[dict], max_chars_each: int = 400) -> str:
    """Format articles for the LLM prompt."""
    parts = []
    for i, a in enumerate(articles, 1):
        # Use English translations if available (from preprocessor)
        title = a.get("title_en") or a.get("title", "")
        content = a.get("content_en") or a.get("content", "")
        content = content[:max_chars_each]
        parts.append(f"[Article {i} — {a.get('source', 'unknown')}]\n{title}\n{content}")
    return "\n\n".join(parts)


def _get_client(provider: str):
    """Build OpenAI-compatible client for the given provider."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("pip install openai")

    config = PROVIDER_CONFIGS[provider]
    api_key = os.getenv(config["api_key_env"])
    if not api_key:
        raise ValueError(
            f"Missing API key. Set {config['api_key_env']} in your .env file.\n"
            f"Get a free key at: "
            + ("https://openrouter.ai/keys" if provider == "openrouter"
               else "https://console.groq.com/keys")
        )

    return OpenAI(
        base_url=config["base_url"],
        api_key=api_key,
        default_headers=config.get("extra_headers", {}),
    )


def llm_summarize(
    articles: list[dict],
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 200,
) -> str:
    """
    Summarize a cluster of articles using an LLM API.

    Args:
        articles:   List of article dicts (with title_en / content_en from preprocessor)
        provider:   "openrouter" or "groq" — defaults to LLM_PROVIDER env var
        model:      Override default model for the provider
        max_tokens: Max tokens in response (200 = ~2-3 sentences)

    Returns:
        2-3 sentence English summary
    """
    provider = provider or os.getenv("LLM_PROVIDER", "openrouter")
    if provider not in PROVIDER_CONFIGS:
        raise ValueError(f"Unknown provider: {provider}. Choose from: {list(PROVIDER_CONFIGS)}")

    config = PROVIDER_CONFIGS[provider]
    model = model or os.getenv("LLM_MODEL") or config["default_model"]

    # Cap articles to 8 to stay within free tier token limits
    articles_subset = articles[:8]
    articles_text = _build_articles_text(articles_subset)
    user_prompt = USER_PROMPT_TEMPLATE.format(
        n=len(articles_subset),
        articles_text=articles_text,
    )

    logger.info("LLM summarize: provider=%s model=%s articles=%d", provider, model, len(articles_subset))

    try:
        client = _get_client(provider)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.3,   # low temperature = more factual, less creative
        )
        summary = response.choices[0].message.content.strip()
        logger.info("LLM summary generated (%d chars)", len(summary))
        return summary

    except Exception as e:
        logger.error("LLM summarization failed (%s/%s): %s", provider, model, e)
        raise


def is_political(tag: str) -> bool:
    """
    Detect if a cluster's tag indicates political content.
    Covers Arabic, French, and English tag variants.
    """
    political_keywords = {
        # English
        "politic", "government", "election", "parliament", "minister",
        "president", "diplomacy", "military", "war", "sanction",
        # French
        "politique", "gouvernement", "élection", "parlement", "ministre",
        "président", "diplomatie", "guerre",
        # Arabic (common tags)
        "سياسة", "حكومة", "انتخابات", "برلمان", "وزير",
        "رئيس", "دبلوماسية", "عسكري", "حرب",
    }
    tag_lower = tag.lower()
    return any(kw in tag_lower for kw in political_keywords)
