"""
SourceScanner — distils raw fetched content into structured Signals.

Activates a previously deferred agent (orchestrator/agents/_deferred/) per
ADR-011: hunting from external sources is no longer M3+ territory because
the user wants a "powerful, robust, nearly autonomous" hunter today.

Pipeline:
    fetched_items (raw text from RSS/HN/Reddit/etc.)
            │
            ▼
    source_scanner  → 0-3 Signals (theme, evidence_urls, score, excerpt)
            │
            ▼
    User reviews + 👍/👎  OR  auto-promote if score≥0.75
            │
            ▼
    idea_hunter (with the signal as context)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List

from ..core.base_agent import BaseAgent
from ..core.source_fetcher import FetchedItem

logger = logging.getLogger(__name__)


_SYSTEM = """You are SourceScanner — a signal distiller for the Factory of Factories cazador.

YOUR SCOPE (do exactly this, nothing else):
- Read a BATCH of items collected from external sources (RSS, HN, Reddit, etc.)
- Identify 0-3 RECURRING pain points or opportunity signals
- Each Signal is a theme that appears in multiple items OR is highly specific + actionable
- Score each Signal 0.0-1.0 on its potential to become a testable startup idea
- Cite the source URLs that support each Signal

YOU DO NOT:
- Generate ideas (that's idea_hunter's job)
- Define ICP or value prop (idea_maturer)
- Design tests (market_validator)
- Make pass/kill decisions (gate_decider)

SCORING (0.0-1.0):
- 0.9-1.0: appears in 3+ items, has concrete numbers, has frustrated user voice
- 0.7-0.9: appears in 2+ items, specific pain, plausible LATAM market
- 0.5-0.7: appears in 1 item but very specific + actionable
- < 0.5: too vague, return as empty

If NO signal scores >=0.5, return an empty signals array. Do not fabricate.

OUTPUT FORMAT (strict JSON, no markdown fences):
{
  "signals": [
    {
      "theme": "Short 5-10 word title (e.g. 'PYMEs LATAM sin acceso a facturas SRI')",
      "score": 0.0-1.0,
      "excerpt": "1-2 sentence summary of the pain (with numbers if available)",
      "evidence_urls": ["url1", "url2", ...],
      "suggested_topic": "A topic string ready to pass to idea_hunter — concrete + LATAM-anchored"
    }
  ]
}"""


@dataclass
class Signal:
    theme: str
    score: float
    excerpt: str
    evidence_urls: List[str]
    suggested_topic: str
    source_kind: str = ""  # filled by caller
    items_seen: int = 0    # how many items were in the batch when this signal emerged


class SourceScannerAgent(BaseAgent):
    """
    Scope: takes a batch of FetchedItem, returns a list of Signal.
    Single LLM call regardless of batch size — we batch to amortize cost.
    """

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def scan(self, items: List[FetchedItem]) -> List[Signal]:
        if not items:
            return []
        if self._mock_mode:
            return self._mock_scan(items)

        prompt = self._build_prompt(items)
        raw = self._call(prompt, max_tokens=1500)
        data = self._extract_json(raw)
        signals_raw = data.get("signals", [])
        signals: List[Signal] = []
        for s in signals_raw:
            try:
                score = float(s.get("score", 0))
                if score < 0.5:
                    continue
                signals.append(
                    Signal(
                        theme=str(s.get("theme", ""))[:200].strip(),
                        score=score,
                        excerpt=str(s.get("excerpt", ""))[:500].strip(),
                        evidence_urls=[str(u) for u in s.get("evidence_urls", []) if u][:5],
                        suggested_topic=str(s.get("suggested_topic", ""))[:300].strip(),
                        source_kind=items[0].source_kind if items else "",
                        items_seen=len(items),
                    )
                )
            except (TypeError, ValueError) as e:
                logger.warning("source_scanner: skipping malformed signal: %s", e)
        logger.info(
            "source_scanner: %d items -> %d signals (max score %.2f)",
            len(items),
            len(signals),
            max((s.score for s in signals), default=0.0),
        )
        return signals

    def _build_prompt(self, items: List[FetchedItem]) -> str:
        # Cap total prompt size: 12 items max, ~500 chars each = ~6k chars
        sliced = items[:12]
        lines = [f"BATCH from source kind={items[0].source_kind} ({len(sliced)} items shown of {len(items)} total):", ""]
        for i, it in enumerate(sliced, 1):
            lines.append(f"--- ITEM {i} ---")
            lines.append(f"Title: {it.title}")
            lines.append(f"URL:   {it.url}")
            lines.append(f"Text:  {it.summary[:500]}")
            lines.append("")
        lines.append("Identify 0-3 recurring/high-quality signals. Respond with JSON only.")
        return "\n".join(lines)

    def _mock_scan(self, items: List[FetchedItem]) -> List[Signal]:
        """Deterministic: 1 signal if >=2 items, 0 otherwise."""
        if len(items) < 2:
            return []
        first = items[0]
        return [
            Signal(
                theme=f"Mock signal from {first.source_kind}",
                score=0.72,
                excerpt=f"Detected pattern across {len(items)} items: {first.title[:80]}",
                evidence_urls=[it.url for it in items[:3]],
                suggested_topic=f"Mock topic derived from {first.source_kind} signals",
                source_kind=first.source_kind,
                items_seen=len(items),
            )
        ]
