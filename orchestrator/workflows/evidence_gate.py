"""
EvidenceGateWorkflow — 4-step linear chassis for Sprint M1.

Justification (AI Builder's Handbook Cap 10 §10.5):
"The pattern we see ship most often is a hybrid: a workflow that embeds small,
scoped agents in specific places they help, with the workflow providing structure
everywhere else. Use workflows as the chassis."

The evidence-gate IS a linear pipeline. Steps run in fixed order:
  1. idea_hunter   → IdeaSpec        (single LLM call)
  2. idea_maturer  → MatureIdeaSpec  (single LLM call)
  3. market_validator → EvidenceTestDesign (single LLM call)
  4a. landing_generator → LandingSpec (single LLM call + tool use)
  4b. gate_decider  → GateDecision   (code rules + optional LLM judge)

NOT a multi-agent system. No dynamic routing. No agent-to-agent negotiation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

import anthropic

from ..agents.gate_decider import GateDeciderAgent
from ..agents.idea_enricher import IdeaEnricherAgent
from ..agents.idea_hunter import IdeaHunterAgent
from ..agents.idea_maturer import IdeaMaturerAgent
from ..agents.landing_generator import LandingGeneratorAgent
from ..agents.market_validator import MarketValidatorAgent
from ..core.canonical_goal import CanonicalGoal
from ..core.models import (
    EvidenceTestDesign,
    GateDecision,
    IdeaSpec,
    LandingSpec,
    MatureIdeaSpec,
    MetricsSnapshot,
)
from ..core.step_budget import BudgetTracker, TrajectoryBudgetExceededError  # noqa: F401

logger = logging.getLogger(__name__)


@dataclass
class EvidenceGateRun:
    run_id: UUID
    topic: str
    started_at: datetime
    idea: IdeaSpec
    mature_idea: MatureIdeaSpec
    test_design: EvidenceTestDesign
    landing: LandingSpec
    decision: GateDecision
    canonical_goal: CanonicalGoal = field(default=None)
    budget_tracker: BudgetTracker = field(default=None)
    completed_at: datetime = field(default_factory=datetime.utcnow)

    def summary(self) -> str:
        elapsed = (self.completed_at - self.started_at).total_seconds()
        return (
            f"Run {self.run_id} | '{self.idea.title}'\n"
            f"Verdict: {self.decision.verdict.value.upper()} "
            f"(confidence {self.decision.confidence:.0%})\n"
            f"Rationale: {self.decision.rationale}\n"
            f"Elapsed: {elapsed:.1f}s"
        )


class EvidenceGateWorkflow:
    """
    Instantiate once, call run() for each topic to evaluate.
    mock_mode=True skips all real API calls — safe for CI.
    """

    def __init__(
        self,
        client: Optional[anthropic.Anthropic] = None,
        mock_mode: bool = False,
    ) -> None:
        self._mock_mode = mock_mode
        _client = client or (None if mock_mode else anthropic.Anthropic())

        self._idea_hunter = IdeaHunterAgent(client=_client, mock_mode=mock_mode)
        self._idea_enricher = IdeaEnricherAgent(client=_client, mock_mode=mock_mode)
        self._idea_maturer = IdeaMaturerAgent(client=_client, mock_mode=mock_mode)
        self._market_validator = MarketValidatorAgent(client=_client, mock_mode=mock_mode)
        self._landing_generator = LandingGeneratorAgent(client=_client, mock_mode=mock_mode)
        self._gate_decider = GateDeciderAgent(client=_client, mock_mode=mock_mode)

    def run(
        self,
        topic: str,
        metrics: Optional[MetricsSnapshot] = None,
    ) -> EvidenceGateRun:
        run_id = uuid4()
        started_at = datetime.utcnow()
        logger.info("EvidenceGate start run_id=%s topic=%r", run_id, topic)

        # R14 — Canonical Goal Statement
        goal = CanonicalGoal(
            workflow_id=run_id,
            goal_statement=(
                "Validate whether a business idea has real market demand through a 14-day "
                "evidence test with real ads and a landing page, before committing to build."
            ),
            success_criteria=[
                "IdeaSpec generated with clear problem statement",
                "ICP defined with specific demographic and acquisition channel",
                "Market test designed with quantitative pass/fail thresholds",
                "Landing page copy generated and ready to deploy",
                "Gate decision made with data-backed rationale",
            ],
            out_of_scope=[
                "Building the actual product",
                "Writing production code",
                "Making architectural decisions",
                "Onboarding real users",
            ],
        )

        # R13 — Step Budget per Trajectory
        tracker = BudgetTracker()

        # Step 1 + 1.5 — Idea generation + enrichment with refinement loop (ADR-007)
        # Bounded: up to MAX_REFINEMENT_ATTEMPTS, stops early on score >= 3.5
        MAX_REFINEMENT_ATTEMPTS = 3
        feedback: Optional[str] = None
        enrichment_meta: dict = {}
        idea: Optional[IdeaSpec] = None
        attempt = 0
        for attempt in range(1, MAX_REFINEMENT_ATTEMPTS + 1):
            logger.info("[1/5] idea_hunter attempt=%d", attempt)
            idea = self._idea_hunter.generate(topic, feedback=feedback)
            tracker.record_step(cost_usd=0.01)
            logger.info("[1/5] done: idea.title=%r", idea.title)

            logger.info("[1.5/5] idea_enricher attempt=%d", attempt)
            idea, enrichment_meta = self._idea_enricher.enrich(idea)
            tracker.record_step(cost_usd=0.01)
            score = enrichment_meta["specificity_score"]
            logger.info(
                "[1.5/5] done: score=%.2f refined=%s research=%s",
                score,
                enrichment_meta["needs_refinement"],
                enrichment_meta.get("research_used", False),
            )

            if score >= 3.5:
                logger.info("specificity gate PASS at attempt=%d", attempt)
                break
            feedback = enrichment_meta.get("refinement_notes") or (
                "The idea remains too vague — quantify the problem with a "
                "specific number, narrow the market to a concrete ICP, and "
                "name a defensible mechanism."
            )
            logger.info("specificity gate FAIL at attempt=%d -> retry with feedback", attempt)
        enrichment_meta["attempts_used"] = attempt

        # Step 2 — ICP + value proposition
        logger.info("[2/5] idea_maturer")
        mature = self._idea_maturer.mature(idea)
        tracker.record_step(cost_usd=0.01)
        logger.info("[2/4] done: value_prop=%r", mature.value_proposition[:60])

        # Step 3 — Test design
        logger.info("[3/4] market_validator")
        test_design = self._market_validator.design_test(mature)
        tracker.record_step(cost_usd=0.01)
        logger.info("[3/4] done: budget=$%.0f duration=%dd", test_design.ad_budget_usd, test_design.test_duration_days)

        # Step 4a — Landing copy
        logger.info("[4a/4] landing_generator")
        landing = self._landing_generator.generate(mature)
        tracker.record_step(cost_usd=0.01)
        logger.info("[4a/4] done: headline=%r slug=%r", landing.headline[:40], landing.domain_slug)

        # Step 4b — Gate decision
        snapshot = metrics or MetricsSnapshot(
            impressions=0, clicks=0, conversions=0,
            cost_usd=0.0, ctr=0.0, conversion_rate=0.0, cost_per_conversion=0.0,
        )
        logger.info("[4b/4] gate_decider")
        decision = self._gate_decider.decide(mature, test_design, snapshot)
        tracker.record_step(cost_usd=0.01)
        logger.info("[4b/4] done: verdict=%s confidence=%.2f", decision.verdict.value, decision.confidence)

        run = EvidenceGateRun(
            run_id=run_id,
            topic=topic,
            started_at=started_at,
            idea=idea,
            mature_idea=mature,
            test_design=test_design,
            landing=landing,
            decision=decision,
            canonical_goal=goal,
            budget_tracker=tracker,
        )
        logger.info("EvidenceGate complete run_id=%s\n%s", run_id, run.summary())
        return run
