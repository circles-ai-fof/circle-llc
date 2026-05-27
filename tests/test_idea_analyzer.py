"""
Smoke tests for IdeaAnalyzer agent against its golden cases.

Runs the agent in mock_mode against each of the 30 cases in
golden_cases/idea_analyzer.jsonl and verifies basic invariants:
  - All required output fields present
  - recommendation is one of the three valid values
  - Lists are actual lists (not strings)
  - No empty required strings

These tests do NOT validate semantic quality — that's the LLM-judge's job
in M4 once we have live data. They DO catch dataclass regressions.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.agents.idea_analyzer import IdeaAnalyzerAgent, SignalAnalysis


GOLDEN_FILE = (
    Path(__file__).resolve().parent.parent
    / "orchestrator" / "evals" / "golden_cases" / "idea_analyzer.jsonl"
)


def _load_cases():
    cases = []
    with GOLDEN_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


@pytest.fixture(scope="module")
def agent():
    return IdeaAnalyzerAgent(mock_mode=True, client=None)


@pytest.fixture(scope="module")
def cases():
    return _load_cases()


def test_golden_file_has_30_cases(cases):
    assert len(cases) == 30, f"Expected 30 cases, got {len(cases)}"


def test_all_case_ids_are_unique(cases):
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "Duplicate case IDs in idea_analyzer.jsonl"


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_mock_returns_valid_signal_analysis(agent, case):
    """For each golden case, the mock agent must produce a fully-populated
    SignalAnalysis with all required fields and a valid recommendation."""
    inp = case["input"]
    result = agent.analyze(
        theme=inp["theme"],
        excerpt=inp["excerpt"],
        suggested_topic=inp["suggested_topic"],
    )

    # Shape: it must be a SignalAnalysis instance
    assert isinstance(result, SignalAnalysis)

    # All required string fields non-empty
    assert result.market_size_estimate, f"{case['id']}: market_size_estimate is empty"
    assert result.icp_probable, f"{case['id']}: icp_probable is empty"
    assert result.reasoning, f"{case['id']}: reasoning is empty"

    # Lists are actual lists with at least one element where required
    assert isinstance(result.competitors, list), f"{case['id']}: competitors not a list"
    assert isinstance(result.risks, list), f"{case['id']}: risks not a list"
    assert len(result.risks) >= 1, f"{case['id']}: at least 1 risk expected"

    # Recommendation is one of the three valid values
    assert result.recommendation in {
        "promote", "wait_for_more_data", "discard"
    }, f"{case['id']}: invalid recommendation {result.recommendation!r}"


def test_mock_consistent_for_same_input(agent):
    """Mock should be deterministic for the same input — same input → same output."""
    args = dict(
        theme="Reconciliación bancaria automática para PYMEs Ecuador",
        excerpt="Pain point claro en gerentes financieros",
        suggested_topic="reconciliacion pymes ecuador",
    )
    r1 = agent.analyze(**args)
    r2 = agent.analyze(**args)
    assert r1.recommendation == r2.recommendation
    assert r1.reasoning == r2.reasoning


def test_mock_recommends_discard_for_garbage(agent):
    """Heuristic in _mock_analyze: theme/excerpt with 'test' or 'mock' → discard."""
    r = agent.analyze(theme="test test test", excerpt="lorem ipsum", suggested_topic="test")
    assert r.recommendation == "discard"


def test_live_path_emits_langfuse_trace_when_enabled():
    """When LANGFUSE is enabled, _call() must publish a generation trace.

    Smoke test that confirms IdeaAnalyzer participates in observability the
    same way idea_hunter et al do — the trace name reflects the agent class
    so the founder can filter by agent in Langfuse.
    """
    import importlib
    import sys
    from unittest.mock import MagicMock, patch

    # IMPORTANT: re-import the agent FRESH inside the test, because earlier
    # tests in the suite (test_api.py, test_observability.py) delete
    # orchestrator.* from sys.modules. The class bound at module-load time
    # would be linked against a stale base_agent that no longer matches
    # sys.modules["orchestrator.core.base_agent"]. Patching the live module
    # would then have no effect on the stale class.
    ia_mod = importlib.import_module("orchestrator.agents.idea_analyzer")
    FreshIdeaAnalyzerAgent = ia_mod.IdeaAnalyzerAgent
    ba = sys.modules[FreshIdeaAnalyzerAgent.__mro__[1].__module__]

    fake_response = MagicMock()
    fake_response.content = [MagicMock(text=json.dumps({
        "market_size_estimate": "Mercado mediano",
        "icp_probable": "PYME LATAM",
        "competitors": [],
        "differentiator": "Foco regional",
        "risks": ["A", "B"],
        "recommendation": "promote",
        "reasoning": "Tema con dolor real",
    }))]
    fake_response.usage = MagicMock(input_tokens=100, output_tokens=50)
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    fake_lf = MagicMock()
    with patch.object(ba, "_LANGFUSE_ENABLED", True), \
         patch.object(ba, "_langfuse_client", fake_lf):
        agent = FreshIdeaAnalyzerAgent(mock_mode=False, client=fake_client)
        agent.analyze(
            theme="Test theme", excerpt="Test excerpt",
            suggested_topic="test topic",
        )

    assert fake_lf.generation.called, "Langfuse.generation was not called"
    call_kwargs = fake_lf.generation.call_args.kwargs
    assert call_kwargs["name"] == "IdeaAnalyzerAgent._call"
    assert call_kwargs["model"]
    assert call_kwargs["usage"]["input"] == 100
    assert call_kwargs["usage"]["output"] == 50
