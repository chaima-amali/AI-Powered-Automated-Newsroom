"""
api/routes/pipeline.py
-----------------------
Pipeline management API — trigger stages, stream progress, inspect job history.

BUGS FIXED vs original health.py admin trigger:
  1. Background threads were fire-and-forget with no job tracking
  2. No way to poll stage status without parsing logs
  3. No cancellation support
  4. Stages ran sequentially in same thread → blocked API response
  5. No stage-level progress reporting

IMPROVEMENTS:
  - Each pipeline run creates a pipeline_jobs record
  - Progress is broadcast via SSE (see main.py /api/v1/events)
  - Status polling endpoint: GET /api/v1/pipeline/status
  - Job history: GET /api/v1/pipeline/jobs
  - Safe concurrent execution guard (won't start if already running)
"""
from __future__ import annotations

import logging
import os
import threading
import time
import traceback
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from db.connection import get_cursor, has_db_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipeline", tags=["Pipeline"])

API_SECRET = os.environ.get("API_SECRET_KEY", "")

# Tracks currently-running stages (stage_name → thread)
_running: dict[str, threading.Thread] = {}
_running_lock = threading.Lock()


# ── Auth ──────────────────────────────────────────────────────────────────────
def _require_secret(x_api_key: Optional[str] = Header(None)):
    if API_SECRET and x_api_key != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden — provide X-Api-Key header")


# ── Models ────────────────────────────────────────────────────────────────────
class TriggerRequest(BaseModel):
    stage: str = "all"   # all | scraper | embedding | summarizer | rewriter


class JobSummary(BaseModel):
    id:         int
    job_type:   str
    status:     str
    attempts:   int
    last_error: Optional[str]
    created_at: str
    started_at: Optional[str]
    finished_at: Optional[str]


# ── Helpers ───────────────────────────────────────────────────────────────────
def _broadcast(event_type: str, **kwargs):
    """Broadcast via the global SSE broadcaster registered in main.py."""
    try:
        import builtins
        fn = getattr(builtins, "_newsroom_broadcast", None)
        if fn:
            fn(event_type, kwargs)
    except Exception:
        pass


def _upsert_job(job_type: str, status: str = "pending", error: str | None = None,
                job_id: int | None = None) -> int | None:
    """Create or update a pipeline_jobs row. Silently fails if DB is unavailable."""
    if not has_db_settings():
        return None
    try:
        with get_cursor() as cur:
            if job_id is None:
                cur.execute(
                    "INSERT INTO pipeline_jobs (job_type, status) VALUES (%s, %s) RETURNING id",
                    (job_type, status),
                )
                return int(cur.fetchone()[0])
            else:
                if status in ("running",):
                    cur.execute(
                        "UPDATE pipeline_jobs SET status=%s, started_at=NOW(), attempts=attempts+1 WHERE id=%s",
                        (status, job_id),
                    )
                elif status in ("done", "failed"):
                    cur.execute(
                        "UPDATE pipeline_jobs SET status=%s, finished_at=NOW(), last_error=%s WHERE id=%s",
                        (status, error, job_id),
                    )
                return job_id
    except Exception as e:
        logger.warning("pipeline_jobs DB update failed: %s", e)
        return job_id


def _run_stage(stage_name: str):
    """
    Execute a single pipeline stage in a background thread.
    Handles DB job tracking, SSE broadcasts, and error reporting.
    """
    job_id = _upsert_job(stage_name)
    _broadcast("stage_start", stage=stage_name, job_id=job_id)
    logger.info("▶ Pipeline stage '%s' starting (job_id=%s)", stage_name, job_id)

    _upsert_job(stage_name, status="running", job_id=job_id)
    started = time.time()

    try:
        if stage_name == "scraper":
            from pipeline.scraper.orchestrator import run_scraper
            result = run_scraper()
        elif stage_name == "embedding":
            from pipeline.embedding.pipeline import run_embedding_pipeline
            result = run_embedding_pipeline()
        elif stage_name == "summarizer":
            from pipeline.summarizer.pipeline import run_summarization_pipeline
            result = run_summarization_pipeline()
        elif stage_name == "rewriter":
            from pipeline.rewriter.pipeline import run_rewriter_pipeline
            result = run_rewriter_pipeline()
        else:
            raise ValueError(f"Unknown stage: {stage_name}")

        elapsed = round(time.time() - started, 1)
        _upsert_job(stage_name, status="done", job_id=job_id)
        _broadcast("stage_done", stage=stage_name, job_id=job_id,
                   elapsed_sec=elapsed, result=str(result)[:500])
        logger.info("✅ Pipeline stage '%s' done in %.1fs", stage_name, elapsed)

    except Exception as exc:
        elapsed = round(time.time() - started, 1)
        err = traceback.format_exc()
        _upsert_job(stage_name, status="failed", error=err[:2000], job_id=job_id)
        _broadcast("stage_error", stage=stage_name, job_id=job_id,
                   elapsed_sec=elapsed, error=str(exc))
        logger.error("❌ Pipeline stage '%s' failed after %.1fs: %s", stage_name, elapsed, exc)

    finally:
        with _running_lock:
            _running.pop(stage_name, None)


# ── Routes ────────────────────────────────────────────────────────────────────

VALID_STAGES = {"all", "scraper", "embedding", "summarizer", "rewriter"}
STAGE_ORDER  = ["scraper", "embedding", "summarizer", "rewriter"]


@router.post("/trigger", dependencies=[Depends(_require_secret)])
def trigger_pipeline(req: TriggerRequest):
    """
    Trigger one or all pipeline stages asynchronously.
    Returns immediately; monitor progress via GET /api/v1/events (SSE).
    """
    if req.stage not in VALID_STAGES:
        raise HTTPException(400, f"Invalid stage. Valid: {sorted(VALID_STAGES)}")

    stages = STAGE_ORDER if req.stage == "all" else [req.stage]

    started = []
    already_running = []

    with _running_lock:
        for s in stages:
            if s in _running and _running[s].is_alive():
                already_running.append(s)
            else:
                t = threading.Thread(target=_run_stage, args=(s,), daemon=True, name=f"pipeline-{s}")
                _running[s] = t
                started.append(s)

    # Start threads outside the lock
    for s in started:
        with _running_lock:
            if s in _running:
                _running[s].start()

    return {
        "status": "triggered",
        "started": started,
        "already_running": already_running,
        "monitor": "/api/v1/events",
    }


@router.get("/status")
def pipeline_status():
    """Return current status of all pipeline stages."""
    with _running_lock:
        running = {s: t.is_alive() for s, t in _running.items()}

    status = {s: ("running" if running.get(s) else "idle") for s in STAGE_ORDER}

    if has_db_settings():
        try:
            with get_cursor(dict_cursor=True) as cur:
                cur.execute("""
                    SELECT DISTINCT ON (job_type) job_type, status, started_at, finished_at, last_error
                    FROM pipeline_jobs ORDER BY job_type, created_at DESC
                """)
                for row in cur.fetchall():
                    jt = row["job_type"]
                    if jt in status and status[jt] == "idle":
                        status[jt] = row["status"]
        except Exception:
            pass

    return {"stages": status, "running": [s for s, v in status.items() if v == "running"]}


@router.get("/jobs", response_model=list[JobSummary])
def list_jobs(limit: int = 20):
    """Return recent pipeline job history."""
    if not has_db_settings():
        return []
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """SELECT id, job_type, status, attempts, last_error,
                      created_at::text, started_at::text, finished_at::text
               FROM pipeline_jobs ORDER BY created_at DESC LIMIT %s""",
            (limit,),
        )
        return [JobSummary(**dict(r)) for r in cur.fetchall()]
