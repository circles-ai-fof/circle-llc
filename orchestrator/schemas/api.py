"""
Request / Response Pydantic models for the EvidenceGate REST API.

Intentionally kept flat and JSON-serialisable — no nested Pydantic
sub-models beyond what FastAPI can handle trivially.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from ..core.models import MetricsSnapshot


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class RunGateRequest(BaseModel):
    topic: str = Field(
        min_length=5,
        max_length=200,
        description="The business idea / trend to evaluate (5–200 chars)",
        examples=["fintech para PYMEs Ecuador"],
    )
    metrics: Optional[MetricsSnapshot] = Field(
        default=None,
        description="Real ad metrics, if already available. Omit for baseline run.",
    )


# ---------------------------------------------------------------------------
# Response — main gate run
# ---------------------------------------------------------------------------


class RunGateResponse(BaseModel):
    run_id: str = Field(description="UUID of this run")
    status: str = Field(description='"completed" | "failed"')
    idea_title: str
    verdict: str = Field(description='"pass" | "kill" | "iterate"')
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    next_steps: List[str]
    landing_headline: str
    landing_slug: str
    test_design: Dict = Field(description="EvidenceTestDesign serialised as dict")
    canonical_goal_statement: str
    steps_used: int
    cost_usd_estimated: float
    # Escalation
    needs_human_review: bool = False
    review_reason: Optional[str] = None
    ensemble_votes: Optional[List[str]] = None
    human_override: Optional[Dict] = None


# ---------------------------------------------------------------------------
# Human override (when ensemble disagrees and a founder decides manually)
# ---------------------------------------------------------------------------


class HumanOverrideRequest(BaseModel):
    verdict: str = Field(
        description='Final verdict chosen by the human: "pass" | "kill" | "iterate"',
        pattern="^(pass|kill|iterate)$",
    )
    reason: str = Field(
        min_length=10,
        max_length=500,
        description="Why this verdict — used for later calibration",
    )
    decided_by: str = Field(
        min_length=2,
        max_length=80,
        description="Name or email of the human deciding",
    )


class HumanOverrideResponse(BaseModel):
    run_id: str
    original_verdict: str
    override_verdict: str
    decided_by: str
    decided_at: str
    reason: str


class PendingReviewItem(BaseModel):
    run_id: str
    idea_title: str
    verdict: str
    confidence: float
    review_reason: str
    ensemble_votes: List[str]
    rationale: str


class PendingReviewResponse(BaseModel):
    pending_count: int
    items: List[PendingReviewItem]


# ---------------------------------------------------------------------------
# Lead capture (anti-bot protected)
# ---------------------------------------------------------------------------


class LeadCaptureRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=80, description="Factory slug the lead came from")
    email: str = Field(min_length=5, max_length=200)
    name: Optional[str] = Field(default=None, max_length=120)
    # Anti-bot fields
    company_website: Optional[str] = Field(
        default=None,
        description="HONEYPOT — humans never fill this; if set, the lead is rejected.",
        max_length=200,
    )
    dwell_ms: Optional[int] = Field(
        default=None,
        description="Milliseconds between first paint and submit; humans take >3000ms.",
        ge=0,
        le=86_400_000,
    )
    turnstile_token: Optional[str] = Field(
        default=None,
        description="Cloudflare Turnstile token (when widget is on the page).",
        max_length=4000,
    )


class LeadCaptureResponse(BaseModel):
    accepted: bool
    slug: str
    message: str


# ---------------------------------------------------------------------------
# Leads viewer (admin)
# ---------------------------------------------------------------------------


class LeadItem(BaseModel):
    """One stored lead. Emails are masked for any unprivileged caller."""
    slug: str
    email: str  # full email only when caller provides X-Gate-Secret
    name: Optional[str] = None
    ts: int  # unix epoch seconds
    ip_masked: Optional[str] = None  # always masked (last octet hidden)


class LeadsListResponse(BaseModel):
    slug: str
    count: int
    leads: List[LeadItem]
    masked: bool = Field(
        description="True when caller did not provide admin secret; emails partially redacted",
    )


class LeadsStatsBySlug(BaseModel):
    slug: str
    count: int


class LeadsStatsResponse(BaseModel):
    total_leads: int
    by_slug: List[LeadsStatsBySlug]


# ---------------------------------------------------------------------------
# Response — agent info
# ---------------------------------------------------------------------------


class AgentInfo(BaseModel):
    name: str
    scope_does: str
    scope_does_not: str
    status: str = Field(description='"active" | "deferred"')


class AgentsResponse(BaseModel):
    agents: List[AgentInfo]
    total: int


# ---------------------------------------------------------------------------
# Response — health check
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    mode: str = Field(description='"live" | "mock"')
    workflow: str = "EvidenceGateWorkflow"


# ---------------------------------------------------------------------------
# Response — error detail (used in error handlers)
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    detail: str
