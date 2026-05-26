"""
IdeaEnricher — refines vague ideas into specific, testable hypotheses.

Position: between idea_hunter and idea_maturer.
Justification: Reganti Cap 5 §5.3 — "vague inputs produce vague outputs.
Refine specificity BEFORE expensive downstream steps."

This agent:
1. Scores the idea's specificity (1-5) on 4 dimensions
2. If specificity >= 3.5 → passes through unchanged
3. If specificity < 3.5 → sharpens it into a specific, testable hypothesis

M1.6 additions:
- Opt-in web_search tool-use (ADR-006) when IDEA_ENRICHER_RESEARCH=true
- Cross-LLM fact-check on numerical claims (ADR-008) when FACT_CHECK_ENABLED=true
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from ..core.base_agent import BaseAgent
from ..core.fact_checker import (
    FactCheckResult,
    count_unsupported,
    fact_check_claims,
    fact_check_enabled,
)
from ..core.models import IdeaSpec, VerticalCategory

logger = logging.getLogger(__name__)

_SYSTEM = """You are IdeaEnricher — a specificity gatekeeper for the Factory of Factories.

YOUR SCOPE (do exactly this, nothing else):
- Score the input idea's specificity on 4 dimensions (1-5 each)
- If overall >= 3.5: return the idea UNCHANGED (with score)
- If overall < 3.5: SHARPEN it into a specific, testable hypothesis
- Use grounded heuristics about LATAM markets when sharpening
- When web_search tool is available, USE IT to ground numerical claims
  in real market data — competitors, regulations, market-size estimates.
  Prefer 2 well-grounded numbers over 5 hallucinated ones.

SPECIFICITY DIMENSIONS (score 1-5 each):
1. Problem Quantification: Does the problem state numbers, frequency, severity?
   5 = "60% PYMEs Ecuador esperan 90+ dias cobrar facturas"
   1 = "empresas necesitan eficiencia"

2. Market Targetability: role + size + geography + sector?
   5 = "CFO PYME 10-50 empleados Ecuador manufactura"
   1 = "todas las empresas"

3. Solution Differentiation: explicit mechanism that competitors lack?
   5 = "Integracion directa API SRI Ecuador unico en mercado"
   1 = "solucion integral con IA"

4. Unfair Advantage: defensible moat in 12 months?
   5 = "Acceso exclusivo a 50k pacientes IESS via partnership"
   1 = "equipo experto"

WHEN SHARPENING:
- Replace vague verbs ("manejar", "gestionar") with concrete actions
- Replace generic markets with specific ICP (role + geo + size)
- Add 1-2 concrete numbers (TAM, time saved, % conversion)
- Use RANGES if uncertain ("30-50%") rather than false precision ("47.3%")
- Keep the original intent — do NOT pivot the idea

OUTPUT FORMAT (strict JSON, no markdown fences):
{
  "specificity_score": 1.0-5.0,
  "needs_refinement": true|false,
  "title": "Short memorable name (3-6 words)",
  "description": "2-3 sentence description (refined if needed)",
  "target_market": "Specific segment with role+size+geo+sector",
  "problem_statement": "The specific pain in one sentence WITH numbers",
  "proposed_solution": "How the product solves it WITH concrete mechanism",
  "vertical_category": "saas|marketplace|community|ecommerce|fintech|healthtech|edtech|other",
  "refinement_notes": "What was sharpened (or 'none' if score >= 3.5)"
}"""


def _research_enabled() -> bool:
    return (
        os.getenv("IDEA_ENRICHER_RESEARCH", "false").lower() in {"true", "1", "yes"}
        and bool(os.getenv("ANTHROPIC_API_KEY"))
    )


class IdeaEnricherAgent(BaseAgent):
    """
    Scope: takes a raw IdeaSpec, returns a sharpened IdeaSpec.
    Single LLM call by default. Opt-in tool-use + fact-check (M1.6).
    """

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def enrich(self, idea: IdeaSpec) -> tuple[IdeaSpec, dict]:
        """
        Returns (refined_idea, metadata).
        Metadata: specificity_score, needs_refinement, refinement_notes,
                  research_used, fact_check_results.
        """
        if self._mock_mode:
            return self._mock_enrich(idea)

        if _research_enabled():
            refined, meta = self._enrich_with_research(idea)
        else:
            refined, meta = self._enrich_parametric(idea)

        # ADR-008: fact-check numerical claims in the refined output
        fc_results: list[FactCheckResult] = []
        if fact_check_enabled():
            combined_text = (
                f"{refined.problem_statement}. {refined.proposed_solution}"
            )
            fc_results = fact_check_claims(combined_text, mock_mode=False)
            unsupported = count_unsupported(fc_results)
            if unsupported > 0:
                # Each UNSUPPORTED claim lowers score by 0.5 (cap floor at 0)
                meta["specificity_score"] = max(
                    0.0, meta["specificity_score"] - 0.5 * unsupported
                )
                meta["needs_refinement"] = meta["specificity_score"] < 3.5
                logger.warning(
                    "idea_enricher: %d UNSUPPORTED claim(s) -> score dropped to %.2f",
                    unsupported,
                    meta["specificity_score"],
                )

        meta["research_used"] = _research_enabled()
        meta["fact_check_results"] = [
            {
                "claim": fc.claim.text,
                "verdict": fc.verdict,
                "rationale": fc.rationale,
                "checker": fc.checker_model,
            }
            for fc in fc_results
        ]

        logger.info(
            "idea_enricher: score=%.2f refined=%s research=%s fact_checks=%d",
            meta["specificity_score"],
            meta["needs_refinement"],
            meta["research_used"],
            len(fc_results),
        )
        return refined, meta

    # ------------------------------------------------------------------ #
    # Internal paths                                                     #
    # ------------------------------------------------------------------ #

    def _enrich_parametric(self, idea: IdeaSpec) -> tuple[IdeaSpec, dict]:
        """Single LLM call, no web search. The M1.5 path."""
        prompt = self._build_prompt(idea)
        raw = self._call(prompt)
        data = self._extract_json(raw)
        return self._unpack(idea, data)

    def _enrich_with_research(self, idea: IdeaSpec) -> tuple[IdeaSpec, dict]:
        """
        Tool-use loop with Anthropic's native web_search (ADR-006).
        Falls back to parametric if the tool errors.
        """
        try:
            user_msg = self._build_prompt(idea) + (
                "\n\nIMPORTANT: Use web_search to verify any numerical claims "
                "(competitors, market size, regulations) before stating them. "
                "Then output ONLY the JSON, no commentary."
            )
            tools = [
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 3,
                }
            ]
            messages = [{"role": "user", "content": user_msg}]
            # Tool-use loop: keep responding until the model emits a final text block
            for _hop in range(4):  # hard cap on hops
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=[
                        {
                            "type": "text",
                            "text": self.system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    tools=tools,
                    messages=messages,
                )
                if response.stop_reason == "tool_use":
                    # Append assistant turn + tool_result placeholder (server handles search)
                    messages.append({"role": "assistant", "content": response.content})
                    # web_search_20250305 is a SERVER tool: results come back inline,
                    # the next .create() call will see them. We just continue the loop.
                    messages.append(
                        {
                            "role": "user",
                            "content": "(tool result returned by server — proceed)",
                        }
                    )
                    continue
                # Final text block
                final_text = next(
                    (b.text for b in response.content if hasattr(b, "text")),
                    "",
                )
                if final_text:
                    data = self._extract_json(final_text)
                    refined, meta = self._unpack(idea, data)
                    return refined, meta
                break  # no text content - fall through
            logger.warning("idea_enricher: tool-use loop exhausted without final JSON")
        except Exception as e:  # noqa: BLE001
            logger.warning("idea_enricher: web_search path failed (%s) -> parametric", e)
        # Fallback
        return self._enrich_parametric(idea)

    def _build_prompt(self, idea: IdeaSpec) -> str:
        return (
            f"Score and (if needed) sharpen this idea:\n"
            f"Title: {idea.title}\n"
            f"Description: {idea.description}\n"
            f"Problem: {idea.problem_statement}\n"
            f"Solution: {idea.proposed_solution}\n"
            f"Market: {idea.target_market}\n"
            f"Category: {idea.vertical_category.value}\n\n"
            f"Respond with JSON only."
        )

    def _unpack(self, idea: IdeaSpec, data: dict) -> tuple[IdeaSpec, dict]:
        refined = IdeaSpec(
            id=idea.id,
            title=data.get("title", idea.title),
            description=data.get("description", idea.description),
            target_market=data.get("target_market", idea.target_market),
            problem_statement=data.get("problem_statement", idea.problem_statement),
            proposed_solution=data.get("proposed_solution", idea.proposed_solution),
            vertical_category=VerticalCategory(
                data.get("vertical_category", idea.vertical_category.value)
            ),
            created_at=idea.created_at,
        )
        meta = {
            "specificity_score": float(data.get("specificity_score", 0)),
            "needs_refinement": bool(data.get("needs_refinement", False)),
            "refinement_notes": data.get("refinement_notes", ""),
        }
        return refined, meta

    def _mock_enrich(self, idea: IdeaSpec) -> tuple[IdeaSpec, dict]:
        # Deterministic: detects vague keywords and sharpens
        vague_terms = [
            "manejar",
            "gestionar",
            "solucion",
            "plataforma para",
            "todas las empresas",
        ]
        text = (idea.problem_statement + " " + idea.target_market).lower()
        is_vague = any(t in text for t in vague_terms)
        if not is_vague:
            return idea, {
                "specificity_score": 4.2,
                "needs_refinement": False,
                "refinement_notes": "none",
                "research_used": False,
                "fact_check_results": [],
            }
        # Sharpen
        refined = IdeaSpec(
            id=idea.id,
            title=idea.title,
            description=idea.description,
            target_market="PYMEs 10-50 empleados, Ecuador, sector tecnologia",
            problem_statement=f"{idea.problem_statement} (afecta a ~30% del mercado objetivo)",
            proposed_solution=f"{idea.proposed_solution} (con API integrada y reportes en tiempo real)",
            vertical_category=idea.vertical_category,
            created_at=idea.created_at,
        )
        return refined, {
            "specificity_score": 2.8,
            "needs_refinement": True,
            "refinement_notes": "Added geo+size to market, quantified problem, specified mechanism",
            "research_used": False,
            "fact_check_results": [],
        }
