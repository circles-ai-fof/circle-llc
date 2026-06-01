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
from typing import Dict, List, Optional
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
    EnrichSignalResponse,
    SignalAnalysisItem,
    SignalFeedback,
    SignalItem,
    SignalsCleanupMocksResponse,
    SignalsDeleteByTypeRequest,
    SignalsDeleteByTypeResponse,
    SignalsStatsByTypeResponse,
    SignalsBulkFeedbackRequest,
    SignalsBulkFeedbackResponse,
    SignalsBulkDeleteByIdsRequest,
    SignalsBulkDeleteByIdsResponse,
    RunsListResponse,
    RunListItem,
    TrendGapsResponse,
    TrendGapItem,
    CountryValidation,
    NicheOpportunitiesResponse,
    NicheOpportunity,
    NicheSubItem,
    TrendGapAnalyzeRequest,
    TrendGapAnalyzeResponse,
    NicheScoutRequest, NicheScoutResponse,
    EventScoringRequest, EventScoringResponse,
    SleeperDetectRequest, SleeperDetectResponse,
    ArbitrageEvalRequest, ArbitrageEvalResponse,
    DigestData,
    DigestSendResponse,
    ConsensusRequest, ConsensusResponse,
    AdminStatusResponse, AdminAgentStatus, AdminEnvCheck, AdminCronStatus,
    DiagnoseDeployResponse, DeployIssue,
    AnalyticsResponse, AnalyticsBucket, AnalyticsVerdictBucket,
    AnalyticsCostBucket, AnalyticsTopItem,
    SignalsCleanupResponse,
    SignalsListResponse,
    StatsResponse,
    TranslateSignalResponse,
    SourceCreate,
    SourceItem,
    SourceQuality,
    AutonomyResponse,
    AutonomyUpdateRequest,
    CheckPlatformRequest,
    CheckPlatformResponse,
    ClusterItem,
    ClustersResponse,
    ConnectedAccountItem,
    ConnectedAccountUpsertRequest,
    ConnectedAccountsListResponse,
    PreferencesEngineInfo,
    ReclusterResponse,
    SourceSuggestionItem,
    SourceSuggestionsResponse,
    SourcesBulkDeleteRequest,
    SourcesBulkDeleteResponse,
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
    # M4.5 — añadidos PUT y DELETE para que /api/v1/autonomy (PUT) y
    # /api/v1/sources/{id} (DELETE) pasen el preflight de CORS. Antes el browser
    # bloqueaba estos requests silenciosamente con "NetworkError" en la consola.
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
    expose_headers=["X-Request-Id"],
    max_age=600,
)


# Security headers middleware (OWASP hardening — M3.17 reforzado)
@app.middleware("http")
async def _security_headers(request: Request, call_next):
    # M3.17: log y bloquea requests con Origin no autorizado (defense in depth
    # — CORSMiddleware ya lo hace pero queremos auditoría)
    origin = request.headers.get("origin")
    if origin and origin not in _DEFAULT_ALLOWED_ORIGINS + _extra_origins:
        # No bloqueamos (CORS ya rechaza la response) pero loggeamos para
        # detectar intentos de scraping cross-origin desde sitios desconocidos
        logger.info("CORS: request from non-allowlisted origin %r blocked by CORSMiddleware", origin)

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
    # M3.17: extras OWASP
    # Disable the legacy XSS auditor (it actually adds attack surface in modern browsers)
    response.headers["X-XSS-Protection"] = "0"
    # Cross-origin process isolation (anti Spectre + XS-Leaks)
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    # Anti enumeration: no exponer la versión del servidor
    response.headers["Server"] = "circles-ai"
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
    resp = RunGateResponse(
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
    # Fire pending-review webhook (best-effort, never raises)
    if resp.needs_human_review and resp.human_override is None:
        try:
            from .core import webhooks as _wh
            base = (os.getenv("DASHBOARD_BASE_URL") or "").rstrip("/")
            _wh.emit("run.pending_review", {
                "run_id": resp.run_id,
                "theme": resp.idea_title,
                "verdict": resp.verdict,
                "confidence": resp.confidence,
                "recommendation": resp.review_reason,
                "dashboard_url": f"{base}/revision" if base else None,
            })
        except Exception:  # noqa: BLE001
            pass
    return resp


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
    """Returns API version, mode (live/mock), and workflow name.

    M3.12: also reports persistent_storage, autoscan_enabled, server_time —
    useful for the founder to verify "is this prod or local?" + "is data
    being persisted?" + "what time does the server think it is?".
    """
    mode = "mock" if _workflow._mock_mode else "live"
    return HealthResponse(
        version=API_VERSION,
        mode=mode,
        persistent_storage=bool(os.getenv("DATABASE_PATH")),
        autoscan_enabled=bool(_autoscan_state.get("enabled")),
        server_time=int(time.time()),
    )


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
def list_pending_review(request: Request) -> PendingReviewResponse:
    """
    Returns all completed runs where the ensemble flagged
    `needs_human_review=True` and no human_override has been recorded yet.

    Auth required (M3.12): pending decisions reveal business strategy and
    must not leak to anyone outside the closed beta.
    """
    _require_user(request)
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

    Auth required (M3.12): overriding a gate verdict modifies business
    decisions — must be restricted to closed-beta users via _require_user.
    """
    _require_user(request)
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
            "webhooks_configured": bool(
                os.getenv("WEBHOOK_URL_SLACK") or os.getenv("WEBHOOK_URL_GENERIC")
            ),
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
    "/api/v1/runs",
    response_model=RunsListResponse,
    summary="M4.10 — Lista de runs recientes para el dashboard de overview",
    tags=["meta"],
)
def list_runs(
    request: Request,
    limit: int = 20,
    verdict: str = "",
) -> RunsListResponse:
    """Lista runs ordenados por fecha desc. Payload ligero (sin landing
    copy completo ni next_steps) — para el detalle hacer
    GET /api/v1/gate/runs/{run_id}.

    Args:
        limit: 1-100 (default 20)
        verdict: "pass" | "kill" | "iterate" o vacío para todos
    """
    _require_user(request)
    from .core.storage import runs_store
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit must be 1-100")
    if verdict and verdict not in {"pass", "kill", "iterate"}:
        raise HTTPException(
            status_code=422,
            detail="verdict must be 'pass'|'kill'|'iterate' o vacío",
        )
    rows = runs_store.list_recent(limit=limit, verdict=verdict or None)
    items = [RunListItem(**r) for r in rows]
    return RunsListResponse(total=len(items), items=items)


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


@app.post(
    "/api/v1/sources/bulk-delete",
    response_model=SourcesBulkDeleteResponse,
    summary="Delete many sources by IDs or filter (kind / name / target)",
    tags=["hunter"],
    responses={
        422: {"model": ErrorDetail, "description": "No deletion criterion provided"},
    },
)
def bulk_delete_sources(
    body: SourcesBulkDeleteRequest, request: Request
) -> SourcesBulkDeleteResponse:
    """Bulk delete with safety guard: must provide at least one criterion
    (explicit IDs OR a filter). Prevents accidental wipe-all.

    Use cases (founder):
      - "Borrar todas las URLs de Instagram": target_contains="instagram.com"
      - "Limpiar todo lo de x.com": target_contains="x.com"
      - "Borrar todas las URLs importadas de mi último archivo": name_contains="chat.txt"
      - "Quitar estas 5 específicas": source_ids=[1,2,3,4,5]
    """
    _require_user(request)
    if not any([body.source_ids, body.kind_filter, body.name_contains, body.target_contains]):
        raise HTTPException(
            status_code=422,
            detail="Provide at least one of: source_ids, kind_filter, name_contains, target_contains",
        )
    from .core.storage import sources_store
    deleted = sources_store.delete_many(
        source_ids=body.source_ids,
        kind_filter=body.kind_filter,
        name_contains=body.name_contains,
        target_contains=body.target_contains,
    )
    return SourcesBulkDeleteResponse(deleted=deleted)


# ---------------------------------------------------------------------------
# M4.0 — connected accounts + platform detection (ADR-018)
# ---------------------------------------------------------------------------


@app.post(
    "/api/v1/sources/check-platform",
    response_model=CheckPlatformResponse,
    summary="Detect platform from URL and report credential status",
    tags=["hunter"],
)
def check_platform(body: CheckPlatformRequest, request: Request) -> CheckPlatformResponse:
    """Cuando el founder pega una URL en /cazar/fuentes, este endpoint:
      1. Detecta la plataforma (youtube / x / linkedin / bluesky / ...)
      2. Devuelve si esa plataforma necesita credenciales
      3. Sugiere qué `kind` de source crear

    Usado por el form de fuentes para mostrar el banner
    "⚠️ Falta conectar cuenta de YouTube — agrega YOUTUBE_API_KEY a .env"
    ANTES de que el founder submita.
    """
    _require_user(request)
    from .core.platforms import detect_platform, check_credentials

    platform = detect_platform(body.url)
    if platform is None:
        # URL genérica — sin requerimientos
        return CheckPlatformResponse(
            url=body.url,
            platform=None,
            status="ready",
            needs_credentials=False,
            message="URL genérica — se registrará como kind 'url' o 'rss' según el formato.",
            recommended_kind="url",
        )

    creds = check_credentials(platform)
    return CheckPlatformResponse(
        url=body.url,
        platform=platform,
        status=creds["status"],
        needs_credentials=creds["needs_credentials"],
        missing_keys=creds["missing_keys"],
        configured_keys=creds["configured_keys"],
        oauth_required=creds["oauth_required"],
        message=creds["message"],
        recommended_kind=creds["recommended_kind"],
        notes=creds["notes"],
    )


@app.get(
    "/api/v1/connected-accounts",
    response_model=ConnectedAccountsListResponse,
    summary="List all platforms + their credential status + founder notes",
    tags=["hunter"],
)
def list_connected_accounts(request: Request) -> ConnectedAccountsListResponse:
    _require_user(request)
    from .core.platforms import list_all_platforms_status
    from .core.storage import connected_accounts_store

    static = list_all_platforms_status()
    saved = {a["platform"]: a for a in connected_accounts_store.list()}
    items: List[ConnectedAccountItem] = []
    for s in static:
        record = saved.get(s["platform"], {})
        items.append(ConnectedAccountItem(
            platform=s["platform"],
            status=s["status"],
            needs_credentials=s["needs_credentials"],
            missing_keys=s["missing_keys"],
            configured_keys=s["configured_keys"],
            oauth_required=s["oauth_required"],
            message=s["message"],
            recommended_kind=s["recommended_kind"],
            notes=s["notes"],
            user_notes=record.get("notes"),
            configured_at=record.get("configured_at"),
        ))
    return ConnectedAccountsListResponse(items=items)


@app.post(
    "/api/v1/connected-accounts",
    response_model=ConnectedAccountItem,
    summary="Mark a platform as configured/deferred (annotation only — does NOT store credentials)",
    tags=["hunter"],
)
def upsert_connected_account(
    body: ConnectedAccountUpsertRequest, request: Request
) -> ConnectedAccountItem:
    """Founder anota qué plataformas ha configurado. NO almacenamos credentials
    aquí — eso vive en env vars. Solo registramos el estado observado para que
    el dashboard sepa diferenciar "ya lo hice" vs "pendiente".
    """
    _require_user(request)
    from .core.platforms import check_credentials, PLATFORM_CATALOG
    from .core.storage import connected_accounts_store

    if body.platform not in PLATFORM_CATALOG:
        raise HTTPException(status_code=404, detail=f"Plataforma desconocida: {body.platform!r}")

    cat = PLATFORM_CATALOG[body.platform]
    connected_accounts_store.upsert(
        platform=body.platform,
        status=body.status,
        oauth_required=bool(cat.get("oauth_required")),
        notes=body.notes,
    )
    static = check_credentials(body.platform)
    record = connected_accounts_store.get(body.platform) or {}
    return ConnectedAccountItem(
        platform=body.platform,
        status=static["status"],
        needs_credentials=static["needs_credentials"],
        missing_keys=static["missing_keys"],
        configured_keys=static["configured_keys"],
        oauth_required=static["oauth_required"],
        message=static["message"],
        recommended_kind=static["recommended_kind"],
        notes=static["notes"],
        user_notes=record.get("notes"),
        configured_at=record.get("configured_at"),
    )


# ---------------------------------------------------------------------------
# M4.1 / ADR-019 — preferences + autonomy
# ---------------------------------------------------------------------------


@app.get(
    "/api/v1/preferences/engine",
    response_model=PreferencesEngineInfo,
    summary="Which engine is active for embeddings + clustering",
    tags=["hunter"],
)
def preferences_engine(request: Request) -> PreferencesEngineInfo:
    _require_user(request)
    from .core.preferences import get_engine_info
    info = get_engine_info()
    return PreferencesEngineInfo(**info)


@app.post(
    "/api/v1/preferences/recluster",
    response_model=ReclusterResponse,
    summary="Embed missing signals + recluster all (HDBSCAN if available)",
    tags=["hunter"],
)
def recluster(request: Request) -> ReclusterResponse:
    """Garantiza que cada signal tenga embedding y reasigna cluster_ids.

    Idempotente — puede ejecutarse manualmente desde la UI. En el futuro
    podría correr como cron job semanal.
    """
    _require_user(request)
    from .core.preferences import compute_embedding, cluster_embeddings, get_engine_info
    from .core.storage import signals_store, embeddings_store

    all_signals = signals_store.list(limit=10_000, min_score=0)
    existing = {e["signal_id"]: e["vector"] for e in embeddings_store.list_all()}

    # 1. Embed missing
    mode = get_engine_info()["mode"]
    embedded_count = 0
    for s in all_signals:
        if s["id"] in existing:
            continue
        text = f"{s.get('theme','')} {s.get('excerpt','')} {s.get('suggested_topic','')}"
        vec = compute_embedding(text)
        embeddings_store.upsert(s["id"], vec, cluster_id=-1, model_version=mode)
        existing[s["id"]] = vec
        embedded_count += 1

    # 2. Recluster all
    sig_ids = list(existing.keys())
    if not sig_ids:
        return ReclusterResponse(signals_embedded=0, clusters_found=0, mode=mode)
    vectors = [existing[sid] for sid in sig_ids]
    labels = cluster_embeddings(vectors)
    for sid, label in zip(sig_ids, labels):
        embeddings_store.set_cluster(sid, int(label))
    unique_clusters = len({l for l in labels if l >= 0})

    return ReclusterResponse(
        signals_embedded=embedded_count,
        clusters_found=unique_clusters,
        mode=mode,
    )


@app.get(
    "/api/v1/preferences/clusters",
    response_model=ClustersResponse,
    summary="Top clusters with their signals + keywords + feedback breakdown",
    tags=["hunter"],
)
def list_clusters(request: Request, limit: int = 10) -> ClustersResponse:
    _require_user(request)
    from .core.preferences import extract_keywords, get_engine_info
    from .core.storage import signals_store, embeddings_store

    embs = embeddings_store.list_all()
    all_signals = {s["id"]: s for s in signals_store.list(limit=10_000, min_score=0)}

    # Group signals by cluster
    by_cluster: Dict[int, List[int]] = {}
    for e in embs:
        cid = e["cluster_id"]
        if cid < 0:
            continue
        by_cluster.setdefault(cid, []).append(e["signal_id"])

    items: List[ClusterItem] = []
    for cid, sids in by_cluster.items():
        valid_signals = [all_signals[s] for s in sids if s in all_signals]
        themes = [s["theme"] for s in valid_signals]
        up = sum(1 for s in valid_signals if s.get("feedback") == "up")
        down = sum(1 for s in valid_signals if s.get("feedback") == "down")
        keywords = extract_keywords(
            [f"{s.get('theme','')} {s.get('excerpt','')}" for s in valid_signals],
            top_n=5,
        )
        items.append(ClusterItem(
            cluster_id=cid,
            signal_ids=sids,
            sample_themes=themes[:3],
            feedback_up=up,
            feedback_down=down,
            keywords=keywords,
        ))

    # Sort by feedback_up desc then size desc
    items.sort(key=lambda c: (-c.feedback_up, -len(c.signal_ids)))
    items = items[:limit]

    return ClustersResponse(
        total_clusters=len(by_cluster),
        mode=get_engine_info()["mode"],
        items=items,
    )


@app.get(
    "/api/v1/sources/suggestions",
    response_model=SourceSuggestionsResponse,
    summary="Source suggestions based on clusters of approved signals (Cazador Fase 3)",
    tags=["hunter"],
)
def source_suggestions(request: Request, limit: int = 5) -> SourceSuggestionsResponse:
    """Genera sugerencias de fuentes/búsquedas basadas en los clusters
    cuyas señales el founder ha aprobado (👍). 'Cluster #5 sobre fintech LATAM
    tiene 8 aprobadas — añade búsqueda Bluesky con esos keywords.'

    Costo: $0 (sin LLM). Solo agregación de keywords.
    """
    _require_user(request)
    from .core.preferences import suggest_sources_from_clusters, get_engine_info
    from .core.storage import signals_store, embeddings_store

    all_signals = {s["id"]: s for s in signals_store.list(limit=10_000, min_score=0)}
    embs = embeddings_store.list_all()
    # Solo clusters con al menos 1 feedback positivo
    cluster_texts: Dict[int, List[str]] = {}
    cluster_has_positive: Dict[int, bool] = {}
    for e in embs:
        cid = e["cluster_id"]
        sig = all_signals.get(e["signal_id"])
        if not sig or cid < 0:
            continue
        if sig.get("feedback") == "up":
            cluster_has_positive[cid] = True
        cluster_texts.setdefault(cid, []).append(
            f"{sig.get('theme','')} {sig.get('excerpt','')}"
        )
    # Filtrar a solo los que tienen positivos
    filtered = {
        cid: texts for cid, texts in cluster_texts.items()
        if cluster_has_positive.get(cid)
    }

    suggestions = suggest_sources_from_clusters(filtered, max_suggestions=limit)
    return SourceSuggestionsResponse(
        mode=get_engine_info()["mode"],
        items=[SourceSuggestionItem(**s) for s in suggestions],
    )


@app.get(
    "/api/v1/autonomy",
    response_model=AutonomyResponse,
    summary="Get current autonomy level of the cazador",
    tags=["hunter"],
)
def get_autonomy(request: Request) -> AutonomyResponse:
    _require_user(request)
    from .core.storage import autonomy_store
    data = autonomy_store.get_full()
    return AutonomyResponse(level=data["level"], updated_at=data["updated_at"])


def _set_autonomy_impl(body: AutonomyUpdateRequest, request: Request) -> AutonomyResponse:
    """Shared implementation for PUT and POST verbs.

    M4.5 (bug del founder): PUT /api/v1/autonomy fallaba en el browser con
    NetworkError porque la preflight de CORS solo aceptaba GET/POST/OPTIONS.
    Aunque ya añadimos PUT a allow_methods, el cambio requiere reiniciar el
    backend. Para que la UI funcione inmediatamente exponemos el mismo
    handler como POST también — POST nunca estuvo bloqueado por CORS.
    """
    _require_user(request)
    from .core.storage import autonomy_store
    autonomy_store.set_level(body.level)
    data = autonomy_store.get_full()
    return AutonomyResponse(level=data["level"], updated_at=data["updated_at"])


@app.put(
    "/api/v1/autonomy",
    response_model=AutonomyResponse,
    summary="Set autonomy level: manual | assisted | autonomous_with_approval (PUT)",
    tags=["hunter"],
)
def set_autonomy_put(body: AutonomyUpdateRequest, request: Request) -> AutonomyResponse:
    """M4.1: 3 niveles de autonomía configurable.

    - manual: founder añade fuentes manualmente, sin sugerencias.
    - assisted (default tras M4.1): sistema muestra sugerencias en
      /cazar/fuentes; founder aprueba o rechaza una por una.
    - autonomous_with_approval: sistema añade sugerencias automáticamente
      pero las marca como "pendiente aprobación" antes de escanearlas.
    """
    return _set_autonomy_impl(body, request)


@app.post(
    "/api/v1/autonomy",
    response_model=AutonomyResponse,
    summary="Set autonomy level (POST alias — works without backend restart on CORS-old deploys)",
    tags=["hunter"],
)
def set_autonomy_post(body: AutonomyUpdateRequest, request: Request) -> AutonomyResponse:
    """M4.5: alias POST del PUT de arriba. Ver _set_autonomy_impl()."""
    return _set_autonomy_impl(body, request)


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
            # M4.1: auto-embed la señal (fallback determinista si sentence-transformers
            # no está instalado — siempre funciona, no rompe el scan).
            try:
                from .core.preferences import compute_embedding, get_engine_info
                from .core.storage import embeddings_store
                text = f"{sig.theme} {sig.excerpt} {sig.suggested_topic}"
                vec = compute_embedding(text)
                mode = get_engine_info()["mode"]
                embeddings_store.upsert(
                    signal_id, vec, cluster_id=-1,
                    model_version=mode,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("scan: auto-embed failed for signal %s: %s", signal_id, exc)
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
            # Webhook: high-trend signal (configurable threshold via WEBHOOK_MIN_TREND)
            try:
                fresh_for_hook = signals_store.get(signal_id)
                if fresh_for_hook:
                    from .core import webhooks as _wh
                    _wh.emit_signal_event(
                        "signal.high_trend",
                        fresh_for_hook,
                        source_name=src.get("name"),
                    )
            except Exception:  # noqa: BLE001
                pass
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
                    # Webhook: auto-promoted signal
                    try:
                        from .core import webhooks as _wh
                        _wh.emit("signal.auto_promoted", {
                            "signal_id": signal_id,
                            "theme": sig.theme,
                            "source_name": src.get("name"),
                            "verdict": response.verdict,
                            "confidence": response.confidence,
                            "run_id": response.run_id,
                            "dashboard_url": _wh._signal_url(signal_id),
                        })
                    except Exception:  # noqa: BLE001
                        pass
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
    search: str = "",
    content_type: str = "",
) -> SignalsListResponse:
    """
    sort:
      - "recent"    (default) — newest first by created_at
      - "score"     — highest score first
      - "trend"     — highest trend_score first (then score)
      - "published" — most-recently-published-by-source first (NULLs last)
    kind:         filter by source_kind (rss/hn/reddit/url/youtube/...). Empty = all.
    search:       case-insensitive substring on theme/excerpt/suggested_topic.
                  Server-side LIKE — escalable a FTS5 cuando supere ~5k señales.
    content_type: filter by classified content type (news/blog/research_paper/
                  tool_product/course_tutorial/video_podcast/community/
                  corporate/unknown). Empty = all. (M4.5)
    """
    _require_user(request)
    from .core.storage import signals_store, sources_store
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="limit must be 1-500")
    if sort not in {"recent", "score", "trend", "published"}:
        raise HTTPException(status_code=422, detail="sort must be one of: recent, score, trend, published")
    # Length-bound the search term to avoid SQL slowdown on absurd inputs
    if len(search) > 200:
        raise HTTPException(status_code=422, detail="search must be ≤200 chars")
    VALID_CONTENT_TYPES = {
        "", "news", "blog", "research_paper", "tool_product",
        "course_tutorial", "video_podcast", "community", "corporate", "unknown",
    }
    if content_type not in VALID_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail=f"invalid content_type. valid: {sorted(VALID_CONTENT_TYPES - {''})}")
    rows = signals_store.list(
        limit=limit, min_score=min_score, search=search or None,
    )
    # Filter by source_kind if requested
    if kind:
        rows = [r for r in rows if r.get("source_kind") == kind]
    # M4.5 — filter by classified content_type if requested
    if content_type:
        rows = [r for r in rows if (r.get("content_type") or "unknown") == content_type]
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
        # M3.13: on-the-fly repair for legacy signals
        r = _polish_signal_for_display(r)
        items.append(SignalItem(**r))
    return SignalsListResponse(total=len(items), items=items)


def _polish_signal_for_display(r: Dict) -> Dict:
    """Repair signal payload before sending to the dashboard.

    1. If theme looks like a placeholder ("Mock signal from rss",
       "Detected pattern across…", etc.) AND we have real item_titles,
       promote the first non-empty title as the displayed theme.
    2. Deduplicate evidence_urls when they point at the same canonical
       resource (same hostname AND no item_titles to distinguish them).
       Common case: an RSS feed produces 10 items all linking back to the
       site's homepage — the old scanner stored 3 copies of the same URL.
    3. Trim item_titles to match deduped urls length.
    """
    import re as _re
    placeholder_pat = _re.compile(
        r"^(Mock signal from|Mock single-source signal from|Tema recurrente en|Item de|Detected pattern|JavaScript is not available|We've detected that JavaScript|Please enable JavaScript|Log in to Instagram|Log into Facebook)",
        _re.IGNORECASE,
    )
    theme = str(r.get("theme") or "")
    titles = list(r.get("item_titles") or [])
    urls = list(r.get("evidence_urls") or [])

    # 1) theme repair
    if placeholder_pat.search(theme):
        first_real = next((t for t in titles if t and t.strip()), None)
        if first_real:
            r["theme"] = first_real[:120]

    # 2) URL deduplication
    if urls and (not titles or all(not t for t in titles)):
        seen = set()
        deduped_urls: List[str] = []
        for u in urls:
            host = u
            try:
                from urllib.parse import urlparse as _up
                host = _up(u).hostname or u
            except Exception:  # noqa: BLE001
                pass
            key = (host, u)  # exact URL + hostname — preserves real distinct articles
            if key in seen:
                continue
            seen.add(key)
            deduped_urls.append(u)
        # If after deduping we have <half of original, all were dupes — keep 1
        if len(deduped_urls) < len(urls):
            r["evidence_urls"] = deduped_urls
            # Trim titles to match
            r["item_titles"] = titles[: len(deduped_urls)] if titles else []
    return r


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
        r = _polish_signal_for_display(r)
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
    "/api/v1/signals/bulk-feedback",
    response_model=SignalsBulkFeedbackResponse,
    summary="M4.9 — Aplicar feedback (up/down/clear) a varias señales",
    tags=["hunter"],
)
def signals_bulk_feedback(
    body: SignalsBulkFeedbackRequest, request: Request
) -> SignalsBulkFeedbackResponse:
    """Founder request natural tras M4.6 (bulk-delete): poder marcar varias
    señales como 👍 / 👎 de un click.

    Iteramos signal_ids y aplicamos feedback. Si un id no existe, lo
    contamos como skipped pero no fallamos el batch — esto evita que un
    refresh stale en el cliente rompa todo el lote.
    """
    _require_user(request)
    from .core.storage import signals_store
    # feedback "clear" se persiste como None en el storage
    fb_to_apply: Optional[str] = None if body.feedback == "clear" else body.feedback
    # Para reportar `skipped_missing` con precisión hacemos un único query de
    # existencia antes del bucle de UPDATEs (set_feedback es silent-no-op para
    # IDs inexistentes). El cost es O(N) sobre signals pero N es < 5k en M4.
    existing = {s["id"] for s in signals_store.list(limit=10_000, min_score=0.0)}
    updated = 0
    skipped = 0
    for sid in body.signal_ids:
        if sid not in existing:
            skipped += 1
            continue
        signals_store.set_feedback(sid, fb_to_apply)
        updated += 1
    return SignalsBulkFeedbackResponse(
        updated=updated,
        feedback_applied=body.feedback,
        skipped_missing=skipped,
    )


@app.post(
    "/api/v1/signals/bulk-delete-by-ids",
    response_model=SignalsBulkDeleteByIdsResponse,
    summary="M4.9 — Borrado masivo de señales por lista explícita de IDs",
    tags=["hunter"],
)
def signals_bulk_delete_by_ids(
    body: SignalsBulkDeleteByIdsRequest, request: Request
) -> SignalsBulkDeleteByIdsResponse:
    """Companion de bulk-feedback. El founder seleccionó manualmente las
    señales que quiere borrar — confiamos en esa decisión y NO preservamos
    promovidas ni con feedback (diferente de delete-by-type que SÍ preserva
    por defecto). Si seleccionas una señal promovida y la borras, te
    quedaste sin la señal pero el run_id sigue vivo en /cazar/{run_id}.
    """
    _require_user(request)
    from .core.storage import signals_store
    deleted = signals_store.delete_by_ids(body.signal_ids)
    return SignalsBulkDeleteByIdsResponse(deleted=deleted)


@app.get(
    "/api/v1/niche-opportunities",
    response_model=NicheOpportunitiesResponse,
    summary="M4.15 — Sub-niches sub-explorados dentro de mercados gigantes",
    tags=["hunter"],
)
def niche_opportunities(
    request: Request,
    min_parent_size: int = 5,
    max_niche_size: int = 3,
    top_parents: int = 10,
) -> NicheOpportunitiesResponse:
    """Founder del audio: 'recoger las migajas de donde están los gigantes'.

    Detecta clusters de ideas dentro de un mercado padre grande (≥
    min_parent_size señales totales) donde hay sub-niches sub-explorados
    (≤ max_niche_size señales) — son las "migajas" del gigante.

    Args:
        min_parent_size: tamaño mínimo del parent para considerarlo gigante.
            Default 5.
        max_niche_size: max signals en un sub-niche para considerarlo
            sub-explorado. Default 3.
        top_parents: cuántos gigantes retornar. Default 10.
    """
    _require_user(request)
    from .core.storage import signals_store
    if min_parent_size < 2 or min_parent_size > 1000:
        raise HTTPException(status_code=422, detail="min_parent_size must be 2-1000")
    if max_niche_size < 1 or max_niche_size > 100:
        raise HTTPException(status_code=422, detail="max_niche_size must be 1-100")
    if top_parents < 1 or top_parents > 100:
        raise HTTPException(status_code=422, detail="top_parents must be 1-100")
    items_raw = signals_store.niche_opportunities(
        min_parent_size=min_parent_size,
        max_niche_size=max_niche_size,
        top_parents=top_parents,
    )
    items = [NicheOpportunity(**it) for it in items_raw]
    return NicheOpportunitiesResponse(total=len(items), items=items)


@app.get(
    "/api/v1/digest/data",
    response_model=DigestData,
    summary="M6.1 — Weekly digest: data JSON estructurada (sin LLM, $0)",
    tags=["meta"],
)
def get_digest_data(request: Request, window_days: int = 7) -> DigestData:
    """Devuelve la data agregada para el digest semanal.

    Recolecta de signals_store, sources_store, runs_store:
    - Stats: signals/runs/sources de la semana
    - Top 3 first-mover gaps (M4.11)
    - Top 3 nichos sub-explorados (M4.15)
    - Eventos recientes (kind=events, score >= 0.5)
    - Trending searches (kind=google_trends, score >= 0.5)
    """
    _require_user(request)
    if window_days < 1 or window_days > 90:
        raise HTTPException(status_code=422, detail="window_days must be 1-90")
    from .core.digest import build_digest_data
    data = build_digest_data(window_days=window_days)
    return DigestData(**data)


@app.get(
    "/api/v1/digest/preview",
    summary="M6.1 — Weekly digest: HTML autocontenido (preview en browser)",
    tags=["meta"],
)
def get_digest_preview(request: Request, window_days: int = 7):
    """Devuelve HTML autocontenido del digest. Se puede abrir directo en el
    browser (o pegar en cliente de email como Mailgun template).

    Auth requerido (data privada del founder).
    """
    _require_user(request)
    if window_days < 1 or window_days > 90:
        raise HTTPException(status_code=422, detail="window_days must be 1-90")
    from .core.digest import build_digest_data, render_digest_html
    from fastapi.responses import HTMLResponse
    data = build_digest_data(window_days=window_days)
    dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:3001")
    html = render_digest_html(data, dashboard_url=dashboard_url)
    return HTMLResponse(content=html, status_code=200)


@app.post(
    "/api/v1/digest/send",
    response_model=DigestSendResponse,
    summary="M6.2 — Envía el digest semanal via SMTP (skip silencioso si no configurado)",
    tags=["meta"],
)
def send_digest(request: Request, window_days: int = 7) -> DigestSendResponse:
    """Envía el digest a DIGEST_TO via SMTP.

    Si SMTP_* env vars no están configurados, retorna sent=False con
    smtp_configured=False (no es error — patrón de "skip silencioso" igual
    que el cron auto-scan de M4.10). El cron weekly de GH Actions consume
    esto y exit-codea 0 cuando smtp_configured=false.

    Auth requerido. Si querés disparar desde un cron sin login: usa
    GATE_RUN_SECRET via X-Gate-Secret header (mismo patrón que /gate/run).
    """
    _require_user(request)
    if window_days < 1 or window_days > 90:
        raise HTTPException(status_code=422, detail="window_days must be 1-90")
    from .core.digest import (
        build_digest_data, render_digest_html, render_digest_text,
        send_digest_email, smtp_config_from_env,
    )
    smtp_cfg = smtp_config_from_env()
    if smtp_cfg is None:
        return DigestSendResponse(
            sent=False,
            detail="SMTP no configurado. Setea SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, DIGEST_FROM, DIGEST_TO en env vars.",
            recipients_count=0,
            smtp_configured=False,
        )
    data = build_digest_data(window_days=window_days)
    dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:3001")
    html = render_digest_html(data, dashboard_url=dashboard_url)
    text = render_digest_text(data)
    subject = os.getenv(
        "DIGEST_SUBJECT",
        f"📡 FoF — Resumen Semanal ({time.strftime('%Y-%m-%d', time.gmtime())})",
    )
    ok, detail = send_digest_email(html, text, subject=subject, config=smtp_cfg)
    n_recipients = len([
        x for x in smtp_cfg["DIGEST_TO"].split(",") if x.strip()
    ])
    return DigestSendResponse(
        sent=ok, detail=detail,
        recipients_count=n_recipients if ok else 0,
        smtp_configured=True,
    )


@app.get(
    "/api/v1/digest/text",
    summary="M6.1 — Weekly digest: texto plano (para clientes sin HTML)",
    tags=["meta"],
)
def get_digest_text(request: Request, window_days: int = 7):
    """Devuelve texto plano del digest. Útil para WhatsApp, Telegram, etc."""
    _require_user(request)
    if window_days < 1 or window_days > 90:
        raise HTTPException(status_code=422, detail="window_days must be 1-90")
    from .core.digest import build_digest_data, render_digest_text
    from fastapi.responses import PlainTextResponse
    data = build_digest_data(window_days=window_days)
    text = render_digest_text(data)
    return PlainTextResponse(content=text, status_code=200)


@app.get(
    "/api/v1/analytics/timeseries",
    response_model=AnalyticsResponse,
    summary="M8.0 — Analytics ejecutivo: time series + tops + feedback distribution",
    tags=["meta"],
)
def analytics_timeseries(request: Request, window_days: int = 30) -> AnalyticsResponse:
    """Devuelve buckets diarios para charts del dashboard ejecutivo:
    - signals_per_day, runs_per_day, verdicts_per_day, cost_per_day
    - top_topics (10) por count de signals
    - top_sources (10) por count de signals
    - feedback_distribution (up/down/unmarked)
    - totals agregados (signals, runs, cost USD, pass_rate%)

    Sin LLM. Costo $0. Heurística pura sobre data persistida.
    """
    _require_user(request)
    if window_days < 1 or window_days > 365:
        raise HTTPException(status_code=422, detail="window_days must be 1-365")

    import time as _t
    from collections import Counter, defaultdict
    from .core.storage import signals_store, runs_store, sources_store

    now = int(_t.time())
    cutoff = now - (window_days * 86_400)

    all_signals = signals_store.list(limit=10_000, min_score=0.0)
    all_runs = list(runs_store.values())
    all_sources = sources_store.list()
    sources_by_id = {s["id"]: s.get("name") or s.get("kind") for s in all_sources}

    # Helper para extraer fecha YYYY-MM-DD desde epoch
    def to_date(ts: int) -> str:
        if not ts:
            return "1970-01-01"
        return _t.strftime("%Y-%m-%d", _t.gmtime(ts))

    # Generar lista de buckets diarios (todos los días en la ventana, incluso vacíos)
    bucket_dates: List[str] = []
    for d in range(window_days):
        bucket_dates.append(to_date(now - (window_days - 1 - d) * 86_400))

    # Signals per day
    signals_by_date: Counter = Counter()
    for s in all_signals:
        ts = s.get("created_at", 0)
        if ts >= cutoff:
            signals_by_date[to_date(ts)] += 1

    # Runs per day + verdicts + cost
    runs_by_date: Counter = Counter()
    verdicts_by_date: defaultdict = defaultdict(lambda: {"pass": 0, "kill": 0, "iterate": 0})
    cost_by_date: defaultdict = defaultdict(float)
    # NOTE: RunsStore .values() doesn't expose created_at; usamos approximación
    # consultando directo el storage si es persistente
    from .core.storage import _db_path, _conn  # type: ignore[attr-defined]
    if _db_path:
        with _conn() as c:
            for row in c.execute(
                "SELECT data_json, created_at FROM gate_runs WHERE created_at >= ?",
                (cutoff,),
            ).fetchall():
                import json as _json
                try:
                    data = _json.loads(row["data_json"])
                except Exception:  # noqa: BLE001
                    continue
                date = to_date(int(row["created_at"]))
                runs_by_date[date] += 1
                verdict = data.get("verdict", "iterate")
                if verdict in ("pass", "kill", "iterate"):
                    verdicts_by_date[date][verdict] += 1
                cost = float(data.get("cost_usd_estimated") or 0)
                cost_by_date[date] += cost

    # Top topics
    topic_counter: Counter = Counter()
    for s in all_signals:
        if s.get("created_at", 0) < cutoff:
            continue
        topic = (s.get("suggested_topic") or "").strip().lower()[:60]
        if topic:
            topic_counter[topic] += 1

    # Top sources
    source_counter: Counter = Counter()
    for s in all_signals:
        if s.get("created_at", 0) < cutoff:
            continue
        sid = s.get("source_id")
        if sid:
            label = sources_by_id.get(sid, f"source_{sid}")
            source_counter[label] += 1

    # Feedback distribution
    up = sum(1 for s in all_signals if s.get("feedback") == "up")
    down = sum(1 for s in all_signals if s.get("feedback") == "down")
    unmarked = sum(1 for s in all_signals if not s.get("feedback"))

    # Totals
    signals_in_window = sum(signals_by_date.values())
    runs_in_window = sum(runs_by_date.values())
    cost_total = sum(cost_by_date.values())
    pass_count = sum(b["pass"] for b in verdicts_by_date.values())
    pass_rate = round(100 * pass_count / runs_in_window, 1) if runs_in_window else 0.0

    return AnalyticsResponse(
        window_days=window_days,
        signals_per_day=[AnalyticsBucket(date=d, count=signals_by_date.get(d, 0)) for d in bucket_dates],
        runs_per_day=[AnalyticsBucket(date=d, count=runs_by_date.get(d, 0)) for d in bucket_dates],
        verdicts_per_day=[
            AnalyticsVerdictBucket(
                date=d,
                pass_count=verdicts_by_date.get(d, {}).get("pass", 0),
                kill_count=verdicts_by_date.get(d, {}).get("kill", 0),
                iterate_count=verdicts_by_date.get(d, {}).get("iterate", 0),
            )
            for d in bucket_dates
        ],
        cost_per_day=[AnalyticsCostBucket(date=d, cost_usd=round(cost_by_date.get(d, 0.0), 4)) for d in bucket_dates],
        top_topics=[AnalyticsTopItem(label=t, count=c) for t, c in topic_counter.most_common(10)],
        top_sources=[AnalyticsTopItem(label=s, count=c) for s, c in source_counter.most_common(10)],
        feedback_distribution={"up": up, "down": down, "unmarked": unmarked},
        totals={
            "signals_in_window": signals_in_window,
            "runs_in_window": runs_in_window,
            "cost_total_usd": round(cost_total, 4),
            "pass_rate_pct": pass_rate,
        },
    )


@app.get(
    "/api/v1/admin/diagnose-deploy",
    response_model=DiagnoseDeployResponse,
    summary="M7.5 — Detecta misconfig común del deploy (env vars, CORS, SMTP, cron)",
    tags=["meta"],
)
def diagnose_deploy(request: Request) -> DiagnoseDeployResponse:
    """Recorre las dimensiones críticas del setup y reporta issues:
    - error:   bloqueante para producción
    - warning: degradación funcional pero no falla
    - info:    nota informativa
    """
    _require_user(request)
    issues: List[DeployIssue] = []

    # ----- 1. API keys de LLM (mock vs live mode) -----
    if not os.getenv("ANTHROPIC_API_KEY"):
        issues.append(DeployIssue(
            severity="warning",
            category="secrets",
            message="ANTHROPIC_API_KEY no está configurado — backend corre en mock_mode",
            fix_hint="Configura ANTHROPIC_API_KEY en las env vars del backend deployed (Railway/Render).",
        ))
    if not os.getenv("OPENAI_API_KEY"):
        issues.append(DeployIssue(
            severity="warning",
            category="secrets",
            message="OPENAI_API_KEY no configurado — gate_decider ensemble degradado a 2 modelos",
            fix_hint="Añadir OPENAI_API_KEY para activar ensemble vote completo.",
        ))
    if not os.getenv("GOOGLE_API_KEY"):
        issues.append(DeployIssue(
            severity="info",
            category="secrets",
            message="GOOGLE_API_KEY no configurado — fact-check con Gemini deshabilitado",
            fix_hint="Opcional: añadir GOOGLE_API_KEY para fact-check cross-LLM.",
        ))

    # ----- 2. CORS / auth -----
    allowed = os.getenv("ALLOWED_EMAILS", "").strip()
    if not allowed:
        issues.append(DeployIssue(
            severity="error",
            category="secrets",
            message="ALLOWED_EMAILS vacío — NADIE puede loguear al dashboard",
            fix_hint="Configura ALLOWED_EMAILS=email1@x.com,email2@x.com en env vars.",
        ))
    elif len([e for e in allowed.split(",") if e.strip()]) < 1:
        issues.append(DeployIssue(
            severity="error",
            category="secrets",
            message="ALLOWED_EMAILS mal-formateado",
            fix_hint="Usa CSV: 'email1@x.com,email2@x.com'.",
        ))

    # ----- 3. Storage persistente -----
    from .core.storage import _db_path  # type: ignore[attr-defined]
    if not _db_path:
        issues.append(DeployIssue(
            severity="warning",
            category="storage",
            message="DATABASE_PATH no configurado — usando storage en memoria (data se pierde al reiniciar)",
            fix_hint="En Railway: monta un Volume en /data y setea DATABASE_PATH=/data/circle.db.",
        ))

    # ----- 4. SMTP para weekly digest -----
    smtp_required = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
                      "DIGEST_FROM", "DIGEST_TO")
    missing_smtp = [v for v in smtp_required if not os.getenv(v)]
    if missing_smtp:
        if len(missing_smtp) == len(smtp_required):
            issues.append(DeployIssue(
                severity="info",
                category="smtp",
                message="SMTP no configurado — weekly digest no se envía (cron skipea silencioso)",
                fix_hint="Para enviar emails: configurá los 6 SMTP_* vars con Gmail App Password.",
            ))
        else:
            issues.append(DeployIssue(
                severity="warning",
                category="smtp",
                message=f"SMTP parcialmente configurado — faltan: {', '.join(missing_smtp)}",
                fix_hint="Completá los SMTP_* faltantes o quitá los que están parciales.",
            ))

    # ----- 5. Cron secrets (auto-scan + weekly-digest) -----
    auto_scan_url = os.getenv("AUTO_SCAN_API_URL")
    auto_scan_token = os.getenv("AUTO_SCAN_TOKEN")
    if not auto_scan_url or not auto_scan_token:
        issues.append(DeployIssue(
            severity="info",
            category="cron",
            message="AUTO_SCAN_API_URL/AUTO_SCAN_TOKEN no configurados — crons GitHub Actions saltan silencioso",
            fix_hint="Configurá los 2 secrets en GitHub repo Settings → Secrets → Actions. "
                     "Token: genera vía POST /api/v1/auth/login.",
        ))

    # ----- 6. Agentes lifecycle -----
    from .agents.trend_gap_analyzer import TrendGapAnalyzerAgent
    from .agents.multi_agent_consensus import MultiAgentConsensusAgent
    for cls in (TrendGapAnalyzerAgent, MultiAgentConsensusAgent):
        if getattr(cls, "EXPERIMENTAL", False):
            issues.append(DeployIssue(
                severity="info",
                category="agents",
                message=f"Agente {cls.AGENT_NAME} en estado experimental",
                fix_hint=f"Promoción a active requiere completar 30 golden cases.",
            ))

    # ----- 7. Tally -----
    errors = sum(1 for i in issues if i.severity == "error")
    warnings = sum(1 for i in issues if i.severity == "warning")
    if errors > 0:
        status = "errors"
        summary = f"{errors} error(es) bloqueante(s) + {warnings} warning(s). NO listo para producción."
    elif warnings > 0:
        status = "warnings"
        summary = f"{warnings} warning(s) — funciona con degradación. Revisar fix_hints."
    else:
        status = "ready"
        summary = "Sistema listo para producción. Sin errores ni warnings."

    return DiagnoseDeployResponse(
        overall_status=status,
        error_count=errors,
        warning_count=warnings,
        issues=issues,
        summary=summary,
    )


@app.get(
    "/api/v1/admin/status",
    response_model=AdminStatusResponse,
    summary="M7.0 — Estado completo del sistema (agentes, crons, env vars)",
    tags=["meta"],
)
def admin_status(request: Request) -> AdminStatusResponse:
    """Snapshot interno del sistema para diagnóstico operacional.

    Auth requerido. Solo revela existencia de env vars, NO sus valores
    (solo primeros 8 chars de SMTP_HOST y similares no-secretos).
    Las API keys / passwords se muestran solo como "set: true" sin masked_value.
    """
    _require_user(request)
    from .core.storage import signals_store, sources_store, runs_store, _db_path  # type: ignore[attr-defined]

    # ----- Agentes registrados (inspección dinámica) -----
    agents_meta = [
        # Workflow (los 7 del EvidenceGateWorkflow)
        ("idea_hunter", "n/a", "active(workflow)", False, "M1"),
        ("idea_enricher", "n/a", "active(workflow)", False, "M3"),
        ("idea_maturer", "n/a", "active(workflow)", False, "M1"),
        ("market_validator", "n/a", "active(workflow)", False, "M1"),
        ("landing_generator", "n/a", "active(workflow)", False, "M1"),
        ("gate_decider", "n/a", "active(workflow)", False, "M1"),
        ("source_scanner", "n/a", "active(workflow)", False, "M3"),
    ]
    # On-demand agents: introspect from clases
    for module_name, agent_cls_name in [
        ("trend_gap_analyzer", "TrendGapAnalyzerAgent"),
        ("niche_scout", "NicheScoutAgent"),
        ("event_relevance_scorer", "EventRelevanceScorerAgent"),
        ("sleeper_company_detector", "SleeperCompanyDetectorAgent"),
        ("product_arbitrage_evaluator", "ProductArbitrageEvaluatorAgent"),
        ("multi_agent_consensus", "MultiAgentConsensusAgent"),
    ]:
        try:
            mod = __import__(f"orchestrator.agents.{module_name}", fromlist=[agent_cls_name])
            cls = getattr(mod, agent_cls_name)
            experimental = getattr(cls, "EXPERIMENTAL", False)
            version = getattr(cls, "AGENT_VERSION", "n/a")
            status = "experimental" if experimental else "active(on-demand)"
            # Sprint origen: heurística por nombre
            sprint_map = {
                "trend_gap_analyzer": "M5.0/M5.1",
                "niche_scout": "M5.2/M5.8",
                "event_relevance_scorer": "M5.3/M5.9",
                "sleeper_company_detector": "M5.4/M5.10",
                "product_arbitrage_evaluator": "M5.5/M5.11",
                "multi_agent_consensus": "M6.0/M6.0b",
            }
            agents_meta.append((
                module_name, version, status, experimental,
                sprint_map.get(module_name, "?"),
            ))
        except Exception:  # noqa: BLE001
            continue

    agents = [
        AdminAgentStatus(
            name=name, version=version, status=status,
            experimental=experimental, sprint_origin=sprint,
        )
        for name, version, status, experimental, sprint in agents_meta
    ]

    # ----- Env vars relevantes -----
    SECRET_VARS = {
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY",
        "SMTP_PASSWORD", "GATE_RUN_SECRET",
    }
    SAFE_VARS = {  # estas sí mostramos masked_value
        "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "DIGEST_FROM",
        "DATABASE_PATH", "DASHBOARD_URL",
    }
    env_check_names = list(SECRET_VARS) + list(SAFE_VARS) + [
        "ALLOWED_EMAILS", "DIGEST_TO", "ENSEMBLE_GATE_ENABLED",
        "IDEA_ENRICHER_RESEARCH", "FACT_CHECK_ENABLED",
    ]
    env_checks: List[AdminEnvCheck] = []
    for name in env_check_names:
        v = os.getenv(name, "")
        if not v:
            env_checks.append(AdminEnvCheck(name=name, set=False, masked_value=None))
        elif name in SECRET_VARS:
            env_checks.append(AdminEnvCheck(name=name, set=True, masked_value=None))
        else:
            # Mostrar primeros 32 chars como hint (config, no secret)
            env_checks.append(AdminEnvCheck(
                name=name, set=True, masked_value=v[:32] + ("…" if len(v) > 32 else ""),
            ))

    # ----- Crons configurados -----
    crons = [
        AdminCronStatus(
            name="Hunter Auto-Scan",
            schedule="0 */6 * * * (cada 6h, minuto 17)",
            secret_keys_required=["AUTO_SCAN_API_URL", "AUTO_SCAN_TOKEN"],
            secret_keys_present=[bool(os.getenv("AUTO_SCAN_API_URL")), bool(os.getenv("AUTO_SCAN_TOKEN"))],
        ),
        AdminCronStatus(
            name="Weekly Digest",
            schedule="0 12 * * 1 (lunes 12 UTC)",
            secret_keys_required=[
                "AUTO_SCAN_API_URL", "AUTO_SCAN_TOKEN",
                "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD",
                "DIGEST_FROM", "DIGEST_TO",
            ],
            secret_keys_present=[
                bool(os.getenv("AUTO_SCAN_API_URL")),
                bool(os.getenv("AUTO_SCAN_TOKEN")),
                bool(os.getenv("SMTP_HOST")),
                bool(os.getenv("SMTP_USER")),
                bool(os.getenv("SMTP_PASSWORD")),
                bool(os.getenv("DIGEST_FROM")),
                bool(os.getenv("DIGEST_TO")),
            ],
        ),
    ]

    # ----- Stats agregados (cheap) -----
    all_sources = sources_store.list()
    all_signals = signals_store.list(limit=10_000, min_score=0.0)
    all_runs = list(runs_store.values())

    return AdminStatusResponse(
        mode="live" if not _workflow._mock_mode else "mock",
        persistent_storage=bool(_db_path),
        db_path=_db_path,
        cors_origins_count=len(_DEFAULT_ALLOWED_ORIGINS + _extra_origins),
        allowed_emails_count=len([
            e for e in os.getenv("ALLOWED_EMAILS", "").split(",") if e.strip()
        ]),
        sources_total=len(all_sources),
        sources_active=sum(1 for s in all_sources if s.get("active")),
        signals_total=len(all_signals),
        runs_total=len(all_runs),
        agents=agents,
        env_checks=env_checks,
        crons=crons,
    )


@app.post(
    "/api/v1/consensus/analyze",
    response_model=ConsensusResponse,
    summary="M6.0 — MultiAgentConsensus: sintetiza N perspectives sobre una decisión",
    tags=["hunter"],
)
def analyze_consensus(
    body: ConsensusRequest, request: Request
) -> ConsensusResponse:
    """Toma una pregunta de decisión + lista de perspectives (cada una con
    source y text) y devuelve un consensus estructurado: agreement_score,
    consensus_view, dissenting_views, key_tradeoffs, final_recommendation,
    confidence.

    R11-compliant: el agente NO invoca otros agentes. Recibe perspectives
    ya producidas y las sintetiza. La decisión de qué agentes invocar antes
    pertenece al caller (frontend o endpoint orquestador), no al agente.

    Status: M6.0 experimental (10/30 golden cases). Costo ~$0.005-0.015.
    """
    _require_user(request)
    from .agents.multi_agent_consensus import MultiAgentConsensusAgent
    agent = MultiAgentConsensusAgent(
        mock_mode=_workflow._mock_mode,
        client=None if _workflow._mock_mode else _workflow._idea_hunter._client,
    )
    analysis = agent.analyze(
        decision_question=body.decision_question,
        perspectives=[p.model_dump() for p in body.perspectives],
    )
    return ConsensusResponse(
        **analysis.to_dict(),
        cost_usd_estimated=0.0 if agent._mock_mode else 0.012,
        mock_mode=agent._mock_mode,
    )


@app.post(
    "/api/v1/niche-opportunities/analyze",
    response_model=NicheScoutResponse,
    summary="M5.2 — NicheScout: plan de entrada al sub-niche (experimental)",
    tags=["hunter"],
)
def analyze_niche_opportunity(
    body: NicheScoutRequest, request: Request
) -> NicheScoutResponse:
    """Toma una NicheOpportunity de M4.15 y devuelve un plan de entrada
    al sub-niche más prometedor.

    Status: M5.2 experimental (10/30 golden cases). Costo ~$0.005-0.01.
    """
    _require_user(request)
    from .agents.niche_scout import NicheScoutAgent
    agent = NicheScoutAgent(
        mock_mode=_workflow._mock_mode,
        client=None if _workflow._mock_mode else _workflow._idea_hunter._client,
    )
    analysis = agent.analyze(
        parent_market=body.parent_market,
        parent_size=body.parent_size,
        leader_niche=body.leader_niche,
        underexplored_niches=body.underexplored_niches,
    )
    return NicheScoutResponse(
        **analysis.to_dict(),
        cost_usd_estimated=0.0 if agent._mock_mode else 0.008,
        mock_mode=agent._mock_mode,
    )


@app.post(
    "/api/v1/events/score",
    response_model=EventScoringResponse,
    summary="M5.3 — EventRelevanceScorer: ¿ir o no? (experimental)",
    tags=["hunter"],
)
def score_event(
    body: EventScoringRequest, request: Request
) -> EventScoringResponse:
    """Toma un evento/feria/congreso y decide go/skip/send_someone_else
    + recomendaciones de preparación.

    Status: M5.3 experimental (10/30 golden cases). Costo ~$0.003.
    """
    _require_user(request)
    from .agents.event_relevance_scorer import EventRelevanceScorerAgent
    agent = EventRelevanceScorerAgent(
        mock_mode=_workflow._mock_mode,
        client=None if _workflow._mock_mode else _workflow._idea_hunter._client,
    )
    analysis = agent.analyze(
        event_title=body.event_title,
        event_description=body.event_description,
        evidence_urls=body.evidence_urls,
        industry_focus=body.industry_focus,
    )
    return EventScoringResponse(
        **analysis.to_dict(),
        cost_usd_estimated=0.0 if agent._mock_mode else 0.003,
        mock_mode=agent._mock_mode,
    )


@app.post(
    "/api/v1/sleeper-companies/detect",
    response_model=SleeperDetectResponse,
    summary="M5.4 — SleeperCompanyDetector: detecta #2 con momentum (experimental)",
    tags=["hunter"],
)
def detect_sleeper_companies(
    body: SleeperDetectRequest, request: Request
) -> SleeperDetectResponse:
    """Toma una lista de empresas públicas (signals kind=sec_edgar) y
    detecta sleeper candidates — empresas no-líder con cadence alta de filings.

    Status: M5.4 experimental (10/30 golden cases). Costo ~$0.01.
    """
    _require_user(request)
    from .agents.sleeper_company_detector import SleeperCompanyDetectorAgent
    agent = SleeperCompanyDetectorAgent(
        mock_mode=_workflow._mock_mode,
        client=None if _workflow._mock_mode else _workflow._idea_hunter._client,
    )
    analysis = agent.analyze(companies=body.companies)
    return SleeperDetectResponse(
        **analysis.to_dict(),
        cost_usd_estimated=0.0 if agent._mock_mode else 0.010,
        mock_mode=agent._mock_mode,
    )


@app.post(
    "/api/v1/arbitrage/evaluate",
    response_model=ArbitrageEvalResponse,
    summary="M5.5 — ProductArbitrageEvaluator: ¿esto se puede dropshipping? (experimental)",
    tags=["hunter"],
)
def evaluate_arbitrage(
    body: ArbitrageEvalRequest, request: Request
) -> ArbitrageEvalResponse:
    """Toma un trending search (kind=google_trends) y evalúa si es producto
    arbitrabable + margin estimate + recomendación test/skip/deepdive.

    Status: M5.5 experimental (10/30 golden cases). Costo ~$0.003.
    """
    _require_user(request)
    from .agents.product_arbitrage_evaluator import ProductArbitrageEvaluatorAgent
    agent = ProductArbitrageEvaluatorAgent(
        mock_mode=_workflow._mock_mode,
        client=None if _workflow._mock_mode else _workflow._idea_hunter._client,
    )
    analysis = agent.analyze(
        trending_query=body.trending_query,
        target_geo=body.target_geo,
        source_cost_usd=body.source_cost_usd,
        target_price_usd=body.target_price_usd,
    )
    return ArbitrageEvalResponse(
        **analysis.to_dict(),
        cost_usd_estimated=0.0 if agent._mock_mode else 0.003,
        mock_mode=agent._mock_mode,
    )


@app.post(
    "/api/v1/trend-gaps/analyze",
    response_model=TrendGapAnalyzeResponse,
    summary="M5.0 — Analizar un gap cross-country con razonamiento LLM (experimental)",
    tags=["hunter"],
)
def analyze_trend_gap(
    body: TrendGapAnalyzeRequest, request: Request
) -> TrendGapAnalyzeResponse:
    """Toma un TrendGapItem (resultado de /api/v1/trend-gaps) y devuelve un
    análisis profundo: qué país atacar primero, timing hypothesis, patrón
    de adopción, go-to-market, riesgos por país.

    Status: M5.0 experimental (R12 — solo 12/30 golden cases todavía).
    Costo: ~$0.005-0.01 por análisis (Haiku/Sonnet single call). En mock
    mode produce un placeholder en español útil para CI/dev.
    """
    _require_user(request)
    from .agents.trend_gap_analyzer import TrendGapAnalyzerAgent
    agent = TrendGapAnalyzerAgent(
        mock_mode=_workflow._mock_mode,
        client=None if _workflow._mock_mode else _workflow._idea_hunter._client,
    )
    analysis = agent.analyze(
        idea_summary=body.idea_summary,
        validated_in=body.validated_in,
        missing_in=body.missing_in,
        opportunity_score=body.opportunity_score,
    )
    return TrendGapAnalyzeResponse(
        priority_country=analysis.priority_country,
        priority_rationale=analysis.priority_rationale,
        timing_hypothesis=analysis.timing_hypothesis,
        adoption_pattern=analysis.adoption_pattern,
        go_to_market=analysis.go_to_market,
        risks_per_country=analysis.risks_per_country,
        effort_estimate_weeks=analysis.effort_estimate_weeks,
        confidence=analysis.confidence,
        reasoning=analysis.reasoning,
        cost_usd_estimated=0.0 if agent._mock_mode else 0.008,
        mock_mode=agent._mock_mode,
    )


@app.get(
    "/api/v1/trend-gaps",
    response_model=TrendGapsResponse,
    summary="M4.11 — Cross-country first-mover opportunities (ideas validadas en país X y ausentes en Y)",
    tags=["hunter"],
)
def trend_gaps(
    request: Request,
    min_validation_signals: int = 2,
    min_validation_feedback: int = 1,
    countries: str = "",
) -> TrendGapsResponse:
    """Founder del audio: 'si llegas first-mover ahí, eventualmente tienes
    posibilidades de poderla reventar'.

    Detecta clusters de ideas que ya están validadas en ≥1 país (por feedback
    o score alto) y mapea los países objetivo donde NO existe ningún signal.

    Args:
        min_validation_signals: mínimo de signals del mismo país para
            considerar "presente". Default 2.
        min_validation_feedback: mínimo de 👍 en ese país para considerar
            "validado por el founder". Default 1.
        countries: lista CSV de países a evaluar como huecos. Vacío usa
            default LATAM + USA + España.
    """
    _require_user(request)
    from .core.storage import signals_store
    if min_validation_signals < 1 or min_validation_signals > 50:
        raise HTTPException(status_code=422, detail="min_validation_signals must be 1-50")
    if min_validation_feedback < 0 or min_validation_feedback > 50:
        raise HTTPException(status_code=422, detail="min_validation_feedback must be 0-50")
    target_countries = None
    if countries.strip():
        target_countries = [c.strip() for c in countries.split(",") if c.strip()]
        if len(target_countries) > 30:
            raise HTTPException(status_code=422, detail="max 30 countries")
    gaps = signals_store.cross_country_gaps(
        min_validation_signals=min_validation_signals,
        min_validation_feedback=min_validation_feedback,
        target_countries=target_countries,
    )
    items = [TrendGapItem(**g) for g in gaps]
    return TrendGapsResponse(total=len(items), items=items)


@app.get(
    "/api/v1/signals/stats-by-type",
    response_model=SignalsStatsByTypeResponse,
    summary="M4.7 — Distribución de señales por content_type",
    tags=["hunter"],
)
def signals_stats_by_type(request: Request) -> SignalsStatsByTypeResponse:
    """Founder request implícito (siguiente paso de M4.6): ver de un vistazo
    cuántas señales hay de cada tipo, para saber qué curar.

    Útil como input visual para el dropdown de filtro y para los botones
    "🗑️ Borrar Noticia" — el founder ve "hay 32 Otros" y decide si vale
    la pena limpiarlos.
    """
    _require_user(request)
    from .core.storage import signals_store
    counts = signals_store.stats_by_content_type()
    return SignalsStatsByTypeResponse(**counts)


@app.post(
    "/api/v1/signals/delete-by-type",
    response_model=SignalsDeleteByTypeResponse,
    summary="M4.6 — Bulk delete signals by classified content_type (news/blog/...)",
    tags=["hunter"],
)
def signals_delete_by_type(
    body: SignalsDeleteByTypeRequest, request: Request
) -> SignalsDeleteByTypeResponse:
    """Founder request: 'debe existir la opción de eliminar las noticias por
    tipo noticia, blog, estudio, etc.' (M4.6) — extendido en M4.6b para
    también borrar por fuente (source_kind / source_id).

    Combina los filtros con AND. Al menos uno de
    {content_type, source_kind, source_id} debe estar presente.

    Por defecto preserva las que tienen feedback (👍/👎) o fueron promovidas,
    para no destruir el historial de decisiones del founder. Si quiere
    borrarlo todo, pasar keep_promoted=false y keep_feedback=false.

    El body usa POST en lugar de DELETE para evitar el problema de CORS
    preflight para verbs no-CORS-simples y para soportar payload con
    parámetros.
    """
    _require_user(request)
    from .core.storage import signals_store
    # Validación: al menos un filtro
    if body.content_type is None and body.source_kind is None and body.source_id is None:
        raise HTTPException(
            status_code=422,
            detail="Debes proveer al menos uno de: content_type, source_kind, source_id",
        )
    # Contar las preservadas ANTES del delete para poder informar al usuario
    rows = signals_store.list(limit=10_000, min_score=0.0)

    def _matches_filter(r: Dict) -> bool:
        if body.content_type is not None:
            ct = r.get("content_type")
            if body.content_type == "unknown":
                if ct not in (None, "", "unknown"):
                    return False
            elif ct != body.content_type:
                return False
        if body.source_kind is not None and r.get("source_kind") != body.source_kind:
            return False
        if body.source_id is not None and r.get("source_id") != body.source_id:
            return False
        return True

    matching = [r for r in rows if _matches_filter(r)]
    kept_promoted = sum(1 for r in matching if r.get("promoted_run_id"))
    kept_feedback = sum(1 for r in matching if r.get("feedback"))
    deleted = signals_store.delete_bulk(
        content_type=body.content_type,
        source_kind=body.source_kind,
        source_id=body.source_id,
        keep_promoted=body.keep_promoted,
        keep_feedback=body.keep_feedback,
    )
    return SignalsDeleteByTypeResponse(
        deleted=deleted,
        content_type=body.content_type,
        source_kind=body.source_kind,
        source_id=body.source_id,
        kept_promoted=kept_promoted if body.keep_promoted else 0,
        kept_feedback=kept_feedback if body.keep_feedback else 0,
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
    "/api/v1/signals/{signal_id}/translate",
    response_model=TranslateSignalResponse,
    summary="Translate the signal's theme + excerpt to Spanish (LLM call ~$0.001)",
    tags=["hunter"],
)
def translate_signal(signal_id: int, request: Request) -> TranslateSignalResponse:
    """M4.4 — traduce theme + excerpt al español con Claude Haiku.

    Si la señal ya está en español (detected language=es), devuelve sin
    cambios + already_in_spanish=true sin gastar LLM.

    Si la señal NO está en español, hace una llamada Haiku (~$0.001) y
    persiste la traducción. Posteriormente, el dashboard puede mostrar
    'ver original / ver traducción' alternando los campos.
    """
    _require_user(request)
    from .core.storage import signals_store
    from .core.language import detect_language

    sig = signals_store.get(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="signal not found")

    theme = sig.get("theme", "")
    excerpt = sig.get("excerpt", "")
    lang, _ = detect_language(f"{theme} {excerpt}")

    # Shortcut: already in Spanish — no LLM call
    if lang == "es":
        return TranslateSignalResponse(
            signal_id=signal_id,
            original_language="es",
            translated_theme=theme,
            translated_excerpt=excerpt,
            cost_usd_estimated=0.0,
            already_in_spanish=True,
        )

    # In mock_mode (no API key), use a deterministic placeholder
    if _workflow._mock_mode:
        t_theme = f"[Traducción demo] {theme}"
        t_excerpt = f"[Traducción demo] {excerpt}"
        signals_store.set_translation(signal_id, t_theme, t_excerpt, original_language=lang)
        return TranslateSignalResponse(
            signal_id=signal_id,
            original_language=lang,
            translated_theme=t_theme,
            translated_excerpt=t_excerpt,
            cost_usd_estimated=0.0,
            already_in_spanish=False,
        )

    # Real LLM call via the existing Anthropic client
    try:
        client = _workflow._idea_hunter._client
        if client is None:
            raise RuntimeError("LLM client not initialised")
        prompt = (
            f"Traduce este título y resumen al español neutro (LATAM). "
            f"Mantén nombres propios y términos técnicos. Devuelve JSON con "
            f"keys 'theme' y 'excerpt'.\n\n"
            f"TITLE: {theme}\n\n"
            f"EXCERPT: {excerpt[:1500]}"
        )
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text if resp.content else ""
        import json as _json
        # Best-effort JSON extraction
        m = __import__("re").search(r"\{[^{}]*\}", raw, __import__("re").DOTALL)
        data = _json.loads(m.group(0)) if m else {}
        t_theme = (data.get("theme") or theme)[:240]
        t_excerpt = (data.get("excerpt") or excerpt)[:1500]
    except Exception as exc:  # noqa: BLE001
        logger.warning("translate: LLM call failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Translation failed: {exc}")

    signals_store.set_translation(signal_id, t_theme, t_excerpt, original_language=lang)
    return TranslateSignalResponse(
        signal_id=signal_id,
        original_language=lang,
        translated_theme=t_theme,
        translated_excerpt=t_excerpt,
        cost_usd_estimated=0.001,
        already_in_spanish=False,
    )


@app.post(
    "/api/v1/signals/{signal_id}/enrich",
    response_model=EnrichSignalResponse,
    summary="Fetch the signal's evidence URLs and pull og:title/og:description into theme+excerpt",
    tags=["hunter"],
)
def enrich_signal(signal_id: int, request: Request) -> EnrichSignalResponse:
    """M3.17 — enriquece una señal SIN LLM.

    Para cada evidence_url, hace fetch del HTML y extrae:
      - og:title o twitter:title o <title>
      - og:description o twitter:description o meta description
      - Texto del body como fallback
    Y actualiza el theme + excerpt + item_titles de la señal con info real.

    Útil cuando una señal viene de un chat (theme="Instagram") y no
    sabes de qué trata realmente. Tras enrich, theme y excerpt reflejan
    el contenido real de las páginas linkeadas.

    NO usa LLM (cost: $0). Solo HTTP GET + regex.
    """
    _require_user(request)
    from .core.storage import signals_store
    from .core.source_fetcher import fetch_url

    sig = signals_store.get(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="signal not found")

    urls = sig.get("evidence_urls", []) or []
    if not urls:
        return EnrichSignalResponse(
            signal_id=signal_id,
            urls_fetched=0, urls_failed=0,
            theme_updated=False, excerpt_updated=False, item_titles_updated=False,
        )

    fetched = []
    failed = 0
    for u in urls[:5]:  # cap a 5 para no bloquear
        item = fetch_url(u)
        if item is None:
            failed += 1
            continue
        fetched.append(item)

    if not fetched:
        return EnrichSignalResponse(
            signal_id=signal_id,
            urls_fetched=0, urls_failed=failed,
            theme_updated=False, excerpt_updated=False, item_titles_updated=False,
        )

    # New theme = title del primer item (mejor que "Instagram")
    new_theme = fetched[0].title[:240]
    # New excerpt = concatenación de los summaries (cap a 1500 chars)
    summaries = [it.summary for it in fetched if it.summary]
    new_excerpt = " | ".join(summaries)[:1500] or sig.get("excerpt", "")
    # New item_titles = títulos de cada item fetcheado, padded a len(urls)
    new_titles = [it.title for it in fetched] + [""] * (len(urls) - len(fetched))

    # Solo actualizar si lo nuevo es mejor (no degradar)
    theme_updated = bool(new_theme) and new_theme != sig.get("theme", "")
    excerpt_updated = bool(new_excerpt) and new_excerpt != sig.get("excerpt", "")
    titles_updated = any(t for t in new_titles)  # al menos un título real

    signals_store.update_content(
        signal_id,
        theme=new_theme if theme_updated else None,
        excerpt=new_excerpt if excerpt_updated else None,
        item_titles=new_titles if titles_updated else None,
    )

    return EnrichSignalResponse(
        signal_id=signal_id,
        urls_fetched=len(fetched),
        urls_failed=failed,
        theme_updated=theme_updated,
        excerpt_updated=excerpt_updated,
        item_titles_updated=titles_updated,
        new_theme=new_theme if theme_updated else None,
        new_excerpt=new_excerpt if excerpt_updated else None,
    )


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
    # Webhook: ping when analyzer recommends promote (high-value signal)
    if analysis.recommendation == "promote":
        try:
            from .core import webhooks as _wh
            sig_fresh = signals_store.get(signal_id)
            if sig_fresh:
                _wh.emit_signal_event(
                    "signal.analyzed.promote",
                    {**sig_fresh, "analysis": analysis.to_dict()},
                    source_name=source_name,
                )
        except Exception:  # noqa: BLE001
            pass
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
    sig = _polish_signal_for_display(sig)
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
    from .core.file_parser import extract_urls, filter_urls_by_quality, parse_file
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

    all_urls = extract_urls(text)
    # M3.15 — filtro de calidad: descarta status de X/IG, reels, perfiles,
    # llamadas, etc. ANTES de guardar. Founder pidió: "filtrar solo las que
    # puedan ser ideas, identificar qué es noticia y qué no, subir solo
    # noticias que me sugieres". Lo hacemos con heurísticas (sin LLM, gratis)
    # y reportamos qué se descartó con razón.
    urls, discarded = filter_urls_by_quality(all_urls)

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
        urls_found=len(all_urls),
        urls_added=urls_added,
        sources_created=sources_created,
        skipped_duplicates=skipped,
        urls_discarded_as_noise=len(discarded),
        discarded_samples=[
            {"url": d["url"], "reason": d["reason"]} for d in discarded[:10]
        ],
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
        # M3.13: auto-cleanup legacy placeholder signals on every startup.
        # Idempotent (no-op if no placeholders) and bounded (LIKE on indexed
        # columns). Founders had complained about "Mock signal from rss"
        # appearing in the dashboard for hours after the scanner fix shipped.
        # Now they never see them — startup wipes them automatically.
        try:
            from .core.storage import signals_store as _signals
            deleted = _signals.cleanup_mocks()
            if deleted > 0:
                logger.info("startup: auto-cleaned %d legacy placeholder signals", deleted)
        except Exception as exc:  # noqa: BLE001
            logger.warning("startup: cleanup_mocks failed: %s", exc)

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
