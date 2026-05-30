"""
MultiAgentConsensus — M6.0 — agente sintetizador de perspectivas para
decisiones de alto stakes.

Founder del audio: "vamos a tener unas estructuras de agentes con razonamientos
tan avanzados que van a poder analizar entre ellos, para hacer los insights,
para poder tomar decisiones".

Scope:
- Input: decision_question (qué pregunta resolver) + perspectives (lista de
  outputs de otros agentes / opiniones del founder / prior runs)
- Output: ConsensusAnalysis con agreement_score, consensus_view,
  dissenting_views, key_tradeoffs, final_recommendation

R11 compliance: este agente NO es un Governor que enrutea decisiones a
otros agentes. Recibe perspectives ya producidas y las sintetiza con
schema FIJO. La decisión de QUÉ agentes invocar antes pertenece al
endpoint/caller, no al agente.

Status: experimental (M6.0). 10 golden cases mínimo para shipear; promoción
a active(on-demand) requiere 30 cases (M6.0b cuando aplique).
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import List

from ..core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


_SYSTEM = """You are MultiAgentConsensus — un agente que sintetiza múltiples
perspectivas sobre una decisión, identificando acuerdos, disensos y
tradeoffs.

ALCANCE (no excederlo):
- Recibís: una pregunta de decisión + lista de perspectives (cada una con
  source + text). Las perspectives ya FUERON producidas por otros agentes
  o el founder. Vos NO invocás más agentes.
- Tu trabajo: razonar sobre el solapamiento + disenso de esas perspectives
  y producir un consenso ESTRUCTURADO. NO elegir cuál perspective es
  "mejor" — síntesis, no juicio de calidad.

PRINCIPIOS:
- agreement_score alto cuando todas las perspectives apuntan al mismo
  resultado y bajan los argumentos.
- agreement_score bajo cuando las perspectives son contradictorias.
- consensus_view debe REPRESENTAR el área de acuerdo común, no la suma
  de las perspectives.
- dissenting_views captura las opiniones que se salen del consenso
  PERO con argumento sólido (no las descalifica).
- key_tradeoffs identifica los ejes de decisión donde las perspectives
  divergen sistemáticamente.
- final_recommendation: tu recomendación tras sintetizar, con caveat si
  agreement_score < 0.6.
- confidence: alto cuando agreement_score alto. Nunca > 0.85 (siempre
  hay incertidumbre en decisiones complejas).

FORMATO (JSON estricto, sin markdown):
{
  "agreement_score": 0.0-1.0,
  "consensus_view": "string — el área de acuerdo común entre perspectives",
  "dissenting_views": ["view 1", "view 2"],
  "key_tradeoffs": ["tradeoff 1", "tradeoff 2"],
  "final_recommendation": "string — tu recomendación con caveat si dispersion alta",
  "confidence": 0.0-0.85,
  "reasoning": "string — 2-3 frases con tu lógica"
}

REGLAS:
- Español neutro LATAM
- Si solo hay 1 perspective, agreement_score=1.0 trivialmente, dissenting=[]
- Si 2+ perspectives son textualmente IDÉNTICAS, no agreement por mérito
  — flagéalo en reasoning ("perspectives redundantes, agregar diversidad")
- Si las perspectives son contradictorias (recomendar X vs recomendar
  not-X), agreement_score < 0.4
- NUNCA inventar perspectives que no fueron provistas
"""


@dataclass
class Perspective:
    source: str  # ej: "trend_gap_analyzer", "founder", "claude_devil_advocate"
    text: str    # opinión textual de esa perspective


@dataclass
class ConsensusAnalysis:
    agreement_score: float = 0.5
    consensus_view: str = ""
    dissenting_views: List[str] = field(default_factory=list)
    key_tradeoffs: List[str] = field(default_factory=list)
    final_recommendation: str = ""
    confidence: float = 0.5
    reasoning: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class MultiAgentConsensusAgent(BaseAgent):
    """Status: experimental (M6.0). 10/30 golden cases. NO governor."""

    AGENT_NAME = "multi_agent_consensus"
    AGENT_VERSION = "0.1.0"
    EXPERIMENTAL = True

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def analyze(
        self,
        decision_question: str,
        perspectives: List[dict],
    ) -> ConsensusAnalysis:
        """perspectives: [{source: str, text: str}, ...]"""
        if not perspectives:
            return ConsensusAnalysis(
                agreement_score=0.0,
                consensus_view="",
                reasoning="Sin perspectives provistas — no hay nada que sintetizar.",
            )
        if self._mock_mode:
            return self._mock_analyze(decision_question, perspectives)
        prompt = self._build_prompt(decision_question, perspectives)
        raw = self._call(prompt)
        data = self._extract_json(raw)
        return ConsensusAnalysis(
            agreement_score=float(data.get("agreement_score", 0.5)),
            consensus_view=str(data.get("consensus_view", "")),
            dissenting_views=list(data.get("dissenting_views", []) or []),
            key_tradeoffs=list(data.get("key_tradeoffs", []) or []),
            final_recommendation=str(data.get("final_recommendation", "")),
            confidence=float(data.get("confidence", 0.5)),
            reasoning=str(data.get("reasoning", "")),
        )

    def _build_prompt(
        self, decision_question: str, perspectives: List[dict],
    ) -> str:
        blocks = []
        for i, p in enumerate(perspectives[:10], start=1):
            src = p.get("source", f"perspective_{i}")
            txt = (p.get("text") or "").strip()[:1000]
            blocks.append(f"[{src}]\n{txt}\n")
        return (
            f"Pregunta de decisión:\n{decision_question}\n\n"
            f"Perspectives recolectadas ({len(perspectives)}):\n\n"
            + "\n".join(blocks)
            + "\nDevuelve el JSON con tu síntesis."
        )

    def _mock_analyze(
        self, decision_question: str, perspectives: List[dict],
    ) -> ConsensusAnalysis:
        """Heurística mock: agreement_score basado en solapamiento textual."""
        n = len(perspectives)
        if n == 1:
            text = (perspectives[0].get("text") or "").strip()
            return ConsensusAnalysis(
                agreement_score=1.0,
                consensus_view=f"[Demo] Una sola perspective ({perspectives[0].get('source', 'src')}): {text[:120]}",
                dissenting_views=[],
                key_tradeoffs=[],
                final_recommendation=f"[Demo] Sigue la única perspective disponible — agrega diversidad para validar.",
                confidence=0.45,  # baja porque solo 1 view
                reasoning="[Demo] Solo 1 perspective → no hay disenso pero tampoco validación cruzada.",
            )

        # Calcular solapamiento aproximado: comparar primeras 30 palabras de cada
        def words_of(p: dict) -> set:
            txt = (p.get("text") or "").lower()
            # Quitar punctuación común
            for ch in ".,;:()[]{}!?\"'":
                txt = txt.replace(ch, " ")
            return set(w for w in txt.split() if len(w) > 3)

        word_sets = [words_of(p) for p in perspectives]
        # Intersección de todos
        if word_sets:
            common = set.intersection(*word_sets) if len(word_sets) > 1 else word_sets[0]
            union = set.union(*word_sets)
            jaccard = len(common) / max(len(union), 1)
        else:
            jaccard = 0.0

        # agreement_score = jaccard normalizado (estirado a rango razonable)
        agreement = min(0.95, max(0.15, jaccard * 2.5))

        # consensus_view: primeras 80 chars de la perspective con más palabras
        # comunes (la "más central")
        if common:
            scores = [(i, len(word_sets[i] & common)) for i in range(n)]
            scores.sort(key=lambda x: x[1], reverse=True)
            central_idx = scores[0][0]
            central_text = (perspectives[central_idx].get("text") or "").strip()[:200]
            consensus_view = f"[Demo] Acuerdo central ({perspectives[central_idx].get('source', '?')}): {central_text}"
        else:
            consensus_view = f"[Demo] Sin acuerdo textual entre las {n} perspectives — son ortogonales."

        # dissenting_views: las perspectives que comparten MENOS palabras con common
        dissenting: List[str] = []
        if common and n > 1:
            scored = [(i, len(word_sets[i] & common)) for i in range(n)]
            scored.sort(key=lambda x: x[1])
            for i, score in scored[:2]:
                if score < (len(common) * 0.3):
                    src = perspectives[i].get("source", f"perspective_{i}")
                    txt = (perspectives[i].get("text") or "").strip()[:150]
                    dissenting.append(f"[Demo] {src}: {txt}")

        # key_tradeoffs: heurística simple
        tradeoffs = [
            f"[Demo] Velocidad vs validación: las {n} perspectives priorizan distinto",
            "[Demo] Costo de oportunidad si esperás vs costo si te equivocás",
        ] if n >= 2 else []

        # confidence proporcional a agreement
        confidence = min(0.85, 0.4 + agreement * 0.5)

        # final_recommendation con caveat
        if agreement >= 0.6:
            rec = f"[Demo] Procedé con el consensus_view — alta convergencia entre {n} perspectives."
        elif agreement >= 0.4:
            rec = f"[Demo] Procedé CON CAUTELA — convergencia parcial. Revisar key_tradeoffs antes de actuar."
        else:
            rec = f"[Demo] NO actuar todavía — {n} perspectives en disenso. Buscar más data o pivotear la pregunta."

        return ConsensusAnalysis(
            agreement_score=round(agreement, 2),
            consensus_view=consensus_view,
            dissenting_views=dissenting,
            key_tradeoffs=tradeoffs,
            final_recommendation=rec,
            confidence=round(confidence, 2),
            reasoning=(
                f"[Demo] {n} perspectives analizadas. Jaccard común/unión = "
                f"{jaccard:.2f}. Agreement normalizado a {agreement:.2f}."
            ),
        )
