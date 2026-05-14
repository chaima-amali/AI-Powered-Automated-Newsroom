#!/usr/bin/env python3
"""Debug embedding pipeline."""
import sys
import traceback
from dotenv import load_dotenv

load_dotenv()

print("[*] Loading database...")
from db.repository import count_unprocessed_articles

count = count_unprocessed_articles(target_date=None, allowed_languages=("ar", "fr", "en"))
print(f"[OK] Found {count} unprocessed articles")

if count == 0:
    print("[!] No articles to process - exiting")
    sys.exit(0)

print("[*] Loading embedding pipeline...")
try:
    from pipeline.embedding.pipeline import run_embedding_pipeline
    print("[*] Starting embedding pipeline...")
    result = run_embedding_pipeline(process_date="*")
    print("[OK] Pipeline complete!")
    import json
    print(json.dumps(result, indent=2))
except Exception as e:
    print(f"\n[ERROR] {type(e).__name__}: {e}")
    traceback.print_exc()
    sys.exit(1)
