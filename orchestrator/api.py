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

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .schemas.api import (
    AgentInfo,
    AgentsResponse,
    AuthAttemptItem,
    AuthAttemptsResponse,
    DiagnosticResponse,
    ErrorDetail,
    HealthResponse,
    HumanOverrideRequest,
    HumanOverrideResponse,
    LeadCaptureRequest,
    LeadCaptureResponse,
    LeadImportItem,
    LeadImportRequest,
    LeadImportResponse,
    LeadItem,
    LeadsListResponse,
    LeadsStatsBySlug,
    LeadsStatsResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    MeResponse,
    PendingReviewItem,
    PendingReviewResponse,
    RunFromSourcesRequest,
    RunGateRequest,
    RunGateResponse,
    ScanRunRequest,
    ScanRunResponse,
    AnalyzeSignalResponse,
    AnalyzeSignalsBatchRequest,
    AnalyzeSignalsBatchResponse,
    SignalAnalysisItem,
    SignalFeedback,
    SignalItem,
    SignalsCleanupMocksResponse,
    SignalsCleanupResponse,
    SignalsListResponse,
    StatsResponse,
    SourceCreate,
    SourceItem,
    SourceQuality,
    SourcesListResponse,
    SourcesQualityResponse,
    AnalyzeBatchRequest,
    AnalyzeBatchResponse,
    FileImportResponse,
    LinkLogItem,
    LinksLogResponse,
    PipelineColumnResponse,
    PipelineResponse,
    RunSummary,
)
from .core.anti_bot import (
    check_dwell,
    check_gate_run_secret,
    check_honeypot,
    check_rate_limit,
    gate_run_secret_required,
    is_disposable_email,
    turnstile_required,
    verify_turnstile_token,
)
from .core.models import GateVerdict, HumanOverride
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
# Run + lead store
# Backed by SQLite when DATABASE_PATH is set (M2 deploy), in-memory otherwise.
# Outcome DB (Postgres) replaces both in M3.
# ---------------------------------------------------------------------------

from .core.storage import leads_store as _leads_persistent_store
from .core.storage import runs_store as _runs

# Backward-compat name for human_review tests that import _runs directly.
# The dict-like API of RunsStore makes this transparent.

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
    # Ensemble votes (if recorded in key_evidence)
    ensemble_votes = [e for e in run.decision.key_evidence if "/" in e]
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
        needs_human_review=run.decision.needs_human_review,
        review_reason=run.decision.review_reason,
        ensemble_votes=ensemble_votes or None,
        human_override=(
            run.decision.human_override.model_dump(mode="json")
            if run.decision.human_override
            else None
        ),
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

    Each call costs ~$0.06 in real LLM mode. Multiple layers of anti-bot
    protection apply (R26):
      1. Optional X-Gate-Secret shared header (if GATE_RUN_SECRET env set)
      2. Per-IP burst + daily quotas (expensive_llm tier)
      3. Legacy 10/60s in-process limit (kept for compatibility)
    """
    ip = _client_ip(request)

    # Layer 6: shared-secret header — strongest, opt-in for private deployments
    secret_check = check_gate_run_secret(request.headers.get("X-Gate-Secret"))
    if not secret_check.allowed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=secret_check.reason or "Authentication required",
        )

    # Layer 1+2: per-IP burst + daily quotas (tier: expensive_llm)
    rl = check_rate_limit(ip, tier="expensive_llm")
    if not rl.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=rl.reason or "Rate limit exceeded",
            headers={"Retry-After": str(rl.retry_after_s or 60)},
        )

    # Legacy global rate limit (for compatibility with older clients/tests)
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
# Human review (escalation) endpoints
# ---------------------------------------------------------------------------


@app.get(
    "/api/v1/gate/pending-review",
    response_model=PendingReviewResponse,
    summary="List runs awaiting human review (ensemble disagreement)",
    tags=["gate", "review"],
)
def list_pending_review() -> PendingReviewResponse:
    """
    Returns all completed runs where the ensemble flagged
    `needs_human_review=True` and no human_override has been recorded yet.
    """
    pending = [
        PendingReviewItem(
            run_id=r.run_id,
            idea_title=r.idea_title,
            verdict=r.verdict,
            confidence=r.confidence,
            review_reason=r.review_reason or "",
            ensemble_votes=r.ensemble_votes or [],
            rationale=r.rationale,
        )
        for r in _runs.values()
        if r.needs_human_review and r.human_override is None
    ]
    return PendingReviewResponse(pending_count=len(pending), items=pending)


@app.post(
    "/api/v1/gate/runs/{run_id}/human-override",
    response_model=HumanOverrideResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a human verdict on a flagged run",
    tags=["gate", "review"],
    responses={
        404: {"model": ErrorDetail, "description": "Run not found"},
        409: {"model": ErrorDetail, "description": "Run not flagged for review or already overridden"},
        422: {"model": ErrorDetail, "description": "Invalid request body or run_id"},
    },
)
def post_human_override(
    run_id: str, body: HumanOverrideRequest, request: Request
) -> HumanOverrideResponse:
    """
    A founder records the final verdict for a run that the ensemble could not
    resolve unanimously. The recorded override is stored alongside the original
    decision and surfaces in the dashboard for future calibration.
    """
    _check_rate_limit(_client_ip(request))

    try:
        UUID(run_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid run_id format: {run_id!r} — expected UUID v4",
        )

    stored = _runs.get(run_id)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id!r} not found.",
        )
    if not stored.needs_human_review:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This run was not flagged for human review (ensemble agreed).",
        )
    if stored.human_override is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This run has already been overridden.",
        )

    override = HumanOverride(
        decided_by=body.decided_by,
        original_verdict=GateVerdict(stored.verdict),
        override_verdict=GateVerdict(body.verdict),
        reason=body.reason,
    )

    # Update stored response in place
    updated = stored.model_copy(
        update={
            "verdict": body.verdict,
            "human_override": override.model_dump(mode="json"),
        }
    )
    _runs[run_id] = updated

    logger.info(
        "human_override: run=%s %s -> %s by=%s",
        run_id,
        stored.verdict,
        body.verdict,
        body.decided_by,
    )

    return HumanOverrideResponse(
        run_id=run_id,
        original_verdict=stored.verdict,
        override_verdict=body.verdict,
        decided_by=body.decided_by,
        decided_at=override.decided_at.isoformat(),
        reason=body.reason,
    )


# ---------------------------------------------------------------------------
# Lead capture (anti-bot protected) — receives form submissions from /f/[slug]
# ---------------------------------------------------------------------------

# Lead store: SQLite-backed when DATABASE_PATH is set, in-memory otherwise.
# `_leads_store` retained as a name so existing tests can patch/clear it.
_leads_store = _leads_persistent_store


@app.post(
    "/api/v1/leads",
    response_model=LeadCaptureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Capture a lead from a factory landing page",
    tags=["leads"],
    responses={
        400: {"model": ErrorDetail, "description": "Honeypot / disposable email / dwell rejected"},
        401: {"model": ErrorDetail, "description": "Turnstile token missing or invalid"},
        429: {"model": ErrorDetail, "description": "Rate limit exceeded"},
        422: {"model": ErrorDetail, "description": "Validation error"},
    },
)
def capture_lead(
    body: LeadCaptureRequest,
    request: Request,
) -> LeadCaptureResponse:
    """
    Public form-submission endpoint for landing pages.

    Anti-bot stack (R26):
      Layer 1+2: per-IP burst + daily quotas (public_form tier)
      Layer 3:   honeypot + dwell-time
      Layer 4:   Cloudflare Turnstile token verify (opt-in)
      Layer 5:   disposable-email blocklist
    """
    ip = _client_ip(request)

    # Layer 1+2: rate limit
    rl = check_rate_limit(ip, tier="public_form")
    if not rl.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=rl.reason or "Rate limit exceeded",
            headers={"Retry-After": str(rl.retry_after_s or 60)},
        )

    # Layer 3a: honeypot
    hp = check_honeypot({"company_website": body.company_website})
    if not hp.allowed:
        # Don't reveal that we detected the honeypot — bots learn
        logger.info("anti_bot: honeypot triggered ip=%s slug=%s", ip, body.slug)
        return LeadCaptureResponse(
            accepted=True,  # silent accept to throw off the bot
            slug=body.slug,
            message="Recibido.",
        )

    # Layer 3b: dwell
    dwell = check_dwell(body.dwell_ms)
    if not dwell.allowed:
        logger.info("anti_bot: dwell-too-fast ip=%s dwell=%s", ip, body.dwell_ms)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please try again in a moment.",
            headers={"Retry-After": str(dwell.retry_after_s or 5)},
        )

    # Layer 4: Turnstile (only enforced when configured)
    if turnstile_required():
        ts = verify_turnstile_token(body.turnstile_token, ip)
        if not ts.allowed:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bot-check failed — please reload and try again.",
            )

    # Layer 5: disposable email
    if is_disposable_email(body.email):
        logger.info("anti_bot: disposable-email rejected ip=%s email_domain=%s", ip, body.email.split('@')[-1])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Disposable email domains are not accepted.",
        )

    # All checks passed -> store (SQLite or memory depending on env)
    _leads_store.add(
        slug=body.slug,
        email=body.email,
        name=body.name,
        ip=ip,
        user_agent=request.headers.get("user-agent", "")[:200] or None,
    )
    logger.info("lead captured slug=%s email=%s", body.slug, body.email)
    return LeadCaptureResponse(
        accepted=True,
        slug=body.slug,
        message="Recibido. Te avisaremos en máximo 14 días si seguimos adelante con esta fábrica.",
    )


# ---------------------------------------------------------------------------
# Leads viewer (admin) — protected by X-Gate-Secret when configured
# ---------------------------------------------------------------------------


def _mask_email(email: str) -> str:
    """Privacy: when no admin secret, expose only first 2 chars and domain."""
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"{local[:1]}***@{domain}"
    return f"{local[:2]}***@{domain}"


def _mask_ip(ip: Optional[str]) -> Optional[str]:
    """Privacy: zero the last octet for IPv4, last segment for IPv6."""
    if not ip:
        return None
    if "." in ip:
        parts = ip.split(".")
        if len(parts) == 4:
            return ".".join(parts[:3] + ["xxx"])
    if ":" in ip:
        parts = ip.split(":")
        return ":".join(parts[:-1] + ["xxxx"])
    return "***"


def _is_admin(request: Request) -> bool:
    """A request is 'admin' if it provides the correct X-Gate-Secret header.
    When GATE_RUN_SECRET is not configured, no caller is admin (always masked)."""
    secret = os.getenv("GATE_RUN_SECRET", "")
    if not secret:
        return False
    return request.headers.get("X-Gate-Secret") == secret


@app.get(
    "/api/v1/leads/stats",
    response_model=LeadsStatsResponse,
    summary="Aggregate lead counts per factory slug",
    tags=["leads"],
)
def leads_stats(request: Request) -> LeadsStatsResponse:
    """
    Public aggregate counts — no PII exposed.
    Returns total leads and breakdown per slug.
    """
    rl = check_rate_limit(_client_ip(request), tier="public_form")
    if not rl.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=rl.reason or "Rate limit exceeded",
            headers={"Retry-After": str(rl.retry_after_s or 60)},
        )
    # Stream-friendly: iterate known slugs via factories catalog OR just use
    # the SQLite COUNT GROUP BY. For now we scan in-memory via list_by_slug
    # for the few known factories. Production would use a single SQL query.
    from .core.storage import leads_store
    # Known slugs come from the landing's factories catalog; for M2 we hard-code
    # the active ones. M3 reads them from the Outcome DB.
    known_slugs = ["techpulse-latam", "opscore-ai"]
    items: List[LeadsStatsBySlug] = []
    total = 0
    for slug in known_slugs:
        n = len(leads_store.list_by_slug(slug))
        items.append(LeadsStatsBySlug(slug=slug, count=n))
        total += n
    items.sort(key=lambda x: x.count, reverse=True)
    return LeadsStatsResponse(total_leads=total, by_slug=items)


@app.get(
    "/api/v1/leads/{slug}",
    response_model=LeadsListResponse,
    summary="List leads for one factory slug",
    tags=["leads"],
    responses={
        404: {"model": ErrorDetail, "description": "Slug has no leads (or doesn't exist)"},
    },
)
def list_leads(slug: str, request: Request, limit: int = 100) -> LeadsListResponse:
    """
    Returns the most recent `limit` leads for the given factory slug.

    When called WITHOUT a valid X-Gate-Secret header, emails are masked
    (`fo***@domain.com`). With the header, full emails are returned.
    """
    rl = check_rate_limit(_client_ip(request), tier="public_form")
    if not rl.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=rl.reason or "Rate limit exceeded",
            headers={"Retry-After": str(rl.retry_after_s or 60)},
        )
    if limit < 1 or limit > 500:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be between 1 and 500",
        )
    from .core.storage import leads_store
    raw = leads_store.list_by_slug(slug)
    is_admin = _is_admin(request)
    items: List[LeadItem] = []
    for r in raw[:limit]:
        items.append(
            LeadItem(
                slug=slug,
                email=r["email"] if is_admin else _mask_email(r["email"]),
                name=r.get("name"),
                ts=int(r["ts"]),
                ip_masked=_mask_ip(r.get("ip")),
            )
        )
    return LeadsListResponse(
        slug=slug,
        count=len(raw),
        leads=items,
        masked=not is_admin,
    )


# ---------------------------------------------------------------------------
# Diagnostic endpoint — public read-only snapshot for debugging from browser
# ---------------------------------------------------------------------------


@app.get(
    "/api/v1/diagnostic",
    response_model=DiagnosticResponse,
    summary="Public snapshot of API config (CORS, features, counts)",
    tags=["meta"],
)
def diagnostic() -> DiagnosticResponse:
    """
    Safe to expose publicly:
      - version, sprint, mode (live/mock)
      - configured CORS allowed origins (so you can see why a browser is blocked)
      - feature flags (ensemble, research, fact-check) — boolean only, no secrets
      - aggregate counts (no PII)
    """
    from .core.storage import leads_store, runs_store
    return DiagnosticResponse(
        version=API_VERSION,
        sprint=SPRINT,
        mode="mock" if _workflow._mock_mode else "live",
        cors_allowed_origins=list(_DEFAULT_ALLOWED_ORIGINS) + _extra_origins,
        features={
            "ensemble_gate_enabled": os.getenv("ENSEMBLE_GATE_ENABLED", "false").lower() in {"true", "1", "yes"},
            "idea_enricher_research": os.getenv("IDEA_ENRICHER_RESEARCH", "false").lower() in {"true", "1", "yes"},
            "fact_check_enabled": os.getenv("FACT_CHECK_ENABLED", "false").lower() in {"true", "1", "yes"},
            "turnstile_required": bool(os.getenv("TURNSTILE_SECRET_KEY")),
            "gate_run_secret_required": bool(os.getenv("GATE_RUN_SECRET")),
            "openai_key_present": bool(os.getenv("OPENAI_API_KEY")),
            "google_key_present": bool(os.getenv("GOOGLE_API_KEY")),
            "anthropic_key_present": bool(os.getenv("ANTHROPIC_API_KEY")),
            "persistent_storage": bool(os.getenv("DATABASE_PATH")),
        },
        leads_count_total=leads_store.count(),
        runs_count_total=len(runs_store.values()),
    )


@app.get(
    "/api/v1/stats",
    response_model=StatsResponse,
    summary="Aggregated counts for sidebar badges + cost indicators",
    tags=["meta"],
)
def stats(request: Request) -> StatsResponse:
    """Single round-trip for the sidebar to populate all its badges.

    Cheap: no LLM, no scan — just store aggregates. Safe to call every
    page load. Auth required (these counts are private business data).
    """
    _require_user(request)
    from .core.storage import signals_store, sources_store, runs_store
    cutoff_24h = int(time.time()) - 86_400
    cutoff_30d = int(time.time()) - 30 * 86_400

    all_signals = signals_store.list(limit=10_000, min_score=0)
    signals_total = len(all_signals)
    signals_new_24h = sum(1 for s in all_signals if s.get("created_at", 0) >= cutoff_24h)
    signals_unmarked = sum(1 for s in all_signals if not s.get("feedback") and not s.get("promoted_run_id"))
    signals_with_analysis = sum(1 for s in all_signals if s.get("analysis"))
    signals_promoted = sum(1 for s in all_signals if s.get("promoted_run_id"))

    all_sources = sources_store.list()
    sources_total = len(all_sources)
    sources_active = sum(1 for s in all_sources if s.get("active"))

    all_runs = list(runs_store.values())
    runs_total = len(all_runs)
    runs_pending_review = sum(
        1 for r in all_runs if r.needs_human_review and r.human_override is None
    )
    runs_pass = sum(1 for r in all_runs if r.verdict == "pass")
    runs_kill = sum(1 for r in all_runs if r.verdict == "kill")
    runs_iterate = sum(1 for r in all_runs if r.verdict == "iterate")

    cost_30d = 0.0
    cost_all = 0.0
    for r in all_runs:
        c = float(r.cost_usd_estimated or 0)
        cost_all += c
        # Best effort 30d filter — RunGateResponse has no created_at, so we
        # approximate "all time" as worst case. Will be tightened when runs
        # get persisted with timestamps (M4).
        cost_30d += c

    return StatsResponse(
        signals_total=signals_total,
        signals_new_24h=signals_new_24h,
        signals_unmarked=signals_unmarked,
        signals_with_analysis=signals_with_analysis,
        signals_promoted=signals_promoted,
        sources_total=sources_total,
        sources_active=sources_active,
        runs_total=runs_total,
        runs_pending_review=runs_pending_review,
        runs_pass=runs_pass,
        runs_kill=runs_kill,
        runs_iterate=runs_iterate,
        cost_usd_total_30d=round(cost_30d, 4),
        cost_usd_total_all_time=round(cost_all, 4),
    )


@app.get(
    "/api/v1/signals.csv",
    summary="Export signals as CSV (full snapshot, audit-friendly)",
    tags=["hunter"],
    response_class=JSONResponse,  # actual response is StreamingResponse below
)
def export_signals_csv(
    request: Request, promoted_only: bool = False, limit: int = 5000,
):
    """Stream every signal as CSV. Useful for spreadsheets/audit.

    Columns: id, created_at, source_name, source_kind, theme, score,
    trend_score, feedback, promoted_run_id, recommendation, market_size,
    icp_probable, evidence_urls (joined by ' | ').
    """
    _require_user(request)
    from fastapi.responses import StreamingResponse
    import csv
    import io
    from datetime import datetime, timezone
    from .core.storage import signals_store, sources_store

    rows = signals_store.list(limit=min(limit, 10_000), min_score=0)
    if promoted_only:
        rows = [r for r in rows if r.get("promoted_run_id")]
    source_names = {s["id"]: s["name"] for s in sources_store.list()}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "created_at_iso", "source_name", "source_kind", "theme",
        "score", "trend_score", "feedback", "promoted_run_id",
        "recommendation", "market_size_estimate", "icp_probable",
        "evidence_urls",
    ])
    for r in rows:
        analysis = r.get("analysis") or {}
        writer.writerow([
            r.get("id"),
            datetime.fromtimestamp(r.get("created_at", 0), tz=timezone.utc).isoformat(),
            source_names.get(r.get("source_id"), ""),
            r.get("source_kind", ""),
            r.get("theme", ""),
            f"{r.get('score', 0):.2f}",
            int(r.get("trend_score") or 0),
            r.get("feedback") or "",
            r.get("promoted_run_id") or "",
            analysis.get("recommendation", ""),
            analysis.get("market_size_estimate", ""),
            analysis.get("icp_probable", ""),
            " | ".join(r.get("evidence_urls", [])),
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=signals_{int(time.time())}.csv",
        },
    )


# ---------------------------------------------------------------------------
# Admin: import leads from a localStorage backup
# Used to rescue leads that were saved client-side because the API was
# unreachable (CORS / NEXT_PUBLIC_API_URL not set on the deploy yet, etc.)
# ---------------------------------------------------------------------------


@app.post(
    "/api/v1/admin/import-leads",
    response_model=LeadImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import leads from a client-side backup (admin only)",
    tags=["admin"],
    responses={
        401: {"model": ErrorDetail, "description": "Missing or invalid X-Gate-Secret"},
        422: {"model": ErrorDetail, "description": "Invalid payload"},
    },
)
def import_leads(body: LeadImportRequest, request: Request) -> LeadImportResponse:
    """
    Bulk-import leads that were stored in the browser's localStorage but never
    confirmed by the server. Requires X-Gate-Secret. De-duplicates by
    (slug, email) — already-stored pairs are skipped.

    Payload format mirrors localStorage entries the LeadForm writes:
        { "leads": [{ "slug", "email", "name", "ts_iso" }, ...] }
    """
    # Layer 6: must have admin secret
    secret = os.getenv("GATE_RUN_SECRET")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin endpoint disabled (GATE_RUN_SECRET not set on server).",
        )
    if request.headers.get("X-Gate-Secret") != secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Gate-Secret",
        )

    from .core.storage import leads_store

    imported = 0
    skipped = 0
    by_slug: Dict[str, int] = defaultdict(int)
    ip = _client_ip(request)

    # Pre-compute existing (slug, email) set for dedup
    seen = set()
    for slug in {item.slug for item in body.leads}:
        for existing in leads_store.list_by_slug(slug):
            seen.add((slug, existing["email"]))

    for item in body.leads:
        key = (item.slug, item.email)
        if key in seen:
            skipped += 1
            continue
        leads_store.add(
            slug=item.slug,
            email=item.email,
            name=item.name,
            ip=f"import-{ip[:30]}",  # tag as imported, not the real client IP
            user_agent=f"backup-import ts={item.ts_iso or ''}",
        )
        seen.add(key)
        imported += 1
        by_slug[item.slug] += 1

    logger.info(
        "admin import-leads: imported=%d skipped=%d by_slug=%s",
        imported, skipped, dict(by_slug),
    )
    return LeadImportResponse(
        imported=imported,
        skipped_duplicates=skipped,
        by_slug=dict(by_slug),
    )


# ---------------------------------------------------------------------------
# Auth (R27 / ADR-010) — closed beta allowlist
# ---------------------------------------------------------------------------


def _current_user(request: Request) -> Optional[Dict]:
    """Validate Authorization: Bearer <token>. Returns {email, expires_at} or None."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None
    from .core.storage import auth_store
    return auth_store.verify_session(token)


def _require_user(request: Request) -> Dict:
    """Raise 401 if no valid session. Returns user dict otherwise."""
    user = _current_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@app.post(
    "/api/v1/auth/login",
    response_model=LoginResponse,
    summary="Login with allowlisted email (closed beta)",
    tags=["auth"],
    responses={
        400: {"model": ErrorDetail, "description": "Malformed email"},
        403: {"model": ErrorDetail, "description": "Email not in beta allowlist"},
        429: {"model": ErrorDetail, "description": "Rate limit exceeded"},
    },
)
def auth_login(body: LoginRequest, request: Request) -> LoginResponse:
    """
    Email-only login for closed beta (R27 / ADR-010).

    - Allowlist via ALLOWED_EMAILS env var (comma-separated).
    - Every attempt is logged (allowed or rejected) for audit and geo lookup.
    - Returns a 7-day session token in the response body.

    NOT a password-protected endpoint. Allowlist secrecy is the security
    boundary; the 3 beta emails are not public.
    """
    from .core.auth import is_allowed, looks_like_email, new_token, session_expiry
    from .core.storage import auth_store

    ip = _client_ip(request)
    ua = request.headers.get("User-Agent", "")[:300]

    # Rate limit (public_form tier — generous, but prevents brute force)
    rl = check_rate_limit(ip, tier="public_form")
    if not rl.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=rl.reason or "Rate limit exceeded",
            headers={"Retry-After": str(rl.retry_after_s or 60)},
        )

    email_raw = body.email.strip()

    if not looks_like_email(email_raw):
        auth_store.log_attempt(email_raw, ip, ua, allowed=False, reason="malformed_email")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email malformado",
        )

    email_normalized = email_raw.lower()
    if not is_allowed(email_normalized):
        auth_store.log_attempt(email_normalized, ip, ua, allowed=False, reason="not_allowlisted")
        logger.info("auth: rejected %s from ip=%s", email_normalized, ip)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "El acceso a la plataforma está habilitado solo para usuarios beta. "
                "Tu email quedó en la lista de espera — te avisaremos cuando esté disponible."
            ),
        )

    # All good — create session
    token = new_token()
    expires_at = session_expiry()
    auth_store.create_session(token, email_normalized, expires_at)
    auth_store.log_attempt(email_normalized, ip, ua, allowed=True, reason="ok")
    logger.info("auth: granted session for %s exp=%d", email_normalized, expires_at)
    return LoginResponse(token=token, email=email_normalized, expires_at=expires_at)


@app.get(
    "/api/v1/auth/me",
    response_model=MeResponse,
    summary="Validate current session token",
    tags=["auth"],
    responses={401: {"model": ErrorDetail, "description": "No / invalid / expired session"}},
)
def auth_me(request: Request) -> MeResponse:
    user = _require_user(request)
    return MeResponse(email=user["email"], expires_at=user["expires_at"])


@app.post(
    "/api/v1/auth/logout",
    response_model=LogoutResponse,
    summary="Revoke current session token",
    tags=["auth"],
)
def auth_logout(request: Request) -> LogoutResponse:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return LogoutResponse(revoked=False)
    token = auth_header.split(" ", 1)[1].strip()
    from .core.storage import auth_store
    pre = auth_store.verify_session(token) is not None
    auth_store.revoke_session(token)
    return LogoutResponse(revoked=pre)


@app.get(
    "/api/v1/admin/auth-attempts",
    response_model=AuthAttemptsResponse,
    summary="List recent login attempts (admin)",
    tags=["admin", "auth"],
    responses={401: {"model": ErrorDetail, "description": "Admin secret required"}},
)
def list_auth_attempts(request: Request, limit: int = 200) -> AuthAttemptsResponse:
    """Requires X-Gate-Secret. Returns the most recent N login attempts.
    Use for audit + future country/geo lookup by IP."""
    secret = os.getenv("GATE_RUN_SECRET", "")
    if not secret or request.headers.get("X-Gate-Secret") != secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin secret required",
        )
    if limit < 1 or limit > 1000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be 1-1000",
        )
    from .core.storage import auth_store
    items = auth_store.list_attempts(limit=limit)
    return AuthAttemptsResponse(
        total=auth_store.count_attempts(),
        items=[AuthAttemptItem(**it) for it in items],
    )


# ---------------------------------------------------------------------------
# Sources + Signals (R28 / ADR-011 — autonomous hunter)
# ---------------------------------------------------------------------------


@app.get(
    "/api/v1/sources",
    response_model=SourcesListResponse,
    summary="List configured sources for the hunter",
    tags=["hunter"],
)
def list_sources(request: Request, active_only: bool = False) -> SourcesListResponse:
    _require_user(request)
    from .core.storage import sources_store
    rows = sources_store.list(active_only=active_only)
    items = [
        SourceItem(
            id=r["id"], kind=r["kind"], target=r["target"], name=r["name"],
            active=bool(r["active"]), last_scanned_at=r["last_scanned_at"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
    return SourcesListResponse(total=len(items), items=items)


@app.post(
    "/api/v1/sources",
    response_model=SourceItem,
    status_code=status.HTTP_201_CREATED,
    summary="Add a source to the hunter catalog",
    tags=["hunter"],
)
def add_source(body: SourceCreate, request: Request) -> SourceItem:
    _require_user(request)
    from .core.storage import sources_store
    new_id = sources_store.add(kind=body.kind, target=body.target, name=body.name)
    row = sources_store.get(new_id)
    if not row:
        raise HTTPException(status_code=500, detail="Failed to read back created source")
    return SourceItem(
        id=row["id"], kind=row["kind"], target=row["target"], name=row["name"],
        active=bool(row["active"]), last_scanned_at=row["last_scanned_at"],
        created_at=row["created_at"],
    )


@app.delete(
    "/api/v1/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a source",
    tags=["hunter"],
)
def delete_source(source_id: int, request: Request) -> None:
    _require_user(request)
    from .core.storage import sources_store
    sources_store.delete(source_id)


def _run_scan_internal(
    source_ids: Optional[List[int]] = None,
    auto_promote_threshold: float = 0.0,
    auto_analyze_trend_threshold: int = 0,
    auto_promote_trend_threshold: int = 0,
) -> Dict:
    """Core scan logic — used by both the manual endpoint and the auto-scan loop.

    Returns a dict with the same shape as ScanRunResponse fields, plus
    `signals_auto_analyzed` (count of signals enriched in-line by IdeaAnalyzer
    because their trend_score met `auto_analyze_trend_threshold`).

    Never raises — wraps each per-source error so one bad source doesn't kill
    the rest of the batch (critical for the background loop).
    """
    from .core.source_fetcher import fetch_by_kind
    from .core.storage import sources_store, signals_store
    from .agents.source_scanner import SourceScannerAgent
    from .agents.idea_analyzer import IdeaAnalyzerAgent

    if source_ids:
        sources = [s for s in (sources_store.get(sid) for sid in source_ids) if s]
    else:
        sources = sources_store.list(active_only=True)

    scanner = SourceScannerAgent(
        mock_mode=_workflow._mock_mode,
        client=None if _workflow._mock_mode else _workflow._idea_hunter._client,
    )

    items_fetched_total = 0
    signals_created = 0
    auto_promoted: List[str] = []
    auto_analyzed = 0

    # Build the analyzer once if we'll need it
    analyzer = None
    if auto_analyze_trend_threshold > 0:
        analyzer = IdeaAnalyzerAgent(
            mock_mode=_workflow._mock_mode,
            client=None if _workflow._mock_mode else _workflow._idea_hunter._client,
        )

    for src in sources:
        try:
            items = fetch_by_kind(src["kind"], src["target"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("scan: fetch failed for source %s (%s): %s", src["id"], src["kind"], exc)
            sources_store.mark_scanned(src["id"])
            continue
        items_fetched_total += len(items)
        if not items:
            sources_store.mark_scanned(src["id"])
            continue
        try:
            new_signals = scanner.scan(items)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scan: scanner agent failed for source %s: %s", src["id"], exc)
            sources_store.mark_scanned(src["id"])
            continue
        for sig in new_signals:
            signal_id = signals_store.add(
                source_id=src["id"], source_kind=sig.source_kind,
                theme=sig.theme, score=sig.score, excerpt=sig.excerpt,
                evidence_urls=sig.evidence_urls, suggested_topic=sig.suggested_topic,
                published_at=sig.published_at,
                item_titles=getattr(sig, "item_titles", None),
            )
            signals_created += 1
            # Auto-analyze if trend score is interesting enough
            if analyzer is not None:
                # Re-fetch signal to get the computed trend_score
                fresh = signals_store.get(signal_id)
                if fresh and (fresh.get("trend_score") or 0) >= auto_analyze_trend_threshold:
                    try:
                        result = analyzer.analyze(
                            theme=sig.theme,
                            excerpt=sig.excerpt,
                            suggested_topic=sig.suggested_topic,
                            evidence_urls=sig.evidence_urls,
                            source_kind=sig.source_kind,
                            source_name=src.get("name", ""),
                        )
                        signals_store.set_analysis(signal_id, result.to_dict())
                        auto_analyzed += 1
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("scan: auto-analyze failed for signal %s: %s", signal_id, exc)
            # Auto-promote by score (existing) OR by trend (new)
            should_promote = False
            if auto_promote_threshold > 0 and sig.score >= auto_promote_threshold:
                should_promote = True
            if auto_promote_trend_threshold > 0:
                fresh = signals_store.get(signal_id)
                if fresh and (fresh.get("trend_score") or 0) >= auto_promote_trend_threshold:
                    should_promote = True
            if should_promote:
                try:
                    run = _workflow.run(sig.suggested_topic or sig.theme)
                    signals_store.mark_promoted(signal_id, str(run.run_id))
                    auto_promoted.append(str(run.run_id))
                    response = _serialize_run(run)
                    _runs[response.run_id] = response
                except Exception as exc:  # noqa: BLE001
                    logger.warning("scan: auto-promote failed for signal %s: %s", signal_id, exc)
        sources_store.mark_scanned(src["id"])

    return {
        "scanned_sources": len(sources),
        "items_fetched": items_fetched_total,
        "signals_created": signals_created,
        "auto_promoted_runs": auto_promoted,
        "signals_auto_analyzed": auto_analyzed,
    }


@app.post(
    "/api/v1/sources/scan",
    response_model=ScanRunResponse,
    summary="Run the hunter pipeline: fetch sources + extract signals",
    tags=["hunter"],
)
def scan_sources(body: ScanRunRequest, request: Request) -> ScanRunResponse:
    """
    Manual scan trigger. For each configured (or specified) source:
      1. Fetch new content via source_fetcher
      2. Pass batch to source_scanner agent (1 LLM call per source)
      3. Persist signals scoring >= 0.5
      4. Optionally auto-promote signals >= threshold by invoking idea_hunter
    """
    _require_user(request)
    result = _run_scan_internal(
        source_ids=body.source_ids,
        auto_promote_threshold=body.auto_promote_threshold,
        auto_analyze_trend_threshold=body.auto_analyze_trend_threshold,
        auto_promote_trend_threshold=body.auto_promote_trend_threshold,
    )

    return ScanRunResponse(**result)


@app.get(
    "/api/v1/signals",
    response_model=SignalsListResponse,
    summary="List collected signals",
    tags=["hunter"],
)
def list_signals(
    request: Request,
    limit: int = 100,
    min_score: float = 0.0,
    sort: str = "recent",
    kind: str = "",
) -> SignalsListResponse:
    """
    sort:
      - "recent"    (default) — newest first by created_at
      - "score"     — highest score first
      - "trend"     — highest trend_score first (then score)
      - "published" — most-recently-published-by-source first (NULLs last)
    kind: filter by source_kind (rss/hn/reddit/url/youtube/...). Empty = all.
    """
    _require_user(request)
    from .core.storage import signals_store, sources_store
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="limit must be 1-500")
    if sort not in {"recent", "score", "trend", "published"}:
        raise HTTPException(status_code=422, detail="sort must be one of: recent, score, trend, published")
    rows = signals_store.list(limit=limit, min_score=min_score)
    # Filter by source_kind if requested
    if kind:
        rows = [r for r in rows if r.get("source_kind") == kind]
    # Re-sort according to client preference (store returns recent-first by default)
    if sort == "score":
        rows.sort(key=lambda r: r.get("score", 0), reverse=True)
    elif sort == "trend":
        rows.sort(key=lambda r: (r.get("trend_score", 0), r.get("score", 0)), reverse=True)
    elif sort == "published":
        # NULLs last: rows without published_at get -inf sort key
        rows.sort(key=lambda r: r.get("published_at") or -1, reverse=True)
    # Join source_name from sources table for nicer UI display
    source_names = {s["id"]: s["name"] for s in sources_store.list()}
    items: List[SignalItem] = []
    for r in rows:
        r["source_name"] = source_names.get(r.get("source_id")) if r.get("source_id") else None
        items.append(SignalItem(**r))
    return SignalsListResponse(total=len(items), items=items)


@app.get(
    "/api/v1/sources/quality",
    response_model=SourcesQualityResponse,
    summary="Per-source signal quality metrics (R29 source quality scoring)",
    tags=["hunter"],
)
def sources_quality(request: Request) -> SourcesQualityResponse:
    """
    Compute per-source quality from the signals + feedback history.
    Useful to decide which sources to keep, prune, or boost.
    """
    _require_user(request)
    from .core.storage import signals_store, sources_store
    by_id = {s["id"]: s for s in sources_store.list()}
    items: List[SourceQuality] = []
    for q in signals_store.quality_by_source():
        src = by_id.get(q["source_id"])
        if not src:
            continue
        items.append(
            SourceQuality(
                source_id=q["source_id"],
                name=src["name"],
                kind=src["kind"],
                signals_total=int(q["signals_total"]),
                signals_up=int(q["signals_up"] or 0),
                signals_down=int(q["signals_down"] or 0),
                signals_promoted=int(q["signals_promoted"] or 0),
                avg_score=float(q["avg_score"] or 0.0),
                quality_score=float(q["quality_score"]),
            )
        )
    # Sort best-first
    items.sort(key=lambda x: x.quality_score, reverse=True)
    return SourcesQualityResponse(items=items)


@app.post(
    "/api/v1/signals/{signal_id}/feedback",
    summary="Thumbs up/down a signal (calibrates future scoring)",
    tags=["hunter"],
)
def signal_feedback(signal_id: int, body: SignalFeedback, request: Request) -> Dict:
    _require_user(request)
    from .core.storage import signals_store
    if signals_store.get(signal_id) is None:
        raise HTTPException(status_code=404, detail="signal not found")
    new_value: Optional[str] = body.feedback if body.feedback in ("up", "down") else None
    signals_store.set_feedback(signal_id, new_value)
    return {"signal_id": signal_id, "feedback": new_value}


@app.get(
    "/api/v1/signals/promoted",
    response_model=SignalsListResponse,
    summary="List signals that were promoted to a workflow run (audit log)",
    tags=["hunter"],
)
def list_promoted_signals(request: Request, limit: int = 50) -> SignalsListResponse:
    """Audit log of promotions: which signals became runs, when, and the
    resulting run_id. Newest first."""
    _require_user(request)
    from .core.storage import signals_store, sources_store
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="limit must be 1-500")
    rows = signals_store.list_promoted(limit=limit)
    source_names = {s["id"]: s["name"] for s in sources_store.list()}
    items: List[SignalItem] = []
    for r in rows:
        r["source_name"] = source_names.get(r.get("source_id")) if r.get("source_id") else None
        items.append(SignalItem(**r))
    return SignalsListResponse(total=len(items), items=items)


@app.post(
    "/api/v1/signals/cleanup",
    response_model=SignalsCleanupResponse,
    summary="Remove stale signals (>N days, no feedback, not promoted)",
    tags=["hunter"],
)
def signals_cleanup(request: Request, older_than_days: int = 30) -> SignalsCleanupResponse:
    """
    Purges signals older than `older_than_days` (default 30) that nobody
    has touched (no thumbs up/down, no promotion). Signals with feedback
    or a promoted_run_id are PRESERVED as audit history.

    Bounded to 7-365 days to prevent accidental wipes.
    """
    _require_user(request)
    if older_than_days < 7 or older_than_days > 365:
        raise HTTPException(status_code=422, detail="older_than_days must be 7-365")
    from .core.storage import signals_store
    # Count how many old-but-kept (for transparency in the response)
    import time
    cutoff = int(time.time()) - older_than_days * 86_400
    all_rows = signals_store.list(limit=10_000, min_score=0)
    survivors = sum(
        1 for r in all_rows
        if r.get("created_at", 0) < cutoff
        and (r.get("feedback") is not None or r.get("promoted_run_id") is not None)
    )
    deleted = signals_store.cleanup_stale(older_than_days=older_than_days)
    return SignalsCleanupResponse(
        deleted=deleted,
        older_than_days=older_than_days,
        survivors_kept_with_feedback=survivors,
    )


@app.post(
    "/api/v1/signals/cleanup-mocks",
    response_model=SignalsCleanupMocksResponse,
    summary="Delete legacy mock-mode signals (theme starts with 'Mock signal from')",
    tags=["hunter"],
)
def signals_cleanup_mocks(request: Request) -> SignalsCleanupMocksResponse:
    """Targeted cleanup of obsolete mock signals from before the scanner used
    real item titles. Safe to run anytime — keys on the literal "Mock signal"
    prefix, so it won't touch real signals."""
    _require_user(request)
    from .core.storage import signals_store
    deleted = signals_store.cleanup_mocks()
    return SignalsCleanupMocksResponse(deleted=deleted)


@app.post(
    "/api/v1/signals/{signal_id}/analyze",
    response_model=AnalyzeSignalResponse,
    summary="Enrich a signal with market/ICP/competitors/recommendation (IdeaAnalyzer)",
    tags=["hunter"],
)
def analyze_signal(signal_id: int, request: Request) -> AnalyzeSignalResponse:
    """Run IdeaAnalyzer on a single signal to produce structured info the
    founder needs to decide whether to promote it: market size estimate,
    probable ICP, known competitors, differentiator, risks, and a
    recommendation (promote / wait_for_more_data / discard).

    Cost: ~$0.005 (single Haiku call). Mock-aware: when the backend runs
    without ANTHROPIC_API_KEY, returns a Spanish placeholder useful for UX.
    """
    _require_user(request)
    from .core.storage import signals_store, sources_store
    from .agents.idea_analyzer import IdeaAnalyzerAgent

    sig = signals_store.get(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="signal not found")

    source = sources_store.get(sig["source_id"]) if sig.get("source_id") else None
    source_name = source["name"] if source else ""

    analyzer = IdeaAnalyzerAgent(
        mock_mode=_workflow._mock_mode,
        client=None if _workflow._mock_mode else _workflow._idea_hunter._client,
    )
    analysis = analyzer.analyze(
        theme=sig["theme"],
        excerpt=sig["excerpt"],
        suggested_topic=sig["suggested_topic"],
        evidence_urls=sig.get("evidence_urls", []),
        source_kind=sig.get("source_kind", ""),
        source_name=source_name,
    )
    # Persist so the dashboard can re-show without re-running the LLM
    signals_store.set_analysis(signal_id, analysis.to_dict())
    return AnalyzeSignalResponse(
        signal_id=signal_id,
        analysis=SignalAnalysisItem(**analysis.to_dict()),
        cost_usd_estimated=0.0 if _workflow._mock_mode else 0.005,
    )


@app.get(
    "/api/v1/signals/{signal_id}",
    response_model=SignalItem,
    summary="Get a single signal by id (for the detail page)",
    tags=["hunter"],
)
def get_signal(signal_id: int, request: Request) -> SignalItem:
    _require_user(request)
    from .core.storage import signals_store, sources_store
    sig = signals_store.get(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="signal not found")
    if sig.get("source_id"):
        source = sources_store.get(sig["source_id"])
        sig["source_name"] = source["name"] if source else None
    else:
        sig["source_name"] = None
    return SignalItem(**sig)


@app.post(
    "/api/v1/signals/analyze-batch",
    response_model=AnalyzeSignalsBatchResponse,
    summary="Analyze multiple signals at once (cost: ~$0.005 each)",
    tags=["hunter"],
)
def analyze_signals_batch(
    body: AnalyzeSignalsBatchRequest, request: Request
) -> AnalyzeSignalsBatchResponse:
    """Run IdeaAnalyzer on a batch of signals — either explicit IDs (max 50)
    or auto-pick top_n not-yet-analyzed signals with trend_score >= min_trend.

    Each signal costs ~$0.005 in mock or live mode (Haiku-tier). Returns a
    summary so the founder can budget.
    """
    _require_user(request)
    from .core.storage import signals_store, sources_store
    from .agents.idea_analyzer import IdeaAnalyzerAgent

    # Resolve which signals to analyze
    if body.signal_ids:
        candidates = [signals_store.get(sid) for sid in body.signal_ids]
        candidates = [s for s in candidates if s]
    else:
        # Auto-pick: top_n highest-trend signals matching criteria
        all_signals = signals_store.list(limit=500, min_score=0)
        candidates = [
            s for s in all_signals
            if (s.get("trend_score") or 0) >= body.min_trend
        ]
        candidates.sort(
            key=lambda s: (s.get("trend_score", 0), s.get("score", 0)),
            reverse=True,
        )
        candidates = candidates[: body.top_n]

    source_names = {s["id"]: s["name"] for s in sources_store.list()}

    analyzer = IdeaAnalyzerAgent(
        mock_mode=_workflow._mock_mode,
        client=None if _workflow._mock_mode else _workflow._idea_hunter._client,
    )

    analyzed_ids: List[int] = []
    skipped = 0
    errors = 0
    for sig in candidates:
        if body.skip_already_analyzed and sig.get("analysis") is not None:
            skipped += 1
            continue
        try:
            result = analyzer.analyze(
                theme=sig["theme"],
                excerpt=sig["excerpt"],
                suggested_topic=sig["suggested_topic"],
                evidence_urls=sig.get("evidence_urls", []),
                source_kind=sig.get("source_kind", ""),
                source_name=source_names.get(sig.get("source_id")) or "",
            )
            signals_store.set_analysis(sig["id"], result.to_dict())
            analyzed_ids.append(sig["id"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("analyze-batch failed on signal %s: %s", sig["id"], exc)
            errors += 1

    cost_per = 0.0 if _workflow._mock_mode else 0.005
    return AnalyzeSignalsBatchResponse(
        analyzed=len(analyzed_ids),
        skipped_already_analyzed=skipped,
        errors=errors,
        cost_usd_estimated=cost_per * len(analyzed_ids),
        signal_ids_analyzed=analyzed_ids,
    )


@app.post(
    "/api/v1/gate/run-from-sources",
    response_model=RunGateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run the full workflow seeded by a topic, URLs, or a signal",
    tags=["hunter", "gate"],
)
def run_gate_from_sources(body: RunFromSourcesRequest, request: Request) -> RunGateResponse:
    """
    Three modes:
      - topic: same as POST /gate/run
      - urls:  fetch each URL, build evidence context, pass to idea_hunter
      - signal_id: load the signal + its evidence URLs, pass to idea_hunter
    """
    _require_user(request)
    from .core.source_fetcher import fetch_url
    from .core.storage import signals_store

    if not (body.topic or body.urls or body.signal_id):
        raise HTTPException(status_code=422, detail="Provide one of: topic, urls, signal_id")

    # Build evidence + final topic
    evidence_parts: List[str] = []
    final_topic = body.topic or ""

    if body.signal_id:
        sig = signals_store.get(body.signal_id)
        if not sig:
            raise HTTPException(status_code=404, detail="signal not found")
        # POTENTIATED PROMPT — frame the topic as a sharper LATAM-anchored hypothesis
        # rather than just passing the raw signal title. This gives the hunter
        # explicit context about WHERE the signal came from + WHEN it was published.
        from .core.storage import sources_store
        source = sources_store.get(sig["source_id"]) if sig.get("source_id") else None
        source_label = source["name"] if source else sig["source_kind"]
        published_label = ""
        if sig.get("published_at"):
            from datetime import datetime, timezone
            try:
                pub_dt = datetime.fromtimestamp(sig["published_at"], tz=timezone.utc)
                published_label = f" (publicado {pub_dt.strftime('%Y-%m-%d')})"
            except Exception:  # noqa: BLE001
                pass
        final_topic = final_topic or (
            f"{sig['suggested_topic'] or sig['theme']}"
            f" — señal capturada en {source_label}{published_label}"
        )
        # Rich evidence block: theme, source attribution, publication date, excerpt
        evidence_parts.append(
            f"=== SEÑAL DEL CAZADOR ===\n"
            f"Tema: {sig['theme']}\n"
            f"Fuente: {source_label} ({sig['source_kind']})\n"
            f"Publicado: {published_label or 'fecha desconocida'}\n"
            f"Score de detección: {sig['score']:.2f} | Trend: +{int(sig.get('trend_score', 0))} (apariciones recurrentes)\n"
            f"Resumen: {sig['excerpt']}\n"
        )
        # If we already have an analysis attached, inject it too — avoids the
        # hunter re-doing market/ICP/competitors estimation from scratch.
        analysis = sig.get("analysis")
        if analysis:
            comp = ", ".join(analysis.get("competitors") or []) or "ninguno conocido"
            risks = "; ".join(analysis.get("risks") or [])
            evidence_parts.append(
                f"=== ANÁLISIS PREVIO (IdeaAnalyzer) ===\n"
                f"Recomendación previa: {analysis.get('recommendation', '?')}  "
                f"({analysis.get('reasoning', '')})\n"
                f"Mercado estimado: {analysis.get('market_size_estimate', '?')}\n"
                f"ICP probable: {analysis.get('icp_probable', '?')}\n"
                f"Diferenciador: {analysis.get('differentiator', '?')}\n"
                f"Competencia: {comp}\n"
                f"Riesgos: {risks}\n"
            )
        for u in sig["evidence_urls"][:5]:
            item = fetch_url(u)
            if item:
                evidence_parts.append(f"\n--- {item.title} ({u}) ---\n{item.body}")

    if body.urls:
        for u in body.urls[:10]:
            item = fetch_url(u)
            if item:
                evidence_parts.append(f"--- {item.title} ({u}) ---\n{item.body}")
                if not final_topic:
                    final_topic = item.title

    if not final_topic:
        raise HTTPException(status_code=422, detail="Could not derive a topic from inputs")

    evidence_context = "\n\n".join(evidence_parts) if evidence_parts else None

    # Patch the workflow's idea_hunter to use the evidence context once
    # (we don't change the workflow signature — too invasive — so we wrap)
    original_generate = _workflow._idea_hunter.generate
    def _generate_with_context(topic: str, feedback: str | None = None):
        return original_generate(topic, feedback=feedback, evidence_context=evidence_context)
    _workflow._idea_hunter.generate = _generate_with_context  # type: ignore
    try:
        run = _workflow.run(topic=final_topic)
    finally:
        _workflow._idea_hunter.generate = original_generate  # restore
    response = _serialize_run(run)
    _runs[response.run_id] = response

    # If seeded by a signal, mark promotion
    if body.signal_id:
        signals_store.mark_promoted(body.signal_id, response.run_id)
    return response


# ---------------------------------------------------------------------------
# File import + Links bitácora + Pipeline (R30 / ADR-013)
# ---------------------------------------------------------------------------


_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
_ALLOWED_FILE_EXTS = (".txt", ".csv", ".docx")


@app.post(
    "/api/v1/sources/import-file",
    response_model=FileImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a .txt / WhatsApp chat / .docx, extract URLs, add as sources",
    tags=["hunter"],
    responses={
        400: {"model": ErrorDetail, "description": "Invalid file (too big / wrong type / empty)"},
    },
)
async def import_file(request: Request, file: UploadFile = File(...)) -> FileImportResponse:
    """
    Accepts .txt, .csv, WhatsApp exports (.txt), .docx. Reads up to 5 MB,
    extracts URLs, then:
      - logs each URL in links_log (status='pending') for the bitácora
      - creates a new `url`-kind source per URL (named from the filename)
      - skips duplicates (already in sources table)
    Triggers no LLM calls — analysis is on-demand via /api/v1/links/analyze.
    """
    _require_user(request)
    from .core.file_parser import extract_urls, parse_file
    from .core.storage import links_log_store, sources_store

    filename = (file.filename or "upload").strip()
    if not filename.lower().endswith(_ALLOWED_FILE_EXTS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Solo se aceptan archivos {_ALLOWED_FILE_EXTS}",
        )

    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Archivo demasiado grande (max {_MAX_UPLOAD_BYTES // 1024 // 1024} MB)",
        )
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archivo vacío")

    text = parse_file(filename, content)
    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo extraer texto del archivo (¿requiere python-docx para .docx?)",
        )

    urls = extract_urls(text)
    urls_added = 0
    sources_created = 0
    skipped = 0
    existing_targets = {s["target"] for s in sources_store.list() if s["kind"] == "url"}

    for i, url in enumerate(urls):
        # Always log to the bitácora
        links_log_store.add(url=url, source_file=filename)
        urls_added += 1
        # Add to sources iff not already a `url`-kind source with same target
        if url in existing_targets:
            skipped += 1
            continue
        # Derive a friendly name: <filename> · #N · domain
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).hostname or "url"
        except Exception:  # noqa: BLE001
            domain = "url"
        name = f"{filename} · #{i+1} · {domain}"[:120]
        sources_store.add(kind="url", target=url, name=name)
        existing_targets.add(url)
        sources_created += 1

    return FileImportResponse(
        filename=filename,
        urls_found=len(urls),
        urls_added=urls_added,
        sources_created=sources_created,
        skipped_duplicates=skipped,
    )


@app.get(
    "/api/v1/links",
    response_model=LinksLogResponse,
    summary="Bitácora de links extraídos/analizados",
    tags=["hunter"],
)
def list_links(
    request: Request,
    status_filter: str = "",
    limit: int = 200,
) -> LinksLogResponse:
    _require_user(request)
    from .core.storage import links_log_store
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="limit must be 1-500")
    sf = status_filter or None
    if sf and sf not in ("pending", "analyzed", "rejected", "error"):
        raise HTTPException(status_code=422, detail="status must be pending|analyzed|rejected|error")
    rows = links_log_store.list(status=sf, limit=limit)
    return LinksLogResponse(
        total=len(rows),
        by_status=links_log_store.stats(),
        items=[LinkLogItem(**r) for r in rows],
    )


@app.post(
    "/api/v1/links/analyze",
    response_model=AnalyzeBatchResponse,
    summary="Analizar links pendientes — fetch + LLM categorización",
    tags=["hunter"],
)
def analyze_links(body: AnalyzeBatchRequest, request: Request) -> AnalyzeBatchResponse:
    """
    Runs link_analyzer on pending links (or a specific list of link_ids).
    Costs ~$0.005-0.01 per link in live mode; 0 in mock mode.
    Use `max_to_analyze` to bound a single call.
    """
    _require_user(request)
    from .agents.link_analyzer import LinkAnalyzerAgent
    from .core.source_fetcher import fetch_url
    from .core.storage import links_log_store

    # Pick links to analyze
    if body.link_ids:
        candidates = [links_log_store.get(lid) for lid in body.link_ids]
        candidates = [c for c in candidates if c and c["status"] == "pending"]
    else:
        candidates = links_log_store.list(status="pending", limit=body.max_to_analyze)
    candidates = candidates[: body.max_to_analyze]

    analyzer = LinkAnalyzerAgent(
        mock_mode=_workflow._mock_mode,
        client=None if _workflow._mock_mode else _workflow._idea_hunter._client,
    )

    analyzed_count = 0
    rejected_count = 0
    error_count = 0

    for link in candidates:
        try:
            fetched = fetch_url(link["url"])
            if not fetched:
                links_log_store.update_analysis(
                    link["id"], status="rejected",
                    rejection_reason="No se pudo descargar la página",
                )
                rejected_count += 1
                continue
            result = analyzer.analyze(fetched)
            links_log_store.update_analysis(
                link["id"], status=result.status,
                idea_summary=result.idea_summary, sector=result.sector,
                area=result.area, rejection_reason=result.rejection_reason,
            )
            if result.status == "analyzed":
                analyzed_count += 1
            elif result.status == "rejected":
                rejected_count += 1
            else:
                error_count += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("analyze_links: failed for %s: %s", link["url"], e)
            links_log_store.update_analysis(
                link["id"], status="error", rejection_reason=f"analyzer exception: {e}",
            )
            error_count += 1

    return AnalyzeBatchResponse(
        analyzed=analyzed_count, rejected=rejected_count, errors=error_count,
    )


@app.get(
    "/api/v1/pipeline",
    response_model=PipelineResponse,
    summary="Vista kanban: runs agrupados por fase actual",
    tags=["hunter"],
)
def pipeline(request: Request) -> PipelineResponse:
    """
    Returns a phase-by-phase view of every EvidenceGate run:
      - 'pending_review'  : ensemble disagreement, needs human verdict
      - 'iterate'         : verdict=iterate (kept active for re-test)
      - 'pass'            : verdict=pass (ready to build)
      - 'kill'            : verdict=kill (archived)
      - 'overridden'      : human override recorded
    """
    _require_user(request)
    from .core.storage import runs_store

    columns_def = [
        ("pending_review", "🟡 Revisión humana"),
        ("iterate", "🔁 Iterar"),
        ("pass", "✅ Aprobada"),
        ("kill", "❌ Rechazada"),
        ("overridden", "⚖️ Override humano"),
    ]
    bucket: Dict[str, List[RunSummary]] = {p: [] for p, _ in columns_def}

    all_runs = runs_store.values()
    for r in all_runs:
        summary = RunSummary(
            run_id=r.run_id,
            idea_title=r.idea_title,
            verdict=r.verdict,
            confidence=r.confidence,
            landing_slug=r.landing_slug,
            needs_human_review=r.needs_human_review,
            has_override=bool(r.human_override),
            cost_usd_estimated=r.cost_usd_estimated,
            steps_used=r.steps_used,
        )
        if r.human_override:
            bucket["overridden"].append(summary)
        elif r.needs_human_review:
            bucket["pending_review"].append(summary)
        else:
            bucket.setdefault(r.verdict, []).append(summary)

    return PipelineResponse(
        total_runs=len(all_runs),
        columns=[
            PipelineColumnResponse(
                phase=phase, label=label,
                count=len(bucket.get(phase, [])),
                runs=bucket.get(phase, []),
            )
            for phase, label in columns_def
        ],
    )


# ---------------------------------------------------------------------------
# Auto-scan background loop (ADR-014 follow-up)
#
# Opt-in via env: AUTOSCAN_INTERVAL_MINUTES=360  (6 hours; 0 = disabled, default)
# Bounded: minimum 15 minutes to prevent rate-limit hell against upstream sources.
# Never runs in pytest (`PYTEST_CURRENT_TEST` env is set by pytest automatically).
# ---------------------------------------------------------------------------

import asyncio as _asyncio

_autoscan_task = None  # type: ignore[assignment]
_autoscan_state = {
    "enabled": False,
    "interval_minutes": 0,
    "last_run_at": None,
    "last_run_signals_created": 0,
    "last_run_error": None,
    "runs_completed": 0,
}


async def _autoscan_loop() -> None:
    """Background coroutine: sleep + scan active sources, forever.

    Sleeps FIRST so import-time and tests don't hammer upstream feeds.
    Each iteration is wrapped in a try/except — a failure logs and continues.
    """
    interval_min = _autoscan_state["interval_minutes"]
    interval_sec = max(15 * 60, interval_min * 60)
    logger.info("autoscan: loop started, interval=%d min", interval_min)
    while True:
        try:
            await _asyncio.sleep(interval_sec)
            # Read thresholds on each iteration so env vars can be updated
            # without a restart (Railway live-reload semantics).
            try:
                auto_an_thr = int(os.getenv("AUTO_ANALYZE_TREND_THRESHOLD", "0"))
            except ValueError:
                auto_an_thr = 0
            try:
                auto_prom_trend = int(os.getenv("AUTO_PROMOTE_TREND_THRESHOLD", "0"))
            except ValueError:
                auto_prom_trend = 0
            result = await _asyncio.to_thread(
                _run_scan_internal, None, 0.0, auto_an_thr, auto_prom_trend
            )
            _autoscan_state["last_run_at"] = int(time.time())
            _autoscan_state["last_run_signals_created"] = result["signals_created"]
            _autoscan_state["last_run_error"] = None
            _autoscan_state["runs_completed"] += 1
            logger.info(
                "autoscan: completed run #%d, signals_created=%d",
                _autoscan_state["runs_completed"],
                result["signals_created"],
            )
        except _asyncio.CancelledError:
            logger.info("autoscan: loop cancelled (shutdown)")
            raise
        except Exception as exc:  # noqa: BLE001
            _autoscan_state["last_run_error"] = str(exc)[:200]
            logger.warning("autoscan: iteration failed: %s", exc)


# --- Lifespan (replaces deprecated @app.on_event) ----------------------------
# We hot-swap the router's lifespan context AFTER `app` was constructed
# (the app variable is defined ~1900 lines above this code). Same semantics
# as passing `lifespan=` to FastAPI(), just kept here so the autoscan
# bookkeeping stays adjacent to its own functions.
import contextlib as _contextlib


@_contextlib.asynccontextmanager
async def _app_lifespan(_app):
    global _autoscan_task
    # --- Startup ---
    if not os.getenv("PYTEST_CURRENT_TEST"):
        try:
            interval = int(os.getenv("AUTOSCAN_INTERVAL_MINUTES", "0"))
        except ValueError:
            interval = 0
        if interval > 0:
            if interval < 15:
                logger.warning(
                    "autoscan: interval %d min clamped to 15 (rate-limit safety)",
                    interval,
                )
                interval = 15
            _autoscan_state["enabled"] = True
            _autoscan_state["interval_minutes"] = interval
            _autoscan_task = _asyncio.create_task(_autoscan_loop())
        else:
            logger.info("autoscan: disabled (AUTOSCAN_INTERVAL_MINUTES=0)")

    try:
        yield
    finally:
        # --- Shutdown ---
        if _autoscan_task is not None:
            _autoscan_task.cancel()
            try:
                await _autoscan_task
            except (_asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            _autoscan_task = None


app.router.lifespan_context = _app_lifespan


@app.get(
    "/api/v1/autoscan/status",
    summary="Status of the background auto-scan loop (R28 / ADR-014)",
    tags=["hunter", "meta"],
)
def autoscan_status(request: Request) -> Dict:
    _require_user(request)
    return dict(_autoscan_state)


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
