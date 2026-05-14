#!/usr/bin/env python3
"""Step-by-step embedding test."""
import sys
sys.path.insert(0, ".")
sys.path.insert(0, "pipeline")

from dotenv import load_dotenv
load_dotenv()

print("\n=== STEP 1: Load Database ===")
from db.repository import fetch_unprocessed_articles
batch = fetch_unprocessed_articles(batch_size=5)
print(f"✓ Fetched {len(batch)} articles")

if not batch:
    print("✗ No articles to process")
    sys.exit(0)

print("\n=== STEP 2: Load Embedding Generator ===")
from embedding.generator import embed_texts, build_text, get_effective_model_version
model_ver = get_effective_model_version()
print(f"✓ Model version: {model_ver}")

print("\n=== STEP 3: Build Text ===")
texts = []
for row in batch:
    txt = build_text(
        row.get("title") or "",
        row.get("content"),
        row.get("summary"),
        row.get("tags"),
    )
    texts.append(txt)
    print(f"  - Article {row['id']}: {len(txt)} chars")

print("\n=== STEP 4: Embed Texts ===")
try:
    vectors = embed_texts(texts, batch_size=2)
    print(f"✓ Generated {len(vectors)} embeddings, shape: {vectors.shape}")
except Exception as e:
    print(f"✗ Error during embedding: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n=== SUCCESS ===")
