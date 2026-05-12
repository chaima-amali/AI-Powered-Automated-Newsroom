"""
db/repository.py (v2)
----------------------
All database operations for the newsroom pipeline.

CRITICAL BUGS FIXED vs v1:
  1. upsert_article() returned bool (True/False) but True/False gave no
     article ID for subsequent image download. Now returns (id, image_url)
     tuple on insert, or None on conflict/error.

  2. bulk_update_embeddings_and_clusters() called
       UPDATE articles ... FROM (VALUES %s) AS v(id,embedding,...) WHERE a.id=v.id::bigint
     but if embedding was a Python list (not a pgvector-formatted string) the
     CAST to ::vector failed silently. Fixed: convert embedding lists to
     pgvector wire format "[x,y,z]" before passing to execute_values.

  3. fetch_unprocessed_articles() filtered WHERE embedding IS NULL — this excluded
     articles that had embeddings but no cluster_id, so re-runs couldn't
     reassign articles to new clusters. Fixed: filter on is_processed=FALSE only.

  4. write_summary() had no error field — if summary_text was empty string it
     would violate NOT NULL on summaries.summary_text. Added guard.

  5. generate_unique_slug() opened two cursors (one for SELECT, one later).
     Now uses a single cursor in a with block.

  6. scrape_runs table had no run_id returned on start — fixed to return id.

  7. cluster_id conversion from full SHA256/UUID hex to INT/BIGINT caused overflow.
      cluster_id is now BIGINT in the schema, and we generate deterministic IDs
      using truncated SHA256 (15 hex chars) that fit safely in BIGINT.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
import uuid
from collections import Counter
from datetime import date, datetime
from typing import Optional, Sequence

from psycopg2.extras import execute_values

from db.connection import get_conn, get_cursor

logger = logging.getLogger(__name__)


def get_max_cluster_id() -> Optional[int]:
    """Return the current maximum cluster_id in the DB, or None if table is empty."""
    with get_cursor() as cur:
        cur.execute("SELECT MAX(cluster_id) FROM clusters")
        row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else None
    """
    Generate a deterministic cluster_id from text, safe for BIGINT.

    Uses SHA256 truncated to 15 hex chars, which stays below PostgreSQL BIGINT
    max value (9223372036854775807).
    """
    return int(
        hashlib.sha256(text.encode()).hexdigest()[:15],
        16
    )


# ── Utils ─────────────────────────────────────────────────────────────────────

def _norm_date(d):
    if d is None:
        return None
    if isinstance(d, date):
        return d
    return datetime.strptime(str(d), "%Y-%m-%d").date()


def _norm_langs(langs) -> list:
    """Convert language input (tuple, list, or None) to list for psycopg2 ANY() binding."""
    if not langs:
        return ["ar", "fr", "en"]
    return list(langs) if isinstance(langs, tuple) else [s.strip().lower() for s in langs if s.strip()] or ["ar", "fr", "en"]


def _vec_str(v) -> Optional[str]:
    """Convert a Python list/ndarray to pgvector wire format '[x,y,z]'."""
    if v is None:
        return None
    if isinstance(v, str):
        return v  # already formatted
    try:
        return "[" + ",".join(str(float(x)) for x in v) + "]"
    except Exception:
        return None


# ── Scrape runs ───────────────────────────────────────────────────────────────

def start_scrape_run(total_sources: int) -> int:
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO scrape_runs (total_sources, run_status) VALUES (%s, 'running') RETURNING id",
            (total_sources,),
        )
        return int(cur.fetchone()[0])


def finish_scrape_run(run_id: int, fetched: int, inserted: int, failed: int,
                      status: str = "completed") -> None:
    with get_cursor() as cur:
        cur.execute(
            """UPDATE scrape_runs
               SET finished_at=NOW(), total_fetched=%s, total_inserted=%s,
                   total_failed=%s, run_status=%s
               WHERE id=%s""",
            (fetched, inserted, failed, status, run_id),
        )


# ── Sources ───────────────────────────────────────────────────────────────────

def ensure_source(name: str, rss_url: str, base_url: str, language: str = "ar") -> int:
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO sources (name, rss_url, base_url, language)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (name) DO UPDATE SET rss_url = EXCLUDED.rss_url
               RETURNING id""",
            (name, rss_url, base_url, language),
        )
        return int(cur.fetchone()[0])


# ── Articles — write ──────────────────────────────────────────────────────────

def upsert_article(article: dict) -> Optional[tuple[int, Optional[str]]]:
    """
    Insert article, skipping on URL conflict.

    Returns:
        (article_id, image_url)  when a new row was inserted
        None                     when the URL already exists (duplicate)

    BUG FIX: original returned bool — callers couldn't get article_id for
    image download. Now returns the real DB id.
    """
    row = {
        **article,
        "discovered_from": article.get("discovered_from", "rss"),
        "is_paywalled":    article.get("is_paywalled", False),
        "scrape_status":   article.get("scrape_status", "success"),
        "error_message":   article.get("error_message"),
    }

    # Safety net: never insert articles with truly empty content.
    # The scraper already filters these, but guard here too.
    content = row.get("content") or ""
    if not content.strip():
        logger.debug("upsert_article: skipping article with no content: %s", row.get("url"))
        return None
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO articles (
                   title, content, summary, author, language, source_id, source_name,
                   url, section, discovered_from, published_at, tags, image_url,
                   word_count, is_paywalled, scrape_status, error_message
               ) VALUES (
                   %(title)s, %(content)s, %(summary)s, %(author)s, %(language)s,
                   %(source_id)s, %(source_name)s, %(url)s, %(section)s,
                   %(discovered_from)s, %(published_at)s, %(tags)s, %(image_url)s,
                   %(word_count)s, %(is_paywalled)s, %(scrape_status)s, %(error_message)s
               )
               ON CONFLICT (url) DO NOTHING
               RETURNING id, image_url""",
            row,
        )
        fetched = cur.fetchone()
    if fetched is None:
        return None  # duplicate
    return (int(fetched[0]), fetched[1])


def update_article_image(article_id: int, local_path: str) -> None:
    with get_cursor() as cur:
        cur.execute(
            "UPDATE articles SET image_local_path=%s, updated_at=NOW() WHERE id=%s",
            (local_path, article_id),
        )


# ── Articles — read for embedding ─────────────────────────────────────────────

def fetch_unprocessed_articles(
    batch_size: int = 256,
    after_id: int = 0,
    target_date=None,
    allowed_languages=None,
) -> list[dict]:
    """
    BUG FIX: removed 'AND embedding IS NULL' condition — articles with
    embeddings but without cluster_id would never be reprocessed.
    Now filters purely on is_processed=FALSE.
    """
    qd   = _norm_date(target_date)
    langs = _norm_langs(allowed_languages)
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """SELECT id, title, content, summary, tags, source_id, source_name,
                      language, embedding, published_at::date AS article_date
               FROM articles
               WHERE scrape_status = 'success'
                 AND id > %s
                 AND published_at IS NOT NULL
                 AND lower(COALESCE(language, '')) = ANY(%s)
                 AND (%s::date IS NULL OR published_at::date = %s::date)
                 AND is_processed = FALSE
               ORDER BY id
               LIMIT %s""",
            (after_id, langs, qd, qd, batch_size),
        )
        return [dict(r) for r in cur.fetchall()]


def count_unprocessed_articles(target_date=None, allowed_languages=None) -> int:
    qd    = _norm_date(target_date)
    langs = _norm_langs(allowed_languages)
    with get_cursor() as cur:
        cur.execute(
            """SELECT COUNT(*) FROM articles
               WHERE scrape_status = 'success'
                 AND published_at IS NOT NULL
                 AND lower(COALESCE(language, '')) = ANY(%s)
                 AND (%s::date IS NULL OR published_at::date = %s::date)
                 AND is_processed = FALSE""",
            (langs, qd, qd),
        )
        return int(cur.fetchone()[0])


def fetch_processed_article_samples(limit: int = 8) -> list[dict]:
    """Return a small sample of processed articles for verification/debug output."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """SELECT id, title, cluster_id, cluster_tag, embedding_model_version, embedding
               FROM articles
               WHERE is_processed = TRUE
               ORDER BY updated_at DESC NULLS LAST, id DESC
               LIMIT %s""",
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


# ── Bulk embedding update ─────────────────────────────────────────────────────

def bulk_update_embeddings_and_clusters(records: list[dict]) -> None:
    """
    BUG FIX: embedding was passed as Python list → pgvector CAST failed.
    Now explicitly formats as '[x,y,z]' string before execute_values.
    """
    if not records:
        return

    article_rows = [
        (
            int(r["id"]),
            _vec_str(r.get("embedding")),   # BUG FIX: convert to pgvector format
            r.get("cluster_id"),
            r.get("embedding_model_version"),
            r.get("cluster_tag_str"),        # BUG FIX: was r.get("tag") — key never existed
        )
        for r in records
    ]

    ac_rows  = [(int(r["id"]), int(r["cluster_id"])) for r in records if r.get("cluster_id") is not None]
    null_ids = [int(r["id"]) for r in records if r.get("cluster_id") is None]

    cluster_payload: dict[int, dict] = {}
    for r in records:
        cid = r.get("cluster_id")
        if cid is None:
            continue
        cid = int(cid)
        p = cluster_payload.setdefault(cid, {"tags": [], "dates": [], "snippets": []})
        # BUG FIX: use "cluster_tag_str" (set by pipeline) not "tag" (never set)
        p["tags"].append(str(r.get("cluster_tag_str") or "untagged"))
        p["dates"].append(str(r.get("article_date") or date.today().isoformat()))
        p["snippets"].append(str(r.get("combined_text_source") or ""))

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Upsert clusters
            if cluster_payload:
                crow = []
                for cid, p in cluster_payload.items():
                    tags = [t for t in p["tags"] if t.strip()]
                    cnt  = Counter(tags)
                    best = sorted(t for t, c in cnt.items() if c == max(cnt.values()))[0] if tags else "untagged"
                    dates = sorted(d for d in p["dates"] if d.strip())
                    crow.append((
                        cid, best,
                        dates[0] if dates else date.today().isoformat(),
                        "\n".join(p["snippets"]).strip(),
                    ))
                execute_values(
                    cur,
                    """INSERT INTO clusters (cluster_id, tag, article_date, article_count, combined_text)
                       VALUES %s
                       ON CONFLICT (cluster_id) DO UPDATE
                         SET tag=EXCLUDED.tag, article_date=EXCLUDED.article_date,
                             combined_text=EXCLUDED.combined_text,
                             article_count=(SELECT COUNT(*) FROM articles WHERE cluster_id=EXCLUDED.cluster_id),
                             created_at=NOW()""",
                    crow,
                    template="(%s, %s, %s, 0, %s)",
                    page_size=200,
                )

            # Update articles
            execute_values(
                cur,
                """UPDATE articles AS a SET
                     embedding = COALESCE(v.embedding::vector, a.embedding),
                     cluster_id = v.cluster_id::bigint,
                     embedding_model_version = COALESCE(v.emv, a.embedding_model_version),
                     cluster_tag = COALESCE(v.ctag, a.cluster_tag),
                     is_processed = TRUE,
                     updated_at = NOW()
                   FROM (VALUES %s) AS v(id, embedding, cluster_id, emv, ctag)
                   WHERE a.id = v.id::bigint""",
                article_rows,
                template="(%s, %s, %s, %s, %s)",
                page_size=500,
            )

            # Maintain article_cluster join table
            if ac_rows:
                execute_values(
                    cur,
                    """INSERT INTO article_cluster (article_id, cluster_id) VALUES %s
                       ON CONFLICT (article_id) DO UPDATE SET cluster_id=EXCLUDED.cluster_id, created_at=NOW()""",
                    ac_rows,
                    template="(%s, %s)",
                    page_size=500,
                )
            if null_ids:
                cur.execute("DELETE FROM article_cluster WHERE article_id = ANY(%s)", (null_ids,))

            # Refresh cluster counts
            if cluster_payload:
                for cid in cluster_payload:
                    cur.execute(
                        "UPDATE clusters SET article_count=(SELECT COUNT(*) FROM articles WHERE cluster_id=%s) WHERE cluster_id=%s",
                        (cid, cid),
                    )
                cur.execute(
                    "DELETE FROM clusters c WHERE NOT EXISTS (SELECT 1 FROM articles a WHERE a.cluster_id=c.cluster_id)"
                )

    logger.info("✅ Persisted embeddings/clusters for %d articles", len(records))


# ── Summarizer ────────────────────────────────────────────────────────────────

def fetch_unsummarized_clusters() -> list[dict]:
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """SELECT c.cluster_id, c.tag, c.article_date, c.article_count
               FROM clusters c
               LEFT JOIN summaries s ON c.cluster_id = s.cluster_id
               WHERE s.cluster_id IS NULL AND c.article_count > 0"""
        )
        return [dict(r) for r in cur.fetchall()]


def fetch_articles_for_cluster(cluster_id: int) -> list[dict]:
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """SELECT title, content, source_name AS source, language AS lang,
                      url, image_url, image_local_path
               FROM articles WHERE cluster_id = %s""",
            (cluster_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def write_summary(cluster_id: int, result: dict) -> None:
    """BUG FIX: guard against empty summary_text violating NOT NULL."""
    text = result.get("summary_text", "") or ""
    if not text.strip():
        logger.warning("Cluster %d: empty summary_text — skipping write", cluster_id)
        return
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO summaries (cluster_id, summary_text, summary_lang, summary_model, strategy)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (cluster_id) DO UPDATE
                 SET summary_text=EXCLUDED.summary_text,
                     summary_model=EXCLUDED.summary_model,
                     strategy=EXCLUDED.strategy,
                     summarized_at=NOW()""",
            (
                cluster_id,
                text,
                result.get("summary_lang", "en"),
                result.get("summary_model", "unknown"),
                result.get("strategy", "unknown"),
            ),
        )


# ── Rewriter ──────────────────────────────────────────────────────────────────

def fetch_unrewritten_summaries() -> list[dict]:
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """SELECT s.id AS summary_id, s.cluster_id, s.summary_text, s.strategy,
                      c.tag, c.article_date, c.article_count
               FROM summaries s
               JOIN clusters c ON c.cluster_id = s.cluster_id
               LEFT JOIN published_articles pa ON pa.cluster_id = s.cluster_id
               WHERE pa.id IS NULL
               ORDER BY c.article_date DESC, c.article_count DESC"""
        )
        return [dict(r) for r in cur.fetchall()]


def get_articles_in_cluster(cluster_id: int) -> list[dict]:
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """SELECT id, title, content, image_url, image_local_path,
                      source_name, published_at
               FROM articles WHERE cluster_id = %s ORDER BY id""",
            (cluster_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def insert_published_article(data: dict) -> int:
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO published_articles (
                   cluster_id, source_article_ids, title, slug, excerpt, body,
                   raw_summary, cover_image_url, cover_image_local, image_alt_text,
                   category, tags, language, seo_title, seo_description,
                   reading_time_min, original_published_at, status, rewrite_model, quality_score
               ) VALUES (
                   %(cluster_id)s, %(source_article_ids)s, %(title)s, %(slug)s,
                   %(excerpt)s, %(body)s, %(raw_summary)s, %(cover_image_url)s,
                   %(cover_image_local)s, %(image_alt_text)s, %(category)s, %(tags)s,
                   %(language)s, %(seo_title)s, %(seo_description)s, %(reading_time_min)s,
                   %(original_published_at)s, %(status)s, %(rewrite_model)s, %(quality_score)s
               ) RETURNING id""",
            data,
        )
        return int(cur.fetchone()[0])


def publish_article(article_id: int) -> None:
    with get_cursor() as cur:
        cur.execute(
            "UPDATE published_articles SET status='published', published_at=NOW(), updated_at=NOW() WHERE id=%s",
            (article_id,),
        )


def get_cluster_info(cluster_id: int) -> Optional[dict]:
    with get_cursor(dict_cursor=True) as cur:
        cur.execute("SELECT * FROM clusters WHERE cluster_id=%s", (cluster_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def fetch_articles_for_cluster_full(cluster_id: int) -> list[dict]:
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """SELECT id, title, content, image_url, image_local_path,
                      source_name, published_at
               FROM articles WHERE cluster_id=%s ORDER BY id""",
            (cluster_id,),
        )
        return [dict(r) for r in cur.fetchall()]


# ── Slug util ─────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)[:100]


def generate_unique_slug(title: str, date_str: str) -> str:
    """BUG FIX: used two separate cursors; now uses one."""
    base      = slugify(title) or "article"
    candidate = f"{base}-{date_str}"
    with get_cursor() as cur:
        cur.execute("SELECT id FROM published_articles WHERE slug=%s", (candidate,))
        if cur.fetchone():
            candidate = f"{base}-{date_str}-{uuid.uuid4().hex[:6]}"
    return candidate


def update_published_embedding(article_id: int, embedding) -> None:
    with get_cursor() as cur:
        cur.execute(
            "UPDATE published_articles SET embedding=%s::vector WHERE id=%s",
            (_vec_str(embedding), article_id),
        )
