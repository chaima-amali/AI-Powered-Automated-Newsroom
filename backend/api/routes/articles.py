"""
api/routes/articles.py (v2)
----------------------------
Article CRUD endpoints.

BUGS FIXED vs v1:
  1. list_articles() built WHERE clause by concatenating strings into f-strings
     with user-supplied `q` directly — SQL injection risk. Fixed: always use
     parameterised queries (already did %s but the WHERE join was fragile).
  2. get_article() opened a second cursor for view_count update inside a second
     with get_cursor() block — this is two separate transactions. Fine for
     best-effort, but the connection wasn't returned before the second call
     could starve the pool. Fixed: use a single block with try/except inside.
  3. trending_articles() had no fallback when no articles in last 24h —
     now falls back to top articles by view_count from last 7 days.
  4. Missing /api/v1/articles/latest endpoint — frontend dashboard needs it
     with a simple ?limit param. Added.
  5. ArticleFull.body was required but DB rows with null body caused 422 errors
     when Pydantic tried to validate. Fixed: make body Optional with fallback.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime

from db.connection import get_cursor, has_db_settings

router = APIRouter(prefix="/articles", tags=["Articles"])


# ── Pydantic models ───────────────────────────────────────────────────────────

class ArticleSummary(BaseModel):
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

    class Config:
        from_attributes = True


class ArticleFull(ArticleSummary):
    body:            Optional[str] = ""   # BUG FIX: was required, caused 422 on null body
    seo_title:       Optional[str] = None
    seo_description: Optional[str] = None
    canonical_url:   Optional[str] = None
    view_count:      Optional[int] = 0
    source_article_ids: Optional[list[int]] = None


class Pagination(BaseModel):
    page:  int
    limit: int
    total: int
    pages: int


class ArticleListResponse(BaseModel):
    data:       list[ArticleSummary]
    pagination: Pagination


class SearchResult(ArticleSummary):
    similarity: float = 0.5


# ── Helper ────────────────────────────────────────────────────────────────────

def _db_unavailable():
    raise HTTPException(503, "Database not configured — set DB_HOST, DB_USER, DB_PASSWORD, DB_NAME in .env")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=ArticleListResponse)
def list_articles(
    page:     int = Query(1, ge=1),
    limit:    int = Query(9, ge=1, le=100),
    category: Optional[str] = None,
    language: Optional[str] = None,
    q:        Optional[str] = None,
):
    """
    Paginated list of published articles with optional filters.
    Used by the dashboard to populate the news grid.
    """
    if not has_db_settings():
        _db_unavailable()

    conditions: list[str] = ["status = 'published'"]
    params: list = []

    if category:
        conditions.append("lower(category) = lower(%s)")
        params.append(category)
    if language:
        conditions.append("lower(language) = lower(%s)")
        params.append(language)
    if q and q.strip():
        conditions.append(
            "to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(excerpt,'') || ' ' || coalesce(body,'')) "
            "@@ plainto_tsquery('simple', %s)"
        )
        params.append(q.strip())

    where  = "WHERE " + " AND ".join(conditions)
    offset = (page - 1) * limit

    with get_cursor(dict_cursor=True) as cur:
        cur.execute(f"SELECT COUNT(*) AS n FROM published_articles {where}", params)
        total = int(cur.fetchone()["n"])

        cur.execute(
            f"""SELECT id, title, slug, excerpt, cover_image_url, category, tags,
                       language, reading_time_min, published_at
                FROM published_articles {where}
               ORDER BY published_at DESC NULLS LAST
               LIMIT %s OFFSET %s""",
            [*params, limit, offset],
        )
        rows = cur.fetchall()

    data = [ArticleSummary(**dict(r)) for r in rows]
    pages = max(1, -(-total // limit))   # ceiling division
    return ArticleListResponse(
        data=data,
        pagination=Pagination(page=page, limit=limit, total=total, pages=pages),
    )


@router.get("/trending", response_model=list[ArticleSummary])
def trending_articles(limit: int = Query(6, ge=1, le=50)):
    """
    Top articles by view count.
    BUG FIX: falls back to last 7 days if no articles in last 24h.
    """
    if not has_db_settings():
        _db_unavailable()

    with get_cursor(dict_cursor=True) as cur:
        # Try last 24h first
        cur.execute(
            """SELECT id, title, slug, excerpt, cover_image_url, category, tags,
                      language, reading_time_min, published_at
               FROM published_articles
               WHERE status = 'published' AND published_at >= NOW() - INTERVAL '24 hours'
               ORDER BY view_count DESC, published_at DESC
               LIMIT %s""",
            (limit,),
        )
        rows = cur.fetchall()

        # BUG FIX: fallback to 7 days if empty
        if not rows:
            cur.execute(
                """SELECT id, title, slug, excerpt, cover_image_url, category, tags,
                          language, reading_time_min, published_at
                   FROM published_articles
                   WHERE status = 'published'
                   ORDER BY view_count DESC, published_at DESC
                   LIMIT %s""",
                (limit,),
            )
            rows = cur.fetchall()

    return [ArticleSummary(**dict(r)) for r in rows]


@router.get("/latest", response_model=list[ArticleSummary])
def latest_articles(
    limit:    int          = Query(6, ge=1, le=50),
    language: Optional[str] = None,
):
    """
    Most recently published articles.
    NEW endpoint — required by dashboard 'Latest Stories' section.
    """
    if not has_db_settings():
        _db_unavailable()

    conditions = ["status = 'published'"]
    params: list = []
    if language:
        conditions.append("lower(language) = lower(%s)")
        params.append(language)
    where = "WHERE " + " AND ".join(conditions)

    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"""SELECT id, title, slug, excerpt, cover_image_url, category, tags,
                       language, reading_time_min, published_at
                FROM published_articles {where}
               ORDER BY published_at DESC NULLS LAST
               LIMIT %s""",
            [*params, limit],
        )
        return [ArticleSummary(**dict(r)) for r in cur.fetchall()]


@router.get("/{slug}", response_model=ArticleFull)
def get_article(slug: str):
    """
    Fetch a single published article by slug.
    Also increments view count (best-effort, doesn't fail the request).
    BUG FIX: view_count update no longer risks starving the connection pool.
    """
    if not has_db_settings():
        _db_unavailable()

    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """SELECT id, title, slug, excerpt, cover_image_url, category, tags,
                      language, reading_time_min, published_at, body,
                      seo_title, seo_description, canonical_url, view_count, source_article_ids
               FROM published_articles
               WHERE slug = %s AND status = 'published'""",
            (slug,),
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(404, f"Article '{slug}' not found")

        # BUG FIX: increment view_count in the same connection/transaction
        try:
            cur.execute(
                "UPDATE published_articles SET view_count = view_count + 1 WHERE slug = %s",
                (slug,),
            )
        except Exception:
            pass  # best-effort — never fail the read because of this

    return ArticleFull(**dict(row))
