"""
EventRelevanceScorer — M5.3 — agente experimental para decidir a qué ferias/
congresos vale la pena ir (signals kind=events de M4.13).

Founder del audio: "ir a Las Vegas a sacar oportunidades reales. Pero ya
te metes en otras ligas. Simplemente le metes otros ceros y con esa gente
simplemente vas navegando por otras oportunidades."

Scope:
- Input: event signal (theme, excerpt, evidence_urls, source) + opcional
  industry_focus del founder
- Output: EventScoring con go/skip/send_someone_else + razones

Status: experimental (M5.3). 10/30 golden cases.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from ..core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


_SYSTEM = """You are EventRelevanceScorer — un agente que decide si una
feria/congreso vale el costo de ir.

ALCANCE:
- Recibís: titulo+resumen del evento + URLs + opcional industry_focus del
  founder (ej: "fintech LATAM", "agtech", "AI infrastructure")
- Tu trabajo: scorear relevance + sugerir go/skip/send_someone_else +
  razones

PRINCIPIOS:
- Founder es CEO de FoF (Factory of Factories). Sus restricciones:
  · Tiempo limitado — no puede ir a 50 eventos/año
  · Presupuesto limitado — eventos en LATAM ~$500-2000, USA $1500-5000+
  · ROI debe ser claro — networking, deals, learning, brand
- "go" si: industry exacta + speakers/sponsors reputados + 200+ asistentes
  relevantes + ROI esperado > 5x el costo del evento
- "send_someone_else" si: industry tangente pero hay valor de scouting
- "skip" si: poco overlap con FoF, demasiado generalista, o costo desproporcionado

FORMATO (JSON estricto, sin markdown):
{
  "relevance_score": 0.0-1.0,
  "expected_attendees_profile": "string — quiénes van típicamente",
  "networking_value": "string — alto/medio/bajo + por qué",
  "learning_value": "string — alto/medio/bajo + por qué",
  "estimated_cost_usd": "string — rango USD incluyendo travel ej '$2000-3500'",
  "expected_roi": "string — cualitativo: '1 lead pago paga el viaje', '5-10 contactos clave', etc.",
  "recommendation": "go" | "skip" | "send_someone_else",
  "preparation_topics": ["topic 1", "topic 2"],
  "reasoning": "string — 2-3 frases con TU lógica"
}

REGLAS:
- Español neutro LATAM
- relevance_score honesta: si no sabés del evento, score ≤ 0.5
- preparation_topics solo si recommendation=go o send_someone_else
"""


@dataclass
class EventScoring:
    relevance_score: float = 0.5
    expected_attendees_profile: str = ""
    networking_value: str = ""
    learning_value: str = ""
    estimated_cost_usd: str = ""
    expected_roi: str = ""
    recommendation: str = "skip"  # go | skip | send_someone_else
    preparation_topics: List[str] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class EventRelevanceScorerAgent(BaseAgent):
    """Status: experimental (M5.3). 10/30 golden cases."""

    AGENT_NAME = "event_relevance_scorer"
    AGENT_VERSION = "0.1.0"
    EXPERIMENTAL = True

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def analyze(
        self,
        event_title: str,
        event_description: str = "",
        evidence_urls: Optional[List[str]] = None,
        industry_focus: str = "",
    ) -> EventScoring:
        if self._mock_mode:
            return self._mock_analyze(event_title, event_description, industry_focus)
        prompt = self._build_prompt(event_title, event_description, evidence_urls or [], industry_focus)
        raw = self._call(prompt)
        data = self._extract_json(raw)
        return EventScoring(
            relevance_score=float(data.get("relevance_score", 0.5)),
            expected_attendees_profile=str(data.get("expected_attendees_profile", "")),
            networking_value=str(data.get("networking_value", "")),
            learning_value=str(data.get("learning_value", "")),
            estimated_cost_usd=str(data.get("estimated_cost_usd", "")),
            expected_roi=str(data.get("expected_roi", "")),
            recommendation=str(data.get("recommendation", "skip")),
            preparation_topics=list(data.get("preparation_topics", []) or []),
            reasoning=str(data.get("reasoning", "")),
        )

    def _build_prompt(
        self, event_title: str, event_description: str,
        evidence_urls: List[str], industry_focus: str,
    ) -> str:
        urls_block = "\n".join(f"  - {u}" for u in evidence_urls[:3]) or "  (sin URLs)"
        focus_line = f"\nIndustry focus del founder: {industry_focus}" if industry_focus else ""
        return (
            f"Evento detectado por el cazador:\n\n"
            f"Título: {event_title}\n"
            f"Descripción: {event_description[:500]}\n"
            f"URLs:\n{urls_block}{focus_line}\n\n"
            f"Devuelve el JSON con tu scoring + recomendación."
        )

    def _mock_analyze(
        self, event_title: str, event_description: str, industry_focus: str,
    ) -> EventScoring:
        text = f"{event_title} {event_description}".lower()
        # Heurística mock: keywords sugieren go/skip
        GO_KEYWORDS = ["fintech", "ai", "saas", "y combinator", "summit",
                       "disrupt", "money 20/20", "techcrunch", "web summit"]
        SEND_KEYWORDS = ["latam", "regional", "expo", "feria"]
        score = 0.4
        rec = "skip"
        for kw in GO_KEYWORDS:
            if kw in text:
                score = 0.78
                rec = "go"
                break
        if rec == "skip":
            for kw in SEND_KEYWORDS:
                if kw in text:
                    score = 0.58
                    rec = "send_someone_else"
                    break
        # Si industry_focus está set y matchea, boost
        if industry_focus and industry_focus.lower() in text:
            score = min(score + 0.15, 0.92)
            if rec == "skip":
                rec = "send_someone_else"

        prep = [
            f"[Demo] Llevar 1-pager de FoF en español + inglés",
            f"[Demo] Lista de 10 personas con las que querés tomar café",
        ] if rec != "skip" else []

        return EventScoring(
            relevance_score=round(score, 2),
            expected_attendees_profile=(
                "[Demo] Founders, VCs early-stage, y angel investors del sector"
                if rec == "go" else
                "[Demo] Profesionales mid-level del sector — útil para scouting"
            ),
            networking_value="[Demo] Alto" if rec == "go" else "[Demo] Medio",
            learning_value="[Demo] Medio — el valor real son los pasillos, no los talks",
            estimated_cost_usd=(
                "[Demo] $2000-3500 incl. flight + hotel + ticket"
                if "vegas" in text or "usa" in text else
                "[Demo] $400-1200 (LATAM)"
            ),
            expected_roi=(
                "[Demo] 5-10 contactos calificados + 1-2 deals exploratorios"
                if rec == "go" else
                "[Demo] 2-3 contactos secundarios + insight de mercado"
            ),
            recommendation=rec,
            preparation_topics=prep,
            reasoning=(
                f"[Demo] Decisión '{rec}' basada en keywords del título y "
                f"{'match' if industry_focus and industry_focus.lower() in text else 'sin match'} "
                f"con industry_focus."
            ),
        )
