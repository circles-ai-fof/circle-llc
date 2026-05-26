"""
Multi-LLM ensemble client — opt-in fan-out to Claude + GPT + Gemini.

Justification: Reganti Cap 8 §8.6 — "Ensembles only where they buy real accuracy.
Use for the FINAL gate decision, never for the workflow's body, where prompt
calibration on one strong model beats ensemble overhead."

Activation:
- ENSEMBLE_GATE_ENABLED=true       → triggers ensemble in gate_decider
- ANTHROPIC_API_KEY                → Claude (required, baseline)
- OPENAI_API_KEY                   → GPT-4 (optional)
- GOOGLE_API_KEY                   → Gemini (optional)

If a provider key is missing the ensemble degrades gracefully to the available
ones. With only Claude available it returns the single Claude vote.
"""
from __future__ import annotations

import logging
import os
from collections import Counter
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EnsembleVote:
    provider: str
    model: str
    verdict: str         # "pass" | "kill" | "iterate"
    confidence: float
    rationale: str


@dataclass
class EnsembleResult:
    final_verdict: str
    final_confidence: float
    votes: list[EnsembleVote]
    agreement_pct: float

    @property
    def unanimous(self) -> bool:
        return self.agreement_pct == 1.0


def _ensemble_enabled() -> bool:
    return os.getenv("ENSEMBLE_GATE_ENABLED", "false").lower() in {"true", "1", "yes"}


def _vote_claude(prompt: str, system: str) -> Optional[EnsembleVote]:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text if resp.content else ""
        return _parse_vote("claude", "claude-sonnet-4-6", text)
    except Exception as e:  # noqa: BLE001
        logger.warning("ensemble: claude vote failed: %s", e)
        return None


def _vote_openai(prompt: str, system: str) -> Optional[EnsembleVote]:
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=400,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        text = resp.choices[0].message.content or ""
        return _parse_vote("openai", "gpt-4o-mini", text)
    except Exception as e:  # noqa: BLE001
        logger.warning("ensemble: openai vote failed: %s", e)
        return None


def _vote_gemini(prompt: str, system: str) -> Optional[EnsembleVote]:
    if not os.getenv("GOOGLE_API_KEY"):
        return None
    # Try new google-genai SDK first (recommended in 2026)
    client = None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        model_name = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
        # Build request (hold `client` in a local — chained calls close the
        # underlying httpx client before the response arrives).
        resp = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=400,
            ),
        )
        text = (resp.text or "") if hasattr(resp, "text") else ""
        return _parse_vote("google", model_name, text)
    except ImportError:
        # Fall back to legacy SDK
        try:
            import google.generativeai as legacy_genai
            legacy_genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
            model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            model = legacy_genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system,
            )
            resp = model.generate_content(prompt)
            text = resp.text or ""
            return _parse_vote("google", model_name, text)
        except Exception as e:  # noqa: BLE001
            logger.warning("ensemble: gemini vote failed (legacy): %s", e)
            return None
    except Exception as e:  # noqa: BLE001
        logger.warning("ensemble: gemini vote failed: %s", e)
        return None


def _parse_vote(provider: str, model: str, text: str) -> Optional[EnsembleVote]:
    """
    Parse a verdict from free-form LLM text. Expects: "VERDICT: pass|kill|iterate"
    on first line. Falls back to keyword detection.
    """
    text = text.strip().lower()
    verdict = None
    confidence = 0.7
    for keyword in ("pass", "kill", "iterate"):
        if f"verdict: {keyword}" in text[:60] or text.startswith(keyword):
            verdict = keyword
            break
    if verdict is None:
        # last-resort keyword detection
        counts = {k: text.count(k) for k in ("pass", "kill", "iterate")}
        verdict = max(counts, key=counts.get) if any(counts.values()) else None
    if verdict is None:
        return None
    # crude confidence extraction
    import re
    m = re.search(r"confidence[:\s]+([0-9.]+)", text)
    if m:
        try:
            confidence = max(0.0, min(1.0, float(m.group(1))))
        except ValueError:
            pass
    return EnsembleVote(
        provider=provider,
        model=model,
        verdict=verdict,
        confidence=confidence,
        rationale=text[:300],
    )


def gate_ensemble_vote(prompt: str, system: str) -> EnsembleResult:
    """
    Fan out the prompt to all configured providers.
    Returns EnsembleResult with majority verdict.
    """
    votes: list[EnsembleVote] = []
    for fn in (_vote_claude, _vote_openai, _vote_gemini):
        vote = fn(prompt, system)
        if vote:
            votes.append(vote)

    if not votes:
        # No providers available — caller should fall back to single-LLM path
        return EnsembleResult(
            final_verdict="iterate",
            final_confidence=0.0,
            votes=[],
            agreement_pct=0.0,
        )

    verdicts = [v.verdict for v in votes]
    counts = Counter(verdicts)
    top, top_count = counts.most_common(1)[0]
    agreement_pct = top_count / len(votes)
    avg_confidence = sum(v.confidence for v in votes if v.verdict == top) / top_count
    # Cap confidence by agreement: 3/3 = full conf, 2/3 = 0.75x, 1/3 = 0.5x
    final_confidence = avg_confidence * agreement_pct

    logger.info(
        "ensemble: %d votes, majority=%s (%d/%d), confidence=%.2f",
        len(votes),
        top,
        top_count,
        len(votes),
        final_confidence,
    )
    return EnsembleResult(
        final_verdict=top,
        final_confidence=final_confidence,
        votes=votes,
        agreement_pct=agreement_pct,
    )


# Public API
__all__ = ["EnsembleVote", "EnsembleResult", "gate_ensemble_vote", "_ensemble_enabled"]
