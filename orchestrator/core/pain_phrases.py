"""
M12.0 — Pain-phrase booster.

The OpportunityScout spec calls out a specific class of signal: people
expressing PAIN or unsolved NEED with explicit language. Examples in
English: "I wish there was", "why is there no", "anyone know a tool for",
"I hate that". In Spanish: "ojalá hubiera", "por qué no existe", "alguien
sabe de una herramienta", "odio que".

These phrases are SHORT, REPEATED, and DETECTABLE WITHOUT AN LLM. Adding a
heuristic match against them lets us boost the source_scanner's score for
signals that explicitly express pain, without spending tokens.

The booster runs over the text BEFORE the source_scanner LLM call. If
the text contains pain phrases, we:
  1. Boost the final signal.score by a fixed multiplier
  2. Add the matched phrase to item_titles so the founder sees WHY the
     signal was promoted (audit trail)

Multiplier defaults to 1.20 (20% boost), tunable via env. Cap is 1.0
so a 0.95 signal with 2 pain phrases doesn't become >1.0.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List

# Multiplier applied per pain-phrase match (capped at MAX_BOOST).
PAIN_BOOST_PER_MATCH = float(os.getenv("PAIN_BOOST_PER_MATCH", "0.10"))
MAX_BOOST = float(os.getenv("PAIN_BOOST_MAX", "0.30"))   # cap aggregate boost


# All phrases are stored as REGEX (case-insensitive). Word-boundary anchored
# where it matters (avoid matching "twisher" when looking for "i wish").
# Each is one of:
#   - explicit unmet need ("I wish there was X")
#   - frustration with status quo ("I hate that X")
#   - active search for tool ("anyone know a tool for X")
#   - missing-tool surprise ("why is there no X")
#
# Stored as (regex, language, label) so the audit trail shows what matched.
_PAIN_PATTERNS_EN: List[tuple[re.Pattern, str]] = [
    (re.compile(r"\bi\s+wish\s+(there|we|i)\s+(was|had|could)\b", re.I), "wish-there-was"),
    (re.compile(r"\bwhy\s+is\s+there\s+no\b", re.I), "why-is-there-no"),
    (re.compile(r"\bwhy\s+doesn'?t\s+(someone|anyone)\s+(make|build|create)\b", re.I), "why-doesnt-someone"),
    (re.compile(r"\b(anyone|anybody)\s+know\s+(of\s+)?a\s+(tool|app|way|service)\b", re.I), "anyone-know-a-tool"),
    (re.compile(r"\bis\s+there\s+(a|any|some)\s+(tool|app|way|service)\s+(to|for|that)\b", re.I), "is-there-a-tool"),
    (re.compile(r"\bi\s+(hate|can'?t\s+stand)\s+(that|when|how)\b", re.I), "i-hate-that"),
    (re.compile(r"\b(would\s+pay|i'?d\s+pay|i\s+would\s+pay)\s+(for|to)\b", re.I), "would-pay-for"),
    (re.compile(r"\bbiggest\s+(pain|frustration|annoyance)\b", re.I), "biggest-pain"),
    (re.compile(r"\b(struggle|struggling)\s+(with|to)\b", re.I), "struggling-with"),
    (re.compile(r"\bwasting\s+(time|hours|days)\s+(on|doing|trying)\b", re.I), "wasting-time"),
    (re.compile(r"\bmanually\s+(doing|tracking|copying|updating)\b", re.I), "manual-pain"),
]

_PAIN_PATTERNS_ES: List[tuple[re.Pattern, str]] = [
    (re.compile(r"\bojal[áa]\s+(hubiera|hubiese|existiera)\b", re.I), "ojala-existiera"),
    (re.compile(r"\bpor\s+qu[ée]\s+no\s+(existe|hay|tienen)\b", re.I), "por-que-no-existe"),
    (re.compile(r"\balguien\s+(sabe|conoce)\s+(de\s+)?(una|un|alguna|alg[úu]n)\s+(herramienta|app|aplicaci[óo]n|servicio|forma)\b", re.I), "alguien-conoce-tool"),
    (re.compile(r"\b(hay|existe)\s+(alguna|alg[úu]n|una|un)\s+(herramienta|app|servicio|forma)\s+(para|de)\b", re.I), "hay-alguna-herramienta"),
    (re.compile(r"\b(odio|detesto)\s+(que|cuando)\b", re.I), "odio-que"),
    (re.compile(r"\b(pagar[íi]a|pagar[íi]amos|pagar[íi]an)\s+(por|para)\b", re.I), "pagaria-por"),
    (re.compile(r"\b(mayor|peor)\s+(dolor|frustraci[óo]n|molestia)\b", re.I), "mayor-dolor"),
    (re.compile(r"\b(perdiendo|gastando)\s+(tiempo|horas|d[íi]as)\b", re.I), "perdiendo-tiempo"),
    (re.compile(r"\bmanualmente\s+(hago|copio|llevo|actualizo)\b", re.I), "manualmente-hacer"),
    (re.compile(r"\bme\s+(canso|cansa)\s+(de|que)\b", re.I), "me-canso-de"),
]


@dataclass
class PainMatch:
    """One pain-phrase hit found in the text."""
    label: str          # which pattern matched (e.g. "wish-there-was")
    snippet: str        # short excerpt around the match (max 160 chars)
    language: str       # "en" | "es" | "mixed"


def detect_pain_phrases(text: str) -> List[PainMatch]:
    """Return every pain phrase found in the text.

    Each match includes a short snippet so callers can surface WHY a signal
    was boosted (auditability — the founder should see the actual pain
    sentence, not just "boosted by +20%").
    """
    if not text:
        return []
    matches: List[PainMatch] = []
    for pattern, label in _PAIN_PATTERNS_EN:
        for m in pattern.finditer(text):
            matches.append(PainMatch(
                label=label,
                snippet=_excerpt_around(text, m.start(), m.end()),
                language="en",
            ))
    for pattern, label in _PAIN_PATTERNS_ES:
        for m in pattern.finditer(text):
            matches.append(PainMatch(
                label=label,
                snippet=_excerpt_around(text, m.start(), m.end()),
                language="es",
            ))
    return matches


def compute_pain_boost(matches: List[PainMatch]) -> float:
    """How much to multiply the original signal score.

    Returns a value in [1.0, 1.0 + MAX_BOOST]. Stacks linearly with
    diminishing returns — multiple matches on the same label count once
    (otherwise spammy "I wish I wish I wish" gets unrealistic boost).
    """
    if not matches:
        return 1.0
    unique_labels = {m.label for m in matches}
    boost = len(unique_labels) * PAIN_BOOST_PER_MATCH
    boost = min(boost, MAX_BOOST)
    return 1.0 + boost


def apply_boost(score: float, text: str) -> tuple[float, List[PainMatch]]:
    """Convenience: detect + apply in one call, clamped to [0, 1].

    Returns (new_score, matches). The matches list is empty when the text
    has no pain phrases. New score never exceeds 1.0 (the original ceiling).
    """
    matches = detect_pain_phrases(text or "")
    if not matches:
        return float(score), []
    multiplier = compute_pain_boost(matches)
    new = float(score) * multiplier
    return min(1.0, new), matches


def _excerpt_around(text: str, start: int, end: int, radius: int = 60) -> str:
    """Return up to ~160 chars centered on the match for the audit trail."""
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    excerpt = text[lo:hi].strip()
    excerpt = re.sub(r"\s+", " ", excerpt)
    if lo > 0:
        excerpt = "…" + excerpt
    if hi < len(text):
        excerpt = excerpt + "…"
    return excerpt[:160]


__all__ = [
    "PainMatch",
    "detect_pain_phrases",
    "compute_pain_boost",
    "apply_boost",
    "PAIN_BOOST_PER_MATCH",
    "MAX_BOOST",
]
