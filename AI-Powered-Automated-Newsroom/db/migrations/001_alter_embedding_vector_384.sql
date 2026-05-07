-- ============================================================
-- Migration 001 — Change embedding column to vector(1536)
-- ============================================================
-- Run this ONCE in the Supabase SQL Editor (or psql) before
-- executing the embedding pipeline for the first time.
--
-- Why 384?
--   sentence-transformers/all-MiniLM-L6-v2 produces 384-dim vectors.
--   Storing them as vector(1536) keeps parity with the current database schema.
--
-- Step 1: Ensure the pgvector extension is installed
CREATE EXTENSION IF NOT EXISTS vector;

-- Step 2: Drop the old embedding column (was vector(1536) for OpenAI)
--         WARNING: this discards any previously stored OpenAI embeddings.
--         If you need to keep them, rename the column instead:
--           ALTER TABLE articles RENAME COLUMN embedding TO embedding_openai;
ALTER TABLE articles DROP COLUMN IF EXISTS embedding;

-- Step 3: Add embedding column sized for all-MiniLM-L6-v2
ALTER TABLE articles ADD COLUMN embedding vector(1536);

-- Step 4: Create an HNSW index for fast approximate nearest-neighbour search.
--         Cosine distance (<=>)  matches the L2-normalised vectors we store.
--         m=16, ef_construction=64 are good defaults; raise for recall vs speed.
CREATE INDEX IF NOT EXISTS articles_embedding_hnsw_idx
    ON articles
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Step 5 (optional): IVFFlat alternative — simpler, uses less memory.
--   Uncomment if you prefer IVFFlat over HNSW:
-- CREATE INDEX IF NOT EXISTS articles_embedding_ivfflat_idx
--     ON articles
--     USING ivfflat (embedding vector_cosine_ops)
--     WITH (lists = 100);   -- rule of thumb: sqrt(total_rows)

-- Verify
SELECT
    column_name,
    data_type,
    udt_name
FROM information_schema.columns
WHERE table_name = 'articles'
  AND column_name = 'embedding';
