"""
SleeperCompanyDetector — M5.4 — agente experimental que razona sobre
empresas públicas US (signals kind=sec_edgar de M4.12) para detectar
"second-best with momentum".

Founder del audio: "identificar cuáles son los líderes del mercado, ya en
diferentes industrias, diferentes frentes, cuál es el segundo de a bordo
que en base a información pública financiera ya se vea que está atrás y
que en realidad tiene potencial de poder crecer."

Scope:
- Input: lista de empresas con sus filings recientes (signals kind=sec_edgar)
- Output: SleeperAnalysis con sleeper candidates + comparación vs leader

Status: ACTIVE (M5.10 — promovido 2026-05-30 con 30/30 golden cases).
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import List

from ..core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


_SYSTEM = """You are SleeperCompanyDetector — un agente que identifica
empresas públicas que están en "second place with momentum" — el segundo
de a bordo en su industria que tiene potencial de superar al líder.

ALCANCE:
- Recibís: lista de empresas (nombre + CIK + filings recientes) en el mismo
  sector/industria (mismo SIC code generalmente)
- Tu trabajo: identificar la(s) sleeper(s) — empresas no-líderes con
  growth signals: nuevos 10-K/10-Q frecuentes, S-1 amendments (raising),
  8-K (eventos materiales), DEF 14A (changes en board).

PRINCIPIOS:
- Líder = empresa con mayor market cap conocido en el grupo
- Sleeper = empresa cuyo cadence de filings recientes sugiere actividad
  alta: M&A, capital raises, governance changes
- NO inventes financials. Razoná desde el cadence de filings + tipo de
  formulario, NO desde cifras que no tenés.
- Confianza máxima 0.75 (no podés realmente predecir desde solo SEC filings)

FORMATO (JSON estricto, sin markdown):
{
  "sector_summary": "string — qué sector parece ser esto",
  "leader_candidate": "string — empresa con perfil de líder + por qué",
  "sleeper_candidates": [
    {"company": "name", "thesis": "string — por qué es sleeper"},
    ...
  ],
  "comparison_signals": ["signal 1", "signal 2"],
  "threat_assessment": "string — qué tan creíble es la sleeper como amenaza",
  "investment_thesis": "string — por qué un VC podría apostar al sleeper",
  "confidence": 0.0-1.0,
  "reasoning": "string"
}

REGLAS:
- Español neutro
- Si solo recibís 1 empresa, sleeper_candidates=[] (no se puede comparar)
- Confidence baja si <3 empresas en el grupo
"""


@dataclass
class SleeperCandidate:
    company: str
    thesis: str


@dataclass
class SleeperAnalysis:
    sector_summary: str = ""
    leader_candidate: str = ""
    sleeper_candidates: List[dict] = field(default_factory=list)
    comparison_signals: List[str] = field(default_factory=list)
    threat_assessment: str = ""
    investment_thesis: str = ""
    confidence: float = 0.5
    reasoning: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class SleeperCompanyDetectorAgent(BaseAgent):
    """Status: ACTIVE (M5.10). 30/30 golden cases. v1.0.0."""

    AGENT_NAME = "sleeper_company_detector"
    AGENT_VERSION = "1.0.0"
    EXPERIMENTAL = False

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def analyze(self, companies: List[dict]) -> SleeperAnalysis:
        """companies: [{name, cik, filings: [{form, date}, ...]}, ...]"""
        if not companies:
            return SleeperAnalysis(confidence=0.0, reasoning="Sin empresas para analizar.")
        if self._mock_mode:
            return self._mock_analyze(companies)
        prompt = self._build_prompt(companies)
        raw = self._call(prompt)
        data = self._extract_json(raw)
        return SleeperAnalysis(
            sector_summary=str(data.get("sector_summary", "")),
            leader_candidate=str(data.get("leader_candidate", "")),
            sleeper_candidates=list(data.get("sleeper_candidates", []) or []),
            comparison_signals=list(data.get("comparison_signals", []) or []),
            threat_assessment=str(data.get("threat_assessment", "")),
            investment_thesis=str(data.get("investment_thesis", "")),
            confidence=float(data.get("confidence", 0.5)),
            reasoning=str(data.get("reasoning", "")),
        )

    def _build_prompt(self, companies: List[dict]) -> str:
        blocks = []
        for c in companies[:10]:
            filings_text = "; ".join(
                f"{f.get('form', '?')} {f.get('date', '?')}"
                for f in (c.get("filings") or [])[:5]
            )
            blocks.append(
                f"  - {c.get('name', '?')} (CIK {c.get('cik', '?')}):\n"
                f"    Filings recientes: {filings_text or '(ninguno)'}"
            )
        return (
            f"Empresas públicas US para analizar:\n"
            + "\n".join(blocks) + "\n\n"
            f"Devuelve el JSON con líder + sleepers + tesis."
        )

    def _mock_analyze(self, companies: List[dict]) -> SleeperAnalysis:
        n = len(companies)
        if n == 1:
            return SleeperAnalysis(
                sector_summary="[Demo] Sector unitario — sin comparación posible",
                leader_candidate=companies[0].get("name", "?"),
                sleeper_candidates=[],
                threat_assessment="[Demo] No aplica con una sola empresa",
                investment_thesis="[Demo] Necesitás al menos 3 empresas para detectar sleepers",
                confidence=0.0,
                reasoning="[Demo] Una sola empresa no permite identificar second-best.",
            )
        # Heurística mock: primer empresa = leader, siguientes = sleepers
        names = [c.get("name", f"Company {i}") for i, c in enumerate(companies)]
        leader = names[0]
        sleepers = []
        for nm in names[1:3]:
            filings_count = len(companies[names.index(nm)].get("filings", []))
            sleepers.append({
                "company": nm,
                "thesis": (
                    f"[Demo] {nm} tiene {filings_count} filings recientes, "
                    f"cadence sugiere actividad alta (M&A o capital raises)."
                ),
            })
        confidence = 0.62 if n >= 3 else 0.45
        return SleeperAnalysis(
            sector_summary=f"[Demo] Grupo de {n} empresas — sector por inferir vía SIC code real",
            leader_candidate=f"[Demo] {leader} (asumido por orden de input)",
            sleeper_candidates=sleepers,
            comparison_signals=[
                "[Demo] Cadence de filings 10-Q/10-K en últimos 12 meses",
                "[Demo] Presencia de 8-K (eventos materiales)",
            ],
            threat_assessment=(
                f"[Demo] Amenaza creíble si sleeper tiene cadence >= 80% del líder en filings."
            ),
            investment_thesis=(
                f"[Demo] {sleepers[0]['company'] if sleepers else 'sleeper'} puede ser "
                f"interesante si su revenue growth supera al líder en próximas 10-K."
            ),
            confidence=confidence,
            reasoning=(
                f"[Demo] Análisis heurístico basado en cadence de filings. "
                f"Confidence={confidence:.2f} por N={n} empresas comparadas."
            ),
        )
