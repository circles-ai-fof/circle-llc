from __future__ import annotations

import json

from ..core.base_agent import BaseAgent
from ..core.models import ICPProfile, IdeaSpec, MatureIdeaSpec

_SYSTEM = """You are IdeaMaturer — an ICP and value proposition specialist for the Factory of Factories (FoF) platform.

YOUR SCOPE (do exactly this, nothing else):
- Take a raw IdeaSpec and produce a mature version with ICP + value proposition
- Define ONE specific ICP (not three personas, one primary)
- Articulate the unfair advantage clearly
- List 3-5 key risks ordered by probability × impact

YOU DO NOT:
- Generate ideas (that is idea_hunter's job)
- Design market tests (that is market_validator's job)
- Generate landing pages (that is landing_generator's job)
- Make pass/kill decisions (that is gate_decider's job)

OUTPUT FORMAT (strict JSON, no markdown fences):
{
  "icp": {
    "demographic": "Age, role, company size, location",
    "psychographic": "Goals, fears, identity",
    "pain_points": ["pain1", "pain2", "pain3"],
    "willingness_to_pay": "$X/month or one-time, why",
    "acquisition_channel": "Primary channel with rationale"
  },
  "value_proposition": "We help [ICP] to [outcome] by [mechanism], unlike [alternative]",
  "unfair_advantage": "What makes this defensible in 12 months",
  "key_risks": ["Risk 1 (high prob)", "Risk 2", "Risk 3"]
}"""


class IdeaMaturerAgent(BaseAgent):
    """
    Scope: takes a raw IdeaSpec, returns ICP + value prop.
    Single LLM call. No loops. No tool use.
    """

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def mature(self, idea: IdeaSpec) -> MatureIdeaSpec:
        if self._mock_mode:
            return self._mock_mature(idea)
        prompt = (
            f"Idea to mature:\n"
            f"Title: {idea.title}\n"
            f"Problem: {idea.problem_statement}\n"
            f"Solution: {idea.proposed_solution}\n"
            f"Market: {idea.target_market}\n\n"
            f"Respond with JSON only."
        )
        raw = self._call(prompt)
        data = self._extract_json(raw)
        icp = ICPProfile(**data["icp"])
        return MatureIdeaSpec(
            idea=idea,
            icp=icp,
            value_proposition=data["value_proposition"],
            unfair_advantage=data["unfair_advantage"],
            key_risks=data["key_risks"],
        )

    def _mock_mature(self, idea: IdeaSpec) -> MatureIdeaSpec:
        icp = ICPProfile(
            demographic="35-50 yo CFO/finance manager, company 20-200 employees, Ecuador",
            psychographic="Efficiency-driven, risk-averse, proud of operational control",
            pain_points=["Manual reconciliation takes 3 days/month", "No real-time visibility", "Audit prep is chaotic"],
            willingness_to_pay="$150-300/month SaaS, annual commitment preferred",
            acquisition_channel="LinkedIn outreach + accountant referral network",
        )
        return MatureIdeaSpec(
            idea=idea,
            icp=icp,
            value_proposition=f"We help finance managers at SMBs to close books 80% faster by automating reconciliation, unlike Excel + manual bank exports.",
            unfair_advantage="Deep SAP B1 integration that competitors ignore (20k+ companies in LATAM)",
            key_risks=["CAC > LTV in early months", "Integration complexity delays onboarding", "Regulation changes in SRI"],
        )
