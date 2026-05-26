"""
orchestrator/api.py — FastAPI application for the EvidenceGate REST API.

Sprint M1 endpoints:
  POST /api/v1/gate/run          — run EvidenceGateWorkflow
  GET  /api/v1/gate/runs/{id}    — fetch a previous run result (in-memory)
  GET  /api/v1/health            — health check
  GET  /api/v1/agents            — list the 5 active agents with their scopes

Design decisions:
  - Workflow singleton created at startup; mock_mode if ANTHROPIC_API_KEY absent.
  - Runs stored in a plain dict (sufficient for M1; Outcome DB comes in M3).
  - Rate limiting: simple in-memory dict keyed by client IP (no extra deps).
  - CORS: circles-ai.ai + localhost variants allowed.
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Dict, List
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .schemas.api import (
    AgentInfo,
    AgentsResponse,
    ErrorDetail,
    HealthResponse,
    RunGateRequest,
    RunGateResponse,
)
from .workflows.evidence_gate import EvidenceGateWorkflow

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

API_VERSION = "0.1.0"
SPRINT = "M1"

# ---------------------------------------------------------------------------
# Rate limiting (simple in-process, no external dep)
# ---------------------------------------------------------------------------

RATE_LIMIT_REQUESTS = 10   # max requests
RATE_LIMIT_WINDOW_S = 60   # per window (seconds)

# ip → list of request timestamps (float epoch seconds)
_rate_limit_store: Dict[str, List[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> None:
    """Raise 429 if `ip` has exceeded RATE_LIMIT_REQUESTS in the last window."""
    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW_S
    timestamps = _rate_limit_store[ip]

    # Evict old timestamps
    timestamps[:] = [t for t in timestamps if t > window_start]

    if len(timestamps) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: max {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW_S}s",
        )

    timestamps.append(now)


# ---------------------------------------------------------------------------
# Workflow singleton
# ---------------------------------------------------------------------------

def _build_workflow() -> EvidenceGateWorkflow:
    has_key = bool(os.getenv("ANTHROPIC_API_KEY", "").strip())
    mock = not has_key
    if mock:
        logger.warning(
            "ANTHROPIC_API_KEY not set — EvidenceGateWorkflow starting in mock_mode. "
            "Responses will be deterministic test stubs."
        )
    return EvidenceGateWorkflow(mock_mode=mock)


_workflow: EvidenceGateWorkflow = _build_workflow()

# ---------------------------------------------------------------------------
# In-memory run store  (M1 — Outcome DB replaces this in M3)
# ---------------------------------------------------------------------------

_runs: Dict[str, RunGateResponse] = {}

# ---------------------------------------------------------------------------
# Agent catalogue (static, from SCOPES.md)
# ---------------------------------------------------------------------------

_AGENTS: List[AgentInfo] = [
    AgentInfo(
        name="idea_hunter",
        scope_does="Generates ONE IdeaSpec from a topic/trend signal (Step 1)",
        scope_does_not="Does not validate ideas, define ICP, design tests, write copy, or make decisions",
        status="active",
    ),
    AgentInfo(
        name="idea_maturer",
        scope_does="Defines ICP + value proposition + key risks for a given IdeaSpec (Step 2)",
        scope_does_not="Does not generate ideas, design tests, write copy, or make decisions",
        status="active",
    ),
    AgentInfo(
        name="market_validator",
        scope_does="Designs the market test — hypothesis, metrics, budget, duration (Step 3)",
        scope_does_not="Does not generate ideas, define ICP, write copy, or make decisions",
        status="active",
    ),
    AgentInfo(
        name="landing_generator",
        scope_does="Writes landing page copy — headline, value props, CTA (Step 4a)",
        scope_does_not="Does not generate ideas, design tests, define ICP, or make decisions",
        status="active",
    ),
    AgentInfo(
        name="gate_decider",
        scope_does="Evaluates real metrics vs. thresholds → pass/kill/iterate (Step 4b)",
        scope_does_not="Does not generate ideas, define ICP, design tests, or write copy",
        status="active",
    ),
]

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Factory of Factories — Orchestrator API",
    description=(
        "EvidenceGate REST API for circles-ai.ai. "
        "Validates business ideas via a 4-step linear workflow before any product is built."
    ),
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — strict allow-list, no wildcards
_DEFAULT_ALLOWED_ORIGINS = [
    "https://circles-ai.ai",
    "https://www.circles-ai.ai",
    "https://dashboard.circles-ai.ai",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
]
_extra_origins = [
    o.strip()
    for o in os.getenv("EXTRA_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEFAULT_ALLOWED_ORIGINS + _extra_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
    expose_headers=["X-Request-Id"],
    max_age=600,
)


# Security headers middleware (OWASP basic hardening)
@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    # Defence-in-depth: prevent clickjacking, MIME sniffing, info leaks
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # HSTS only meaningful over HTTPS; harmless otherwise
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    # API only serves JSON — disallow all script/img sources
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )
    return response

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_ip(request: Request) -> str:
    """Extract best-guess client IP from request."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _serialize_run(run) -> RunGateResponse:  # noqa: ANN001  (EvidenceGateRun)
    """Convert an EvidenceGateRun dataclass to RunGateResponse."""
    return RunGateResponse(
        run_id=str(run.run_id),
        status="completed",
        idea_title=run.idea.title,
        verdict=run.decision.verdict.value,
        confidence=run.decision.confidence,
        rationale=run.decision.rationale,
        next_steps=run.decision.next_steps,
        landing_headline=run.landing.headline,
        landing_slug=run.landing.domain_slug,
        test_design=run.test_design.model_dump(),
        canonical_goal_statement=(
            run.canonical_goal.goal_statement if run.canonical_goal else ""
        ),
        steps_used=run.budget_tracker.steps_used if run.budget_tracker else 0,
        cost_usd_estimated=run.budget_tracker.cost_used_usd if run.budget_tracker else 0.0,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["meta"],
)
def health() -> HealthResponse:
    """Returns API version, mode (live/mock), and workflow name."""
    mode = "mock" if _workflow._mock_mode else "live"
    return HealthResponse(version=API_VERSION, mode=mode)


@app.get(
    "/api/v1/agents",
    response_model=AgentsResponse,
    summary="List active agents",
    tags=["meta"],
)
def list_agents() -> AgentsResponse:
    """Returns the 5 agents active in Sprint M1 with their exclusive scopes."""
    return AgentsResponse(agents=_AGENTS, total=len(_AGENTS))


@app.post(
    "/api/v1/gate/run",
    response_model=RunGateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run the EvidenceGate workflow",
    tags=["gate"],
    responses={
        422: {"model": ErrorDetail, "description": "Validation error (e.g. topic too short)"},
        429: {"model": ErrorDetail, "description": "Rate limit exceeded"},
        500: {"model": ErrorDetail, "description": "Workflow error"},
    },
)
def run_gate(
    body: RunGateRequest,
    request: Request,
) -> RunGateResponse:
    """
    Launch an EvidenceGateWorkflow for the given topic.

    - Instantiates idea_hunter → idea_maturer → market_validator →
      landing_generator → gate_decider in sequence.
    - Returns the full gate result including verdict, landing copy, and test design.
    - Run result is stored in memory and retrievable via GET /api/v1/gate/runs/{run_id}.
    """
    ip = _client_ip(request)
    _check_rate_limit(ip)

    try:
        run = _workflow.run(topic=body.topic, metrics=body.metrics)
    except Exception as exc:
        logger.exception("EvidenceGateWorkflow.run failed for topic=%r", body.topic)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Workflow error: {exc}",
        ) from exc

    response = _serialize_run(run)
    _runs[response.run_id] = response
    return response


@app.get(
    "/api/v1/gate/runs/{run_id}",
    response_model=RunGateResponse,
    summary="Get a gate run result by ID",
    tags=["gate"],
    responses={
        404: {"model": ErrorDetail, "description": "Run ID not found"},
    },
)
def get_run(run_id: str) -> RunGateResponse:
    """
    Retrieve a previously completed gate run by its UUID.

    Runs are stored in-memory for the lifetime of the process (M1).
    Persistent storage via Outcome DB is planned for M3.
    """
    # Validate UUID format to give a useful 422 before a 404
    try:
        UUID(run_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid run_id format: {run_id!r} — expected UUID v4",
        )

    result = _runs.get(run_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id!r} not found. Runs are stored in-memory; restart clears them.",
        )
    return result


# ---------------------------------------------------------------------------
# Generic exception handler for unexpected errors
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def _unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )
