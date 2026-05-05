"""
summarizer/
────────────
AI Newsroom Pipeline — Summarization Module

Public API:
    from summarizer.pipeline import run_summarization_pipeline
    from summarizer.router import route_and_summarize
"""

from .pipeline import run_summarization_pipeline
from .router import route_and_summarize

__all__ = ["run_summarization_pipeline", "route_and_summarize"]
