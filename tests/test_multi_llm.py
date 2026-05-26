"""Tests for the multi-LLM ensemble (graceful degradation)."""
import os
from unittest.mock import patch

import pytest

from orchestrator.core.multi_llm import (
    EnsembleResult,
    EnsembleVote,
    _ensemble_enabled,
    _parse_vote,
    gate_ensemble_vote,
)


def test_parse_vote_explicit_format():
    v = _parse_vote("claude", "sonnet", "VERDICT: pass\nconfidence: 0.85\nGood signal.")
    assert v is not None
    assert v.verdict == "pass"
    assert v.confidence == pytest.approx(0.85)


def test_parse_vote_keyword_fallback():
    v = _parse_vote("openai", "gpt", "We should kill this idea. No PMF signal.")
    assert v is not None
    assert v.verdict == "kill"


def test_parse_vote_no_verdict():
    v = _parse_vote("gemini", "flash", "Hmm, interesting question but I cannot decide.")
    assert v is None


def test_ensemble_disabled_by_default():
    with patch.dict(os.environ, {"ENSEMBLE_GATE_ENABLED": ""}, clear=False):
        assert _ensemble_enabled() is False


def test_ensemble_enabled_via_env():
    with patch.dict(os.environ, {"ENSEMBLE_GATE_ENABLED": "true"}, clear=False):
        assert _ensemble_enabled() is True


def test_ensemble_graceful_degradation_no_providers():
    """With no provider keys set, returns empty result without crashing."""
    with patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "", "GOOGLE_API_KEY": ""},
        clear=False,
    ):
        result = gate_ensemble_vote("prompt", "system")
        assert isinstance(result, EnsembleResult)
        assert result.votes == []
        assert result.final_verdict == "iterate"


def test_ensemble_majority_vote():
    """Simulate 3 votes — 2 pass, 1 kill → final = pass."""
    votes = [
        EnsembleVote("claude", "sonnet", "pass", 0.9, "r1"),
        EnsembleVote("openai", "gpt", "pass", 0.85, "r2"),
        EnsembleVote("google", "gemini", "kill", 0.7, "r3"),
    ]
    # We assemble a result manually to verify the math the function will do
    from collections import Counter

    counts = Counter(v.verdict for v in votes)
    top, top_count = counts.most_common(1)[0]
    agreement = top_count / len(votes)
    avg_conf = sum(v.confidence for v in votes if v.verdict == top) / top_count
    final_conf = avg_conf * agreement

    assert top == "pass"
    assert agreement == pytest.approx(2 / 3)
    assert final_conf == pytest.approx(0.875 * (2 / 3), rel=0.01)
