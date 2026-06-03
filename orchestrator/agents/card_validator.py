"""
M11.0 — CardValidator (Claude vision).

The app_marketplace fetcher (M9.2) surfaces cards from Lovable / Claude
Creations / Adorable APP. Many of those cards are FIGMA MOCKUPS — pretty
screenshots of UI ideas that never shipped. Without filtering, the cazador
ranks them the same as real working apps and the founder wastes attention.

This agent inspects the card's image (logo, hero screenshot, thumbnail)
with Claude vision and returns:

  - kind:        "real_app" | "mockup" | "unknown"
  - confidence:  0.0-1.0
  - rationale:   1-2 lines explaining the call

Heuristics Claude is asked to apply:
  - Real apps tend to show UI with realistic data (numbers, names, dates),
    not lorem ipsum or filler labels.
  - Mockups often have over-perfect typography, "Title" placeholders, or
    Figma frame shadows.
  - Logos alone (no UI) are inconclusive → "unknown" (don't penalize).

Cost: ~$0.0015-0.003 per image with claude-haiku-4-5 (vision). Capped per
day at MAX_VALIDATIONS_PER_DAY (default 50) so a runaway scan doesn't
empty the LLM budget.

Safety:
  - Returns "unknown" + score 0.5 (neutral) if the image can't be fetched
  - Returns "unknown" if Claude raises (best-effort, never blocks the scan)
  - In mock mode (no API key) returns deterministic placeholder
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

MAX_VALIDATIONS_PER_DAY = int(os.getenv("M110_MAX_VALIDATIONS", "50"))
VISION_MODEL = os.getenv("VISION_MODEL", "claude-haiku-4-5")
VISION_MAX_TOKENS = int(os.getenv("VISION_MAX_TOKENS", "300"))

# Score multipliers we apply downstream. mockup → kill, real → keep.
SCORE_MULTIPLIER_MOCKUP = 0.3
SCORE_MULTIPLIER_REAL = 1.0
SCORE_MULTIPLIER_UNKNOWN = 0.85   # mild penalty — vision couldn't decide


@dataclass
class CardValidation:
    """Verdict of a single card inspection."""
    kind: str               # "real_app" | "mockup" | "unknown"
    confidence: float       # 0.0-1.0
    rationale: str
    image_url: str = ""

    @property
    def score_multiplier(self) -> float:
        if self.kind == "mockup":
            return SCORE_MULTIPLIER_MOCKUP
        if self.kind == "real_app":
            return SCORE_MULTIPLIER_REAL
        return SCORE_MULTIPLIER_UNKNOWN


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are CardValidator. You inspect screenshots/logos of products listed "
    "on AI-app marketplaces (Lovable, Claude Creations, Adorable APP, etc.) "
    "and decide whether they look like a REAL working app or a Figma MOCKUP "
    "/ placeholder. \n\n"
    "Signals that point to MOCKUP:\n"
    "  - Lorem ipsum or placeholder labels (Title, Heading, Item 1)\n"
    "  - Over-clean Figma frame shadows around the whole thing\n"
    "  - No realistic data (no numbers, names, dates with variation)\n"
    "  - Identical UI repeated multiple times (template feel)\n"
    "Signals that point to REAL_APP:\n"
    "  - Concrete numbers / dates / names\n"
    "  - UI shows interaction states (selected, expanded, error)\n"
    "  - Imperfections — slightly misaligned things, real user data\n"
    "When unsure (logo alone, abstract art), reply UNKNOWN — do not guess.\n\n"
    "Reply with exactly this format (one line each, no markdown):\n"
    "KIND: real_app | mockup | unknown\n"
    "CONFIDENCE: <float 0.0-1.0>\n"
    "RATIONALE: <one short sentence>"
)


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------

def _mock_validation(image_url: str) -> CardValidation:
    """Mock mode: deterministic placeholder so tests don't burn tokens."""
    return CardValidation(
        kind="unknown",
        confidence=0.5,
        rationale="[mock_mode] vision not invoked — set ANTHROPIC_API_KEY",
        image_url=image_url,
    )


def validate_card(image_url: str) -> CardValidation:
    """Inspect a single card image and return a verdict.

    Best-effort: any exception (network, parse, API) returns "unknown" with
    a neutral score so the caller never breaks the scan.
    """
    if not image_url or not isinstance(image_url, str):
        return CardValidation(
            kind="unknown", confidence=0.5,
            rationale="empty image_url", image_url=image_url or "",
        )

    if not os.getenv("ANTHROPIC_API_KEY"):
        return _mock_validation(image_url)

    try:
        import anthropic
        client = anthropic.Anthropic()
        # Use the URL source — Anthropic fetches the image server-side, no
        # need to download + base64 here.
        resp = client.messages.create(
            model=VISION_MODEL,
            max_tokens=VISION_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "url", "url": image_url,
                    }},
                    {"type": "text",
                     "text": "Inspect this card and reply with the 3-line format."},
                ],
            }],
        )
        text = resp.content[0].text if resp.content else ""
        return _parse_verdict(text, image_url)
    except Exception as e:  # noqa: BLE001 — best effort
        logger.warning("card_validator: failed for %s: %s", image_url, e)
        return CardValidation(
            kind="unknown", confidence=0.5,
            rationale=f"vision error: {type(e).__name__}",
            image_url=image_url,
        )


def _parse_verdict(text: str, image_url: str) -> CardValidation:
    """Parse 'KIND: ... / CONFIDENCE: ... / RATIONALE: ...' format."""
    if not text:
        return CardValidation(
            kind="unknown", confidence=0.5,
            rationale="empty model response", image_url=image_url,
        )

    kind = "unknown"
    confidence = 0.5
    rationale = ""

    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("kind:"):
            v = line.split(":", 1)[1].strip().lower()
            if "mockup" in v:
                kind = "mockup"
            elif "real_app" in v or "real-app" in v or v == "real":
                kind = "real_app"
            elif "unknown" in v:
                kind = "unknown"
        elif low.startswith("confidence:"):
            try:
                v = line.split(":", 1)[1].strip()
                confidence = max(0.0, min(1.0, float(v)))
            except (ValueError, IndexError):
                pass
        elif low.startswith("rationale:"):
            rationale = line.split(":", 1)[1].strip()

    if not rationale:
        rationale = text.strip()[:200]

    return CardValidation(
        kind=kind, confidence=confidence,
        rationale=rationale, image_url=image_url,
    )


# ---------------------------------------------------------------------------
# Batch entry — used by the scan path with a budget cap
# ---------------------------------------------------------------------------

def validate_cards_batch(
    image_urls: list[str],
    max_validations: Optional[int] = None,
) -> list[CardValidation]:
    """Validate multiple cards with a hard cap.

    Caller is expected to pass `max_validations` based on a per-day budget
    tracked in the store. Anything past the cap returns "unknown" without
    invoking the LLM.
    """
    cap = max_validations if max_validations is not None else MAX_VALIDATIONS_PER_DAY
    out: list[CardValidation] = []
    for i, url in enumerate(image_urls or []):
        if i >= cap:
            out.append(CardValidation(
                kind="unknown", confidence=0.5,
                rationale="batch cap reached — try again tomorrow",
                image_url=url,
            ))
            continue
        out.append(validate_card(url))
    return out


__all__ = [
    "CardValidation",
    "validate_card",
    "validate_cards_batch",
    "MAX_VALIDATIONS_PER_DAY",
    "SCORE_MULTIPLIER_MOCKUP",
    "SCORE_MULTIPLIER_REAL",
    "SCORE_MULTIPLIER_UNKNOWN",
]
