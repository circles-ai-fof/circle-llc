"""
M11.1 — Selective adversarial callback (per ADR-028).

Triggered by gate_decider AFTER the 4-LLM ensemble vote, ONLY when the
final_confidence falls in the borderline band [ADV_BAND_LOW, ADV_BAND_HIGH]
(default 0.6 - 0.8). The check asks a single LLM (Grok by default, Claude
fallback) to play devil's advocate and find specific reasons why the
verdict is wrong. If it finds >= MIN_OBJECTIONS strong objections, the
verdict is downgraded to "iterate" so the workflow asks for more evidence
instead of pushing forward on a shaky 3-of-4 majority.

This is NOT a Governor pattern:
  - The callback is hard-coded in gate_decider (no LLM decides who to call)
  - One-shot direction (adversarial cannot call back)
  - Bounded by confidence band (skipped for clear PASS/KILL)
  - Fixed role: "find 3 reasons this verdict is wrong" — not free conversation

See ADR-028 for the full rationale + revisit criteria.

Activation:
  ADVERSARIAL_CALLBACK_ENABLED=true  # default off until we calibrate
  M111_ADV_BAND_LOW=0.6
  M111_ADV_BAND_HIGH=0.8
  M111_MIN_OBJECTIONS=2

The check is cost-bounded: only ~30% of runs fall in the band, each costs
~$0.005 (single Haiku/Grok call). Net: ~$1.50 per 100 runs.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _band_low() -> float:
    return float(os.getenv("M111_ADV_BAND_LOW", "0.6"))


def _band_high() -> float:
    return float(os.getenv("M111_ADV_BAND_HIGH", "0.8"))


def _min_objections() -> int:
    return int(os.getenv("M111_MIN_OBJECTIONS", "2"))


def adversarial_enabled() -> bool:
    return os.getenv("ADVERSARIAL_CALLBACK_ENABLED", "false").lower() in {
        "true", "1", "yes",
    }


def in_borderline_band(confidence: float) -> bool:
    """Whether the gate's final_confidence is in the band that triggers
    the adversarial callback."""
    return _band_low() <= float(confidence) <= _band_high()


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------


@dataclass
class Objection:
    """One specific reason the adversarial check thinks the verdict is wrong."""
    severity: str   # "weak" | "strong" — we only count `strong` against the verdict
    text: str       # human-readable explanation


@dataclass
class AdversarialResult:
    """Output of the adversarial check + whether the verdict was degraded."""
    original_verdict: str
    final_verdict: str          # may differ from original if degraded
    confidence_in: float        # band-trigger confidence
    objections: List[Objection] = field(default_factory=list)
    degraded: bool = False
    provider: str = ""
    error: Optional[str] = None

    @property
    def strong_objection_count(self) -> int:
        return sum(1 for o in self.objections if o.severity == "strong")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You are an adversarial reviewer. The gate_decider just voted "
    "{verdict} for the idea below. Find the 2-3 STRONGEST reasons that "
    "verdict could be wrong. Be brutally honest — your job is to catch "
    "false positives, not validate. If you can't find strong objections, "
    "say so explicitly.\n\n"
    "Reply with JSON ONLY (no markdown), schema:\n"
    "{{\n"
    '  "objections": [\n'
    '    {{"severity": "strong" | "weak", "text": "<1-2 sentence reason>"}}\n'
    "  ]\n"
    "}}\n"
    "Only mark severity=\"strong\" if it's a deal-breaker (CAC>LTV, "
    "regulatory blocker, no real demand). Mark severity=\"weak\" for "
    "minor concerns. Empty list is a valid answer if the verdict is solid."
)


def _user_prompt(verdict: str, rationale: str, evidence: str) -> str:
    return (
        f"VERDICT TO CHALLENGE: {verdict}\n\n"
        f"RATIONALE GIVEN: {rationale[:600]}\n\n"
        f"EVIDENCE/METRICS:\n{evidence[:800]}\n\n"
        f"Find the 2-3 strongest reasons this {verdict} is wrong."
    )


# ---------------------------------------------------------------------------
# LLM callers — Grok preferred (contrarian), Claude fallback
# ---------------------------------------------------------------------------


def _call_grok(verdict: str, rationale: str, evidence: str) -> Optional[str]:
    """Use Grok via xAI's OpenAI-compatible endpoint. Grok's training on X
    makes it more willing to surface unpopular truths, which is exactly
    what the adversarial role needs."""
    api_key = os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("XAI_BASE_URL", "https://api.x.ai/v1"),
        )
        model_name = os.getenv("ADVERSARIAL_MODEL_GROK", "grok-3-mini")
        resp = client.chat.completions.create(
            model=model_name,
            max_tokens=500,
            messages=[
                {"role": "system", "content": _SYSTEM.format(verdict=verdict)},
                {"role": "user", "content": _user_prompt(verdict, rationale, evidence)},
            ],
        )
        return resp.choices[0].message.content or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("adversarial: grok failed: %s", e)
        return None


def _call_claude(verdict: str, rationale: str, evidence: str) -> Optional[str]:
    """Claude fallback when XAI_API_KEY is absent."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=os.getenv("ADVERSARIAL_MODEL_CLAUDE", "claude-haiku-4-5"),
            max_tokens=500,
            system=_SYSTEM.format(verdict=verdict),
            messages=[{"role": "user",
                       "content": _user_prompt(verdict, rationale, evidence)}],
        )
        return resp.content[0].text if resp.content else ""
    except Exception as e:  # noqa: BLE001
        logger.warning("adversarial: claude failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def _parse_objections(raw: str) -> List[Objection]:
    text = (raw or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rstrip()
        if text.endswith("```"):
            text = text[:-3].rstrip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(data, dict):
        return []
    items = data.get("objections")
    if not isinstance(items, list):
        return []
    out: List[Objection] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sev = str(item.get("severity", "")).strip().lower()
        txt = str(item.get("text", "")).strip()
        if sev not in {"strong", "weak"} or not txt:
            continue
        out.append(Objection(severity=sev, text=txt[:400]))
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_adversarial_check(
    verdict: str,
    confidence: float,
    rationale: str,
    evidence: str,
) -> AdversarialResult:
    """Per ADR-028: only fires inside the borderline band.

    Returns AdversarialResult with:
      - degraded=True + final_verdict='iterate' if >= MIN_OBJECTIONS strong
        objections were raised
      - degraded=False + final_verdict=original otherwise (band-skip, no
        objections, or LLM unavailable)
    """
    result = AdversarialResult(
        original_verdict=verdict,
        final_verdict=verdict,
        confidence_in=float(confidence),
    )

    if not adversarial_enabled():
        result.error = "ADVERSARIAL_CALLBACK_ENABLED=false"
        return result

    if not in_borderline_band(confidence):
        result.error = f"confidence {confidence:.2f} outside band [{_band_low():.2f}, {_band_high():.2f}]"
        return result

    # Try Grok first (contrarian voice), Claude fallback
    raw = _call_grok(verdict, rationale, evidence)
    if raw:
        result.provider = "xai"
    else:
        raw = _call_claude(verdict, rationale, evidence)
        if raw:
            result.provider = "claude"

    if not raw:
        result.error = "no LLM available for adversarial check"
        return result

    result.objections = _parse_objections(raw)

    if result.strong_objection_count >= _min_objections():
        result.final_verdict = "iterate"
        result.degraded = True
        logger.info(
            "adversarial: %d strong objections raised, degrading %s -> iterate",
            result.strong_objection_count, verdict,
        )

    return result


__all__ = [
    "Objection",
    "AdversarialResult",
    "run_adversarial_check",
    "in_borderline_band",
    "adversarial_enabled",
]
