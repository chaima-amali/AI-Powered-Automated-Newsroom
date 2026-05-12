"""
pipeline/rewriter/quality.py
------------------------------
Automated quality gate before publishing.
Returns a float score 0.0–1.0 and a list of failure reasons.
Articles scoring below QUALITY_THRESHOLD are kept as 'draft' for human review.
"""
from __future__ import annotations

import os
import re

QUALITY_THRESHOLD = float(os.environ.get("QUALITY_THRESHOLD", 0.60))

# Known AI refusal / failure markers
_AI_MARKERS = [
    "as an ai", "i cannot", "i'm sorry", "je ne peux pas",
    "en tant qu'ia", "je suis désolé", "لا أستطيع", "كذكاء اصطناعي",
    "i don't have", "i am unable",
]

# Minimum body word count
MIN_WORDS = int(os.environ.get("QUALITY_MIN_WORDS", 120))
MAX_WORDS = int(os.environ.get("QUALITY_MAX_WORDS", 2000))


def _word_count(text: str) -> int:
    return len(text.split())


def _contains_ai_marker(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in _AI_MARKERS)


def _title_ok(title: str) -> tuple[bool, str]:
    if not title or not title.strip():
        return False, "title is empty"
    n = len(title.strip())
    if n < 10:
        return False, f"title too short ({n} chars)"
    if n > 200:
        return False, f"title too long ({n} chars)"
    return True, ""


def _body_ok(body: str) -> tuple[bool, str]:
    if not body or not body.strip():
        return False, "body is empty"
    wc = _word_count(body)
    if wc < MIN_WORDS:
        return False, f"body too short ({wc} words, min={MIN_WORDS})"
    if wc > MAX_WORDS:
        return False, f"body too long ({wc} words, max={MAX_WORDS})"
    if _contains_ai_marker(body):
        return False, "body contains AI refusal marker"
    return True, ""


def _excerpt_ok(excerpt: str) -> tuple[bool, str]:
    if not excerpt or len(excerpt.strip()) < 20:
        return False, "excerpt too short"
    return True, ""


def score_article(title: str, excerpt: str, body: str) -> tuple[float, list[str]]:
    """
    Score a rewritten article.

    Returns:
        (score, issues) where score is 0.0–1.0 and issues is a list of failure strings.
        score >= QUALITY_THRESHOLD means the article passes.
    """
    checks = {
        "title":   _title_ok(title),
        "body":    _body_ok(body),
        "excerpt": _excerpt_ok(excerpt),
    }

    issues = [msg for key, (ok, msg) in checks.items() if not ok and msg]
    passed = sum(1 for ok, _ in checks.values() if ok)
    score  = round(passed / len(checks), 2)

    # Bonus: extra words = slightly higher score
    if not issues:
        wc = _word_count(body)
        if wc >= 250:
            score = min(1.0, score + 0.1)

    return score, issues


def passes_quality_gate(title: str, excerpt: str, body: str) -> tuple[bool, float, list[str]]:
    """
    Run the full quality gate.

    Returns:
        (passes, score, issues)
    """
    score, issues = score_article(title, excerpt, body)
    passes = score >= QUALITY_THRESHOLD and not issues
    return passes, score, issues


def estimate_reading_time(body: str) -> int:
    """Estimate reading time in minutes (avg 200 words/minute)."""
    return max(1, round(_word_count(body) / 200))
