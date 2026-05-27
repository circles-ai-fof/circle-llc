"""
IdeaAnalyzer — enriches a captured signal with structured info so the founder
can decide whether to promote it to a full workflow run.

Scope (M3.5):
- Input: a Signal (theme + excerpt + suggested_topic + evidence URLs + source)
- Output: SignalAnalysis with:
    * market_size_estimate    — short string ("~50k empresas en LATAM", "$2B TAM global", "Nicho pequeño <1k usuarios")
    * icp_probable             — perfil del cliente probable
    * competitors              — lista de competidores conocidos (puede ser vacía)
    * differentiator           — por qué esta idea podría ganar
    * risks                    — 2-3 riesgos principales
    * recommendation           — "promote" | "wait_for_more_data" | "discard"
    * reasoning                — 1-2 frases explicando la recomendación

Cost target: <$0.005 (single Haiku call). Optional — only invoked when the
founder clicks "Analizar" in the dashboard.

Mock-aware: when no API key is present, produces a plausible Spanish
placeholder so the dashboard stays usable.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from ..core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


_SYSTEM = """You are IdeaAnalyzer — un agente de triage rápido para decidir si una
señal capturada por el cazador merece convertirse en una corrida completa del
workflow (~$0.06).

ALCANCE (hacer SOLO esto):
- Leer una señal (tema + extracto + topic sugerido + URLs de evidencia + fuente)
- Devolver un análisis estructurado EN ESPAÑOL con foco LATAM
- Producir una recomendación accionable: promover / esperar / descartar

CRITERIOS DE RECOMENDACIÓN:
- "promote": dolor real + ICP claro + mercado >5k usuarios potenciales en LATAM
- "wait_for_more_data": señal interesante pero ICP/mercado ambiguo
- "discard": noticia genérica, hype, sin pain point, o mercado <500 usuarios

FORMATO DE SALIDA (JSON estricto, sin markdown fences):
{
  "market_size_estimate": "string — ej: '~50k empresas en LATAM', '$2B TAM global', 'Nicho pequeño <1k usuarios'",
  "icp_probable": "string — perfil del cliente más probable, específico (rol + tamaño empresa + país/región)",
  "competitors": ["string", "string"],  // 0-5 nombres de competidores conocidos o "ninguno conocido"
  "differentiator": "string — ángulo único o diferenciador potencial (1 frase)",
  "risks": ["string", "string"],  // 2-3 riesgos principales
  "recommendation": "promote" | "wait_for_more_data" | "discard",
  "reasoning": "string — 1-2 frases explicando la recomendación"
}

REGLAS:
- TODO en español (no mezclar inglés)
- Foco LATAM (Ecuador, Colombia, México, Perú, Chile, Argentina) cuando aplique
- Si la señal es ambigua, prefiere "wait_for_more_data" sobre "promote"
- NO inventes competidores específicos si no estás seguro — usa "ninguno conocido públicamente"
"""


@dataclass
class SignalAnalysis:
    """Structured analysis attached to a Signal — helps the founder decide."""
    market_size_estimate: str
    icp_probable: str
    competitors: List[str] = field(default_factory=list)
    differentiator: str = ""
    risks: List[str] = field(default_factory=list)
    recommendation: str = "wait_for_more_data"  # promote | wait_for_more_data | discard
    reasoning: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class IdeaAnalyzerAgent(BaseAgent):
    """Single-call enrichment agent — cheap, mock-aware, LATAM-focused."""

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def analyze(
        self,
        theme: str,
        excerpt: str,
        suggested_topic: str,
        evidence_urls: Optional[List[str]] = None,
        source_kind: str = "",
        source_name: str = "",
    ) -> SignalAnalysis:
        if self._mock_mode:
            return self._mock_analyze(theme, excerpt, suggested_topic)
        prompt = self._build_prompt(
            theme=theme, excerpt=excerpt, suggested_topic=suggested_topic,
            evidence_urls=evidence_urls or [], source_kind=source_kind,
            source_name=source_name,
        )
        raw = self._call(prompt)
        data = self._extract_json(raw)
        return SignalAnalysis(
            market_size_estimate=str(data.get("market_size_estimate", "")),
            icp_probable=str(data.get("icp_probable", "")),
            competitors=list(data.get("competitors", []) or []),
            differentiator=str(data.get("differentiator", "")),
            risks=list(data.get("risks", []) or []),
            recommendation=str(data.get("recommendation", "wait_for_more_data")),
            reasoning=str(data.get("reasoning", "")),
        )

    def _build_prompt(
        self,
        theme: str,
        excerpt: str,
        suggested_topic: str,
        evidence_urls: List[str],
        source_kind: str,
        source_name: str,
    ) -> str:
        urls_block = "\n".join(f"  - {u}" for u in evidence_urls[:5]) or "  (sin URLs)"
        return (
            f"Señal capturada por el cazador:\n\n"
            f"Tema: {theme}\n"
            f"Fuente: {source_name or source_kind} ({source_kind})\n"
            f"Extracto: {excerpt[:600]}\n"
            f"Topic sugerido: {suggested_topic}\n"
            f"URLs de evidencia:\n{urls_block}\n\n"
            f"Devuelve el JSON con tu análisis."
        )

    def _mock_analyze(
        self,
        theme: str,
        excerpt: str,
        suggested_topic: str,
    ) -> SignalAnalysis:
        """Mock — placeholder útil en español cuando no hay API key.

        Heurísticas mínimas: si el tema menciona ciertos keywords, ajustamos
        la recomendación para que el UX no sea constante.
        """
        text = f"{theme} {excerpt} {suggested_topic}".lower()
        if any(k in text for k in ("ai ", "ia ", "llm", "gpt", "agente")):
            recommendation = "wait_for_more_data"
            reasoning = (
                "[Modo demo] Tema de IA es relevante pero saturado — espera "
                "más data de trend antes de gastar $0.06 en una corrida."
            )
        elif any(k in text for k in ("404", "test", "lorem", "mock")):
            recommendation = "discard"
            reasoning = (
                "[Modo demo] Señal sin contenido sustantivo — descartar para "
                "limpiar el feed."
            )
        else:
            recommendation = "promote"
            reasoning = (
                "[Modo demo] Tema con pain point identificable y mercado "
                "estimable — buena candidata para promover."
            )
        return SignalAnalysis(
            market_size_estimate="~10-50k empresas potenciales en LATAM (estimado demo)",
            icp_probable=(
                "Founder o gerente operativo de PYME 10-200 empleados en Ecuador / "
                "Colombia / México (perfil demo)"
            ),
            competitors=["ninguno conocido públicamente (análisis demo)"],
            differentiator=(
                "Integración local + soporte en español + precio LATAM — "
                "ángulos típicos para este tipo de oportunidad (demo)"
            ),
            risks=[
                "Pricing power limitado en LATAM vs USA",
                "Adopción lenta en PYMEs tradicionales",
                "Dependencia de canales de adquisición de bajo costo",
            ],
            recommendation=recommendation,
            reasoning=reasoning,
        )
