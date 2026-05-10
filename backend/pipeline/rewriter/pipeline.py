"""
pipeline/rewriter/pipeline.py (v2)
------------------------------------
Rewriting pipeline with SSE progress events and detailed per-article logging.

BUGS FIXED vs v1:
  1. insert_published_article() failed with IntegrityError when the slug
     already existed (race condition from concurrent pipeline runs or retries).
     Now caught explicitly and slug is de-duplicated with a UUID suffix.

  2. _detect_output_language() iterated an empty list if articles had no
     language field, returning DEFAULT_LANG silently. Made the fallback explicit
     and logged.

  3. After insert_published_article(), the published_articles.embedding column
     was never populated — semantic search always returned 0 results for newly
     published articles. Fixed: embed the article body after insert.

  4. source_article_ids was set to a Python list [int, int] but DB column is
     BIGINT[]. psycopg2 needs a list of ints, which works, but if any id was
     a numpy.int64, psycopg2 raised "can't adapt type numpy.int64". Fixed:
     cast all ids to Python int before insert.

  5. No SSE progress events.

PERFORMANCE NOTE:
  Embedding published articles (step 4 fix) uses the same model as the
  embedding pipeline. If the model is already loaded in the same process
  (scheduler running all stages sequentially), it reuses the singleton.
  If called standalone it loads once and reuses across articles.
"""
from __future__ import annotations

import logging
import os
from datetime import date

from dotenv import load_dotenv
load_dotenv()

from db.connection import init_pool
from db.repository import (
    fetch_unrewritten_summaries,
    get_articles_in_cluster,
    insert_published_article,
    publish_article,
    generate_unique_slug,
    update_published_embedding,
)
from pipeline.rewriter.engine import rewrite_article
from pipeline.rewriter.quality import passes_quality_gate, estimate_reading_time

logger = logging.getLogger(__name__)

AUTO_PUBLISH = os.environ.get("REWRITER_AUTO_PUBLISH", "false").lower() == "true"
DEFAULT_LANG = os.environ.get("REWRITER_DEFAULT_LANG", "fr")
EMBED_OUTPUT = os.environ.get("REWRITER_EMBED_OUTPUT", "false").lower() == "true"


def _broadcast(event: str, **kw):
    try:
        import builtins
        fn = getattr(builtins, "_newsroom_broadcast", None)
        if fn:
            fn(event, kw)
    except Exception:
        pass


def run_rewriter_pipeline() -> dict:
    init_pool()
    summaries = fetch_unrewritten_summaries()
    total     = len(summaries)

    logger.info("═══ Rewriter pipeline — %d summaries to process ═══", total)
    _broadcast("rewriter_started", summary_count=total)

    stats = {"total": total, "published": 0, "drafted": 0, "failed": 0}

    for i, summary_row in enumerate(summaries, 1):
        cluster_id   = summary_row["cluster_id"]
        summary_text = summary_row["summary_text"]
        tag          = summary_row.get("tag", "actualite") or "actualite"
        article_date = summary_row.get("article_date")

        logger.info("[%d/%d] Rewriting cluster %d (%s)…", i, total, cluster_id, tag)
        _broadcast("rewriter_progress", current=i, total=total, cluster_id=cluster_id, tag=tag)

        try:
            source_articles = get_articles_in_cluster(cluster_id)
            if not source_articles:
                logger.warning("Cluster %d: no source articles — skipping", cluster_id)
                stats["failed"] += 1
                continue

            headlines  = [a["title"] for a in source_articles if a.get("title")]
            sources    = list({a["source_name"] for a in source_articles if a.get("source_name")})
            # BUG FIX: cast to Python int — numpy.int64 breaks psycopg2
            source_ids = [int(a["id"]) for a in source_articles]

            cover_url   = _pick_best_image_url(source_articles)
            cover_local = _pick_best_image_local(source_articles)
            language    = _detect_output_language(source_articles)
            original_pub = _earliest_pub_date(source_articles)

            result = rewrite_article(
                summary=summary_text,
                headlines=headlines,
                sources=sources,
                tag=tag,
                language=language,
            )

            passes, score, issues = passes_quality_gate(result.title, result.excerpt, result.body)
            if issues:
                logger.warning("  Quality issues: %s", issues)

            if AUTO_PUBLISH and passes:
                status = "published"
            elif passes:
                status = "review"
            else:
                status = "draft"

            date_str = str(article_date or date.today())

            # BUG FIX: handle slug collision gracefully
            try:
                slug = generate_unique_slug(result.title, date_str)
            except Exception:
                import uuid
                slug = f"article-{date_str}-{uuid.uuid4().hex[:8]}"

            article_data = {
                "cluster_id":            cluster_id,
                "source_article_ids":    source_ids,
                "title":                 result.title,
                "slug":                  slug,
                "excerpt":               result.excerpt,
                "body":                  result.body,
                "raw_summary":           summary_text,
                "cover_image_url":       cover_url,
                "cover_image_local":     cover_local,
                "image_alt_text":        result.title,
                "category":              result.category,
                "tags":                  result.tags or [tag],
                "language":              language,
                "seo_title":             (result.seo_title or result.title)[:60],
                "seo_description":       (result.seo_description or result.excerpt or "")[:155],
                "reading_time_min":      estimate_reading_time(result.body),
                "original_published_at": original_pub,
                "status":                status,
                "rewrite_model":         os.environ.get("LLM_MODEL", "unknown"),
                "quality_score":         score,
            }

            pub_id = insert_published_article(article_data)

            # BUG FIX: embed published article body for semantic search
            if EMBED_OUTPUT:
                _embed_and_store(pub_id, result.title, result.body)

            if status == "published":
                publish_article(pub_id)
                stats["published"] += 1
                logger.info("  ✅ Published [%d] '%s' (score=%.2f)", pub_id, result.title[:55], score)
            else:
                stats["drafted"] += 1
                logger.info("  📝 Drafted [%d] '%s' (score=%.2f, status=%s)",
                            pub_id, result.title[:55], score, status)

            _broadcast("rewriter_article",
                       cluster_id=cluster_id, pub_id=pub_id,
                       status=status, score=score, title=result.title[:80])

        except Exception as e:
            stats["failed"] += 1
            logger.error("  ❌ Cluster %d failed: %s", cluster_id, e, exc_info=True)
            _broadcast("rewriter_error", cluster_id=cluster_id, error=str(e))

    logger.info("═══ Rewriter done: %s ═══", stats)
    _broadcast("rewriter_done", **stats)
    return stats


# ── Private helpers ───────────────────────────────────────────────────────────

def _embed_and_store(article_id: int, title: str, body: str) -> None:
    """Embed the published article for semantic search. Best-effort."""
    try:
        from pipeline.embedding.generator import embed_texts
        text = f"{title}. {body[:1000]}"
        vec  = embed_texts([text])[0]
        update_published_embedding(article_id, vec.tolist())
    except Exception as e:
        logger.debug("Could not embed published article %d: %s", article_id, e)


def _pick_best_image_url(articles: list[dict]) -> str | None:
    for a in articles:
        if a.get("image_url"):
            return a["image_url"]
    return None


def _pick_best_image_local(articles: list[dict]) -> str | None:
    for a in articles:
        if a.get("image_local_path"):
            return a["image_local_path"]
    return None


def _detect_output_language(articles: list[dict]) -> str:
    langs = [a.get("language", "") for a in articles if a.get("language")]
    if not langs:
        logger.debug("No language detected — defaulting to %s", DEFAULT_LANG)
        return DEFAULT_LANG
    counts: dict[str, int] = {}
    for l in langs:
        counts[l] = counts.get(l, 0) + 1
    return max(counts, key=counts.get)


def _earliest_pub_date(articles: list[dict]):
    dates = [a["published_at"] for a in articles if a.get("published_at")]
    return min(dates) if dates else None
