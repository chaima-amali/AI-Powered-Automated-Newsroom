import os
import traceback
from dotenv import load_dotenv

load_dotenv("../.env")

os.environ["EMBEDDING_MODEL_NAME"] = "sentence-transformers/LaBSE"
os.environ["EMBEDDING_VECTOR_DIM"] = "768"

from db.connection import get_cursor
from pipeline.embedding.pipeline import run_embedding_pipeline

with get_cursor() as cur:
    cur.execute(
        """
        UPDATE articles
        SET is_processed = FALSE,
            embedding = NULL,
            embedding_model_version = NULL,
            cluster_id = NULL,
            cluster_tag = NULL,
            updated_at = NOW()
        WHERE scrape_status = 'success'
          AND published_at IS NOT NULL
          AND lower(COALESCE(language, '')) IN ('ar','fr','en')
          AND COALESCE(embedding_model_version, '') <> %s
        """,
        ("sentence-transformers/LaBSE",),
    )
    reset_count = cur.rowcount

print(f"reset_for_reembed={reset_count}")

try:
    result = run_embedding_pipeline(process_date="*")
    print(f"pipeline_result={result}")
except Exception as exc:
    print(f"pipeline_error={type(exc).__name__}: {exc}")
    traceback.print_exc()
    raise

with get_cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM articles WHERE is_processed=TRUE")
    processed_total = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM articles WHERE is_processed=TRUE AND embedding_model_version=%s",
        ("sentence-transformers/LaBSE",),
    )
    processed_labse = cur.fetchone()[0]

print(f"processed_total={processed_total}")
print(f"processed_labse={processed_labse}")
