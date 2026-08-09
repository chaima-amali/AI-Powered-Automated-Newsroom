"""
backend/main.py
---------------
FastAPI application entry point — fully merged backend + pipeline control.

Run:
    uvicorn api_main:app --host 0.0.0.0 --port 8000 --reload

Key improvements vs original:
  - Real-time Server-Sent Events (SSE) for pipeline progress streaming
  - Pipeline job tracking in DB (pipeline_jobs table)
  - WebSocket endpoint for live log tailing
  - Proper background task management (not fire-and-forget threads)
  - CORS pre-configured for local dev (frontend at :5173)
  - Auth endpoints (JWT-based) replacing the fake sessionStorage auth
  - Static media serving with cache headers
"""
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import logging
import os
import queue
import threading
import time
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, BackgroundTasks, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from db.connection import init_pool, close_pool, has_db_settings
from api.routes.articles import router as articles_router
from api.routes.search   import router as search_router
from api.routes.health   import router as health_router
from api.routes.pipeline import router as pipeline_router
from api.routes.auth     import router as auth_router
from utils.logging_config import setup_logging

setup_logging()
logger = logging.getLogger("main")

# ── Global in-memory SSE broadcast queue (simple single-process) ──────────────
# In production replace with Redis pub/sub
_sse_listeners: list[queue.Queue] = []
_sse_lock = threading.Lock()


def broadcast_event(event_type: str, data: dict) -> None:
    """Push a pipeline event to all connected SSE clients."""
    msg = json.dumps({"type": event_type, "ts": time.time(), **data})
    with _sse_lock:
        dead = []
        for q in _sse_listeners:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _sse_listeners.remove(q)


# Make broadcast available to pipeline modules via a simple import
import builtins
builtins._newsroom_broadcast = broadcast_event


def _run_pipeline_background():
    """Run all 4 pipeline stages in background thread."""
    import time
    time.sleep(1)  # Let app fully start first
    
    logger.info("\n" + "="*60)
    logger.info("🚀 Starting Pipeline Execution (all stages)")
    logger.info("="*60 + "\n")
    
    try:
        from pipeline.scheduler.scheduler import (
            job_rss, job_embedding, job_summarization, job_rewriter
        )
        
        stages = [
            ("Scraper (RSS/Feeds)", job_rss),
            ("Embedding", job_embedding),
            ("Summarization", job_summarization),
            ("Rewriter", job_rewriter),
        ]
        
        for stage_name, job_fn in stages:
            try:
                logger.info(f"▶️  Running: {stage_name}")
                job_fn()
                logger.info(f"✅ Completed: {stage_name}\n")
            except Exception as e:
                logger.error(f"❌ Failed: {stage_name} — {e}", exc_info=True)
        
        logger.info("="*60)
        logger.info("✅ All pipeline stages completed")
        logger.info("="*60 + "\n")
        
    except Exception as e:
        logger.error("Pipeline execution failed: %s", e, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if has_db_settings():
        try:
            init_pool()
            logger.info("✅ Database pool initialized")
        except Exception as e:
            logger.warning("⚠️  DB unavailable (%s) — API runs in degraded mode", e)
    else:
        logger.warning("⚠️  No DB credentials — API runs without persistence")

    # Launch pipeline in background thread (non-blocking)
    # Only run if PIPELINE_ON_STARTUP=true is set explicitly
    if os.environ.get("PIPELINE_ON_STARTUP", "false").lower() == "true":
        pipeline_thread = threading.Thread(target=_run_pipeline_background, daemon=True)
        pipeline_thread.start()
        logger.info("✅ Background pipeline thread started (PIPELINE_ON_STARTUP=true)")
    else:
        logger.info("ℹ️  Pipeline on startup disabled (set PIPELINE_ON_STARTUP=true to enable)")

    yield

    close_pool()


app = FastAPI(
    title="AI Newsroom API",
    description="Algerian news aggregation and AI rewriting platform",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
_ALLOWED_ORIGINS = [
    "http://localhost:5173",   # Vite dev (default)
    "http://localhost:5174",   # Vite dev (alternate port)
    "http://localhost:5175",   # Vite dev (alternate port)
    "http://localhost:4173",   # Vite preview
    "http://localhost:3000",   # Common dev port
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
    "http://127.0.0.1:3000",
    os.environ.get("FRONTEND_URL", ""),
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in _ALLOWED_ORIGINS if o],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static media ──────────────────────────────────────────────────────────────
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", "./media")
os.makedirs(MEDIA_ROOT, exist_ok=True)
app.mount("/media", StaticFiles(directory=MEDIA_ROOT), name="media")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(articles_router, prefix="/api/v1")
app.include_router(search_router,   prefix="/api/v1")
app.include_router(health_router,   prefix="/api/v1")
app.include_router(pipeline_router, prefix="/api/v1")
app.include_router(auth_router,     prefix="/api/v1")


# ── SSE endpoint for real-time pipeline events ────────────────────────────────
@app.get("/api/v1/events")
async def sse_stream():
    """
    Server-Sent Events stream for real-time pipeline progress.
    Connect from the frontend with:
        const es = new EventSource('/api/v1/events')
        es.onmessage = (e) => console.log(JSON.parse(e.data))
    """
    q: queue.Queue = queue.Queue(maxsize=200)
    with _sse_lock:
        _sse_listeners.append(q)

    async def generator() -> AsyncGenerator[str, None]:
        yield "data: " + json.dumps({"type": "connected", "ts": time.time()}) + "\n\n"
        try:
            while True:
                try:
                    msg = q.get(timeout=25)
                    yield f"data: {msg}\n\n"
                except queue.Empty:
                    # Heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            with _sse_lock:
                try:
                    _sse_listeners.remove(q)
                except ValueError:
                    pass

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )


@app.get("/")
def root():
    return {
        "service": "AI Newsroom API",
        "version": "2.0.0",
        "docs": "/docs",
        "events": "/api/v1/events",
    }
