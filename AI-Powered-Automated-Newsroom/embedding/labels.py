"""Tag normalization: map French + Arabic variants to canonical labels.

This module implements the mapping dictionary provided by the user and a
normalize_tag() helper suitable for use in the pipeline.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Iterable, Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

# Canonical mapping (keeps entries small and focused). Add more variants as needed.
_MAPPING = {
    "politics": {"politique", "gouvernement", "etat", "état", "parlement", "elections", "élections", "diplomatie", "سياسة", "الحكومة", "الدولة", "البرلمان", "انتخابات", "دبلوماسية"},
    "economy": {"economie", "économie", "finance", "marche", "marché", "inflation", "commerce", "اقتصاد", "مالية", "سوق", "تضخم", "تجارة"},
    "society": {"societe", "société", "social", "population", "vie quotidienne", "مجتمع", "اجتماعي", "سكان", "حياة يومية"},
    "international": {"international", "monde", "etranger", "étranger", "دولي", "العالم", "الخارج", "أخبار العالم"},
    "sports": {"sport", "football", "match", "كرة القدم", "رياضة", "مباراة"},
    "technology": {"technologie", "numerique", "numérique", "informatique", "ia", "تكنولوجيا", "رقمي", "معلوماتية", "ذكاء اصطناعي"},
    "health": {"sante", "santé", "hopital", "hôpital", "medecine", "médecine", "صحة", "مستشفى", "طب"},
    "education": {"education", "éducation", "ecole", "école", "universite", "université", "تعليم", "مدرسة", "جامعة"},
    "environment": {"environnement", "climat", "pollution", "بيئة", "مناخ", "تلوث"},
    "culture": {"culture", "art", "cinema", "cinéma", "musique", "ثقافة", "فن", "سينما", "موسيقى"},
    "religion": {"religion", "islam", "mosquee", "mosquée", "دين", "إسلام", "اسلام", "مسجد"},
    "security": {"securite", "sécurité", "police", "terrorisme", "أمن", "امن", "شرطة", "إرهاب", "ارهاب"},
    "justice": {"justice", "tribunal", "loi", "عدالة", "محكمة", "قانون"},
    "transport": {"transport", "route", "trafic", "نقل", "طريق", "مرور"},
    "energy": {"energie", "énergie", "petrole", "pétrole", "gaz", "طاقة", "نفط", "غاز"},
    "agriculture": {"agriculture", "agriculteur", "زراعة", "فلاح"},
    "tourism": {"tourisme", "voyage", "سياحة", "سفر"},
    "science": {"science", "recherche", "علم", "بحث"},
    "media": {"media", "média", "presse", "journal", "إعلام", "اعلام", "صحافة"},
    "local_news": {"national", "nation", "algerie", "algérie", "local", "اخبار الجزائر", "وطني","الوطني","المحلي", "محلي"},
    "press_release": {"communiqué de presse", "بيان صحفي"},
    "travel": {"voyages" ,"voyage" , "سفر" },


}

# Reverse lookup for fast membership checks
_REVERSE: dict[str, str] = {}
for can, variants in _MAPPING.items():
    for v in variants:
        _REVERSE[v] = can


def _strip_accents(text: str) -> str:
    """Remove accents/diacritics (useful for French variants)."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def normalize_tag(tag: str | None) -> str | None:
    """Normalize a single tag into the canonical label or return a cleaned token.

    Returns canonical label (e.g. 'politics') if a known variant matches; otherwise
    returns a cleaned, lowercased, accent-stripped token suitable for downstream
    fallback labeling.
    """
    if not tag:
        return None
    raw = str(tag).strip().lower()
    if not raw:
        return None

    # direct match (try raw and accent-stripped)
    if raw in _REVERSE:
        return _REVERSE[raw]
    stripped = _strip_accents(raw)
    if stripped in _REVERSE:
        return _REVERSE[stripped]

    # tokenise common delimiters and check each token
    for token in re.split(r"[\s,;/|\-]+", stripped):
        if not token:
            continue
        if token in _REVERSE:
            return _REVERSE[token]

    # fallback: return accent-free single token
    parts = [p for p in re.split(r"[\s,;/|\-]+", stripped) if p]
    return parts[0] if parts else None


def normalize_tags(tags: Iterable[str] | None) -> list[str]:
    if not tags:
        return []
    out: list[str] = []
    for t in tags:
        n = normalize_tag(t)
        if n:
            out.append(n)
    return out


def normalize_tag_values(value: object) -> list[str]:
    """Normalize any article-level tag payload into unique canonical labels."""
    if value is None:
        return []
    if isinstance(value, str):
        candidates: Sequence[str] = [value]
    elif isinstance(value, Iterable):
        candidates = [str(item) for item in value]
    else:
        candidates = [str(value)]

    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        for token in re.split(r"[\s,;/|\-]+", candidate):
            cleaned = normalize_tag(token)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                normalized.append(cleaned)
    return normalized


def _looks_like_a_la_une(tag: str) -> bool:
    cleaned = _strip_accents(str(tag).strip().lower())
    cleaned = re.sub(r"[\s,;/|\-]+", " ", cleaned).strip()
    return cleaned in {"a la une", "ala une"} or cleaned.replace(" ", "") == "alaune"


def pick_primary_tag_value(value: object) -> str | None:
    """Pick the first usable tag for article-level grouping.

    Rules:
    - if the tag section is NULL, return None
    - if the first tag is "a la une", ignore the article for clustering
    - if multiple tags exist, always use only the first one
    - normalize the selected tag to a canonical label when possible
    """
    if value is None:
        return None

    if isinstance(value, str):
        candidates: Sequence[str] = [value]
    elif isinstance(value, Iterable):
        candidates = [str(item) for item in value]
    else:
        candidates = [str(value)]

    for candidate in candidates:
        raw = str(candidate).strip()
        if not raw:
            continue
        if _looks_like_a_la_une(raw):
            return None

        first_piece = re.split(r"[\s,;/|\-]+", raw)[0]
        normalized = normalize_tag(first_piece)
        return normalized or first_piece.strip().lower() or None

    return None


def _clean_keyword(token: str) -> str:
    token = _strip_accents(token.lower()).strip()
    token = re.sub(r"[^\w\u0600-\u06FF]+", "_", token)
    token = re.sub(r"_+", "_", token).strip("_")
    return token


def extract_cluster_keywords(titles: Iterable[str], max_features: int = 20) -> list[str]:
    """Extract a few representative title keywords for tagless clusters."""
    cleaned_titles = [str(title).strip() for title in titles if str(title).strip()]
    if not cleaned_titles:
        return []

    try:
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=max_features,
            token_pattern=r"(?u)\b\w+\b",
        )
        matrix = vectorizer.fit_transform(cleaned_titles)
    except ValueError:
        return []

    scores = matrix.mean(axis=0).A1
    if scores.size == 0:
        return []

    ordered = np.argsort(scores)[::-1]
    keywords: list[str] = []
    for index in ordered:
        token = vectorizer.get_feature_names_out()[index]
        cleaned = _clean_keyword(token)
        if cleaned and cleaned not in keywords:
            keywords.append(cleaned)
        if len(keywords) >= 3:
            break
    return keywords


def choose_cluster_tag(articles: Sequence[dict]) -> str:
    """Label a cluster from article tags, then title keywords, then unknown."""
    normalized_tags: list[str] = []
    titles: list[str] = []

    for article in articles:
        titles.append(str(article.get("title") or ""))
        tags = article.get("tags")
        if tags is None:
            tags = article.get("tag")
        normalized_tags.extend(normalize_tag_values(tags))

    if normalized_tags:
        counts = Counter(normalized_tags)
        best_count = max(counts.values())
        best_tags = sorted(tag for tag, count in counts.items() if count == best_count)
        return best_tags[0]

    keywords = extract_cluster_keywords(titles)
    if keywords:
        return keywords[0]

    return "unknown"
