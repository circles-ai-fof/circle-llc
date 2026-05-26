from __future__ import annotations

import json

from ..core.base_agent import BaseAgent
from ..core.models import EvidenceTestDesign, MatureIdeaSpec

_SYSTEM = """You are MarketValidator — an evidence-gate test designer for the Factory of Factories (FoF) platform.

YOUR SCOPE (do exactly this, nothing else):
- Design ONE minimum viable market test (landing + ads)
- Set quantitative pass/fail thresholds based on vertical benchmarks
- Duration: 7-30 days. Budget: $50-$2000 USD.
- Use conversion rate benchmarks: SaaS 2-5%, Marketplace 1-3%, Community 5-10%

YOU DO NOT:
- Generate ideas (idea_hunter's job)
- Define ICP (idea_maturer's job)
- Build the landing page (landing_generator's job)
- Make the final pass/kill call (gate_decider's job)

OUTPUT FORMAT (strict JSON, no markdown fences):
{
  "hypothesis": "If we show [ICP] a landing about [value_prop], then [X]% will convert because [reason]",
  "success_metrics": ["CTR > 2%", "Conversion > 3%", "CPC < $2"],
  "failure_metrics": ["CTR < 0.5%", "0 conversions after $200 spend"],
  "test_duration_days": 14,
  "ad_budget_usd": 300,
  "target_ctr": 0.02,
  "target_conversion_rate": 0.03
}"""


class MarketValidatorAgent(BaseAgent):
    """
    Scope: designs the evidence-gate test parameters given a mature idea.
    Single LLM call. No loops. No tool use.
    """

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def design_test(self, mature: MatureIdeaSpec) -> EvidenceTestDesign:
        if self._mock_mode:
            return self._mock_design_test(mature)
        prompt = (
            f"Design a market test for:\n"
            f"Idea: {mature.idea.title}\n"
            f"Value prop: {mature.value_proposition}\n"
            f"ICP: {mature.icp.demographic}\n"
            f"Channel: {mature.icp.acquisition_channel}\n"
            f"Vertical: {mature.idea.vertical_category.value}\n\n"
            f"Respond with JSON only."
        )
        raw = self._call(prompt)
        data = self._extract_json(raw)
        return EvidenceTestDesign(**data)

    def _mock_design_test(self, mature: MatureIdeaSpec) -> EvidenceTestDesign:
        return EvidenceTestDesign(
            hypothesis=(
                f"If we show finance managers a landing about '{mature.idea.title}', "
                "then 3% will sign up for a demo because the pain (3-day close) is urgent."
            ),
            success_metrics=["CTR > 2%", "Conversion > 3%", "CPC < $2.50"],
            failure_metrics=["CTR < 0.5% after 1000 impressions", "0 conversions after $150 spend"],
            test_duration_days=14,
            ad_budget_usd=300.0,
            target_ctr=0.02,
            target_conversion_rate=0.03,
        )
