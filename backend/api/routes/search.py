"""
api/routes/search.py (v2)
--------------------------
Semantic + full-text search.

BUGS FIXED vs v1:
  1. _embed_query() used hasattr() on a function object to cache the model —
     this is fragile. The model was attached as a function attribute (_model),
     which doesn't survive module reload in development. Fixed: use a
     module-level singleton with proper lazy initialization.
  2. semantic_search() passed the vector string twice in params list for the
     ORDER BY clause but the SELECT also used it — params list order was wrong
     when language filter was added (shifted positions). Fixed: named query
     with explicit param list.
  3. No graceful degradation message to the user when DB is unavailable.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
from pydantic import BaseModel

from db.connection import get_cursor, has_db_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["Search"])


# ── Embedding model singleton ─────────────────────────────────────────────────
_embed_model = None


def _get_embed_model():
    """Lazy singleton — loads once, reuses across requests."""
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        env_model = os.environ.get("EMBEDDING_MODEL_NAME", "sentence-transformers/LaBSE")
        # Enforce LaBSE for query embedding to match the pipeline embeddings.
        model_name = "sentence-transformers/LaBSE"
        if env_model and env_model.lower() != model_name.lower():
            logger.warning(
                "Search endpoint EMBEDDING_MODEL_NAME is '%s' but using '%s' to match pipeline embeddings.",
                env_model,
                model_name,
            )
        logger.info("Loading search embedding model: %s", model_name)
        _embed_model = SentenceTransformer(model_name)
    return _embed_model


def _embed_query(text: str) -> list[float]:
    """Embed a search query using the same model as the pipeline."""
    model = _get_embed_model()
    vec = model.encode(f"query: {text}", normalize_embeddings=True)
    return vec.tolist()


# ── Pydantic models ───────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    id:               int
    title:            str
    slug:             Optional[str] = None
    excerpt:          Optional[str] = None
    cover_image_url:  Optional[str] = None
    category:         Optional[str] = None
    tags:             Optional[list[str]] = None
    language:         Optional[str] = None
    reading_time_min: Optional[int] = None
    published_at:     Optional[datetime] = None
    similarity:       float = 0.5

    class Config:
        from_attributes = True


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[SearchResult])
def semantic_search(
    q:        str           = Query(..., min_length=2, description="Search query"),
    limit:    int           = Query(10, ge=1, le=50),
    language: Optional[str] = None,
):
    """
    Semantic similarity search over published articles.
    Falls back to full-text search if embedding model or pgvector is unavailable.
    """
    if not has_db_settings():
        raise HTTPException(503, "Database not configured")

    if not q.strip():
        raise HTTPException(400, "Query cannot be empty")

    # Try semantic search first
    try:
        embedding   = _embed_query(q)
        vec_str     = "[" + ",".join(str(v) for v in embedding) + "]"

        lang_filter = "AND lower(language) = lower(%(lang)s)" if language else ""
        params = {
            "vec": vec_str,
            "lang": language or "",
            "limit": limit,
        }

        with get_cursor(dict_cursor=True) as cur:
            cur.execute(
                f"""SELECT id, title, slug, excerpt, cover_image_url, category, tags,
                           language, reading_time_min, published_at,
                           1 - (embedding <=> %(vec)s::vector) AS similarity
                    FROM published_articles
                    WHERE status = 'published' AND embedding IS NOT NULL
                    {lang_filter}
                    ORDER BY embedding <=> %(vec)s::vector
                    LIMIT %(limit)s""",
                params,
            )
            rows = cur.fetchall()

        if rows:
            return [SearchResult(**dict(r)) for r in rows]
        # Fall through to FTS if vector search found nothing
    except Exception as e:
        logger.info("Semantic search unavailable (%s) — using full-text fallback", type(e).__name__)

    # Full-text search fallback
    with get_cursor(dict_cursor=True) as cur:
        conditions = [
            "status = 'published'",
            "to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(body,'')) @@ plainto_tsquery('simple', %s)",
        ]
        params_fts: list = [q]
        if language:
            conditions.append("lower(language) = lower(%s)")
            params_fts.append(language)
        params_fts.append(limit)

        where = " AND ".join(conditions)
        cur.execute(
            f"""SELECT id, title, slug, excerpt, cover_image_url, category, tags,
                      language, reading_time_min, published_at, 0.5 AS similarity
               FROM published_articles WHERE {where}
               ORDER BY published_at DESC LIMIT %s""",
            params_fts,
        )
        return [SearchResult(**dict(r)) for r in cur.fetchall()]
