"""
M11.3 — IdeaValidator (red-team pre-test gate).

The Evidence-Gate workflow today spends ~$50 in ads per idea to discover
which ones are bad. That's the right call once an idea has cleared a
basic plausibility filter — real CTR data beats LLM intuition. But it
means EVERY idea that survives idea_maturer goes to ads, including
the ones that have unit economics that can't possibly work, or that
attack a non-problem.

This agent is the missing pre-test gate: it acts as a skeptical
investor / scarred operator who tries to KILL the idea with the best
argument possible. Only ideas that survive the attack continue to
market_validator + landing + ads.

Position in the workflow:

  idea_hunter -> idea_enricher -> idea_maturer -> [IdeaValidator] -> market_validator -> ...

The agent's contract is loaded directly from the spec at
docs/idea-validator-spec.md (a verbatim port of the user-provided
.md). The spec mandates:

  - Identify the most lethal assumption first
  - Every critique must be falsifiable (cite the experiment + days)
  - Cite WebSearch / WebFetch sources (year + source) for any numbers
  - Answer 3 obligatory questions explicitly
  - Final verdict in fixed format

Verdicts:
  - MATAR:                kill the idea now, no ad spend
  - PIVOTAR:              return to idea_maturer with a specific condition
  - AVANZAR_CON_EVIDENCIA: continue to market_validator (Step 3)

Activation:
  IDEA_VALIDATOR_ENABLED=true       # opt-in until calibrated
  IDEA_VALIDATOR_RESEARCH=true      # opt-in web_search (Anthropic native tool)
  IDEA_VALIDATOR_MODEL=claude-opus-4-5

This agent does NOT decide unilaterally — its verdict is surfaced to the
founder via the dashboard. MATAR auto-short-circuits the workflow if the
founder has set autonomy_level=autonomous_with_approval; otherwise it's a
recommendation requiring explicit acceptance.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


def validator_enabled() -> bool:
    return os.getenv("IDEA_VALIDATOR_ENABLED", "false").lower() in {
        "true", "1", "yes",
    }


def research_enabled() -> bool:
    """Whether the agent should use Anthropic's native web_search tool
    for the 'DATOS A APORTAR' section. Costs more but grounds claims."""
    return os.getenv("IDEA_VALIDATOR_RESEARCH", "false").lower() in {
        "true", "1", "yes",
    }


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


@dataclass
class LethalAssumption:
    """The single assumption that, if false, makes everything else collapse."""
    statement: str
    why_lethal: str = ""


@dataclass
class ExperimentDesign:
    """The $50 + 1-week experiment that proves or refutes the lethal
    assumption. Must be concrete, falsifiable, and cheap."""
    description: str
    budget_usd: float = 50.0
    duration_days: int = 7
    success_criterion: str = ""


@dataclass
class AttackVector:
    """One vector the validator probed (demanda, WTP, distribución, etc)."""
    name: str
    finding: str
    is_blocker: bool = False


@dataclass
class ValidatorResult:
    """Full output of the validator run."""
    verdict: str                           # MATAR | PIVOTAR | AVANZAR_CON_EVIDENCIA
    lethal_assumption: LethalAssumption
    experiment: ExperimentDesign
    precondition: str = ""                 # populated when verdict in {PIVOTAR, AVANZAR}
    attack_vectors: List[AttackVector] = field(default_factory=list)
    pre_mortem_60d: List[str] = field(default_factory=list)   # Q1 answers
    real_buyer: str = ""                                       # Q2 answer
    economic_impact: str = ""                                  # Q3 answer
    sources: List[str] = field(default_factory=list)           # cited urls
    provider: str = ""                                         # "claude" | "mock"
    raw_text: str = ""                                         # full prose for dashboard display
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# System prompt — direct port of the user's idea-validator.md
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """# ROL

Eres un inversor escéptico y operador con cicatrices que ha visto fracasar
cientos de ideas. Tu trabajo NO es ser amable ni equilibrado: es intentar MATAR
la idea que te presenten con el mejor argumento posible. Si la idea sobrevive a
tu ataque, será porque es genuinamente sólida, no porque te faltó dureza. Sesgo
por defecto: "esto no funciona; demuéstrame lo contrario".

# REGLAS DE COMBATE

1. Empieza identificando LA SUPOSICIÓN MÁS LETAL: aquella que, si es falsa, hace
   colapsar todo lo demás. Atácala primero y con más fuerza.
2. Toda crítica debe ser FALSABLE. Prohibido el escepticismo vago. Cada ataque
   termina en: "esto se confirma o se refuta haciendo [experimento concreto y
   barato] en [días]".
3. Sé específico y cuantitativo. "La competencia es fuerte" no vale. "X ya
   ofrece esto gratis y tiene Y usuarios" sí vale.
4. NUNCA inventes datos. Cuando des una cifra, marca la fuente y año. Si no
   tienes acceso a búsqueda en vivo, márcala como `[ASUNCIÓN — verificar]`
   con un rango razonado y di qué dato buscar y dónde.

# VECTORES DE ATAQUE (recórrelos todos, ordenados por letalidad)

- DEMANDA: ¿el dolor existe y es urgente, o es un "estaría bien tener"?
- DISPOSICIÓN A PAGAR: ¿quién ya gasta dinero/tiempo resolviendo esto hoy de
  forma chapucera? Si nadie, alerta roja.
- ALTERNATIVA "NO HACER NADA": tu competidor real suele ser la inercia y el
  Excel. ¿Por qué cambiarían?
- MERCADO: tamaño real alcanzable, no el TAM de fantasía. ¿Grande Y accesible?
- DISTRIBUCIÓN: ¿cómo llegas a los clientes y cuánto cuesta? Muchas ideas buenas
  mueren aquí, no en el producto.
- ECONOMÍA UNITARIA: CAC, precio, margen, periodo de recuperación.
- DEFENSIBILIDAD: si funciona, ¿qué impide que alguien más grande lo copie en
  6 meses?
- TIMING / REGULACIÓN / EJECUCIÓN: ¿por qué ahora? ¿qué barrera lo frena?

# LAS TRES PREGUNTAS OBLIGATORIAS

Responde explícitamente con tu mejor razonamiento:

1. ¿Qué tendría que suceder para que esto fracase en los próximos 60 días?
2. ¿Quién, con perfil concreto, pagaría esto HOY y cuánto? Si no puedes nombrar
   a nadie verosímil, dilo claramente.
3. ¿Cuál es el impacto económico medible? Da la fórmula y los supuestos.

# FORMATO DE SALIDA

Devuelve PRIMERO tu análisis en prose (vectores + 3 preguntas + datos), y AL
FINAL un bloque JSON con el veredicto estructurado:

```json
{
  "verdict": "MATAR" | "PIVOTAR" | "AVANZAR_CON_EVIDENCIA",
  "lethal_assumption": {"statement": "...", "why_lethal": "..."},
  "experiment": {
    "description": "...",
    "budget_usd": 50.0,
    "duration_days": 7,
    "success_criterion": "..."
  },
  "precondition": "...",            // requerido si verdict en {PIVOTAR, AVANZAR_CON_EVIDENCIA}
  "attack_vectors": [
    {"name": "DEMANDA", "finding": "...", "is_blocker": false}
  ],
  "pre_mortem_60d": ["razón 1", "razón 2", ...],
  "real_buyer": "...",
  "economic_impact": "...",
  "sources": ["url1", "url2"]
}
```

El bloque JSON es OBLIGATORIO al final. El agente principal solo lee ese bloque.
"""


def _user_prompt(topic: str, value_prop: str, icp: str, evidence: str) -> str:
    return (
        f"Idea a validar:\n"
        f"  TOPIC: {topic}\n"
        f"  VALUE PROP: {value_prop}\n"
        f"  ICP: {icp}\n\n"
        f"Evidencia / contexto disponible:\n{evidence[:1500]}\n\n"
        f"Atacá la idea con todo. Aplicá los vectores en orden de letalidad. "
        f"Respondé las 3 preguntas obligatorias. Cerrá con el bloque JSON."
    )


# ---------------------------------------------------------------------------
# LLM caller — Opus (best reasoning for adversarial analysis)
# ---------------------------------------------------------------------------


def _call_claude(topic: str, value_prop: str, icp: str, evidence: str) -> Optional[str]:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        client = anthropic.Anthropic()
        model_name = os.getenv("IDEA_VALIDATOR_MODEL", "claude-opus-4-5")
        # web_search tool only attached when explicit opt-in; costs ~3x baseline.
        tools = []
        if research_enabled():
            tools = [{"type": "web_search_20250305", "name": "web_search"}]
        kwargs = {
            "model": model_name,
            "max_tokens": 2500,
            "system": _SYSTEM_PROMPT,
            "messages": [{
                "role": "user",
                "content": _user_prompt(topic, value_prop, icp, evidence),
            }],
        }
        if tools:
            kwargs["tools"] = tools
        resp = client.messages.create(**kwargs)
        # When tools are used the response can have multiple content blocks;
        # we collect all text blocks and join.
        out_parts: List[str] = []
        for block in resp.content or []:
            if hasattr(block, "text") and block.text:
                out_parts.append(block.text)
        return "\n".join(out_parts)
    except Exception as e:  # noqa: BLE001
        logger.warning("idea_validator: claude failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

_VALID_VERDICTS = {"MATAR", "PIVOTAR", "AVANZAR_CON_EVIDENCIA"}


def _extract_json_block(text: str) -> Optional[dict]:
    """Find every top-level JSON object in the response, then return the
    one with a valid `verdict`. The spec mandates the structured verdict
    at the END of the response after the prose analysis.

    A naive `re.findall(r'\\{.*\\}')` fails when the response contains
    multiple JSON-ish snippets (e.g. an embedded example + the final
    block) — greedy match captures everything between the first `{` and
    the last `}` and yields invalid JSON. We instead walk the text with
    a brace counter to find each balanced top-level object.
    """
    if not text:
        return None

    candidates: List[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth == 0:
                continue  # stray closer — ignore
            depth -= 1
            if depth == 0 and start != -1:
                candidates.append(text[start: i + 1])
                start = -1

    if not candidates:
        return None

    # Prefer the LAST candidate with a valid verdict (spec says the
    # structured block lives at the end of the response).
    for cand in reversed(candidates):
        try:
            data = json.loads(cand)
            if isinstance(data, dict) and data.get("verdict") in _VALID_VERDICTS:
                return data
        except json.JSONDecodeError:
            continue

    # Fallback: last candidate even if verdict is invalid — caller will
    # default to MATAR safely.
    try:
        return json.loads(candidates[-1])
    except json.JSONDecodeError:
        return None


def _parse_validator_output(raw: str) -> ValidatorResult:
    """Parse the LLM's prose + JSON block into a ValidatorResult."""
    if not raw:
        return ValidatorResult(
            verdict="MATAR",
            lethal_assumption=LethalAssumption("empty model response"),
            experiment=ExperimentDesign(description="N/A"),
            error="empty response",
            raw_text="",
        )

    data = _extract_json_block(raw)
    if not data:
        # Couldn't parse a structured verdict — fail closed (default to MATAR)
        return ValidatorResult(
            verdict="MATAR",
            lethal_assumption=LethalAssumption(
                "validator output unparseable",
                "JSON block missing or malformed in LLM response"
            ),
            experiment=ExperimentDesign(
                description="Re-run validator with structured-output forced",
            ),
            raw_text=raw[:5000],
            error="json parse failed",
        )

    # Verdict (default to MATAR if invalid — fail closed)
    verdict_raw = str(data.get("verdict", "MATAR")).strip().upper()
    verdict = verdict_raw if verdict_raw in _VALID_VERDICTS else "MATAR"

    # Lethal assumption
    la_blob = data.get("lethal_assumption") or {}
    if isinstance(la_blob, str):
        la = LethalAssumption(statement=la_blob[:400])
    else:
        la = LethalAssumption(
            statement=str(la_blob.get("statement", ""))[:400],
            why_lethal=str(la_blob.get("why_lethal", ""))[:400],
        )

    # Experiment
    exp_blob = data.get("experiment") or {}
    exp = ExperimentDesign(
        description=str(exp_blob.get("description", ""))[:600],
        budget_usd=float(exp_blob.get("budget_usd", 50.0) or 50.0),
        duration_days=int(exp_blob.get("duration_days", 7) or 7),
        success_criterion=str(exp_blob.get("success_criterion", ""))[:300],
    )

    # Attack vectors
    av_blobs = data.get("attack_vectors") or []
    avs: List[AttackVector] = []
    if isinstance(av_blobs, list):
        for v in av_blobs[:10]:
            if not isinstance(v, dict):
                continue
            avs.append(AttackVector(
                name=str(v.get("name", ""))[:50],
                finding=str(v.get("finding", ""))[:400],
                is_blocker=bool(v.get("is_blocker", False)),
            ))

    pre_mortem = data.get("pre_mortem_60d") or []
    if isinstance(pre_mortem, list):
        pre_mortem = [str(x)[:300] for x in pre_mortem[:5]]
    else:
        pre_mortem = []

    sources = data.get("sources") or []
    if isinstance(sources, list):
        sources = [str(x)[:300] for x in sources[:10]]
    else:
        sources = []

    return ValidatorResult(
        verdict=verdict,
        lethal_assumption=la,
        experiment=exp,
        precondition=str(data.get("precondition", ""))[:600],
        attack_vectors=avs,
        pre_mortem_60d=pre_mortem,
        real_buyer=str(data.get("real_buyer", ""))[:500],
        economic_impact=str(data.get("economic_impact", ""))[:600],
        sources=sources,
        raw_text=raw[:8000],
    )


# ---------------------------------------------------------------------------
# Mock mode (no API key) — deterministic placeholder so tests don't burn tokens
# ---------------------------------------------------------------------------


def _mock_result(topic: str) -> ValidatorResult:
    """Mock-mode placeholder. Verdict defaults to MATAR (fail closed) so the
    workflow's safety behavior is testable end-to-end without an API key."""
    return ValidatorResult(
        verdict="MATAR",
        lethal_assumption=LethalAssumption(
            statement=f"[mock_mode] no real analysis run for: {topic[:80]}",
            why_lethal="ANTHROPIC_API_KEY unset — validator returned safe default",
        ),
        experiment=ExperimentDesign(
            description="[mock_mode] set ANTHROPIC_API_KEY to get a real analysis",
        ),
        provider="mock",
        raw_text="[mock_mode]",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def validate_idea(
    topic: str,
    value_prop: str = "",
    icp: str = "",
    evidence: str = "",
) -> ValidatorResult:
    """Run the red-team validator on a matured idea.

    Returns ValidatorResult with one of three verdicts:
      MATAR                   - kill before ad spend
      PIVOTAR                 - go back to idea_maturer with `precondition`
      AVANZAR_CON_EVIDENCIA   - continue to market_validator (Step 3)

    The caller decides what to do with each verdict. In mock mode (no
    ANTHROPIC_API_KEY) returns a placeholder MATAR result.

    Never raises — LLM errors swallowed into ValidatorResult.error.
    """
    if not topic and not value_prop:
        return ValidatorResult(
            verdict="MATAR",
            lethal_assumption=LethalAssumption(
                "no idea provided", "topic + value_prop both empty"),
            experiment=ExperimentDesign(description="N/A"),
            error="empty input",
        )

    if not os.getenv("ANTHROPIC_API_KEY"):
        return _mock_result(topic)

    raw = _call_claude(topic, value_prop, icp, evidence)
    if not raw:
        # Fail closed — better to recommend KILL than push forward blind
        return ValidatorResult(
            verdict="MATAR",
            lethal_assumption=LethalAssumption(
                "validator unavailable", "Claude call returned empty"),
            experiment=ExperimentDesign(description="retry when API is healthy"),
            error="LLM unavailable",
        )

    result = _parse_validator_output(raw)
    if not result.provider:
        result.provider = "claude"
    return result


__all__ = [
    "LethalAssumption",
    "ExperimentDesign",
    "AttackVector",
    "ValidatorResult",
    "validate_idea",
    "validator_enabled",
    "research_enabled",
]
