import os
import sys
import logging
from datetime import datetime, timedelta
import numpy as np
from sklearn.cluster import DBSCAN
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# Load env
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from db.connection import get_cursor, get_conn, init_pool, close_pool

def init_db():
    init_pool()
    with get_cursor() as cur:
        # alter clusters table to add date_min and date_max if they don't exist
        cur.execute("""
            ALTER TABLE clusters 
            ADD COLUMN IF NOT EXISTS date_min DATE,
            ADD COLUMN IF NOT EXISTS date_max DATE;
        """)

def fetch_articles():
    with get_cursor(dict_cursor=True) as cur:
        cur.execute("""
            SELECT id, title, content, 
                   COALESCE(published_at::date, scraped_at::date) as date, 
                   tags as tag, source_name as source
            FROM articles
            WHERE content IS NOT NULL
        """)
        return cur.fetchall()

def process_articles(articles):
    valid_articles = []
    for art in articles:
        content = art['content'] or ""
        title = art['title'] or ""
        # first paragraph
        paras = [p.strip() for p in content.split('\n') if p.strip()]
        first_para = paras[0] if paras else ""
        input_text = f"{title}\n{first_para}"
        
        if len(input_text) < 40:
            continue
            
        art['input_text'] = input_text
        
        # normalize tags
        tags = art['tag'] or []
        norm_tags = []
        for t in tags:
            try:
                norm_tags.append(str(t).lower().strip())
            except:
                pass
        art['norm_tags'] = norm_tags
        
        valid_articles.append(art)
    return valid_articles

def compute_embeddings(articles):
    logger.info("Loading model...")
    model = SentenceTransformer('intfloat/multilingual-e5-base')
    texts = [a['input_text'] for a in articles]
    logger.info(f"Embedding {len(texts)} texts...")
    embeddings = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True, batch_size=32)
    return embeddings

def cluster_embeddings(embeddings):
    logger.info("Clustering starting...")
    dbscan = DBSCAN(eps=0.15, min_samples=2, metric='cosine', n_jobs=-1)
    labels = dbscan.fit_predict(embeddings)
    return labels

def main():
    init_db()
    articles = fetch_articles()
    logger.info(f"Fetched {len(articles)} articles.")
    
    articles = process_articles(articles)
    logger.info(f"Valid articles after preprocessing: {len(articles)}")
    if not articles:
        close_pool()
        return

    embeddings = compute_embeddings(articles)
    
    # Validating dimension
    if embeddings.shape[1] != 768:
        logger.error(f"Invalid dimension: {embeddings.shape[1]}")
        sys.exit(1)
        
    labels = cluster_embeddings(embeddings)
    
    # Group by cluster
    from collections import defaultdict
    clusters = defaultdict(list)
    for i, label in enumerate(labels):
        if label != -1:
            clusters[label].append((articles[i], embeddings[i]))
            
    # Process clusters
    db_clusters = []
    db_articles = []
    
    print("\n\n=== CLUSTERING RESULTS ===")
    print(f"Total Clusters found: {len(clusters)}")
    
    cluster_idx = 1
    printed = 0
    for label, members in clusters.items():
        arts = [m[0] for m in members]
        embs = [m[1] for m in members]
        
        # Date validation
        dates = [a['date'] for a in arts if a['date']]
        if dates:
            min_d, max_d = min(dates), max(dates)
            date_diff = (max_d - min_d).days
        else:
            min_d, max_d, date_diff = None, None, 0
            
        # Tags validation
        all_tags = []
        for a in arts:
            all_tags.extend(a['norm_tags'])
        
        from collections import Counter
        tag_counts = Counter(all_tags)
        cluster_tag = tag_counts.most_common(1)[0][0] if tag_counts else "unknown"
        
        # Cosine sim
        emb_matrix = np.array(embs)
        sim_matrix = np.dot(emb_matrix, emb_matrix.T)
        triu_indices = np.triu_indices_from(sim_matrix, k=1)
        sims = sim_matrix[triu_indices]
        
        if len(sims) > 0:
            mean_sim, min_sim, max_sim = sims.mean(), sims.min(), sims.max()
        else:
            mean_sim = min_sim = max_sim = 1.0
            
        db_clusters.append({
            'cluster_id': cluster_idx,
            'cluster_tag': cluster_tag,
            'article_count': len(arts),
            'date_min': min_d,
            'date_max': max_d,
            'tag': cluster_tag,
            'article_date': min_d or datetime.utcnow().date()
        })
        
        for a in arts:
            db_articles.append({
                'id': a['id'],
                'cluster_id': cluster_idx,
                'cluster_tag': cluster_tag
            })
            
        # Print
        if printed < 3:
            print(f"\nCluster ID: {cluster_idx}")
            print(f"Number of articles: {len(arts)}")
            print(f"Tags: {cluster_tag} (All: {list(set(all_tags))})")
            print(f"Dates: {min_d} to {max_d}")
            print("Sources:", list(set([a['source'] for a in arts])))
            print(f"Similarity: mean={mean_sim:.3f}, min={min_sim:.3f}, max={max_sim:.3f}")
            for a in arts:
                print(f" - {a['title']}")
            printed += 1
            
        if date_diff > 2:
            print(f"WARNING (Cluster {cluster_idx}): Contains very different dates (> 2 days range). Date range: {date_diff} days")
        if min_sim < 0.5:
            print(f"WARNING (Cluster {cluster_idx}): Has very low similarity (< 0.5): min_sim={min_sim:.3f}")
            
        cluster_idx += 1
        
    # Store to DB
    logger.info("Storing to DB...")
    with get_conn() as conn:
        with conn.cursor() as cur:
            from psycopg2.extras import execute_values
            
            if db_clusters:
                # We need to insert to clusters table
                cluster_rows = [
                    (c['cluster_id'], c['tag'], c['article_date'], c['article_count'], c['date_min'], c['date_max'])
                    for c in db_clusters
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO clusters (cluster_id, tag, article_date, article_count, date_min, date_max)
                    VALUES %s
                    ON CONFLICT (cluster_id) DO UPDATE SET
                    tag = EXCLUDED.tag,
                    article_count = EXCLUDED.article_count,
                    date_min = EXCLUDED.date_min,
                    date_max = EXCLUDED.date_max
                    """,
                    cluster_rows,
                    page_size=100
                )
                
            if db_articles:
                art_rows = [
                    (a['id'], a['cluster_id'], a['cluster_tag']) for a in db_articles
                ]
                execute_values(
                    cur,
                    """
                    UPDATE articles AS a
                    SET cluster_id = v.cluster_id,
                        cluster_tag = v.cluster_tag,
                        is_processed = TRUE
                    FROM (VALUES %s) AS v(id, cluster_id, cluster_tag)
                    WHERE a.id = v.id
                    """,
                    art_rows,
                    template="(%s, %s, %s)",
                    page_size=1000
                )
    logger.info("Done storing to DB.")
    close_pool()

if __name__ == "__main__":
    main()