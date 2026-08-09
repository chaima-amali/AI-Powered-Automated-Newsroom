"""
api/routes/health.py (v2)
--------------------------
Health check and category listing endpoints.

BUGS FIXED:
  1. v_pipeline_health VIEW query selected * — if schema changes, column order
     mismatch caused Pydantic validation to silently use wrong values.
     Fixed: SELECT named columns explicitly.
  2. No fallback when DB is unavailable — crashed at startup if pool not ready.
"""
from __future__ import annotations

from typing import Optional
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from db.connection import get_cursor, has_db_settings

router = APIRouter(tags=["System"])


class PipelineHealth(BaseModel):
    total_articles:    int = 0
    pending_embedding: int = 0
    total_clusters:    int = 0
    total_summaries:   int = 0
    published_count:   int = 0
    draft_count:       int = 0
    last_scrape_at:    Optional[datetime] = None
    last_generated_at: Optional[datetime] = None


class CategoryStat(BaseModel):
    category:      str
    article_count: int


@router.get("/health", response_model=PipelineHealth)
def health():
    """Pipeline health summary — publicly readable. Returns zeros when DB unavailable."""
    if not has_db_settings():
        return PipelineHealth()

    try:
        with get_cursor(dict_cursor=True) as cur:
            # BUG FIX: select named columns to avoid positional mismatch
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM articles WHERE scrape_status='success')              AS total_articles,
                    (SELECT COUNT(*) FROM articles WHERE is_processed=FALSE AND scrape_status='success') AS pending_embedding,
                    (SELECT COUNT(*) FROM clusters)                                             AS total_clusters,
                    (SELECT COUNT(*) FROM summaries)                                            AS total_summaries,
                    (SELECT COUNT(*) FROM published_articles WHERE status='published')          AS published_count,
                    (SELECT COUNT(*) FROM published_articles WHERE status='draft')              AS draft_count,
                    (SELECT MAX(started_at) FROM scrape_runs)                                   AS last_scrape_at,
                    (SELECT MAX(generated_at) FROM published_articles)                          AS last_generated_at
            """)
            row = cur.fetchone()
        return PipelineHealth(**dict(row))
    except Exception:
        return PipelineHealth()


@router.get("/categories", response_model=list[CategoryStat])
def list_categories():
    """List all categories with article counts (includes draft/review so filter always works)."""
    if not has_db_settings():
        return []
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """SELECT category, COUNT(*) AS article_count
               FROM published_articles
               WHERE status IN ('published', 'draft', 'review') AND category IS NOT NULL
               GROUP BY category ORDER BY article_count DESC"""
        )
        return [CategoryStat(**dict(r)) for r in cur.fetchall()]
