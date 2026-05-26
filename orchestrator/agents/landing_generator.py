from __future__ import annotations

import json
import re

from ..core.base_agent import BaseAgent
from ..core.models import LandingSpec, MatureIdeaSpec

_SYSTEM = """You are LandingGenerator — a conversion copywriter for the Factory of Factories (FoF) platform.

YOUR SCOPE (do exactly this, nothing else):
- Write landing page copy optimized for the evidence-gate test
- Headline: benefit-driven, max 80 chars
- Subheadline: clarifies who it's for, max 160 chars
- 3-5 value props (bullet points, concrete outcomes)
- CTA: action verb + outcome, max 40 chars
- Social proof: one believable data point or testimonial stub
- domain_slug: URL-safe slug (lowercase, hyphens only)

COPYWRITING RULES:
- Lead with the outcome, not the feature
- Use specific numbers when possible ("Save 3 hours/week" not "Save time")
- Mirror the ICP's language from the value proposition
- Spanish if the market is LATAM, English if global/US

YOU DO NOT:
- Build the actual HTML (that is a tool's job)
- Design tests (market_validator's job)
- Evaluate metrics (gate_decider's job)

OUTPUT FORMAT (strict JSON, no markdown fences):
{
  "headline": "...",
  "subheadline": "...",
  "value_props": ["Outcome 1", "Outcome 2", "Outcome 3"],
  "cta_text": "Get early access",
  "social_proof": "...",
  "domain_slug": "product-name"
}"""

_VALIDATE_SLUG_TOOL = {
    "name": "validate_domain_slug",
    "description": "Checks if a slug is URL-safe (lowercase letters, numbers, hyphens only, 3-50 chars). Returns {valid: bool, suggestion: str}.",
    "input_schema": {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "The slug to validate"}
        },
        "required": ["slug"],
    },
}


def _validate_slug(slug: str) -> dict:
    pattern = r"^[a-z0-9][a-z0-9\-]{1,48}[a-z0-9]$"
    valid = bool(re.match(pattern, slug))
    suggestion = re.sub(r"[^a-z0-9\-]", "", slug.lower().replace(" ", "-"))[:50]
    return {"valid": valid, "suggestion": suggestion}


class LandingGeneratorAgent(BaseAgent):
    """
    Scope: generates landing page copy for the evidence-gate.
    Uses tool use for domain slug validation (the one explicit tool in the workflow).
    """

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def generate(self, mature: MatureIdeaSpec) -> LandingSpec:
        if self._mock_mode:
            return self._mock_generate(mature)

        prompt = (
            f"Write landing copy for:\n"
            f"Product: {mature.idea.title}\n"
            f"Value prop: {mature.value_proposition}\n"
            f"ICP: {mature.icp.demographic}\n"
            f"Pain: {', '.join(mature.icp.pain_points[:2])}\n"
            f"Market: {mature.idea.target_market}\n\n"
            f"Use the validate_domain_slug tool to confirm your slug is URL-safe.\n"
            f"Then respond with JSON only."
        )

        # First call with tool available
        response = self._call_with_tools(prompt, tools=[_VALIDATE_SLUG_TOOL])

        # Handle tool use if the model called validate_domain_slug
        final_text = ""
        if response.stop_reason == "tool_use":
            tool_block = next(b for b in response.content if b.type == "tool_use")
            slug = tool_block.input.get("slug", "")
            validation_result = _validate_slug(slug)

            # Feed tool result back
            messages = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response.content},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": json.dumps(validation_result),
                        }
                    ],
                },
            ]
            final_response = self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=[{"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}}],
                tools=[_VALIDATE_SLUG_TOOL],
                messages=messages,
            )
            final_text = next(b.text for b in final_response.content if hasattr(b, "text"))
        else:
            final_text = next(b.text for b in response.content if hasattr(b, "text"))

        data = self._extract_json(final_text)
        return LandingSpec(**data)

    def _mock_generate(self, mature: MatureIdeaSpec) -> LandingSpec:
        slug = re.sub(r"[^a-z0-9\-]", "", mature.idea.title.lower().replace(" ", "-"))[:30].strip("-")
        return LandingSpec(
            headline="Cierra tus libros en 1 día, no en 3",
            subheadline="Para gerentes financieros de PYMEs en Ecuador que usan SAP B1",
            value_props=[
                "Reconciliación automática: 3 horas → 15 minutos",
                "Integración nativa SAP B1 sin código",
                "Reportes SRI listos para auditoría con 1 clic",
            ],
            cta_text="Solicita tu demo gratis",
            social_proof="12 empresas en beta — tiempo de cierre promedio: 1.2 días",
            domain_slug=slug or "fof-idea",
        )
