"""
Tests for M9.4 — SourceDiscoveryAgent.

The agent's contract:
  - Takes cluster keywords from approved signals
  - Asks an LLM (Gemini first, Claude fallback) for plausible new sources
  - Parses JSON proposals strictly into ProposedSource dataclasses
  - Drops kinds outside the supported set (prevents bad data reaching DB)
  - De-dupes against existing sources so dashboard doesn't show "add HN"
    when HN is already active
  - Caps proposals at MAX_PROPOSALS_PER_CALL (default 5)

LLM cost is avoided in tests via the gemini_caller / claude_caller
constructor params — inject a function that returns a canned JSON string.
"""
import json

from orchestrator.agents.source_discovery import (
    DiscoveryResult,
    ProposedSource,
    SourceDiscoveryAgent,
    _parse_proposals_json,
)


# A realistic LLM response shape
_CANNED_GEMINI_RESPONSE = json.dumps({
    "proposals": [
        {"kind": "reddit", "target": "SaaS",
         "name": "Reddit r/SaaS",
         "reason": "fintech LATAM keywords match indie SaaS discussions"},
        {"kind": "rss", "target": "https://contxto.com/en/feed/",
         "name": "Contxto LATAM Tech",
         "reason": "LATAM startup coverage matches your approved cluster"},
        {"kind": "telegram", "target": "ecuadortech",
         "name": "Telegram — Ecuador Tech",
         "reason": "Ecuador-specific tech community channel"},
    ]
})


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def test_parse_proposals_extracts_three():
    items = _parse_proposals_json(_CANNED_GEMINI_RESPONSE)
    assert len(items) == 3
    assert items[0].kind == "reddit"
    assert items[0].target == "SaaS"


def test_parse_proposals_drops_invalid_kind():
    """If the LLM hallucinates 'twitter' (which we explicitly excluded), the
    proposal must be DROPPED, not silently inserted as a bad source_kind."""
    raw = json.dumps({"proposals": [
        {"kind": "twitter", "target": "x", "name": "X", "reason": "y"},
        {"kind": "rss", "target": "https://x.com/feed", "name": "OK", "reason": "y"},
    ]})
    items = _parse_proposals_json(raw)
    assert len(items) == 1
    assert items[0].kind == "rss"


def test_parse_proposals_drops_missing_target():
    raw = json.dumps({"proposals": [
        {"kind": "rss", "target": "", "name": "no target", "reason": "y"},
        {"kind": "rss", "target": "https://ok.com", "name": "ok", "reason": "y"},
    ]})
    items = _parse_proposals_json(raw)
    assert len(items) == 1
    assert items[0].name == "ok"


def test_parse_proposals_handles_markdown_fences():
    """Some models wrap JSON in ```json fences. Parser must strip them."""
    raw = "```json\n" + _CANNED_GEMINI_RESPONSE + "\n```"
    items = _parse_proposals_json(raw)
    assert len(items) == 3


def test_parse_proposals_handles_preamble_text():
    """Some models add a preamble before the JSON body."""
    raw = "Here are the proposals:\n" + _CANNED_GEMINI_RESPONSE
    items = _parse_proposals_json(raw)
    assert len(items) == 3


def test_parse_proposals_empty_input_returns_empty():
    assert _parse_proposals_json("") == []
    assert _parse_proposals_json("not json") == []
    assert _parse_proposals_json("{}") == []


# ---------------------------------------------------------------------------
# Agent integration
# ---------------------------------------------------------------------------

def test_agent_uses_gemini_when_available():
    """Agent must prefer Gemini over Claude when both are configured."""
    def _gemini(_kws): return _CANNED_GEMINI_RESPONSE
    def _claude(_kws): return '{"proposals": []}'

    agent = SourceDiscoveryAgent(
        gemini_caller=_gemini,
        claude_caller=_claude,
        existing_sources=[],
    )
    res = agent.discover(["fintech", "latam"])
    assert res.llm_provider == "google"
    assert len(res.proposals) == 3


def test_agent_falls_back_to_claude_when_gemini_returns_nothing():
    """If Gemini caller returns None (e.g. no GOOGLE_API_KEY), use Claude."""
    def _gemini(_kws): return None
    def _claude(_kws): return _CANNED_GEMINI_RESPONSE

    agent = SourceDiscoveryAgent(
        gemini_caller=_gemini,
        claude_caller=_claude,
        existing_sources=[],
    )
    res = agent.discover(["fintech"])
    assert res.llm_provider == "claude"
    assert len(res.proposals) == 3


def test_agent_returns_empty_with_no_llm_configured():
    """If NEITHER caller produces output, return empty with explanation in
    errors — never crash, never invent fake proposals."""
    agent = SourceDiscoveryAgent(
        gemini_caller=lambda _k: None,
        claude_caller=lambda _k: None,
        existing_sources=[],
    )
    res = agent.discover(["fintech"])
    assert res.proposals == []
    assert any("no LLM" in e for e in res.errors)


def test_agent_empty_keywords_returns_error():
    agent = SourceDiscoveryAgent(
        gemini_caller=lambda _k: _CANNED_GEMINI_RESPONSE,
        existing_sources=[],
    )
    res = agent.discover([])
    assert res.proposals == []
    assert any("no keywords" in e for e in res.errors)


def test_agent_dedups_against_existing_sources():
    """If 'Reddit r/SaaS' is already an active source, do NOT propose it."""
    existing = [
        {"kind": "reddit", "target": "saas"},  # case-insensitive match
    ]
    agent = SourceDiscoveryAgent(
        gemini_caller=lambda _k: _CANNED_GEMINI_RESPONSE,
        existing_sources=existing,
    )
    res = agent.discover(["fintech"])
    targets = [p.target.lower() for p in res.proposals]
    assert "saas" not in targets
    assert len(res.proposals) == 2  # rss + telegram still get through


def test_agent_caps_proposals_at_max():
    """Even if the LLM returns 20 proposals, we cap to MAX_PROPOSALS_PER_CALL."""
    big = json.dumps({"proposals": [
        {"kind": "rss", "target": f"https://a{i}.com", "name": f"a{i}", "reason": "x"}
        for i in range(20)
    ]})
    from orchestrator.agents.source_discovery import MAX_PROPOSALS_PER_CALL
    agent = SourceDiscoveryAgent(
        gemini_caller=lambda _k: big,
        existing_sources=[],
    )
    res = agent.discover(["fintech"])
    assert len(res.proposals) == MAX_PROPOSALS_PER_CALL


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------

def test_discover_endpoint_passes_explicit_keywords():
    """POST with explicit keywords lets the founder do manual exploration
    without waiting for clustering."""
    import os
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    os.environ["ALLOWED_EMAILS"] = "test@example.com"
    from orchestrator.api import app
    # Make sure the agent's LLM callers never actually fire
    with patch(
        "orchestrator.agents.source_discovery._call_gemini",
        return_value=_CANNED_GEMINI_RESPONSE,
    ), patch(
        "orchestrator.agents.source_discovery._call_claude",
        return_value=None,
    ):
        c = TestClient(app)
        t = c.post("/api/v1/auth/login", json={"email": "test@example.com"}).json()["token"]
        h = {"Authorization": f"Bearer {t}"}
        r = c.post(
            "/api/v1/sources/discover",
            headers=h,
            json={"keywords": ["fintech", "latam"]},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["keywords"] == ["fintech", "latam"]
    assert body["llm_provider"] == "google"
    assert len(body["proposals"]) >= 1
