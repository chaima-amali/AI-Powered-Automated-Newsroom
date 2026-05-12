# NewsDispatch — AI-Powered Automated Newsroom

> Aggregates, clusters, summarises and rewrites Algerian news from 16+ sources — fully automated, end-to-end.

---

## Architecture Overview

```
16+ RSS Feeds
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 1: Scraper                                               │
│  ThreadPoolExecutor(8 sources × 10 articles) + rate limiting    │
│  Trafilatura → newspaper3k → BeautifulSoup fallback chain       │
└────────────────────────────┬────────────────────────────────────┘
                             │ articles table (PostgreSQL)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 2: Embedding                                             │
│  multilingual-e5-base (768-dim) → DBSCAN → refine_cluster_labels│
│  Batch encode (64/call) → execute_values bulk upsert            │
└────────────────────────────┬────────────────────────────────────┘
                             │ clusters + article_cluster tables
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 3: Summarizer                                            │
│  Route per cluster size/tag:                                    │
│    1 article  → extractive (3 sentences)                        │
│    2-4 arts   → BART hybrid                                     │
│    5+ political → LLM (Mistral-7B / Llama-3.1)                 │
└────────────────────────────┬────────────────────────────────────┘
                             │ summaries table
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 4: Rewriter                                              │
│  LLM → JSON (title, excerpt, body, tags, SEO) → quality gate   │
│  score ≥ 0.60 → published | draft for human review             │
└────────────────────────────┬────────────────────────────────────┘
                             │ published_articles table
                             ▼
                    FastAPI + React frontend
                    SSE live pipeline monitor
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 15+ **with pgvector extension** (or Supabase free tier)
- 4 GB RAM minimum (for BART model)

### 1. Setup
```bash
unzip newsroom-v2-complete.zip && cd newsroom
bash setup.sh
```

### 2. Configure
```bash
nano backend/.env
# Fill in: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
# Optional: OPENROUTER_API_KEY or GROQ_API_KEY
```

### 3. Apply schema
```bash
cd backend && source .venv/bin/activate
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f db/schema.sql
```

### 4. Run
```bash
# Start API + frontend together
bash start-dev.sh

# Or separately:
# Terminal 1
cd backend && source .venv/bin/activate && uvicorn api_main:app --reload
# Terminal 2
cd frontend && npm run dev
```

### 5. Open
- **Frontend:** http://localhost:5173
- **API docs:** http://localhost:8000/docs
- **Login:** `alex@newsdispatch.com` / `news1234`

---

## Running the Pipeline

### Manual (recommended for first run)
```bash
cd backend && source .venv/bin/activate

# Full pipeline
python main.py

# Individual stages
python main.py --stage scraper
python main.py --stage embedding
python main.py --stage summarizer
python main.py --stage rewriter

# Health check
python main.py --health
```

### Via API (Pipeline Monitor in UI)
1. Log in to the frontend → Pipeline Monitor
2. Enter your `API_SECRET_KEY` from `.env`
3. Click **▶ Run Full Pipeline**
4. Watch SSE logs stream live in the browser

### Automated scheduler
```bash
# In .env:
SCHEDULER_ENABLED=true   # auto-starts with the API server

# Or run standalone:
python -m pipeline.scheduler.scheduler
```

Schedule:
| Job | Frequency |
|-----|-----------|
| RSS scraping | Every 30 min |
| Sitemap crawl | Daily 02:00 |
| Category crawl | Daily 03:00 |
| Embedding + clustering | Every 2 hours |
| Summarization | Every 3 hours |
| Rewriting | Every 4 hours |
| DB cleanup | Daily 04:00 |

---

## Key Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DB_HOST` | ✅ | PostgreSQL host |
| `DB_USER` | ✅ | DB username |
| `DB_PASSWORD` | ✅ | DB password |
| `DB_NAME` | ✅ | Database name |
| `DB_SSLMODE` | — | `prefer` (default), `require`, `disable` |
| `OPENROUTER_API_KEY` | — | For LLM rewriting (free tier: Mistral-7B) |
| `GROQ_API_KEY` | — | Alternative LLM (very fast, free tier) |
| `API_SECRET_KEY` | — | Protects `/pipeline/trigger` endpoint |
| `REWRITER_AUTO_PUBLISH` | — | `true` to skip human review queue |
| `SUMMARIZER_USE_DISTIL` | — | `true` for 6x faster (smaller) model |
| `SCHEDULER_ENABLED` | — | `true` to auto-start scheduler with API |

See `backend/.env.example` for the full list with documentation.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/login` | JWT login |
| POST | `/api/v1/auth/register` | User registration |
| GET | `/api/v1/articles` | Paginated article list |
| GET | `/api/v1/articles/trending` | Top by view count |
| GET | `/api/v1/articles/latest` | Most recent |
| GET | `/api/v1/articles/{slug}` | Article detail |
| GET | `/api/v1/search?q=...` | Semantic + FTS search |
| GET | `/api/v1/health` | Pipeline health stats |
| GET | `/api/v1/categories` | Category list with counts |
| POST | `/api/v1/pipeline/trigger` | Trigger pipeline stage |
| GET | `/api/v1/pipeline/status` | Current stage statuses |
| GET | `/api/v1/pipeline/jobs` | Job history |
| GET | `/api/v1/events` | **SSE** live event stream |

---

## Database Schema

```
users               — authentication
sources             — RSS source registry
articles            — raw scraped articles (internal)
clusters            — DBSCAN story clusters
article_cluster     — article ↔ cluster join
summaries           — BART/LLM cluster summaries
published_articles  — final AI-rewritten articles (public)
scrape_runs         — scraper run history
pipeline_jobs       — API-triggered job tracking
```

Full schema: `backend/db/schema.sql`

---

## Project Structure

```
newsroom/
├── backend/
│   ├── api_main.py          FastAPI server with SSE /events
│   ├── main.py              CLI pipeline runner
│   ├── api/routes/          articles, auth, health, pipeline, search
│   ├── db/                  connection pool + repository
│   ├── pipeline/
│   │   ├── scraper/         orchestrator, parser, deduplication
│   │   ├── embedding/       generator, clustering, pipeline
│   │   ├── summarizer/      hybrid, llm, router, preprocessor
│   │   ├── rewriter/        engine, prompts, quality, pipeline
│   │   └── scheduler/       APScheduler automated runner
│   ├── config/sources.py    16 Algerian news sources
│   └── utils/               logging, health check
└── frontend/
    ├── src/
    │   ├── services/api.js  Centralised API client
    │   ├── context/         AuthContext (real JWT)
    │   ├── hooks/           useArticles, useHealth, usePipelineStatus
    │   ├── pages/           Landing, Login, Signup, Dashboard, Article, Pipeline
    │   └── components/      Navbar, ArticleCard, ProtectedRoute
    └── vite.config.js       /api proxy to :8000
```

---

## Troubleshooting

### "Nothing stored in database"
1. Check `DB_SSLMODE` — use `prefer` or `disable` for local Postgres
2. Run `python main.py --health` — it will diagnose the issue
3. Check `backend/logs/pipeline.log` for detailed errors

### "Pipeline stage hangs / takes hours"
- First run downloads ML models (~2 GB total) — this is one-time only
- Set `SUMMARIZER_USE_DISTIL=true` for 6× faster summarization
- Reduce `ARTICLES_PER_SOURCE=10` in `.env` for testing

### "Semantic search returns nothing"
- Set `REWRITER_EMBED_OUTPUT=true` in `.env` and re-run the rewriter
- This embeds published articles so vector search works

### "SSE logs not appearing in browser"
- Check that the API is running on `:8000`
- The Vite proxy forwards `/api/v1/events` — no CORS issues in dev
- Check browser DevTools → Network → EventStream tab

### "LLM rewriting not working"
- Set `OPENROUTER_API_KEY` or `GROQ_API_KEY` in `.env`
- Without a key, rewriter falls back to extractive text (still works)
- OpenRouter free tier includes Mistral-7B-Instruct
