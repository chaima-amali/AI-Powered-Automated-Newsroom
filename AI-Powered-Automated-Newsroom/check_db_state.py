#!/usr/bin/env python
import sys
from dotenv import load_dotenv
load_dotenv()
from db.connection import init_pool, close_pool, get_cursor

init_pool()
with get_cursor() as cur:
    # Check how many articles have non-null embeddings
    cur.execute("SELECT COUNT(*) FROM articles WHERE embedding IS NOT NULL;")
    non_null_count = cur.fetchone()[0]
    print(f"Articles with non-null embeddings: {non_null_count}")
    
    # Check how many have cluster_id
    cur.execute("SELECT COUNT(*) FROM articles WHERE cluster_id IS NOT NULL;")
    clustered_count = cur.fetchone()[0]
    print(f"Articles with cluster_id: {clustered_count}")
    
    # Fetch a sample embedding vector raw
    cur.execute("SELECT id, embedding, cluster_id FROM articles WHERE embedding IS NOT NULL LIMIT 1;")
    row = cur.fetchone()
    if row:
        aid, emb, cid = row
        print(f"\nSample article id={aid}, cluster_id={cid}")
        print(f"  Embedding type: {type(emb)}, value preview: {str(emb)[:80]}")
    else:
        print("No articles with embeddings found!")
    
    # Check clusters table
    cur.execute("SELECT COUNT(*) FROM clusters;")
    cluster_count = cur.fetchone()[0]
    print(f"\nClusters in DB: {cluster_count}")
    if cluster_count > 0:
        cur.execute("SELECT cluster_id, tag, article_count FROM clusters LIMIT 5;")
        for cid, tag, cnt in cur.fetchall():
            print(f"  cluster_id={cid}, tag={tag}, article_count={cnt}")

close_pool()
