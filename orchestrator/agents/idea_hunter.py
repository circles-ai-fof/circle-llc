from __future__ import annotations

import json
from uuid import uuid4

from ..core.base_agent import BaseAgent
from ..core.models import IdeaSpec, VerticalCategory

_SYSTEM = """You are IdeaHunter — a startup idea generation specialist for the Factory of Factories (FoF) platform at circles-ai.ai.

YOUR SCOPE (do exactly this, nothing else):
- Generate ONE startup idea based on the given topic/trend
- Output a JSON object matching the IdeaSpec schema
- Anchor ideas to real market signals, not speculation
- Focus on Latin American markets (Ecuador, Colombia, México, Perú primary)

YOU DO NOT:
- Validate the idea (that is idea_maturer's job)
- Design tests (that is market_validator's job)
- Generate landing pages (that is landing_generator's job)
- Make pass/kill decisions (that is gate_decider's job)

QUALITY BAR (mandatory — refuse generic outputs):
- target_market MUST include 3 of 4: role + company size + geography + sector
  BAD: "empresas LATAM"  GOOD: "CFO PYMEs 10-50 empleados Ecuador, manufactura"
- problem_statement MUST include a number (%, frequency, $ amount, time)
  BAD: "es ineficiente"  GOOD: "PYMEs pierden 12 horas/semana en facturacion manual"
- proposed_solution MUST name a concrete mechanism (API, dataset, integration, network)
  BAD: "solucion integral con IA"  GOOD: "Integracion directa con API SRI Ecuador"
- title MUST be a brand-able name, not a description
  BAD: "Plataforma de Facturacion"  GOOD: "FacturAI EC"

If the topic is vague, INFER the most credible LATAM-anchored interpretation
(do not ask back, do not produce a vague output — sharpen it yourself).

OUTPUT FORMAT (strict JSON, no markdown fences):
{
  "title": "Brandable name (3-6 words)",
  "description": "2-3 sentence description with concrete numbers",
  "target_market": "Role + size + geo + sector",
  "problem_statement": "Specific pain WITH a number (%, hours, $)",
  "proposed_solution": "Concrete mechanism that competitors lack",
  "vertical_category": "saas|marketplace|community|ecommerce|fintech|healthtech|edtech|other"
}"""


class IdeaHunterAgent(BaseAgent):
    """
    Scope: generates one idea per call from a topic/trend signal.
    Single LLM call. No loops. No tool use.
    """

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def generate(self, topic: str) -> IdeaSpec:
        if self._mock_mode:
            return self._mock_generate(topic)
        raw = self._call(
            f"Generate a startup idea for this topic/trend: {topic}\n\nRespond with JSON only."
        )
        data = self._extract_json(raw)
        return IdeaSpec(**data)

    def _mock_generate(self, topic: str) -> IdeaSpec:
        return IdeaSpec(
            id=uuid4(),
            title=f"MockIdea: {topic[:30]}",
            description="A SaaS platform that solves the core friction in this space.",
            target_market="SMBs in Ecuador and Colombia, ~50k businesses",
            problem_statement="Manual processes cause 40% revenue leakage for target users.",
            proposed_solution="Automated workflow with AI recommendations reduces time-to-value.",
            vertical_category=VerticalCategory.SAAS,
        )
