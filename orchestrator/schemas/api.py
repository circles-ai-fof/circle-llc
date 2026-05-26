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
