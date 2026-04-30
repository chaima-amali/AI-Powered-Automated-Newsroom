from dotenv import load_dotenv
load_dotenv('../.env')
from db.connection import init_pool, close_pool, get_cursor
import json

init_pool()
try:
    with get_cursor(dict_cursor=True) as cur:
        # Fetch cluster 0 with more details
        cur.execute('''
            SELECT a.id, a.title, a.cluster_id, 
                   COALESCE(a.tags[1], 'no-tag') as primary_tag,
                   a.published_at
            FROM articles a 
            WHERE a.cluster_id = 0 
            ORDER BY a.published_at, a.id
        ''')
        rows = cur.fetchall()
        
        print(f'\n===== CLUSTER 0 DEEP DIVE ({len(rows)} articles) =====\n')
        
        # Group by date + tag combo to see the level-1 buckets
        buckets = {}
        for row in rows:
            date = str(row['published_at'])[:10]
            tag = row['primary_tag']
            bucket_key = f"{date}|{tag}"
            if bucket_key not in buckets:
                buckets[bucket_key] = []
            buckets[bucket_key].append(row)
        
        print(f"Level-1 groups (date|tag) that merged into cluster 0: {len(buckets)}\n")
        
        for bucket_key in sorted(buckets.keys()):
            articles = buckets[bucket_key]
            date, tag = bucket_key.split('|')
            print(f"  {date} | {tag:20s} → {len(articles):2d} articles")
        
        # Sample titles from different tags to show mixing
        print(f"\n===== SAMPLE CONTENT MIXING =====")
        by_tag = {}
        for row in rows:
            tag = row['primary_tag']
            if tag not in by_tag:
                by_tag[tag] = []
            by_tag[tag].append(row['title'][:70])
        
        for tag in sorted(by_tag.keys()):
            titles = by_tag[tag]
            print(f"\n--- {tag} ({len(titles)} articles) ---")
            for title in titles[:3]:
                print(f"  • {title}")
            if len(titles) > 3:
                print(f"  ... {len(titles) - 3} more")

        # Root cause analysis
        print(f"\n===== ROOT CAUSE ANALYSIS =====")
        no_tag_count = len(by_tag.get('no-tag', []))
        tagged_count = sum(len(v) for k, v in by_tag.items() if k != 'no-tag')
        print(f"  No-tag articles: {no_tag_count} ({100*no_tag_count/len(rows):.1f}%)")
        print(f"  Tagged articles: {tagged_count} ({100*tagged_count/len(rows):.1f}%)")
        print(f"\n  Problem: {no_tag_count} untagged articles → same level-1 bucket")
        print(f"  → DBSCAN connects them via embedding similarity")
        print(f"  → Even eps=0.28 can't split a dense connected component")
        print(f"\n  Solution: Exclude no-tag articles or pre-assign tags from content")
        
finally:
    close_pool()
