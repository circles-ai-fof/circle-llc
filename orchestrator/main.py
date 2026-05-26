"""
orchestrator/main.py — Entry point for uvicorn.

Usage:
    # from repo root
    uvicorn orchestrator.main:app --reload --port 8000

    # or directly
    python -m uvicorn orchestrator.main:app --reload --port 8000
"""
from .api import app  # noqa: F401  — re-exported for uvicorn

__all__ = ["app"]
