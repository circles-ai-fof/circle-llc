"""
M9.4 — SourceDiscoveryAgent.

Closes the loop on the cazador's preferences engine. Today M4.1 clusters
approved signals and surfaces shared keywords; this agent takes those
keywords and proposes NEW URLs/feeds/subreddits the founder could add.

The pipeline:

  approved signals
       │
       ▼
  preferences.suggest_sources_from_clusters() -> shared keywords
       │
       ▼
  SourceDiscoveryAgent.discover(keywords)  ← this module
       │
       ▼
  list of ProposedSource  -> /cazar/fuentes review queue

The agent ASKS an LLM for plausible sources. It defaults to Gemini because
Gemini has live Google Search grounding (ideal for "what blogs / feeds
exist about X"), but falls back to Claude if GOOGLE_API_KEY is absent.

Safety:
- Returns [] gracefully if no LLM key is configured
- Caps proposals at MAX_PROPOSALS_PER_CALL (default 5) so a single discovery
  request can't flood the dashboard
- Validates that proposed `kind` strings are in the supported set
- De-dupes against existing sources before returning so the founder doesn't
  see "add HN" when HN is already active

NOT in scope here (deferred to later sprints):
- LLM-driven crawling of proposed URLs to verify they exist
- Auto-add to sources table (always requires explicit approval)
- Quality scoring of proposed sources (M9.5 takes over once they're added)
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)


MAX_PROPOSALS_PER_CALL = int(os.getenv("M94_MAX_PROPOSALS", "5"))

# Supported source kinds — must match what fetch_by_kind() dispatches.
# If the LLM proposes a kind outside this set we drop the proposal.
_SUPPORTED_KINDS = {
    "rss", "url", "hn", "reddit", "github_trending", "product_hunt",
    "youtube", "bluesky", "telegram", "events", "sec_edgar",
    "google_trends", "app_marketplace",
}


@dataclass
class ProposedSource:
    """Same shape as link_follower.ProposedSource so the dashboard can render
    proposals from both agents in one unified queue."""
    kind: str
    target: str
    name: str
    reason: str
    origin_url: str = ""    # M9.4 leaves this blank; LLM proposes from scratch
    score: float = 0.5


@dataclass
class DiscoveryResult:
    keywords: List[str]
    proposals: List[ProposedSource] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    llm_provider: str = ""    # "google" | "claude" | "" (none available)


# ---------------------------------------------------------------------------
# LLM callers — best-effort, gracefully fall back
# ---------------------------------------------------------------------------

def _system_prompt() -> str:
    return (
        "You are SourceDiscoveryAgent for a startup-validation platform. "
        "The user gives you keywords drawn from a cluster of business ideas "
        "the founder has already APPROVED — they signal what kind of signals "
        "the founder wants more of. Propose 3-5 specific NEW content sources "
        "(blog feeds, subreddits, github topic pages, telegram channels) that "
        "would surface MORE ideas in this space.\n\n"
        f"VALID kinds (use these exactly): {sorted(_SUPPORTED_KINDS)}\n\n"
        "Return JSON ONLY (no markdown, no preamble). Schema:\n"
        '{ "proposals": [\n'
        '    {"kind": "<kind>", "target": "<url or subreddit name>",\n'
        '     "name": "<human readable label>",\n'
        '     "reason": "<one sentence why this matches the keywords>"} ]\n'
        "}\n"
        "Constraints:\n"
        "  - target for 'reddit' is the subreddit NAME only (e.g. 'SaaS'), not the URL.\n"
        "  - target for 'rss' is the feed URL.\n"
        "  - target for 'url' is a landing/article URL (single fetch).\n"
        "  - Do NOT propose Twitter/X (paywalled API).\n"
        "  - Do NOT propose LinkedIn (no public API).\n"
    )


def _user_prompt(keywords: Iterable[str]) -> str:
    kw_list = ", ".join(keywords) or "(no keywords provided)"
    return (
        f"Cluster keywords from approved signals: {kw_list}\n\n"
        f"Propose 3-5 specific new sources the cazador should monitor."
    )


def _call_gemini(keywords: List[str]) -> Optional[str]:
    """Try Gemini first — Google Search grounding gives it an edge for
    discovering current blogs/communities."""
    if not os.getenv("GOOGLE_API_KEY"):
        return None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        model_name = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
        resp = client.models.generate_content(
            model=model_name,
            contents=_user_prompt(keywords),
            config=types.GenerateContentConfig(
                system_instruction=_system_prompt(),
                max_output_tokens=800,
            ),
        )
        return (resp.text or "") if hasattr(resp, "text") else ""
    except Exception as e:  # noqa: BLE001
        logger.warning("source_discovery: gemini failed: %s", e)
        return None


def _call_claude(keywords: List[str]) -> Optional[str]:
    """Fallback to Claude when Google key is absent."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=os.getenv("DISCOVERY_MODEL", "claude-haiku-4-5"),
            max_tokens=800,
            system=_system_prompt(),
            messages=[{"role": "user", "content": _user_prompt(keywords)}],
        )
        return resp.content[0].text if resp.content else ""
    except Exception as e:  # noqa: BLE001
        logger.warning("source_discovery: claude failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# JSON extraction — same lenient parsing pattern as translator
# ---------------------------------------------------------------------------

def _parse_proposals_json(raw: str) -> List[ProposedSource]:
    text = (raw or "").strip()
    if not text:
        return []
    # Strip ```json fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rstrip()
        if text.endswith("```"):
            text = text[:-3].rstrip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Loose: find the first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return []
        try:
            data = json.loads(text[start: end + 1])
        except json.JSONDecodeError:
            return []
    if not isinstance(data, dict):
        return []
    items = data.get("proposals")
    if not isinstance(items, list):
        return []
    out: List[ProposedSource] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).strip().lower()
        target = str(item.get("target", "")).strip()
        name = str(item.get("name", "")).strip()
        reason = str(item.get("reason", "")).strip()
        if kind not in _SUPPORTED_KINDS:
            continue
        if not target or not name:
            continue
        out.append(ProposedSource(
            kind=kind, target=target, name=name, reason=reason,
            score=0.55,  # LLM-proposed = moderate confidence
        ))
    return out


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class SourceDiscoveryAgent:
    """Stateless agent. Inject custom callers in tests to avoid LLM cost."""

    def __init__(
        self,
        gemini_caller: Optional[callable] = None,
        claude_caller: Optional[callable] = None,
        existing_sources: Optional[List[dict]] = None,
    ) -> None:
        self._call_gemini = gemini_caller or _call_gemini
        self._call_claude = claude_caller or _call_claude
        self._existing = existing_sources

    def discover(self, keywords: Iterable[str]) -> DiscoveryResult:
        kws = [k.strip() for k in (keywords or []) if k and k.strip()]
        result = DiscoveryResult(keywords=kws)

        if not kws:
            result.errors.append("no keywords provided")
            return result

        # Try Gemini first (better grounding), fall back to Claude
        raw = self._call_gemini(kws)
        if raw:
            result.llm_provider = "google"
        else:
            raw = self._call_claude(kws)
            if raw:
                result.llm_provider = "claude"

        if not raw:
            result.errors.append("no LLM provider configured (set GOOGLE_API_KEY or ANTHROPIC_API_KEY)")
            return result

        proposals = _parse_proposals_json(raw)
        # Cap proposals per call
        proposals = proposals[:MAX_PROPOSALS_PER_CALL]
        # Dedup against existing sources by (kind, target) lower-cased
        existing_keys = self._existing_keys()
        proposals = [p for p in proposals
                     if (p.kind, p.target.lower()) not in existing_keys]
        result.proposals = proposals
        return result

    # ------------------------------------------------------------------

    def _existing_keys(self) -> set:
        if self._existing is None:
            try:
                from ..core.storage import sources_store
                rows = sources_store.list()
            except Exception:  # noqa: BLE001
                return set()
        else:
            rows = self._existing
        return {(str(r.get("kind", "")).lower(), str(r.get("target", "")).lower())
                for r in rows}


__all__ = [
    "ProposedSource",
    "DiscoveryResult",
    "SourceDiscoveryAgent",
    "MAX_PROPOSALS_PER_CALL",
]
