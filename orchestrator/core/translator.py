"""
M9.1 — scrape-time translator (Claude Haiku).

Before M9.1, translation was on-demand: every time the founder clicked
"🌐 Traducir" the backend made a fresh Haiku call. That meant:
  - First view of a signal is always in the original language
  - Repeat views of the same signal cost LLM tokens N times
  - Lists of signals showed mixed-language theme/excerpt

M9.1 flips it: at scrape time, if user_settings.auto_translate_to is set
AND the detected language differs from the target, we translate ONCE and
persist `translated_theme` + `translated_excerpt` on the signal row. The
dashboard reads the translated fields directly.

Cost model: ~$0.001 per signal at scan time. For a 50-signal scan with
half non-Spanish that's ~$0.025 per run vs. unbounded clicks at $0.001/click
forever. Net win at >25 views per non-ES signal lifetime.

Safety:
  - Returns (None, None) on any failure (missing key, API error, parse fail)
  - Never raises — the caller treats translation as best-effort
  - In mock mode (no ANTHROPIC_API_KEY) returns deterministic placeholders
    so tests see predictable output without burning real tokens
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# Configurable via env in case we want to swap to a stronger model later.
_TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "claude-haiku-4-5")
_TRANSLATE_MAX_TOKENS = int(os.getenv("TRANSLATE_MAX_TOKENS", "800"))


def _is_mock_mode() -> bool:
    return not os.getenv("ANTHROPIC_API_KEY")


def translate_text(
    theme: str,
    excerpt: str,
    target_lang: str = "es",
) -> Tuple[Optional[str], Optional[str]]:
    """Translate (theme, excerpt) → (theme_translated, excerpt_translated).

    Returns (None, None) if any failure occurs. Callers MUST treat this as
    best-effort and never block the signal save on translation.

    Args:
        theme:        Short title (under 200 chars typically).
        excerpt:      Long-form summary (max 1500 chars sent to LLM).
        target_lang:  Two-letter language code ("es", "en", ...). The Haiku
                      prompt expands this into natural language for clarity.
    """
    if not theme and not excerpt:
        return None, None
    if not target_lang:
        return None, None

    # In mock mode, emit a deterministic placeholder so tests can assert behavior
    # without real API calls.
    if _is_mock_mode():
        return (
            f"[Traducción demo] {theme}",
            f"[Traducción demo] {excerpt[:200]}",
        )

    target_phrase = _target_phrase(target_lang)
    prompt = (
        f"Traduce este título y resumen al {target_phrase}. "
        f"Mantén nombres propios y términos técnicos. Devuelve JSON puro con "
        f"keys 'theme' y 'excerpt'. NO añadas markdown ni explicaciones.\n\n"
        f"TITLE: {theme}\n\n"
        f"EXCERPT: {(excerpt or '')[:1500]}"
    )

    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=_TRANSLATE_MODEL,
            max_tokens=_TRANSLATE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text if resp.content else ""
        return _parse_translation_json(raw, theme, excerpt)
    except Exception as e:  # noqa: BLE001 — best-effort path
        logger.warning("translator: scrape-time translation failed: %s", e)
        return None, None


def _target_phrase(code: str) -> str:
    """Convert 'es' / 'en' to a natural-language target spec for the LLM."""
    code = (code or "").lower().strip()
    mapping = {
        "es": "español neutro (LATAM)",
        "es-mx": "español de México",
        "es-ec": "español de Ecuador",
        "en": "English",
        "en-us": "English (US)",
        "en-gb": "English (UK)",
        "pt": "português",
        "fr": "français",
        "de": "Deutsch",
    }
    return mapping.get(code, code)


def _parse_translation_json(
    raw: str, fallback_theme: str, fallback_excerpt: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Strict-then-loose JSON parsing.

    The model may wrap output in fences (```json ... ```), or add a
    preamble. We try strict json.loads first, then fall back to extracting
    {"theme": ..., "excerpt": ...} via a brace scan.
    """
    text = (raw or "").strip()
    if not text:
        return None, None

    # Strip common markdown fences
    if text.startswith("```"):
        # Drop opening fence (possibly with language tag) and closing fence
        text = text.split("\n", 1)[-1].rstrip()
        if text.endswith("```"):
            text = text[:-3].rstrip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Loose extraction: find first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None, None
        try:
            data = json.loads(text[start: end + 1])
        except json.JSONDecodeError:
            return None, None

    if not isinstance(data, dict):
        return None, None

    theme_t = data.get("theme")
    excerpt_t = data.get("excerpt")
    if not isinstance(theme_t, str) or not isinstance(excerpt_t, str):
        return None, None
    if not theme_t.strip():
        return None, None
    return theme_t.strip(), excerpt_t.strip()


__all__ = ["translate_text"]
