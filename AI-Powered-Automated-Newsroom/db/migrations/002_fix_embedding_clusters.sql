-- Migration: Fix embedding dimension and add clusters table
-- Run this on your Supabase database to update the schema

-- ============================================================
-- 1. Create clusters table
-- ============================================================
CREATE TABLE IF NOT EXISTS clusters (
    cluster_id      INT PRIMARY KEY,
    article_date    DATE NOT NULL,
    article_count   INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clusters_date ON clusters (article_date DESC);

-- ============================================================
-- 2. Ensure embedding column dimension is vector(1536)
--    This requires dropping and recreating the column
-- ============================================================

-- If the embedding column has data, back it up first
ALTER TABLE articles RENAME COLUMN embedding TO embedding_old;

-- Create the new column with correct dimension
ALTER TABLE articles ADD COLUMN embedding vector(1536);

-- Drop the old column (if you had data, migrate it first)
ALTER TABLE articles DROP COLUMN embedding_old;

-- ============================================================
-- 3. Ensure articles.cluster_id exists and add FK to clusters table
-- ============================================================
ALTER TABLE articles
ADD COLUMN IF NOT EXISTS cluster_id INT;

-- First ensure the constraint doesn't already exist
ALTER TABLE articles
DROP CONSTRAINT IF EXISTS articles_cluster_id_fkey;

ALTER TABLE articles
ADD CONSTRAINT articles_cluster_id_fkey 
    FOREIGN KEY (cluster_id) 
    REFERENCES clusters(cluster_id) 
    ON DELETE SET NULL;

-- ============================================================
-- 4. Create indices for performance
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_articles_cluster_id ON articles (cluster_id) WHERE cluster_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_articles_is_processed ON articles (is_processed) WHERE is_processed = FALSE;

-- ============================================================
-- Done! You can now run the embedding pipeline:
-- python run_embedding_pipeline.py
-- ============================================================
