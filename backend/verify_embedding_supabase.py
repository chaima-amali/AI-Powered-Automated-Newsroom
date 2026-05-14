from dotenv import load_dotenv
load_dotenv("../.env")

from db.connection import get_cursor
from db.repository import count_unprocessed_articles

unprocessed = count_unprocessed_articles(target_date=None, allowed_languages=("ar", "fr", "en"))
print(f"unprocessed={unprocessed}")

with get_cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM articles WHERE is_processed=TRUE")
    processed_total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM articles WHERE is_processed=TRUE AND embedding_model_version=%s", ("sentence-transformers/LaBSE",))
    processed_labse = cur.fetchone()[0]

    cur.execute(
        """
        SELECT id, cluster_id, embedding_model_version
        FROM articles
        WHERE is_processed=TRUE
        ORDER BY updated_at DESC NULLS LAST, id DESC
        LIMIT 5
        """
    )
    latest = cur.fetchall()

print(f"processed_total={processed_total}")
print(f"processed_labse={processed_labse}")
print("latest5=")
for row in latest:
    print(row)
