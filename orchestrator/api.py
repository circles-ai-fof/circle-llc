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
    RunGateRequest,
    RunGateResponse,
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
