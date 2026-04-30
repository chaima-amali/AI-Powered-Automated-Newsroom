-- Migration 004: Add semantic cluster analysis columns
-- Apply this after migration 003 so existing Supabase databases can store
-- cluster labels, date ranges, and centroids from the new semantic pipeline.

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE clusters
    ADD COLUMN IF NOT EXISTS cluster_tag VARCHAR(120),
    ADD COLUMN IF NOT EXISTS date_min DATE,
    ADD COLUMN IF NOT EXISTS date_max DATE,
    ADD COLUMN IF NOT EXISTS centroid vector(768);

UPDATE clusters
SET cluster_tag = COALESCE(NULLIF(cluster_tag, ''), tag)
WHERE cluster_tag IS NULL OR cluster_tag = '';
