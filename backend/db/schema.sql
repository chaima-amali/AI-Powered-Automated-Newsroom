-- ============================================================
-- AI Newsroom — Database Schema v4
-- PostgreSQL 15+ / Supabase compatible
-- Run once on a fresh database: psql -f db/schema.sql
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgvector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ── users (NEW in v4 — replaces fake sessionStorage auth) ─────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            BIGSERIAL PRIMARY KEY,
    name          VARCHAR(255) NOT NULL,
    email         VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(64)  NOT NULL,   -- SHA-256 hex
    role          VARCHAR(20)  DEFAULT 'reader'
                      CHECK (role IN ('reader', 'editor', 'admin')),
    preferences   TEXT[],
    avatar_color  VARCHAR(20),
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);
-- Seed demo user (password: news1234 → SHA-256)
INSERT INTO users (name, email, password_hash, role)
VALUES (
    'Alex Johnson',
    'alex@newsdispatch.com',
    '5e8948f4a09cc7cf7f2bce5ded2e0dbcde73aff52f1f90a7ecbc17ab5c68a2b1',
    'admin'
) ON CONFLICT (email) DO NOTHING;

-- ── sources ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sources (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(255) NOT NULL UNIQUE,
    rss_url    TEXT,
    base_url   TEXT         NOT NULL,
    language   VARCHAR(10)  DEFAULT 'ar',
    country    VARCHAR(50)  DEFAULT 'Algeria',
    is_active  BOOLEAN      DEFAULT TRUE,
    created_at TIMESTAMPTZ  DEFAULT NOW()
);

-- ── clusters ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clusters (
    cluster_id    BIGINT PRIMARY KEY,
    tag           VARCHAR(120) NOT NULL,
    cluster_tag   VARCHAR(120),
    article_date  DATE         NOT NULL,
    article_count INT          DEFAULT 0,
    combined_text TEXT,
    centroid      vector(768),
    created_at    TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_clusters_date ON clusters (article_date DESC);
CREATE INDEX IF NOT EXISTS idx_clusters_tag  ON clusters (tag);

-- ── articles (raw — internal) ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS articles (
    id               BIGSERIAL PRIMARY KEY,
    title            TEXT         NOT NULL,
    content          TEXT,
    summary          TEXT,
    author           VARCHAR(255),
    language         VARCHAR(10),
    source_id        INT          REFERENCES sources(id) ON DELETE SET NULL,
    source_name      VARCHAR(255),
    url              TEXT         NOT NULL UNIQUE,
    section          TEXT,
    discovered_from  VARCHAR(20)  CHECK (discovered_from IN ('rss','sitemap','category','unknown')),
    image_url        TEXT,
    image_local_path TEXT,
    published_at     TIMESTAMPTZ,
    scraped_at       TIMESTAMPTZ  DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  DEFAULT NOW(),
    tags             TEXT[],
    word_count       INT,
    is_paywalled     BOOLEAN      DEFAULT FALSE,
    scrape_status    VARCHAR(20)  DEFAULT 'success'
                         CHECK (scrape_status IN ('success','partial','failed')),
    error_message    TEXT,
    embedding        vector(768),
    embedding_model_version TEXT,
    cluster_tag      VARCHAR(120),
    cluster_id       BIGINT       REFERENCES clusters(cluster_id) ON DELETE SET NULL,
    is_processed     BOOLEAN      DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_art_published   ON articles (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_art_source      ON articles (source_id);
CREATE INDEX IF NOT EXISTS idx_art_scraped     ON articles (scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_art_language    ON articles (language);
CREATE INDEX IF NOT EXISTS idx_art_unprocessed ON articles (is_processed) WHERE is_processed = FALSE;
CREATE INDEX IF NOT EXISTS idx_art_cluster     ON articles (cluster_id) WHERE cluster_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_art_disc        ON articles (discovered_from);
CREATE INDEX IF NOT EXISTS idx_art_fts ON articles
    USING GIN (to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(content,'')));

-- ── article_cluster join ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS article_cluster (
    article_id BIGINT PRIMARY KEY REFERENCES articles(id)         ON DELETE CASCADE,
    cluster_id BIGINT NOT NULL    REFERENCES clusters(cluster_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ac_cluster ON article_cluster (cluster_id);

-- ── summaries ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS summaries (
    id            BIGSERIAL PRIMARY KEY,
    cluster_id    BIGINT      NOT NULL UNIQUE REFERENCES clusters(cluster_id) ON DELETE CASCADE,
    summary_text  TEXT        NOT NULL,
    summary_lang  VARCHAR(10) DEFAULT 'en',
    summary_model VARCHAR(120),
    strategy      VARCHAR(30),
    summarized_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── published_articles (frontend table) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS published_articles (
    id                    BIGSERIAL PRIMARY KEY,
    cluster_id            BIGINT    REFERENCES clusters(cluster_id) ON DELETE SET NULL,
    source_article_ids    BIGINT[],
    title                 TEXT        NOT NULL,
    slug                  TEXT        UNIQUE,
    excerpt               TEXT,
    body                  TEXT        NOT NULL,
    raw_summary           TEXT,
    cover_image_url       TEXT,
    cover_image_local     TEXT,
    image_alt_text        TEXT,
    category              VARCHAR(80),
    tags                  TEXT[],
    language              VARCHAR(10) DEFAULT 'fr',
    seo_title             TEXT,
    seo_description       TEXT,
    canonical_url         TEXT,
    reading_time_min      INT,
    embedding             vector(768),
    original_published_at TIMESTAMPTZ,
    generated_at          TIMESTAMPTZ DEFAULT NOW(),
    published_at          TIMESTAMPTZ,
    updated_at            TIMESTAMPTZ DEFAULT NOW(),
    status                VARCHAR(20) DEFAULT 'draft'
                              CHECK (status IN ('draft','review','published','archived')),
    rewrite_model         VARCHAR(120),
    quality_score         FLOAT,
    view_count            INT     DEFAULT 0,
    is_duplicate          BOOLEAN DEFAULT FALSE,
    duplicate_of          BIGINT  REFERENCES published_articles(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_pub_status   ON published_articles (published_at DESC) WHERE status='published';
CREATE INDEX IF NOT EXISTS idx_pub_category ON published_articles (category) WHERE status='published';
CREATE INDEX IF NOT EXISTS idx_pub_tags     ON published_articles USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_pub_slug     ON published_articles (slug);
CREATE INDEX IF NOT EXISTS idx_pub_language ON published_articles (language) WHERE status='published';
CREATE INDEX IF NOT EXISTS idx_pub_fts      ON published_articles
    USING GIN (to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(excerpt,'') || ' ' || coalesce(body,'')));

-- ── scrape_runs ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scrape_runs (
    id             BIGSERIAL PRIMARY KEY,
    started_at     TIMESTAMPTZ DEFAULT NOW(),
    finished_at    TIMESTAMPTZ,
    total_sources  INT DEFAULT 0,
    total_fetched  INT DEFAULT 0,
    total_inserted INT DEFAULT 0,
    total_failed   INT DEFAULT 0,
    run_status     VARCHAR(20) DEFAULT 'running'
                       CHECK (run_status IN ('running','completed','failed')),
    notes          TEXT
);

-- ── pipeline_jobs ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_jobs (
    id          BIGSERIAL PRIMARY KEY,
    job_type    VARCHAR(50) NOT NULL,
    payload     JSONB,
    status      VARCHAR(20) DEFAULT 'pending'
                    CHECK (status IN ('pending','running','done','failed')),
    attempts    INT         DEFAULT 0,
    last_error  TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON pipeline_jobs (created_at DESC) WHERE status IN ('pending','running');

-- ── monitoring views ──────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_pipeline_health AS
SELECT
    (SELECT COUNT(*) FROM articles WHERE scrape_status='success')              AS total_articles,
    (SELECT COUNT(*) FROM articles WHERE is_processed=FALSE AND scrape_status='success') AS pending_embedding,
    (SELECT COUNT(*) FROM clusters)                                             AS total_clusters,
    (SELECT COUNT(*) FROM summaries)                                            AS total_summaries,
    (SELECT COUNT(*) FROM published_articles WHERE status='published')          AS published_count,
    (SELECT COUNT(*) FROM published_articles WHERE status='draft')              AS draft_count,
    (SELECT MAX(started_at) FROM scrape_runs)                                   AS last_scrape_at,
    (SELECT MAX(generated_at) FROM published_articles)                          AS last_generated_at;

CREATE OR REPLACE VIEW v_daily_stats AS
SELECT published_at::date AS day, category,
       COUNT(*) AS articles, SUM(view_count) AS views
FROM published_articles WHERE status='published'
GROUP BY 1, 2 ORDER BY 1 DESC, 3 DESC;
