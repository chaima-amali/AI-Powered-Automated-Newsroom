-- ============================================================
-- AI Newsroom — Database Schema
-- PostgreSQL (Supabase compatible)
-- ============================================================

-- Enable pgvector extension for semantic search (optional, for later AI steps)
CREATE EXTENSION IF NOT EXISTS pgvector;

-- ============================================================
-- CLUSTERS TABLE — semantic article clusters by date
-- ============================================================
CREATE TABLE IF NOT EXISTS clusters (
    cluster_id      INT PRIMARY KEY,
    tag             VARCHAR(120) NOT NULL,
    cluster_tag     VARCHAR(120),
    article_date    DATE NOT NULL,
    article_count   INT DEFAULT 0,
    combined_text   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clusters_date ON clusters (article_date DESC);
CREATE INDEX IF NOT EXISTS idx_clusters_tag ON clusters (tag);

-- ============================================================
-- SOURCES TABLE — registered newspapers/journals
-- ============================================================
CREATE TABLE IF NOT EXISTS sources (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL UNIQUE,
    rss_url     TEXT,
    base_url    TEXT NOT NULL,
    language    VARCHAR(10) DEFAULT 'ar',   -- 'ar', 'fr', 'en'
    country     VARCHAR(50) DEFAULT 'Algeria',
    city        VARCHAR(50) DEFAULT 'Algiers',
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- ARTICLES TABLE — scraped & parsed articles
-- ============================================================
CREATE TABLE IF NOT EXISTS articles (
    id               BIGSERIAL PRIMARY KEY,

    -- Core content
    title            TEXT NOT NULL,
    content          TEXT,
    summary          TEXT,                          -- auto-generated or RSS excerpt
    author           VARCHAR(255),
    language         VARCHAR(10),

    -- Source & location
    source_id        INT REFERENCES sources(id) ON DELETE SET NULL,
    source_name      VARCHAR(255),                  -- denormalized for query speed
    url              TEXT NOT NULL UNIQUE,
    section          VARCHAR(100),                   -- e.g. "politique", "société"

    -- Dates
    published_at     TIMESTAMPTZ,
    scraped_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW(),

    -- Metadata
    tags             TEXT[],                        -- extracted keywords / tags
    image_url        TEXT,                          -- main article image
    word_count       INT,
    is_paywalled     BOOLEAN DEFAULT FALSE,
    scrape_status    VARCHAR(20) DEFAULT 'success'  -- 'success', 'partial', 'failed'
                         CHECK (scrape_status IN ('success', 'partial', 'failed')),
    error_message    TEXT,                          -- populated on scrape failure

    -- AI pipeline fields (used in later steps)
    embedding        vector(768),                   -- intfloat/multilingual-e5-base
    embedding_model_version TEXT,
    cluster_tag      VARCHAR(120),
    cluster_id       INT REFERENCES clusters(cluster_id) ON DELETE SET NULL,
    is_processed     BOOLEAN DEFAULT FALSE          -- has been through AI pipeline
);

-- ============================================================
-- SCRAPE RUNS TABLE — audit log for every collection run
-- ============================================================
CREATE TABLE IF NOT EXISTS scrape_runs (
    id              BIGSERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    total_sources   INT DEFAULT 0,
    total_fetched   INT DEFAULT 0,
    total_inserted  INT DEFAULT 0,
    total_failed    INT DEFAULT 0,
    run_status      VARCHAR(20) DEFAULT 'running'
                        CHECK (run_status IN ('running', 'completed', 'failed')),
    notes           TEXT
);

-- ============================================================
-- INDEXES — for common query patterns
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_articles_published_at  ON articles (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_source_id     ON articles (source_id);
CREATE INDEX IF NOT EXISTS idx_articles_scraped_at    ON articles (scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_language      ON articles (language);
CREATE INDEX IF NOT EXISTS idx_articles_section       ON articles (section);
CREATE INDEX IF NOT EXISTS idx_articles_is_processed  ON articles (is_processed) WHERE is_processed = FALSE;
CREATE INDEX IF NOT EXISTS idx_articles_cluster_id    ON articles (cluster_id) WHERE cluster_id IS NOT NULL;
-- Full-text search index (Arabic + French)
CREATE INDEX IF NOT EXISTS idx_articles_fts
    ON articles USING GIN (to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content, '')));

CREATE TABLE IF NOT EXISTS article_cluster (
    article_id  BIGINT PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
    cluster_id  INT NOT NULL REFERENCES clusters(cluster_id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_article_cluster_cluster_id ON article_cluster (cluster_id);
