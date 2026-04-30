from dotenv import load_dotenv
import sys
sys.path.insert(0, r'C:\Users\j\OneDrive\Desktop\AI-Powered-Automated-Newsroom\AI-Powered-Automated-Newsroom')
load_dotenv()
from db.connection import init_pool, close_pool, get_cursor

init_pool()
try:
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM articles WHERE cluster_id IS NOT NULL;")
        print('clustered_articles=', cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM clusters;")
        print('clusters=', cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM article_cluster;")
        print('article_cluster_rows=', cur.fetchone()[0])
finally:
    close_pool()
