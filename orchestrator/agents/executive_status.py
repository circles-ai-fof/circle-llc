"""
M15.0 — Executive Status agent.

The "brain" piece of the WhatsApp Gateway spec. Aggregates Circle LLC's
current state (signals + runs + agents + recent commits) and produces a
natural-language briefing in Spanish for the founder/CEO. Exposed via
POST /api/v1/executive-status so any channel (dashboard, email cron,
future WhatsApp gateway) can call it.

Two modes:
  - REPORT mode (no question): standalone weekly/daily briefing.
    "Generá el reporte ejecutivo de Circle LLC ahora."
  - QA mode (with question):   answer a specific question grounded in
    current state. "¿Está lista la fase 3?" / "¿cómo va el cazador?"

The agent is intentionally NON-AUTHORITATIVE about the future — it only
reports observed state + flags risks. Decisions (kill / pivot / advance)
still belong to gate_decider + IdeaValidator.

Cost: ~$0.005-0.01 per call with Sonnet 4.6 (input ~3K tokens, output
~800 tokens). Daily cron = $0.30/month. Reactive querying capped by
WhatsApp 24h window in the gateway layer (not here).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EXEC_MODEL = os.getenv("EXEC_STATUS_MODEL", "claude-sonnet-4-6")
EXEC_MAX_TOKENS = int(os.getenv("EXEC_STATUS_MAX_TOKENS", "1500"))


# ---------------------------------------------------------------------------
# State snapshot — pure aggregator, no LLM
# ---------------------------------------------------------------------------


@dataclass
class StateSnapshot:
    """The raw context the brain reasons over. All counts are real-time."""
    signals_total: int = 0
    signals_new_24h: int = 0
    signals_promoted: int = 0
    signals_with_pain_boost: int = 0
    sources_total: int = 0
    sources_active: int = 0
    sources_top_quality: List[Dict] = field(default_factory=list)
    runs_total: int = 0
    runs_pass: int = 0
    runs_kill: int = 0
    runs_iterate: int = 0
    runs_pending_review: int = 0
    runs_kill_early: int = 0  # M11.4 — IdeaValidator MATAR short-circuits
    agents_count: int = 0
    features_on: Dict[str, bool] = field(default_factory=dict)
    recent_commits: List[Dict] = field(default_factory=list)
    cost_usd_30d: float = 0.0
    autonomy_level: str = "manual"


def collect_state() -> StateSnapshot:
    """Build the snapshot from in-process stores + git log. Best-effort:
    each section is wrapped in try/except so a single store failure doesn't
    blank the whole briefing."""
    snap = StateSnapshot()
    try:
        from ..core.storage import (
            signals_store, sources_store, runs_store, autonomy_store,
        )
        all_signals = signals_store.list()
        snap.signals_total = len(all_signals)
        now_unix = int(__import__("time").time())
        cutoff_24h = now_unix - 24 * 3600
        snap.signals_new_24h = sum(
            1 for s in all_signals if int(s.get("created_at", 0) or 0) >= cutoff_24h
        )
        snap.signals_promoted = sum(
            1 for s in all_signals if s.get("promoted_run_id")
        )
        # Heuristic: pain boost manifested as score > base 0.7 + non-default
        # solution_type. (Coarse — we don't store the boost flag explicitly.)
        snap.signals_with_pain_boost = sum(
            1 for s in all_signals
            if float(s.get("score") or 0) > 0.7
            and (s.get("solution_type") and s["solution_type"] != "unknown")
        )

        all_sources = sources_store.list()
        snap.sources_total = len(all_sources)
        snap.sources_active = sum(1 for s in all_sources if s.get("active"))
        # Top 5 by quality (M9.5)
        ranked = sorted(
            all_sources,
            key=lambda s: float(s.get("quality_score") or 0.5),
            reverse=True,
        )[:5]
        snap.sources_top_quality = [
            {
                "name": s.get("name", ""),
                "kind": s.get("kind", ""),
                "quality": round(float(s.get("quality_score") or 0.5), 2),
                "hit_rate": round(float(s.get("hit_rate") or 0.0), 2),
            }
            for s in ranked
        ]

        recent_runs = runs_store.list_recent(limit=100) if hasattr(runs_store, "list_recent") else []
        snap.runs_total = len(recent_runs)
        for r in recent_runs:
            v = (r.get("verdict") or "").lower()
            if v == "pass":
                snap.runs_pass += 1
            elif v == "kill":
                snap.runs_kill += 1
                rationale = (r.get("summary") or r.get("rationale") or "")
                if "matar" in rationale.lower() or "ideavalidator" in rationale.lower():
                    snap.runs_kill_early += 1
            elif v == "iterate":
                snap.runs_iterate += 1
            elif not v:
                snap.runs_pending_review += 1

        snap.autonomy_level = autonomy_store.get_level()
    except Exception as e:  # noqa: BLE001
        logger.warning("collect_state: store section failed: %s", e)

    # Features in production
    try:
        snap.features_on = {
            "ensemble_gate_enabled": os.getenv("ENSEMBLE_GATE_ENABLED", "").lower() in {"true", "1", "yes"},
            "adversarial_callback_enabled": os.getenv("ADVERSARIAL_CALLBACK_ENABLED", "").lower() in {"true", "1", "yes"},
            "idea_validator_enabled": os.getenv("IDEA_VALIDATOR_ENABLED", "").lower() in {"true", "1", "yes"},
            "idea_validator_research": os.getenv("IDEA_VALIDATOR_RESEARCH", "").lower() in {"true", "1", "yes"},
            "fact_check_enabled": os.getenv("FACT_CHECK_ENABLED", "").lower() in {"true", "1", "yes"},
        }
    except Exception:  # noqa: BLE001
        pass

    # Agents count — read from disk listing under orchestrator/agents/
    try:
        import pathlib
        agents_dir = pathlib.Path(__file__).parent
        snap.agents_count = sum(
            1 for p in agents_dir.iterdir()
            if p.is_file() and p.suffix == ".py" and not p.name.startswith("_")
        )
    except Exception:  # noqa: BLE001
        pass

    # Last 5 commits (best-effort — fails silently when not in a git checkout)
    try:
        result = subprocess.run(
            ["git", "log", "-5", "--pretty=format:%h|%ar|%s"],
            capture_output=True, text=True, timeout=3,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        )
        if result.returncode == 0:
            for line in (result.stdout or "").splitlines():
                parts = line.split("|", 2)
                if len(parts) == 3:
                    snap.recent_commits.append({
                        "sha": parts[0], "when": parts[1], "subject": parts[2][:160],
                    })
    except Exception:  # noqa: BLE001
        pass

    return snap


# ---------------------------------------------------------------------------
# Briefing schema
# ---------------------------------------------------------------------------


@dataclass
class ExecutiveBriefing:
    summary: str                       # 1-2 sentence headline
    body: str                          # full natural-language report
    highlights: List[str] = field(default_factory=list)   # bullet points
    risks: List[str] = field(default_factory=list)        # things to watch
    asks: List[str] = field(default_factory=list)         # actions for the CEO
    snapshot: Optional[StateSnapshot] = None
    mode: str = "report"               # "report" | "qa"
    question: Optional[str] = None
    cost_usd_estimated: float = 0.0
    mock_mode: bool = True


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = (
    "Eres el agente executive-status de Circle LLC (proyecto Factory of "
    "Factories, dominio circles-ai.ai). Tu rol es entregar reportes "
    "ejecutivos al CEO/fundador (Cristian) en español neutro, con tono de "
    "operador honesto: nada de hype, nada de tranquilizadores vacíos.\n\n"
    "REGLAS:\n"
    "1. Solo reportá HECHOS OBSERVADOS desde el contexto que te paso. NO "
    "   inventes métricas, fuentes ni eventos. Si un dato no está, decí "
    "   'no disponible'.\n"
    "2. Estructurá la salida en bloques cortos: HEADLINE / HIGHLIGHTS / "
    "   RIESGOS / PRÓXIMOS PASOS. Cada bloque máximo 4 bullets.\n"
    "3. Lenguaje directo y operativo: 'el cazador trajo 12 señales nuevas en "
    "   24h' > 'la actividad ha sido positiva'.\n"
    "4. Si el contexto tiene un problema obvio (0 runs, fuentes con "
    "   quality_score=0.0, autonomy_level=manual cuando debería estar "
    "   asistido), señalalo en RIESGOS.\n"
    "5. En modo QA respondé la pregunta primero (2-3 oraciones) y luego "
    "   anclá la respuesta a los datos del contexto.\n"
    "6. Cerrá SIEMPRE con una sección 'PRÓXIMOS PASOS' con 2-3 acciones "
    "   concretas + estimación de quién las debe ejecutar.\n"
    "7. NO uses markdown pesado ni emojis. WhatsApp + email los renderizan "
    "   inconsistente. Texto plano con saltos de línea es suficiente."
)


def _user_prompt(snap: StateSnapshot, question: Optional[str]) -> str:
    """Compose the prompt the LLM receives. Stringifies the snapshot as
    JSON because that's the most token-efficient way to hand structured
    state without prose padding."""
    context_json = json.dumps({
        "signals_total": snap.signals_total,
        "signals_new_24h": snap.signals_new_24h,
        "signals_promoted": snap.signals_promoted,
        "signals_with_pain_boost": snap.signals_with_pain_boost,
        "sources_total": snap.sources_total,
        "sources_active": snap.sources_active,
        "sources_top_quality": snap.sources_top_quality,
        "runs_total": snap.runs_total,
        "runs_pass": snap.runs_pass,
        "runs_kill": snap.runs_kill,
        "runs_iterate": snap.runs_iterate,
        "runs_pending_review": snap.runs_pending_review,
        "runs_kill_early": snap.runs_kill_early,
        "agents_count": snap.agents_count,
        "features_on": snap.features_on,
        "autonomy_level": snap.autonomy_level,
        "recent_commits": snap.recent_commits,
    }, ensure_ascii=False, indent=2)

    if question:
        return (
            f"CONTEXTO ACTUAL (Circle LLC):\n```json\n{context_json}\n```\n\n"
            f"PREGUNTA DEL CEO:\n{question.strip()[:500]}\n\n"
            "Respondé en español, primero la respuesta directa y después el "
            "soporte con los datos del contexto. Cerrá con PRÓXIMOS PASOS."
        )
    # Standalone briefing
    return (
        f"CONTEXTO ACTUAL (Circle LLC):\n```json\n{context_json}\n```\n\n"
        "Generá el reporte ejecutivo actual. Estructura: HEADLINE, "
        "HIGHLIGHTS, RIESGOS, PRÓXIMOS PASOS. Tono operativo y honesto."
    )


# ---------------------------------------------------------------------------
# LLM caller
# ---------------------------------------------------------------------------


def _call_claude(snap: StateSnapshot, question: Optional[str]) -> Optional[str]:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=EXEC_MODEL,
            max_tokens=EXEC_MAX_TOKENS,
            system=_SYSTEM,
            messages=[{"role": "user", "content": _user_prompt(snap, question)}],
        )
        return resp.content[0].text if resp.content else ""
    except Exception as e:  # noqa: BLE001
        logger.warning("executive_status: claude call failed: %s", e)
        return None


def _mock_briefing(snap: StateSnapshot, question: Optional[str]) -> str:
    """Deterministic placeholder used when ANTHROPIC_API_KEY is absent.
    Lets the endpoint smoke-test end-to-end without LLM cost."""
    intro = (
        f"[Modo demo — sin LLM]\n"
        f"Reporte ejecutivo Circle LLC.\n\n"
    )
    if question:
        intro = f"[Modo demo — sin LLM] Pregunta: {question[:80]}\n\n"
    return (
        intro
        + f"HEADLINE\n"
        + f"  Cazador: {snap.signals_total} señales (+{snap.signals_new_24h} en 24h). "
        + f"{snap.runs_pass} pass / {snap.runs_kill} kill / {snap.runs_iterate} iterate.\n\n"
        + f"HIGHLIGHTS\n"
        + f"  - {snap.sources_active}/{snap.sources_total} fuentes activas\n"
        + f"  - Autonomía: {snap.autonomy_level}\n"
        + f"  - Agentes registrados: {snap.agents_count}\n\n"
        + f"RIESGOS\n"
        + (f"  - 0 runs todavía — el funnel no se está ejercitando.\n" if snap.runs_total == 0 else "")
        + (f"  - Autonomía en manual — el cazador no se auto-prioriza.\n" if snap.autonomy_level == "manual" else "")
        + f"\nPRÓXIMOS PASOS\n"
        + f"  - Disparar un /gate/run para validar la pipeline end-to-end.\n"
        + f"  - Revisar las top {len(snap.sources_top_quality)} fuentes por quality_score.\n"
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def briefing(question: Optional[str] = None) -> ExecutiveBriefing:
    """Run the briefing. In mock mode (no API key) returns a deterministic
    placeholder. NEVER raises — LLM failures degrade to mock briefing."""
    snap = collect_state()
    is_mock = not os.getenv("ANTHROPIC_API_KEY")
    raw: Optional[str] = None
    if not is_mock:
        raw = _call_claude(snap, question)
    if not raw:
        raw = _mock_briefing(snap, question)
        is_mock = True

    summary, highlights, risks, asks = _parse_sections(raw)
    return ExecutiveBriefing(
        summary=summary,
        body=raw,
        highlights=highlights,
        risks=risks,
        asks=asks,
        snapshot=snap,
        mode="qa" if question else "report",
        question=question,
        cost_usd_estimated=0.0 if is_mock else 0.008,
        mock_mode=is_mock,
    )


def _parse_sections(text: str) -> tuple[str, List[str], List[str], List[str]]:
    """Best-effort split of the LLM output into headline + sections.

    The system prompt asks for HEADLINE / HIGHLIGHTS / RIESGOS / PRÓXIMOS
    PASOS but LLMs sometimes drift. We pattern-scan for those headers
    (case-insensitive) and collect bullet lines under each.
    """
    headline = ""
    buckets: Dict[str, List[str]] = {
        "highlights": [], "risks": [], "asks": [],
    }
    current = None
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        low = line.lower()
        if not line:
            continue
        # Section detection
        if "headline" in low and ":" not in low:
            current = "headline"
            continue
        if "highlight" in low and len(line) < 40:
            current = "highlights"
            continue
        if ("riesgo" in low or "risks" in low or "watch" in low) and len(line) < 40:
            current = "risks"
            continue
        if (("próxim" in low or "proxim" in low or "next" in low or "ask" in low)
                and len(line) < 60):
            current = "asks"
            continue
        # Content
        if current == "headline":
            if not headline:
                headline = line[:200]
            else:
                headline = (headline + " " + line)[:200]
        elif current in buckets:
            # Strip leading bullet markers
            cleaned = line.lstrip("-•*").strip()
            if cleaned:
                buckets[current].append(cleaned[:280])
    if not headline:
        # Fall back to first non-empty line
        for line in (text or "").splitlines():
            if line.strip():
                headline = line.strip()[:200]
                break
    return headline, buckets["highlights"][:6], buckets["risks"][:6], buckets["asks"][:6]


__all__ = [
    "StateSnapshot",
    "ExecutiveBriefing",
    "collect_state",
    "briefing",
]
