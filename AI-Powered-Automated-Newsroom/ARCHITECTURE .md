# AI Newsroom — Web Scraper Architecture

## Overview

A production-ready, concurrent news scraping system for all major Algerian
newspapers and journals. Feeds the AI pipeline (embedding → clustering →
summarisation) described in the project presentation.

---

## Project Structure

```
newsroom_scraper/
│
├── main.py                      ← entry point (one-shot or scheduled)
│
├── config/
│   └── sources.py               ← registry of ALL Algerian sources (add here only)
│
├── scraper/
│   ├── orchestrator.py          ← concurrent engine (ThreadPoolExecutor)
│   ├── feed_collector.py        ← RSS/Atom fetcher (feedparser)
│   └── parser.py                ← HTML → article dict (newspaper3k + BS4 fallback)
│
├── db/
│   ├── schema.sql               ← run once on a fresh DB
│   ├── connection.py            ← thread-safe connection pool (psycopg2)
│   └── repository.py            ← all SQL in one place (no SQL elsewhere)
│
├── utils/
│   ├── logging_config.py        ← rotating file + stdout logging
│   └── health_check.py          ← verify feeds + DB before going live
│
├── requirements.txt
└── .env.example                 ← copy → .env with your credentials
```

---

## Database Design

### `sources` table
Tracks registered newspapers. Add a source once; it's referenced by all its articles.

| Column      | Type         | Notes                          |
|-------------|--------------|--------------------------------|
| id          | SERIAL PK    |                                |
| name        | VARCHAR(255) | unique identifier              |
| rss_url     | TEXT         | RSS/Atom feed                  |
| base_url    | TEXT         | homepage                       |
| language    | VARCHAR(10)  | 'ar' / 'fr' / 'en'            |
| is_active   | BOOLEAN      | toggle without deleting        |

### `articles` table
One row per article. Deduplication via `UNIQUE(url)`.

| Column        | Type         | Notes                              |
|---------------|--------------|------------------------------------|
| id            | BIGSERIAL PK |                                    |
| title         | TEXT         |                                    |
| content       | TEXT         | full body text                     |
| summary       | TEXT         | RSS excerpt or auto-generated      |
| author        | VARCHAR(255) |                                    |
| language      | VARCHAR(10)  | inherited from source              |
| source_id     | FK → sources |                                    |
| source_name   | VARCHAR      | denormalised for fast queries      |
| url           | TEXT UNIQUE  | primary dedup key                  |
| section       | VARCHAR      | politics / culture / etc.          |
| published_at  | TIMESTAMPTZ  |                                    |
| scraped_at    | TIMESTAMPTZ  | auto-set to NOW()                  |
| updated_at    | TIMESTAMPTZ  |                                    |
| tags          | TEXT[]       | keywords / categories              |
| image_url     | TEXT         | main article image                 |
| word_count    | INT          |                                    |
| scrape_status | VARCHAR(20)  | success / partial / failed         |
| error_message | TEXT         | populated on failure               |
| embedding     | vector(1536) | OpenAI embedding (AI pipeline)     |
| cluster_id    | INT          | assigned during clustering step    |
| is_processed  | BOOLEAN      | has gone through AI pipeline       |

### `scrape_runs` table
Audit log — one row per execution.

| Column         | Type         | Notes                      |
|----------------|--------------|----------------------------|
| id             | BIGSERIAL PK |                            |
| started_at     | TIMESTAMPTZ  |                            |
| finished_at    | TIMESTAMPTZ  |                            |
| total_sources  | INT          |                            |
| total_fetched  | INT          |                            |
| total_inserted | INT          | new articles added         |
| total_failed   | INT          |                            |
| run_status     | VARCHAR(20)  | running / completed / failed |

---

## Concurrency Design

```
run_scraper()
└── ThreadPoolExecutor(max_workers=10)   ← 10 sources in PARALLEL (SIMULTANEOUS)
    ├── _process_source(Ennahar)         ← Running concurrently with all others
    │   └── ThreadPoolExecutor(max_workers=15)  ← 15 articles in PARALLEL
    │       ├── _scrape_and_store(article_1)
    │       ├── _scrape_and_store(article_2)
    │       └── ...
    ├── _process_source(El Watan)        ← Running concurrently with all others
    │   └── ThreadPoolExecutor(max_workers=15)
    │       └── ...
    └── ...  (all sources run SIMULTANEOUSLY, not sequentially)
    
Max concurrent requests = 10 sources × 15 articles = 150 simultaneous HTTP requests
```

**Why threads over asyncio?**
Scraping is I/O-bound (network + disk). Python threads release the GIL during
I/O, giving near-identical throughput to asyncio with simpler, more debuggable
code. Asyncio would be preferred only if managing 1000+ concurrent connections.

---

## Extraction Pipeline (per article)

```
RSS entry
    │
    ├─ RSS has full content (≥300 chars)?  ──YES──► use RSS content directly
    │                                                (no HTTP request needed)
    │
    └─NO──► 1. Trafilatura.extract()  (PRIMARY - fast, robust, best for Arabic)
                │
                ├─ Success?  ──YES──► structured article dict
                │
                └─NO──► 2. newspaper3k.download() + parse()  (FALLBACK)
                            │
                            ├─ Success?  ──YES──► structured article dict
                            │
                            └─NO──► 3. BeautifulSoup fallback  (LAST RESORT)
                                        │
                                        ├─ Try source-specific CSS selectors (config/sources.py)
                                        └─ Then generic selectors (article, div.content, main…)
```

**Trafilatura** (primary) handles:
- Excellent Arabic (RTL) and multilingual text extraction
- Superior boilerplate removal (ads, navigation, comments)
- Fast processing and active maintenance
- Built-in metadata extraction

**newspaper3k** (fallback) handles:
- Alternative extraction when Trafilatura fails
- Author extraction from bylines
- Publication date from meta tags
- Main image detection

---

## Error Handling Strategy

| Layer          | Strategy                                      |
|----------------|-----------------------------------------------|
| HTTP errors    | Log + mark `scrape_status='failed'`; don't crash |
| Timeouts       | 15s timeout; log warning                      |
| Feed errors    | Log; return empty list; source skipped        |
| Parse errors   | Fallback extractor chain (newspaper → BS4)    |
| DB errors      | Connection pool auto-retry; rollback on error |
| Thread crashes | `as_completed()` catches per-future exceptions |
| Rate limiting  | 0.5s delay between requests per domain        |

Articles that fail scraping are still inserted with `scrape_status='failed'`
and an `error_message`, so you know what to fix — no silent data loss.

---

## How to Add a New Source

Edit `config/sources.py` — add one dict:

```python
{
    "name": "Mon Journal",
    "rss_url": "https://monjournal.dz/feed/",
    "base_url": "https://monjournal.dz",
    "language": "fr",
    "article_selectors": ["div.article-body", "article"],  # inspect the site HTML
},
```

That's it. No other file needs to change.

---

## Setup & Running

```bash
# 1. Install dependencies
pip install -r requirements.txt
python -c "import nltk; nltk.download('punkt')"

# 2. Configure credentials
cp .env.example .env
# edit .env with your Supabase credentials

# 3. Create DB schema
psql $DATABASE_URL -f db/schema.sql

# 4. Verify everything works
python -m utils.health_check

# 5. Run
python main.py                   # one shot
python main.py --schedule 60     # every 60 minutes
python main.py --sources "TSA"   # specific source only
```

---

## Fixing Content Extraction for a Specific Site

If `health_check.py` reports "article parsed but short" for a source:

1. Open the article URL in a browser
2. Right-click the article body → Inspect Element
3. Find the wrapping `<div>` or `<article>` tag and its class
4. Add it to `article_selectors` in `config/sources.py`:

```python
"article_selectors": ["div.the-class-you-found", ...]
```

---

## Recommended Enhancements

| Enhancement              | How                                              |
|--------------------------|--------------------------------------------------|
| Retry with backoff       | `tenacity` library on `extract_article()`        |
| Proxy rotation           | Pass rotating proxy list to `requests.Session`   |
| Duplicate near-detection | pgvector cosine similarity (AI pipeline step)    |
| Scheduling (production)  | APScheduler or Celery + Redis                    |
| Monitoring               | Expose `scrape_runs` stats via FastAPI endpoint  |
| Alerting                 | Telegram/email if `total_failed > threshold`     |
| Docker deployment        | `Dockerfile` + `docker-compose.yml` with cron    |
