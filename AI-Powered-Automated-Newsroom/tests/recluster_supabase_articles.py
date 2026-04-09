from __future__ import annotations

import ast
from collections import defaultdict

import numpy as np
from dotenv import load_dotenv
from sklearn.cluster import DBSCAN

load_dotenv()

from db.connection import close_pool, get_cursor, init_pool
from db.repository import bulk_update_embeddings_and_clusters

DBSCAN_EPS = 0.20
DBSCAN_MIN_SAMPLES = 2


def _parse_embedding(value: object) -> list[float]:
    if isinstance(value, str):
        parsed = ast.literal_eval(value)
        return [float(item) for item in parsed]
    if isinstance(value, (list, tuple, np.ndarray)):
        return [float(item) for item in value]
    raise TypeError(f"Unsupported embedding type: {type(value)!r}")


def fetch_processed_articles() -> list[dict]:
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """
            SELECT
                id,
                title,
                embedding,
                COALESCE(published_at::date, scraped_at::date) AS article_date
              FROM articles
             WHERE is_processed = TRUE
               AND embedding IS NOT NULL
             ORDER BY article_date, id
            """
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def recluster_articles(rows: list[dict]) -> list[dict]:
    date_groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        date_groups[str(row["article_date"])].append(row)

    next_cluster_id = 0
    records: list[dict] = []

    for date_key in sorted(date_groups.keys()):
        date_rows = sorted(date_groups[date_key], key=lambda row: row["id"])
        embeddings = np.array([_parse_embedding(row["embedding"]) for row in date_rows], dtype=np.float32)

        if len(date_rows) < DBSCAN_MIN_SAMPLES:
            labels = np.full(len(date_rows), -1, dtype=np.int32)
        else:
            labels = DBSCAN(
                eps=DBSCAN_EPS,
                min_samples=DBSCAN_MIN_SAMPLES,
                metric="cosine",
                algorithm="brute",
                n_jobs=-1,
            ).fit_predict(embeddings)

        local_to_global: dict[int, int] = {}
        for row, embedding, label in zip(date_rows, embeddings, labels):
            label = int(label)
            if label == -1:
                cluster_id = None
            else:
                if label not in local_to_global:
                    local_to_global[label] = next_cluster_id
                    next_cluster_id += 1
                cluster_id = local_to_global[label]

            records.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "embedding": embedding.tolist(),
                    "cluster_id": cluster_id,
                    "cluster_label": label,
                    "article_date": date_key,
                }
            )

    return records


def refresh_cluster_counts(cluster_ids: list[int]) -> None:
    if not cluster_ids:
        return

    with get_cursor() as cur:
        for cluster_id in cluster_ids:
            cur.execute(
                """
                UPDATE clusters
                   SET article_count = (
                        SELECT COUNT(*)
                          FROM articles
                         WHERE cluster_id = %s
                   ),
                       article_date = (
                        SELECT COALESCE(MIN(published_at::date), MIN(scraped_at::date))
                          FROM articles
                         WHERE cluster_id = %s
                   )
                 WHERE cluster_id = %s
                """,
                (cluster_id, cluster_id, cluster_id),
            )


def main() -> None:
    init_pool()
    try:
        rows = fetch_processed_articles()
        print(f"Fetched {len(rows)} processed articles")

        records = recluster_articles(rows)
        non_null_cluster_ids = sorted({int(record["cluster_id"]) for record in records if record["cluster_id"] is not None})

        bulk_update_embeddings_and_clusters(records)
        refresh_cluster_counts(non_null_cluster_ids)

        print(f"Updated {len(records)} articles")
        print(f"Stored {len(non_null_cluster_ids)} clusters in Supabase")
        print(f"Cluster IDs: {non_null_cluster_ids}")
    finally:
        close_pool()


if __name__ == "__main__":
    main()
