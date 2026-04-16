-- Migration 003: Align schema with multilingual-e5 clustering pipeline
-- Apply in Supabase SQL editor before running the pipeline.

CREATE EXTENSION IF NOT EXISTS vector;

-- 1) Ensure embedding column supports multilingual-e5-base dimensions (768)
ALTER TABLE articles
    DROP COLUMN IF EXISTS embedding;

ALTER TABLE articles
    ADD COLUMN embedding vector(768);

-- 2) Add optional metadata columns on articles
ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS embedding_model_version TEXT,
    ADD COLUMN IF NOT EXISTS cluster_tag VARCHAR(120);

-- 3) Enrich clusters table with tag and combined text payload for summarization
ALTER TABLE clusters
    ADD COLUMN IF NOT EXISTS tag VARCHAR(120),
    ADD COLUMN IF NOT EXISTS combined_text TEXT;

-- tag is required for new inserts
UPDATE clusters
SET tag = COALESCE(NULLIF(tag, ''), 'untagged')
WHERE tag IS NULL OR tag = '';

ALTER TABLE clusters
    ALTER COLUMN tag SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_clusters_tag ON clusters (tag);
