"""
pipeline/rewriter/engine.py
-----------------------------
Core LLM rewriting engine.
Calls OpenRouter (or Groq) to transform summaries into publication-ready articles.
Always requests JSON output and validates the response with Pydantic.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Optional

import requests
from pydantic import BaseModel, Field, validator

from pipeline.rewriter.prompts import (REWRITE_SYSTEM, REWRITE_USER,
                                        FALLBACK_REWRITE_USER,
                                        ARABIC_REWRITE_SYSTEM, ARABIC_REWRITE_USER)

logger = logging.getLogger(__name__)

LLM_PROVIDER      = os.environ.get("LLM_PROVIDER", "openrouter")
OPENROUTER_KEY    = os.environ.get("OPENROUTER_API_KEY", "")
GROQ_KEY          = os.environ.get("GROQ_API_KEY", "")
LLM_MODEL         = os.environ.get("LLM_MODEL", "mistralai/mistral-7b-instruct")
LLM_MAX_TOKENS    = int(os.environ.get("LLM_MAX_TOKENS", 1500))
LLM_TEMPERATURE   = float(os.environ.get("LLM_TEMPERATURE", 0.3))
LLM_TIMEOUT       = int(os.environ.get("LLM_TIMEOUT_SEC", 60))
LLM_MAX_RETRIES   = int(os.environ.get("LLM_MAX_RETRIES", 2))


# ── Pydantic schema for LLM response validation ───────────────────────────────

class RewriteResult(BaseModel):
    title:           str = Field(..., min_length=5,  max_length=200)
    excerpt:         str = Field(..., min_length=10, max_length=500)
    body:            str = Field(..., min_length=100)
    seo_title:       str = Field(default="", max_length=100)
    seo_description: str = Field(default="", max_length=300)
    tags:            list[str] = Field(default_factory=list)
    category:        str = Field(default="Actualité")

    @validator("body")
    def body_no_ai_markers(cls, v):
        bad = ["as an ai", "i cannot", "i'm sorry", "je ne peux pas", "en tant qu'ia"]
        low = v.lower()
        for marker in bad:
            if marker in low:
                raise ValueError(f"Body contains AI refusal marker: '{marker}'")
        return v

    @validator("tags", pre=True)
    def tags_list(cls, v):
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        return v or []


# ── LLM API clients ───────────────────────────────────────────────────────────

def _call_openrouter(system: str, user: str, model: str) -> str:
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENROUTER_KEY}",
                 "Content-Type": "application/json",
                 "HTTP-Referer": "https://newsroom.dz"},
        json={"model": model, "max_tokens": LLM_MAX_TOKENS, "temperature": LLM_TEMPERATURE,
              "messages": [{"role": "system", "content": system},
                           {"role": "user",   "content": user}]},
        timeout=LLM_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_groq(system: str, user: str, model: str) -> str:
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_KEY}",
                 "Content-Type": "application/json"},
        json={"model": model, "max_tokens": LLM_MAX_TOKENS, "temperature": LLM_TEMPERATURE,
              "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": system},
                           {"role": "user",   "content": user}]},
        timeout=LLM_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_llm(system: str, user: str) -> str:
    """Call the configured LLM provider with retry logic."""
    model = LLM_MODEL
    last_exc: Exception | None = None

    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            if LLM_PROVIDER == "groq":
                return _call_groq(system, user, model)
            else:
                return _call_openrouter(system, user, model)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                wait = 2 ** attempt
                logger.warning("LLM rate-limited, retry in %ds", wait)
                time.sleep(wait)
            last_exc = e
        except Exception as e:
            last_exc = e
            logger.warning("LLM call failed (attempt %d): %s", attempt + 1, e)
            time.sleep(1)

    raise RuntimeError(f"LLM failed after {LLM_MAX_RETRIES + 1} attempts") from last_exc


# ── JSON extraction & parsing ─────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Extract JSON from raw LLM output, stripping markdown fences if present."""
    text = text.strip()
    # Strip ```json ... ``` fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract first JSON object
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from LLM response: {text[:200]!r}")


# ── Public API ────────────────────────────────────────────────────────────────

def rewrite_article(
    summary: str,
    headlines: list[str],
    sources: list[str],
    tag: str = "actualite",
    language: str = "fr",
) -> RewriteResult:
    """
    Transform a cluster summary into a publication-ready article.

    Args:
        summary:   The cluster summary text from the summarizer pipeline.
        headlines: List of original article titles from source articles.
        sources:   List of source names.
        tag:       Topic tag / category hint.
        language:  Output language ('fr' or 'ar').

    Returns:
        Validated RewriteResult with title, excerpt, body, SEO fields, tags, category.
    """
    headlines_text = "\n".join(f"- {h}" for h in headlines[:10])
    sources_text   = ", ".join(set(sources[:8]))

    # Choose prompts based on output language
    if language == "ar":
        system = ARABIC_REWRITE_SYSTEM
        user   = ARABIC_REWRITE_USER.format(
            summary=summary, headlines=headlines_text,
            sources=sources_text, tag=tag,
        )
    else:
        system = REWRITE_SYSTEM
        user   = REWRITE_USER.format(
            summary=summary, headlines=headlines_text,
            sources=sources_text, tag=tag,
        )

    raw = _call_llm(system, user)

    try:
        data = _extract_json(raw)
        return RewriteResult(**data)
    except Exception as first_err:
        logger.warning("Primary rewrite parse failed (%s). Trying fallback prompt.", first_err)
        # Fallback: simpler prompt
        fallback_user = FALLBACK_REWRITE_USER.format(summary=summary[:1000])
        try:
            raw2 = _call_llm(REWRITE_SYSTEM, fallback_user)
            data2 = _extract_json(raw2)
            return RewriteResult(**data2)
        except Exception as second_err:
            logger.error("Fallback rewrite also failed: %s", second_err)
            # Last resort: build a minimal result from the summary itself
            return RewriteResult(
                title   = headlines[0][:90] if headlines else "Article",
                excerpt = summary[:200],
                body    = summary,
                seo_title       = (headlines[0][:60] if headlines else "Article"),
                seo_description = summary[:155],
                tags    = [tag] if tag and tag != "unknown" else [],
                category = "Actualité",
            )
