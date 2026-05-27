from __future__ import annotations

from datetime import datetime, timezone


def _utc_now() -> datetime:
    """Replacement for the deprecated datetime.utcnow() — returns an
    aware datetime in UTC."""
    return datetime.now(timezone.utc)
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class VerticalCategory(str, Enum):
    SAAS = "saas"
    MARKETPLACE = "marketplace"
    COMMUNITY = "community"
    ECOMMERCE = "ecommerce"
    FINTECH = "fintech"
    HEALTHTECH = "healthtech"
    EDTECH = "edtech"
    OTHER = "other"


class IdeaSpec(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    description: str
    target_market: str
    problem_statement: str
    proposed_solution: str
    vertical_category: VerticalCategory
    created_at: datetime = Field(default_factory=_utc_now)


class ICPProfile(BaseModel):
    demographic: str
    psychographic: str
    pain_points: List[str]
    willingness_to_pay: str
    acquisition_channel: str


class MatureIdeaSpec(BaseModel):
    idea: IdeaSpec
    icp: ICPProfile
    value_proposition: str
    unfair_advantage: str
    key_risks: List[str]


class EvidenceTestDesign(BaseModel):
    hypothesis: str
    success_metrics: List[str]
    failure_metrics: List[str]
    test_duration_days: int = Field(ge=7, le=30)
    ad_budget_usd: float = Field(ge=50.0, le=2000.0)
    target_ctr: float = Field(ge=0.005, le=0.20)
    target_conversion_rate: float = Field(ge=0.01, le=0.50)


class LandingSpec(BaseModel):
    headline: str = Field(max_length=80)
    subheadline: str = Field(max_length=160)
    value_props: List[str] = Field(min_length=3, max_length=5)
    cta_text: str = Field(max_length=40)
    social_proof: str
    domain_slug: str


class MetricsSnapshot(BaseModel):
    impressions: int = Field(ge=0)
    clicks: int = Field(ge=0)
    conversions: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)
    ctr: float = Field(ge=0.0)
    conversion_rate: float = Field(ge=0.0)
    cost_per_conversion: float = Field(ge=0.0)


class GateVerdict(str, Enum):
    PASS = "pass"
    KILL = "kill"
    ITERATE = "iterate"


class HumanOverride(BaseModel):
    """Recorded when a human overrides a gate decision flagged for review."""
    decided_by: str
    decided_at: datetime = Field(default_factory=_utc_now)
    original_verdict: GateVerdict
    override_verdict: GateVerdict
    reason: str = Field(min_length=10, max_length=500)


class GateDecision(BaseModel):
    verdict: GateVerdict
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    key_evidence: List[str]
    next_steps: List[str]
    metrics: MetricsSnapshot
    # Escalation fields — set by gate_decider when ensemble disagrees
    needs_human_review: bool = False
    review_reason: Optional[str] = None  # why escalation was triggered
    human_override: Optional[HumanOverride] = None
