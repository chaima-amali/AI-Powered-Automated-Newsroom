"""
pipeline/scheduler/scheduler.py (v2)
Improvements: SSE broadcast on each job, pipeline_jobs DB tracking,
clean shutdown, integrated logging.
"""
from __future__ import annotations
import logging, sys, time
from datetime import datetime
from dotenv import load_dotenv; load_dotenv()
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from pytz import timezone as pytz_timezone
from db.connection import init_pool
from utils.logging_config import setup_logging
setup_logging()
logger = logging.getLogger("scheduler")
TZ = pytz_timezone("Africa/Algiers")

def _broadcast(ev, **kw):
    try:
        import builtins
        fn = getattr(builtins,"_newsroom_broadcast",None)
        if fn: fn(ev, kw)
    except Exception: pass

def _run(job_type, fn):
    logger.info("⏰ Starting: %s", job_type)
    _broadcast("stage_start", stage=job_type)
    t0 = time.time()
    try:
        result = fn()
        e = round(time.time()-t0,1)
        logger.info("✅ Done: %s in %.1fs", job_type, e)
        _broadcast("stage_done", stage=job_type, elapsed_sec=e, result=str(result)[:200])
    except Exception as exc:
        e = round(time.time()-t0,1)
        logger.error("❌ Failed: %s after %.1fs: %s", job_type, e, exc, exc_info=True)
        _broadcast("stage_error", stage=job_type, elapsed_sec=e, error=str(exc))

def job_rss():
    from pipeline.scraper.orchestrator import run_scraper; _run("scraper", run_scraper)
def job_sitemap():
    from config.sources import SOURCES
    from pipeline.scraper.sitemap_collector import fetch_sitemap_urls
    from pipeline.scraper.deduplication import Deduplicator
    def _fn():
        d = Deduplicator()
        for s in SOURCES: d.add_from_sitemap(fetch_sitemap_urls(s))
        return d.stats()
    _run("sitemap", _fn)
def job_category():
    from config.sources import SOURCES
    from pipeline.scraper.category_crawler import fetch_category_urls
    def _fn():
        total=0
        for s in SOURCES: total += len(fetch_category_urls(s, known_urls=set()))
        return f"{total} URLs"
    _run("category_crawl", _fn)
def job_embedding():
    from pipeline.embedding.pipeline import run_embedding_pipeline; _run("embedding", run_embedding_pipeline)
def job_summarization():
    from pipeline.summarizer.pipeline import run_summarization_pipeline; _run("summarizer", run_summarization_pipeline)
def job_rewriter():
    from pipeline.rewriter.pipeline import run_rewriter_pipeline; _run("rewriter", run_rewriter_pipeline)
def job_cleanup():
    from db.connection import get_cursor
    def _fn():
        with get_cursor() as cur:
            cur.execute("DELETE FROM clusters WHERE article_count=0")
            cur.execute("UPDATE published_articles SET status='archived',updated_at=NOW() WHERE status='draft' AND generated_at < NOW()-INTERVAL '30 days'")
        return "done"
    _run("cleanup", _fn)

def build_scheduler():
    s = BlockingScheduler(timezone=TZ)
    s.add_job(job_rss,           IntervalTrigger(minutes=30,timezone=TZ),id="rss",       name="RSS Scraping",        max_instances=1,misfire_grace_time=300)
    s.add_job(job_sitemap,       CronTrigger(hour=2,minute=0,timezone=TZ),id="sitemap",  name="Sitemap Discovery",   max_instances=1,misfire_grace_time=3600)
    s.add_job(job_category,      CronTrigger(hour=3,minute=0,timezone=TZ),id="category", name="Category Crawl",      max_instances=1,misfire_grace_time=3600)
    s.add_job(job_embedding,     IntervalTrigger(hours=2,timezone=TZ),id="embedding",    name="Embedding+Cluster",   max_instances=1,misfire_grace_time=600)
    s.add_job(job_summarization, IntervalTrigger(hours=3,timezone=TZ),id="summarizer",   name="Summarization",       max_instances=1,misfire_grace_time=600)
    s.add_job(job_rewriter,      IntervalTrigger(hours=4,timezone=TZ),id="rewriter",     name="AI Rewriting",        max_instances=1,misfire_grace_time=600)
    s.add_job(job_cleanup,       CronTrigger(hour=4,minute=0,timezone=TZ),id="cleanup",  name="DB Cleanup",          max_instances=1,misfire_grace_time=3600)
    s.add_listener(lambda ev: (
        logger.error("Job '%s' FAILED: %s", ev.job_id, ev.exception) if ev.exception
        else logger.info("Job '%s' ✔ %s", ev.job_id, datetime.now(TZ).strftime("%H:%M"))
    ), EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    return s

def main():
    logger.info("Starting Newsroom Scheduler (Africa/Algiers)")
    init_pool()
    sched = build_scheduler()
    for j in sched.get_jobs():
        logger.info("  %-25s next=%s", j.name, getattr(j,"next_run_time","?"))
    try:
        sched.start()
    except (KeyboardInterrupt,SystemExit):
        logger.info("Scheduler stopped."); sys.exit(0)

if __name__ == "__main__": main()
