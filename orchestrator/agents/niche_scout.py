"""
NicheScout — M5.2 — agente experimental que razona sobre las "migajas"
detectadas heurísticamente por M4.15 (niche_opportunities).

Scope:
- Input: NicheOpportunity (parent_market, parent_size, leader_niche,
  underexplored_niches) producido por GET /api/v1/niche-opportunities
- Output: NicheEntryPlan con plan de entrada al sub-niche más atractivo

Status: experimental (M5.2). Per R12, 10 golden cases mínimos. Promoción
a active(on-demand) requiere ≥30 cases (M5.x posterior).
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import List

from ..core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


_SYSTEM = """You are NicheScout — un agente que razona sobre sub-niches
sub-explorados dentro de mercados gigantes (las "migajas" del audio del
founder: "recoger las migajas de donde están los gigantes").

ALCANCE:
- Recibís un NicheOpportunity: parent_market (gigante), su líder, y los
  sub-niches sub-explorados (≤3 señales cada uno)
- Tu trabajo: razonar qué sub-niche atacar primero, por qué tiene espacio,
  y cómo entrar

PRINCIPIOS:
- El líder del gigante YA TIENE producto-market fit en su sub-niche.
  No competir con él directamente; flanquear con un sub-niche que él no
  prioriza por size.
- Buscar sub-niches con (a) ICP suficientemente distinto del líder,
  (b) demanda demostrada (al menos hay 1-2 signals), (c) gap que un
  founder pequeño puede llenar antes que el líder.
- Realismo: NO inventes TAM en USD. Sé cualitativo ("nicho pequeño pero
  defendible", "subset del mercado del líder").

FORMATO (JSON estricto, sin markdown):
{
  "target_subniche": "string — el topic completo del sub-niche elegido",
  "entry_thesis": "string — 2-3 frases: por qué este sub-niche tiene espacio
                   frente al líder, qué le perdona el líder",
  "competitive_advantage": "string — diferenciador realista frente al líder",
  "minimum_viable_offer": "string — qué lanzar primero (NO el producto
                          completo, solo el MVP testeable en 2-4 semanas)",
  "validation_metrics": ["metric 1", "metric 2", "metric 3"],
  "estimated_capture_pct": "string — ej: '5-10% del parent', 'micro-segmento <2%'",
  "key_risks": ["risk 1", "risk 2"],
  "confidence": 0.0-1.0,
  "reasoning": "string — 2-3 frases resumiendo TU lógica"
}

REGLAS:
- Español neutro LATAM
- Confidence ≤ 0.85 (siempre hay incertidumbre con sub-niches)
- Si hay 0 underexplored_niches en el input, devolvé target_subniche=""
  con confidence=0
"""


@dataclass
class NicheEntryPlan:
    target_subniche: str = ""
    entry_thesis: str = ""
    competitive_advantage: str = ""
    minimum_viable_offer: str = ""
    validation_metrics: List[str] = field(default_factory=list)
    estimated_capture_pct: str = ""
    key_risks: List[str] = field(default_factory=list)
    confidence: float = 0.5
    reasoning: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class NicheScoutAgent(BaseAgent):
    """Status: experimental (M5.2). 10/30 golden cases."""

    AGENT_NAME = "niche_scout"
    AGENT_VERSION = "0.1.0"
    EXPERIMENTAL = True

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def analyze(
        self,
        parent_market: str,
        parent_size: int,
        leader_niche: dict,
        underexplored_niches: List[dict],
    ) -> NicheEntryPlan:
        if not underexplored_niches:
            return NicheEntryPlan(confidence=0.0, reasoning="No hay sub-niches sub-explorados.")
        if self._mock_mode:
            return self._mock_analyze(parent_market, parent_size, leader_niche, underexplored_niches)
        prompt = self._build_prompt(parent_market, parent_size, leader_niche, underexplored_niches)
        raw = self._call(prompt)
        data = self._extract_json(raw)
        return NicheEntryPlan(
            target_subniche=str(data.get("target_subniche", "")),
            entry_thesis=str(data.get("entry_thesis", "")),
            competitive_advantage=str(data.get("competitive_advantage", "")),
            minimum_viable_offer=str(data.get("minimum_viable_offer", "")),
            validation_metrics=list(data.get("validation_metrics", []) or []),
            estimated_capture_pct=str(data.get("estimated_capture_pct", "")),
            key_risks=list(data.get("key_risks", []) or []),
            confidence=float(data.get("confidence", 0.5)),
            reasoning=str(data.get("reasoning", "")),
        )

    def _build_prompt(
        self, parent_market: str, parent_size: int,
        leader_niche: dict, underexplored_niches: List[dict],
    ) -> str:
        leader_text = (
            f"  topic: {leader_niche.get('topic', '?')}\n"
            f"  signals: {leader_niche.get('signals', 0)}\n"
            f"  ejemplos: {'; '.join(leader_niche.get('sample_themes', [])[:2])}"
        )
        sub_blocks = []
        for n in underexplored_niches[:5]:
            sub_blocks.append(
                f"  - {n.get('topic', '?')} (signals={n.get('signals', 0)})"
            )
        return (
            f"Mercado gigante: {parent_market} ({parent_size} señales totales)\n\n"
            f"Líder del gigante (alta competencia):\n{leader_text}\n\n"
            f"Sub-niches sub-explorados (las migajas):\n"
            + "\n".join(sub_blocks) + "\n\n"
            f"Devuelve el JSON con tu plan de entrada al MEJOR sub-niche."
        )

    def _mock_analyze(
        self, parent_market: str, parent_size: int,
        leader_niche: dict, underexplored_niches: List[dict],
    ) -> NicheEntryPlan:
        # Heurística mock: elegir el primer underexplored (menos signals)
        target = underexplored_niches[0]
        target_topic = target.get("topic", "")
        # Confidence baja si parent muy chiquito, sube si grande
        if parent_size >= 20:
            confidence = 0.72
        elif parent_size >= 10:
            confidence = 0.60
        else:
            confidence = 0.48
        return NicheEntryPlan(
            target_subniche=target_topic,
            entry_thesis=(
                f"[Demo] {target_topic} es atractivo porque el líder "
                f"({leader_niche.get('topic', '?')}) prioriza segmentos de mayor "
                f"volumen y deja este nicho sin atención competitiva directa."
            ),
            competitive_advantage=(
                f"[Demo] Especialización vertical en {target_topic} permite onboarding "
                f"más rápido y menor CAC que un competidor horizontal."
            ),
            minimum_viable_offer=(
                f"[Demo] Landing en español + 3 estudios de caso + lista de espera "
                f"con 50 prospects de {target_topic}, todo en 2-4 semanas sin construir producto."
            ),
            validation_metrics=[
                "[Demo] Tasa de conversión landing → email ≥ 8%",
                "[Demo] Click-through de ads → landing ≥ 3%",
                "[Demo] 15-25 emails de prospects con pain validado en 4 semanas",
            ],
            estimated_capture_pct="[Demo] 3-8% del parent_market en 12-18 meses",
            key_risks=[
                f"[Demo] {parent_market} entero podría estar maduro y el sub-niche ya "
                f"explorado fuera de nuestro radar de señales",
                "[Demo] ICP demasiado pequeño para sustentar pricing decente",
            ],
            confidence=confidence,
            reasoning=(
                f"[Demo] Sub-niche {target_topic} elegido por menor signal density vs "
                f"líder ({leader_niche.get('signals', 0)} sig). "
                f"Parent_size={parent_size} sugiere mercado real."
            ),
        )
