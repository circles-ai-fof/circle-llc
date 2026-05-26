"""
IdeaEnricher — refines vague ideas into specific, testable hypotheses.

Position: between idea_hunter and idea_maturer.
Justification: Reganti Cap 5 §5.3 — "vague inputs produce vague outputs.
Refine specificity BEFORE expensive downstream steps."

This agent:
1. Scores the idea's specificity (1-5) on 4 dimensions
2. If specificity >= 3.5 → passes through unchanged
3. If specificity < 3.5 → asks clarifying questions and produces a sharpened IdeaSpec
"""
from __future__ import annotations

import logging
from uuid import uuid4

from ..core.base_agent import BaseAgent
from ..core.models import IdeaSpec, VerticalCategory

logger = logging.getLogger(__name__)

_SYSTEM = """You are IdeaEnricher — a specificity gatekeeper for the Factory of Factories.

YOUR SCOPE (do exactly this, nothing else):
- Score the input idea's specificity on 4 dimensions (1-5 each)
- If overall >= 3.5: return the idea UNCHANGED (with score)
- If overall < 3.5: SHARPEN it into a specific, testable hypothesis
- Use grounded heuristics about LATAM markets when sharpening

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
- Replace vague verbs ("manejar", "gestionar") with concrete actions ("publicar 3 articulos/dia")
- Replace generic markets with specific ICP (role + geo + size)
- Add 1-2 concrete numbers (TAM estimate, time saved, % conversion)
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


class IdeaEnricherAgent(BaseAgent):
    """
    Scope: takes a raw IdeaSpec, returns a sharpened IdeaSpec.
    Single LLM call. No loops. No tool use.
    """

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def enrich(self, idea: IdeaSpec) -> tuple[IdeaSpec, dict]:
        """
        Returns (refined_idea, metadata).
        Metadata contains: specificity_score, needs_refinement, refinement_notes.
        """
        if self._mock_mode:
            return self._mock_enrich(idea)

        prompt = (
            f"Score and (if needed) sharpen this idea:\n"
            f"Title: {idea.title}\n"
            f"Description: {idea.description}\n"
            f"Problem: {idea.problem_statement}\n"
            f"Solution: {idea.proposed_solution}\n"
            f"Market: {idea.target_market}\n"
            f"Category: {idea.vertical_category.value}\n\n"
            f"Respond with JSON only."
        )
        raw = self._call(prompt)
        data = self._extract_json(raw)

        refined = IdeaSpec(
            id=idea.id,  # preserve original id
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
        metadata = {
            "specificity_score": float(data.get("specificity_score", 0)),
            "needs_refinement": bool(data.get("needs_refinement", False)),
            "refinement_notes": data.get("refinement_notes", ""),
        }
        logger.info(
            "idea_enricher: score=%.2f refined=%s notes=%s",
            metadata["specificity_score"],
            metadata["needs_refinement"],
            metadata["refinement_notes"][:80] if metadata["refinement_notes"] else "(none)",
        )
        return refined, metadata

    def _mock_enrich(self, idea: IdeaSpec) -> tuple[IdeaSpec, dict]:
        # Deterministic: detects vague keywords and sharpens
        vague_terms = ["manejar", "gestionar", "solucion", "plataforma para", "todas las empresas"]
        text = (idea.problem_statement + " " + idea.target_market).lower()
        is_vague = any(t in text for t in vague_terms)
        if not is_vague:
            return idea, {
                "specificity_score": 4.2,
                "needs_refinement": False,
                "refinement_notes": "none",
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
        }
