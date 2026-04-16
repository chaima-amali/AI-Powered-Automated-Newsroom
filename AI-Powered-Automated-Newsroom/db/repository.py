"""Database repository layer for scraping and embedding pipeline operations."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional, Sequence

from db.connection import get_conn, get_cursor
from psycopg2.extras import execute_values

logger = logging.getLogger(__name__)


# --- Scrape run helpers --------------------------------------------------------

def start_scrape_run(total_sources: int) -> int:
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO scrape_runs (total_sources, run_status)
            VALUES (%s, 'running')
            RETURNING id
            """,
            (total_sources,),
        )
        return int(cur.fetchone()[0])


def finish_scrape_run(
    run_id: int,
    fetched: int,
    inserted: int,
    failed: int,
    status: str = "completed",
) -> None:
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE scrape_runs
               SET finished_at = NOW(),
                   total_fetched = %s,
                   total_inserted = %s,
                   total_failed = %s,
                   run_status = %s
             WHERE id = %s
            """,
            (fetched, inserted, failed, status, run_id),
        )


# --- Article write/read helpers ------------------------------------------------

def upsert_article(article: dict) -> bool:
    """Insert article and skip when URL already exists."""
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO articles (
                title, content, summary, author, language,
                source_id, source_name, url, section,
                published_at, tags, image_url, word_count,
                is_paywalled, scrape_status, error_message
            ) VALUES (
                %(title)s, %(content)s, %(summary)s, %(author)s, %(language)s,
                %(source_id)s, %(source_name)s, %(url)s, %(section)s,
                %(published_at)s, %(tags)s, %(image_url)s, %(word_count)s,
                %(is_paywalled)s, %(scrape_status)s, %(error_message)s
            )
            ON CONFLICT (url) DO NOTHING
            RETURNING id
            """,
            article,
        )
        row = cur.fetchone()
        return row is not None


def get_source_id(source_name: str) -> Optional[int]:
    with get_cursor() as cur:
        cur.execute("SELECT id FROM sources WHERE name = %s", (source_name,))
        row = cur.fetchone()
    return int(row[0]) if row else None


def ensure_source(name: str, rss_url: str, base_url: str, language: str = "ar") -> int:
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO sources (name, rss_url, base_url, language)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET rss_url = EXCLUDED.rss_url
            RETURNING id
            """,
            (name, rss_url, base_url, language),
        )
        return int(cur.fetchone()[0])


def _normalize_date_filter(target_date: date | str | None) -> date | None:
    if target_date is None:
        return None
    if isinstance(target_date, date):
        return target_date
    return datetime.strptime(target_date, "%Y-%m-%d").date()


def _normalize_languages(allowed_languages: Sequence[str] | None) -> list[str]:
    if not allowed_languages:
        return ["ar", "fr"]
    normalized = [str(item).strip().lower() for item in allowed_languages if str(item).strip()]
    return normalized or ["ar", "fr"]


def fetch_unprocessed_articles(
    batch_size: int = 256,
    after_id: int = 0,
    target_date: date | str | None = None,
    allowed_languages: Sequence[str] | None = None,
) -> list[dict]:
    """
    Fetch articles pending embedding/clustering with optional date/language filters.

    Rules:
    - scrape_status = 'success'
    - must have at least one tag
    - language in allowed_languages
    - target date if provided
    - not fully processed yet (embedding missing OR cluster missing OR is_processed=false)
    """
    query_date = _normalize_date_filter(target_date)
    languages = _normalize_languages(allowed_languages)

    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """
            SELECT
                id,
                title,
                content,
                summary,
                tags,
                language,
                embedding,
                COALESCE(published_at::date, scraped_at::date) AS article_date
            FROM articles
            WHERE scrape_status = 'success'
              AND id > %s
              AND COALESCE(array_length(tags, 1), 0) > 0
              AND lower(COALESCE(language, '')) = ANY(%s)
              AND (%s::date IS NULL OR COALESCE(published_at::date, scraped_at::date) = %s::date)
              AND (
                    embedding IS NULL
                 OR cluster_id IS NULL
                 OR is_processed = FALSE
              )
            ORDER BY id
            LIMIT %s
            """,
            (after_id, languages, query_date, query_date, batch_size),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def count_unprocessed_articles(
    target_date: date | str | None = None,
    allowed_languages: Sequence[str] | None = None,
) -> int:
    query_date = _normalize_date_filter(target_date)
    languages = _normalize_languages(allowed_languages)

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM articles
            WHERE scrape_status = 'success'
              AND COALESCE(array_length(tags, 1), 0) > 0
              AND lower(COALESCE(language, '')) = ANY(%s)
              AND (%s::date IS NULL OR COALESCE(published_at::date, scraped_at::date) = %s::date)
              AND (
                    embedding IS NULL
                 OR cluster_id IS NULL
                 OR is_processed = FALSE
              )
            """,
            (languages, query_date, query_date),
        )
        return int(cur.fetchone()[0])


def bulk_update_embeddings_and_clusters(records: list[dict]) -> None:
    """Persist article embeddings, cluster ids, and cluster summary rows in one transaction."""
    if not records:
        return

    article_rows = [
        (
            int(record["id"]),
            record.get("embedding"),
            record.get("cluster_id"),
            record.get("embedding_model_version"),
            record.get("tag"),
        )
        for record in records
    ]

    cluster_payload: dict[tuple[int, str, str], list[str]] = {}
    for record in records:
        cluster_id = record.get("cluster_id")
        if cluster_id is None:
            continue
        cluster_id = int(cluster_id)
        cluster_tag = str(record.get("tag") or "untagged")
        cluster_date = str(record.get("article_date"))
        key = (cluster_id, cluster_tag, cluster_date)
        cluster_payload.setdefault(key, []).append(str(record.get("combined_text_source") or ""))

    with get_conn() as conn:
        with conn.cursor() as cur:
            if cluster_payload:
                cluster_rows = []
                for (cluster_id, cluster_tag, cluster_date), snippets in cluster_payload.items():
                    combined_text = "\n".join(item for item in snippets if item).strip()
                    cluster_rows.append((cluster_id, cluster_tag, cluster_date, combined_text))

                execute_values(
                    cur,
                    """
                    INSERT INTO clusters (cluster_id, tag, article_date, article_count, combined_text)
                    VALUES %s
                    ON CONFLICT (cluster_id) DO UPDATE
                    SET tag = EXCLUDED.tag,
                        article_date = EXCLUDED.article_date,
                        combined_text = EXCLUDED.combined_text,
                        article_count = (
                            SELECT COUNT(*)
                            FROM articles
                            WHERE cluster_id = EXCLUDED.cluster_id
                        ),
                        created_at = NOW()
                    """,
                    cluster_rows,
                    template="(%s, %s, %s, 0, %s)",
                    page_size=200,
                )

            execute_values(
                cur,
                """
                UPDATE articles AS a
                SET embedding = COALESCE(v.embedding::vector, a.embedding),
                    cluster_id = v.cluster_id::int,
                    embedding_model_version = COALESCE(v.embedding_model_version, a.embedding_model_version),
                    cluster_tag = COALESCE(v.cluster_tag, a.cluster_tag),
                    is_processed = TRUE,
                    updated_at = NOW()
                FROM (VALUES %s) AS v(id, embedding, cluster_id, embedding_model_version, cluster_tag)
                WHERE a.id = v.id::bigint
                """,
                article_rows,
                template="(%s, %s, %s, %s, %s)",
                page_size=500,
            )

            if cluster_payload:
                cluster_ids = sorted({item[0] for item in cluster_payload.keys()})
                for cluster_id in cluster_ids:
                    cur.execute(
                        """
                        UPDATE clusters
                        SET article_count = (
                            SELECT COUNT(*)
                            FROM articles
                            WHERE cluster_id = %s
                        )
                        WHERE cluster_id = %s
                        """,
                        (cluster_id, cluster_id),
                    )

    logger.info("Persisted embedding/cluster updates for %d articles", len(records))


def get_cluster_info(cluster_id: int) -> dict | None:
    with get_cursor(dict_cursor=True) as cur:
        cur.execute("SELECT * FROM clusters WHERE cluster_id = %s", (cluster_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def get_articles_in_cluster(cluster_id: int) -> list[dict]:
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """
            SELECT id, title, content, cluster_id, is_processed
            FROM articles
            WHERE cluster_id = %s
            ORDER BY id
            """,
            (cluster_id,),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def fetch_processed_article_samples(limit: int = 5) -> list[dict]:
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """
            SELECT
                id,
                cluster_id,
                cluster_tag,
                embedding_model_version,
                embedding,
                COALESCE(published_at::date, scraped_at::date) AS article_date
            FROM articles
            WHERE is_processed = TRUE
            ORDER BY updated_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]
