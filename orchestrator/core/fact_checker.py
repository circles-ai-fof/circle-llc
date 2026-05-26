"""
Cross-LLM fact-check on numerical claims (ADR-008).

Uses Gemini (cheapest, distinct training corpus) to verify numerical claims
produced by idea_enricher. NOT debate, NOT consensus — single-shot binary check.

Activation:
- FACT_CHECK_ENABLED=true
- GOOGLE_API_KEY set
- Not in mock_mode

Falls back to no-op (empty list) if disabled or provider fails.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

# Regex covers: "60%", "30-50%", "$1,200", "$1.5M", "90 dias", "12 horas/semana",
# "4+ horas/dia", "1k usuarios", "X de N empresas", etc.
_CLAIM_PATTERN = re.compile(
    r"""(
        \d+(?:[.,]\d+)?\s*[%]                       # percentages: 60%, 30.5%
      | \$\s?\d+(?:[.,]\d+)?\s*[KMB]?               # money: $1,200, $1.5M
      | \d+(?:[.,]\d+)?\s*\+?\s*(?:horas?|dias?|     # time durations
            semanas?|meses?|min(?:utos?)?|seg(?:undos?)?)
            (?:[/-]\w+)?                              # optional /dia, /semana
      | \d+(?:[.,]\d+)?\s*[KMB]\s+\w+                # 50K usuarios, 10M PYMEs
      | \d+\s+de\s+\w+\s+\w+                         # "3 de cada 10 ..."
    )""",
    re.IGNORECASE | re.VERBOSE,
)


@dataclass
class Claim:
    text: str          # the matched snippet, e.g. "60%"
    context: str       # surrounding sentence


@dataclass
class FactCheckResult:
    claim: Claim
    verdict: str       # "SUPPORTED" | "UNSUPPORTED" | "NEEDS_VERIFICATION"
    rationale: str
    checker_model: str


def fact_check_enabled() -> bool:
    return (
        os.getenv("FACT_CHECK_ENABLED", "false").lower() in {"true", "1", "yes"}
        and bool(os.getenv("GOOGLE_API_KEY"))
    )


def extract_claims(text: str, max_claims: int = 6) -> List[Claim]:
    """Cheap regex extraction. Returns at most `max_claims` Claim objects."""
    if not text:
        return []
    claims: List[Claim] = []
    seen: set[str] = set()
    for m in _CLAIM_PATTERN.finditer(text):
        snippet = m.group(0).strip()
        if snippet in seen:
            continue
        seen.add(snippet)
        # Walk back/forward to grab the sentence containing the match
        start = max(0, text.rfind(".", 0, m.start()) + 1)
        end = text.find(".", m.end())
        end = len(text) if end == -1 else end
        context = text[start:end].strip()
        claims.append(Claim(text=snippet, context=context))
        if len(claims) >= max_claims:
            break
    return claims


def _check_with_gemini(claim: Claim) -> Optional[FactCheckResult]:
    """Single-shot Gemini call. Returns None on transport failure."""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        model_name = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

        system = (
            "You are a fact-checker for business claims. Given a specific "
            "numerical claim (e.g. '60% PYMEs Ecuador') with its surrounding "
            "sentence, decide if the claim is plausible given general market "
            "knowledge. Respond in EXACTLY this format on the FIRST line:\n"
            "VERDICT: SUPPORTED | UNSUPPORTED | NEEDS_VERIFICATION\n"
            "Then on a second line a 1-sentence rationale.\n\n"
            "Rules:\n"
            "- SUPPORTED: the number is consistent with broadly known data\n"
            "- UNSUPPORTED: the number contradicts known data or is fabricated\n"
            "- NEEDS_VERIFICATION: the topic is too niche to evaluate\n"
            "Be honest. Prefer NEEDS_VERIFICATION over guessing."
        )
        prompt = f'Claim: "{claim.text}"\nContext: "{claim.context}"\n\nVerdict?'

        resp = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=200,
            ),
        )
        text = (resp.text or "").strip()

        # Parse first-line verdict
        verdict = "NEEDS_VERIFICATION"
        for v in ("SUPPORTED", "UNSUPPORTED", "NEEDS_VERIFICATION"):
            if f"verdict: {v.lower()}" in text.lower()[:80]:
                verdict = v
                break

        # Rationale = remaining lines, trimmed
        lines = text.splitlines()
        rationale = " ".join(l.strip() for l in lines[1:] if l.strip())[:240]
        if not rationale:
            rationale = text[:240]

        return FactCheckResult(
            claim=claim,
            verdict=verdict,
            rationale=rationale,
            checker_model=model_name,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("fact_check: gemini failed for claim %r: %s", claim.text, e)
        return None


def fact_check_claims(text: str, mock_mode: bool = False) -> List[FactCheckResult]:
    """
    Public entry point. Returns list of FactCheckResult.
    Empty list when disabled, no claims, or provider failure.
    Mock mode returns 1 SUPPORTED + 1 UNSUPPORTED deterministically (for tests).
    """
    claims = extract_claims(text)
    if not claims:
        return []

    if mock_mode:
        # Deterministic mock: alternate verdicts so tests can assert behavior
        verdicts = ["SUPPORTED", "UNSUPPORTED", "NEEDS_VERIFICATION"]
        return [
            FactCheckResult(
                claim=c,
                verdict=verdicts[i % len(verdicts)],
                rationale=f"Mock check for {c.text!r}",
                checker_model="mock",
            )
            for i, c in enumerate(claims)
        ]

    if not fact_check_enabled():
        return []

    results: List[FactCheckResult] = []
    for claim in claims:
        r = _check_with_gemini(claim)
        if r is not None:
            results.append(r)
    return results


def count_unsupported(results: List[FactCheckResult]) -> int:
    return sum(1 for r in results if r.verdict == "UNSUPPORTED")


__all__ = [
    "Claim",
    "FactCheckResult",
    "extract_claims",
    "fact_check_claims",
    "fact_check_enabled",
    "count_unsupported",
]
