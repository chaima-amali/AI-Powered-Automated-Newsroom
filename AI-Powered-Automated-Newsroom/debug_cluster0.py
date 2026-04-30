from dotenv import load_dotenv
load_dotenv('../.env')
from db.connection import init_pool, close_pool, get_cursor

init_pool()
try:
    with get_cursor(dict_cursor=True) as cur:
        # Fetch all articles in cluster 0
        cur.execute('''
            SELECT a.id, a.title, a.cluster_id, 
                   COALESCE(a.tags[1], 'no-tag') as primary_tag,
                   a.published_at
            FROM articles a 
            WHERE a.cluster_id = 0 
            ORDER BY a.published_at, a.id
        ''')
        rows = cur.fetchall()
        print(f'\n===== CLUSTER 0 COMPOSITION ({len(rows)} articles) =====\n')
        
        # Group by tag to see the topic mixing
        by_tag = {}
        for row in rows:
            tag = row['primary_tag']
            if tag not in by_tag:
                by_tag[tag] = []
            by_tag[tag].append(row)
        
        print(f"Tags in cluster 0: {sorted(by_tag.keys())}\n")
        
        for tag in sorted(by_tag.keys()):
            articles = by_tag[tag]
            print(f"\n--- TAG: {tag} ({len(articles)} articles) ---")
            for row in articles[:8]:  # Show first 8 per tag
                title_short = row['title'][:75]
                date = str(row['published_at'])[:10]
                print(f"  [{date}] {title_short}")
            if len(articles) > 8:
                print(f"  ... and {len(articles) - 8} more")
        
        # Also analyze the distribution of dates
        print("\n\n===== DATE DISTRIBUTION IN CLUSTER 0 =====")
        date_counts = {}
        for row in rows:
            date = str(row['published_at'])[:10]
            date_counts[date] = date_counts.get(date, 0) + 1
        
        for date in sorted(date_counts.keys()):
            print(f"  {date}: {date_counts[date]} articles")
                
finally:
    close_pool()
