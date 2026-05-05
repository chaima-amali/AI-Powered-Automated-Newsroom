"""
check_db.py
-----------
Run from your project root:
    python check_db.py
"""

from dotenv import load_dotenv
load_dotenv()

from db.connection import get_cursor, init_pool, close_pool

init_pool()

with get_cursor(dict_cursor=True) as cur:

    # 1. Check summaries table columns
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'summaries'
        ORDER BY ordinal_position
    """)
    cols = [r["column_name"] for r in cur.fetchall()]
    print("summaries columns:", cols)

    # 2. Count clustered articles
    cur.execute("SELECT COUNT(*) AS n FROM articles WHERE cluster_id IS NOT NULL")
    print("clustered articles:", cur.fetchone()["n"])

    # 3. Count clusters
    cur.execute("SELECT COUNT(*) AS n FROM clusters")
    print("total clusters    :", cur.fetchone()["n"])

    # 4. Count existing summaries
    cur.execute("SELECT COUNT(*) AS n FROM summaries")
    print("existing summaries:", cur.fetchone()["n"])

    # 5. Show a sample cluster
    cur.execute("""
        SELECT cluster_id, tag, article_count
        FROM clusters
        LIMIT 3
    """)
    print("sample clusters   :", cur.fetchall())

close_pool()
print("\nAll checks passed.")