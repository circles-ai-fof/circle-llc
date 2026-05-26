from __future__ import annotations

import json
import logging

from ..core.base_agent import BaseAgent
from ..core.models import (
    EvidenceTestDesign,
    GateDecision,
    GateVerdict,
    MatureIdeaSpec,
    MetricsSnapshot,
)

logger = logging.getLogger(__name__)

_SYSTEM = """You are GateDecider — the final judge in the Factory of Factories evidence-gate.

YOUR SCOPE (do exactly this, nothing else):
- Receive metrics + test design + idea context
- Evaluate whether metrics justify advancing to Sprint M1 build
- Return ONE of three verdicts: pass | kill | iterate
- Provide concrete, data-backed rationale

VERDICT RULES (apply in order):
1. AUTO-PASS: CTR >= target AND conversion_rate >= target AND cost_per_conversion <= budget/10
2. AUTO-KILL: impressions >= 1000 AND CTR < target/3 AND conversions == 0
3. BORDERLINE: everything else → use your judgment with explicit rationale

FOR BORDERLINE CASES, weigh:
- Signal quality (few impressions = low signal, many = high signal)
- Cost efficiency vs benchmark
- Qualitative signals (if provided)
- Market size vs cost structure

YOU DO NOT:
- Generate ideas, design tests, write copy — those are done
- Suggest architectural decisions — that is Sprint M1 scope

OUTPUT FORMAT (strict JSON, no markdown fences):
{
  "verdict": "pass|kill|iterate",
  "confidence": 0.0-1.0,
  "rationale": "2-3 sentence data-backed explanation",
  "key_evidence": ["evidence1", "evidence2"],
  "next_steps": ["step1", "step2", "step3"]
}"""


def _apply_code_rules(
    metrics: MetricsSnapshot,
    design: EvidenceTestDesign,
) -> tuple[GateVerdict | None, float, str]:
    """
    Deterministic code-based rules applied before LLM judge.
    Returns (verdict | None, confidence, rationale).
    None means borderline → escalate to LLM judge.
    """
    if (
        metrics.ctr >= design.target_ctr
        and metrics.conversion_rate >= design.target_conversion_rate
        and metrics.impressions >= 500
    ):
        return GateVerdict.PASS, 0.92, "All quantitative thresholds met with sufficient signal."

    if (
        metrics.impressions >= 1000
        and metrics.ctr < design.target_ctr / 3
        and metrics.conversions == 0
    ):
        return GateVerdict.KILL, 0.90, "No signal after 1000+ impressions. Market does not respond."

    return None, 0.0, ""


class GateDeciderAgent(BaseAgent):
    """
    Scope: evaluates evidence-gate metrics → pass/kill/iterate.
    Two-stage: code rules first, LLM judge only for borderline cases.
    Justification: code-based evals are cheap and fast (Cap 7).
    LLM judge only when code rules can't decide (Cap 8).
    """

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def decide(
        self,
        mature: MatureIdeaSpec,
        design: EvidenceTestDesign,
        metrics: MetricsSnapshot,
    ) -> GateDecision:
        if self._mock_mode:
            return self._mock_decide(mature, design, metrics)

        # Stage 1: code rules (fast, deterministic)
        code_verdict, confidence, code_rationale = _apply_code_rules(metrics, design)
        if code_verdict is not None:
            logger.info("gate_decider: code-rule verdict=%s confidence=%.2f", code_verdict, confidence)
            return GateDecision(
                verdict=code_verdict,
                confidence=confidence,
                rationale=code_rationale,
                key_evidence=[
                    f"CTR: {metrics.ctr:.1%} (target {design.target_ctr:.1%})",
                    f"CVR: {metrics.conversion_rate:.1%} (target {design.target_conversion_rate:.1%})",
                    f"Impressions: {metrics.impressions}",
                ],
                next_steps=_next_steps(code_verdict, mature),
                metrics=metrics,
            )

        # Stage 2: LLM judge for borderline cases
        logger.info("gate_decider: borderline → LLM judge")
        prompt = (
            f"Evaluate evidence-gate for: {mature.idea.title}\n\n"
            f"Test design:\n"
            f"  Hypothesis: {design.hypothesis}\n"
            f"  Target CTR: {design.target_ctr:.1%}\n"
            f"  Target CVR: {design.target_conversion_rate:.1%}\n"
            f"  Budget: ${design.ad_budget_usd}\n\n"
            f"Actual metrics:\n"
            f"  Impressions: {metrics.impressions}\n"
            f"  Clicks: {metrics.clicks}\n"
            f"  Conversions: {metrics.conversions}\n"
            f"  CTR: {metrics.ctr:.1%}\n"
            f"  CVR: {metrics.conversion_rate:.1%}\n"
            f"  Cost: ${metrics.cost_usd:.2f}\n"
            f"  CPC: ${metrics.cost_per_conversion:.2f}\n\n"
            f"Respond with JSON only."
        )
        raw = self._call(prompt)
        data = self._extract_json(raw)
        return GateDecision(
            verdict=GateVerdict(data["verdict"]),
            confidence=data["confidence"],
            rationale=data["rationale"],
            key_evidence=data["key_evidence"],
            next_steps=data["next_steps"],
            metrics=metrics,
        )

    def _mock_decide(
        self,
        mature: MatureIdeaSpec,
        design: EvidenceTestDesign,
        metrics: MetricsSnapshot,
    ) -> GateDecision:
        code_verdict, confidence, rationale = _apply_code_rules(metrics, design)
        verdict = code_verdict or GateVerdict.ITERATE
        confidence = confidence or 0.60
        rationale = rationale or "Borderline signal — insufficient impressions for confidence."
        return GateDecision(
            verdict=verdict,
            confidence=confidence,
            rationale=rationale,
            key_evidence=[
                f"CTR: {metrics.ctr:.1%} vs target {design.target_ctr:.1%}",
                f"CVR: {metrics.conversion_rate:.1%} vs target {design.target_conversion_rate:.1%}",
            ],
            next_steps=_next_steps(verdict, mature),
            metrics=metrics,
        )


def _next_steps(verdict: GateVerdict, mature: MatureIdeaSpec) -> list[str]:
    if verdict == GateVerdict.PASS:
        return [
            f"Advance '{mature.idea.title}' to Sprint M1 build phase",
            "Assign TechAgent to generate architecture blueprint",
            "Set Sprint M1 budget and timeline",
        ]
    if verdict == GateVerdict.KILL:
        return [
            f"Archive '{mature.idea.title}' in outcome-db with kill rationale",
            "Run idea_hunter on adjacent verticals",
            "Review ICP assumptions — channel may be wrong, not idea",
        ]
    return [
        "Adjust ad creative and headline (A/B test 2 variants)",
        "Extend test 7 more days with revised targeting",
        "Re-evaluate at $150 additional spend",
    ]
