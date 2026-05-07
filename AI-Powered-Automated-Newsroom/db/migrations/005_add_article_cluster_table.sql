-- Migration 005: add article_cluster join table and cluster_tag/date range support

CREATE TABLE IF NOT EXISTS article_cluster (
    article_id  BIGINT PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
    cluster_id   INT NOT NULL REFERENCES clusters(cluster_id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_article_cluster_cluster_id ON article_cluster (cluster_id);

ALTER TABLE clusters
    ADD COLUMN IF NOT EXISTS cluster_tag VARCHAR(120),
    ADD COLUMN IF NOT EXISTS date_min DATE,
    ADD COLUMN IF NOT EXISTS date_max DATE;

UPDATE clusters
SET cluster_tag = COALESCE(NULLIF(cluster_tag, ''), tag)
WHERE cluster_tag IS NULL OR cluster_tag = '';