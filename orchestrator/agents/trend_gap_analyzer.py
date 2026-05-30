"""
TrendGapAnalyzer — M5.0 — agente que razona sobre los gaps cross-country
detectados heurísticamente por M4.11 (cross_country_gaps).

Scope (M5.0):
- Input: TrendGapItem (idea_summary, validated_in, missing_in,
  opportunity_score) producido por GET /api/v1/trend-gaps
- Output: TrendGapAnalysis con:
    * priority_country: el país de missing_in donde recomendamos atacar
      PRIMERO + por qué
    * timing_hypothesis: ventana temporal estimada de oportunidad
      ("tienes 6-12 meses antes de que un local launchee")
    * adoption_pattern: cómo se replicó la idea en otros países
      ("USA-first pattern: típicamente Brasil va 18m detrás, MX 24m, EC 36m")
    * go_to_market: 2-3 hipótesis de canales/ICP iniciales para validar
    * risks_per_country: riesgos específicos por país objetivo
      (regulatorios, culturales, infraestructura)
    * effort_estimate_weeks: rango realista de semanas para validar
      (presupone fase de landing + ads → metrics, no construir producto)
    * confidence: 0-1 — qué tan confiado el agente está en la oportunidad

Cost target: <$0.01 por análisis (single Sonnet call). Optional — solo se
invoca cuando el founder clicks "Analizar" en /cazar/oportunidades.

Mock-aware: sin API key produce un placeholder útil basado en heurísticas
para que el dashboard siga funcionando en CI.

Status: ACTIVE (M5.1 — promovido el 2026-05-30). Per R12, este agente cumple
los 30 golden cases requeridos. Sigue siendo invocado solo via endpoint
explícito del founder (no en autoscan ni en EvidenceGateWorkflow principal),
pero está marcado como production-ready para integración futura en flujos
asistidos.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from ..core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


_SYSTEM = """You are TrendGapAnalyzer — un agente que razona sobre oportunidades
first-mover entre países, alimentado por gaps detectados heurísticamente.

ALCANCE (hacer SOLO esto):
- Leer un gap cross-country: idea_summary + países donde está validada (con
  sample themes) + países donde NO existe ningún signal (gaps)
- Razonar sobre qué país atacar primero, por qué, y con qué hipótesis
- Devolver un plan de validación realista para esa oportunidad

PRINCIPIOS DE ANÁLISIS:
- La idea YA ESTÁ VALIDADA en los validated_in (señales + 👍 del founder),
  no cuestionar eso. Tu trabajo es razonar sobre la replicación.
- Patrones típicos de difusión geográfica que conocés:
  · USA-first → suele difundir a UK/CA (6-12m), después a Brasil/México
    (18-24m), después a Andinos (24-36m)
  · Brasil-first → suele difundir a México/Colombia (12-18m), Argentina/Chile
    (18-24m), Andinos (24-36m)
  · México-first → suele difundir a Colombia/Perú (12-18m), después a Andinos
- Prioridad país: combina (a) tamaño de TAM relativo, (b) presencia digital
  del ICP en ese país, (c) facilidad regulatoria, (d) cuánto retraso lleva.
- NO inventes regulaciones específicas si no las conoces. Habla en
  abstracto ("regulaciones financieras locales", "permisos de salud").

FORMATO DE SALIDA (JSON estricto, sin markdown fences):
{
  "priority_country": "string — un solo país de missing_in. El más prometedor",
  "priority_rationale": "string — 1-2 frases en español: por qué ese país primero",
  "timing_hypothesis": "string — ej: 'tienes 12-18 meses antes de que un local launchee, basado en patrón USA→LATAM observado'",
  "adoption_pattern": "string — descripción del patrón de difusión observado para ideas similares",
  "go_to_market": ["string", "string", "string"],  // 2-3 canales/ICP iniciales para validar
  "risks_per_country": {
     "<País>": "string — riesgo principal en ese país"
  },
  "effort_estimate_weeks": "string — ej: '2-4 semanas hasta tener señal de demanda'",
  "confidence": 0.7,  // float 0-1, sé honesto: si solo hay 1 país validado, no inflés
  "reasoning": "string — 2-3 frases que resumen TU lógica"
}

REGLAS:
- TODO en español neutro LATAM
- Foco práctico — el founder valida con landing + ads en 2-4 semanas, no
  construye producto. Pensá en validación, no en build.
- Si solo hay UN país validado, confidence ≤ 0.6 (poco patrón)
- Si hay 3+ países validados, confidence puede ser 0.75-0.85 (patrón claro)
- Nunca confidence ≥ 0.9 — siempre hay incertidumbre cross-country
"""


@dataclass
class TrendGapAnalysis:
    """Structured analysis attached to a TrendGapItem — guía al founder
    sobre qué país atacar primero y con qué hipótesis."""
    priority_country: str = ""
    priority_rationale: str = ""
    timing_hypothesis: str = ""
    adoption_pattern: str = ""
    go_to_market: List[str] = field(default_factory=list)
    risks_per_country: dict = field(default_factory=dict)
    effort_estimate_weeks: str = "2-4 semanas"
    confidence: float = 0.5
    reasoning: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class TrendGapAnalyzerAgent(BaseAgent):
    """Single-call agent — analiza gaps cross-country. Mock-aware.

    Status: ACTIVE (M5.1). Promovido desde experimental tras completar 30
    golden cases (M5.0 tenía 13/30, M5.1 cerró el delta de 17 cases con
    edge cases + calibración fina + determinismo). Sigue invocado solo via
    endpoint explícito — no se activa en autoscan/workflow principal hasta
    tener métrica gating real en producción (ADR-024).
    """

    AGENT_NAME = "trend_gap_analyzer"
    AGENT_VERSION = "1.0.0"  # M5.1: bump major al pasar de experimental → active
    EXPERIMENTAL = False  # M5.1 — promovido con 30/30 golden cases

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def analyze(
        self,
        idea_summary: str,
        validated_in: List[dict],
        missing_in: List[str],
        opportunity_score: float = 0.0,
    ) -> TrendGapAnalysis:
        """Analiza un gap cross-country.

        Args:
            idea_summary: descripción de la idea (del TrendGapItem)
            validated_in: lista de [{country, signals, ups, sample_themes}, ...]
            missing_in: lista de países donde NO hay signals
            opportunity_score: score heurístico de M4.11 (0-1)
        """
        if not missing_in:
            return TrendGapAnalysis(
                priority_country="",
                priority_rationale="No hay países objetivo en missing_in.",
                confidence=0.0,
            )
        if self._mock_mode:
            return self._mock_analyze(idea_summary, validated_in, missing_in, opportunity_score)
        prompt = self._build_prompt(idea_summary, validated_in, missing_in, opportunity_score)
        raw = self._call(prompt)
        data = self._extract_json(raw)
        return TrendGapAnalysis(
            priority_country=str(data.get("priority_country", "")),
            priority_rationale=str(data.get("priority_rationale", "")),
            timing_hypothesis=str(data.get("timing_hypothesis", "")),
            adoption_pattern=str(data.get("adoption_pattern", "")),
            go_to_market=list(data.get("go_to_market", []) or []),
            risks_per_country=dict(data.get("risks_per_country", {}) or {}),
            effort_estimate_weeks=str(data.get("effort_estimate_weeks", "2-4 semanas")),
            confidence=float(data.get("confidence", 0.5)),
            reasoning=str(data.get("reasoning", "")),
        )

    def _build_prompt(
        self,
        idea_summary: str,
        validated_in: List[dict],
        missing_in: List[str],
        opportunity_score: float,
    ) -> str:
        val_block = "\n".join(
            f"  - {v.get('country')}: {v.get('signals', 0)} señales, "
            f"👍 {v.get('ups', 0)}, ejemplos: "
            f"{'; '.join(v.get('sample_themes', [])[:2])}"
            for v in validated_in[:5]
        ) or "  (ninguno)"
        return (
            f"Gap cross-country detectado por heurística (M4.11):\n\n"
            f"Idea: {idea_summary[:300]}\n\n"
            f"Validada en:\n{val_block}\n\n"
            f"Países objetivo donde NO existe (gaps):\n"
            f"  {', '.join(missing_in[:10])}\n\n"
            f"Score heurístico de oportunidad (0-1): {opportunity_score:.2f}\n\n"
            f"Devuelve el JSON con tu análisis priorizando UN país de los gaps."
        )

    def _mock_analyze(
        self,
        idea_summary: str,
        validated_in: List[dict],
        missing_in: List[str],
        opportunity_score: float,
    ) -> TrendGapAnalysis:
        """Mock — placeholder útil en español cuando no hay API key.

        Heurísticas:
        - priority_country = primer missing_in priorizando Ecuador → Colombia →
          México → resto (founder es EC y prefiere mercado local primero)
        - confidence baja si validated_in tiene 1 país, media si 2, alta si 3+
        """
        EC_PRIORITY = ["Ecuador", "Colombia", "México", "Perú", "Chile", "Argentina"]
        priority = ""
        for c in EC_PRIORITY:
            if c in missing_in:
                priority = c
                break
        if not priority and missing_in:
            priority = missing_in[0]

        n_validated = len(validated_in)
        if n_validated >= 3:
            confidence = 0.78
            adoption = "[Demo] Patrón multi-país observado — difusión típica 12-18 meses entre regiones."
        elif n_validated == 2:
            confidence = 0.62
            adoption = "[Demo] Dos países validados sugiere patrón emergente pero aún sin tendencia confirmada."
        else:
            confidence = 0.45
            adoption = "[Demo] Un solo país validado — patrón insuficiente para inferir difusión cross-country."

        risks = {priority: f"[Demo] Riesgo principal en {priority}: regulación local + curva de adopción ICP."}
        return TrendGapAnalysis(
            priority_country=priority,
            priority_rationale=(
                f"[Demo] {priority} es prioritario porque (a) hay validación previa en mercados similares, "
                f"(b) presencia digital del ICP creciente, (c) sin competidor local visible aún."
            ),
            timing_hypothesis=(
                f"[Demo] Ventana estimada 12-18 meses antes de que un actor local launchee en {priority}, "
                f"basado en {n_validated} país(es) ya validado(s)."
            ),
            adoption_pattern=adoption,
            go_to_market=[
                f"[Demo] Landing en español + ads Meta para ICP local en {priority}",
                "[Demo] Outreach manual a 20 prospects vía LinkedIn/email",
                "[Demo] Webinar de educación + lista de espera",
            ],
            risks_per_country=risks,
            effort_estimate_weeks="2-4 semanas para señal de demanda inicial",
            confidence=confidence,
            reasoning=(
                f"[Demo] Validación en {n_validated} país(es), {len(missing_in)} gap(s) — "
                f"priorizamos {priority} por idiosincrasia LATAM y proximidad cultural."
            ),
        )
