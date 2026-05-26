"""Tests for the cross-LLM fact-checker (ADR-008)."""
import os
from unittest.mock import patch

import pytest

from orchestrator.core.fact_checker import (
    Claim,
    FactCheckResult,
    count_unsupported,
    extract_claims,
    fact_check_claims,
    fact_check_enabled,
)


def test_extract_percent_claim():
    claims = extract_claims("Los CFOs reportan 60% de retraso en cobros.")
    assert len(claims) == 1
    assert "60%" in claims[0].text


def test_extract_dollar_claim():
    claims = extract_claims("El TAM es de $1.5M en Ecuador.")
    assert len(claims) == 1
    assert "$1.5M" in claims[0].text or "$1.5" in claims[0].text


def test_extract_duration_claim():
    claims = extract_claims("Las PYMEs pierden 4+ horas/dia monitoreando.")
    assert any("horas" in c.text for c in claims)


def test_extract_multiple_claims_dedup():
    text = "60% PYMEs, 60% retraso, $200 spend, 4 horas/dia."
    claims = extract_claims(text)
    # 60% appears twice but should be deduped
    snippets = [c.text for c in claims]
    assert snippets.count("60%") == 1


def test_extract_no_claims():
    assert extract_claims("Una idea sin numeros concretos") == []


def test_extract_caps_at_max():
    text = "1% 2% 3% 4% 5% 6% 7% 8% 9% 10%"
    claims = extract_claims(text, max_claims=4)
    assert len(claims) == 4


def test_fact_check_disabled_by_default():
    with patch.dict(os.environ, {"FACT_CHECK_ENABLED": "", "GOOGLE_API_KEY": "x"}, clear=False):
        assert fact_check_enabled() is False


def test_fact_check_disabled_without_key():
    with patch.dict(os.environ, {"FACT_CHECK_ENABLED": "true", "GOOGLE_API_KEY": ""}, clear=False):
        assert fact_check_enabled() is False


def test_fact_check_enabled_when_both_set():
    with patch.dict(
        os.environ,
        {"FACT_CHECK_ENABLED": "true", "GOOGLE_API_KEY": "AIzaXXXX"},
        clear=False,
    ):
        assert fact_check_enabled() is True


def test_fact_check_mock_mode_returns_deterministic():
    results = fact_check_claims("60% PYMEs, 4 horas/dia, $200 spend.", mock_mode=True)
    assert len(results) == 3
    # mock alternates verdicts
    verdicts = [r.verdict for r in results]
    assert verdicts == ["SUPPORTED", "UNSUPPORTED", "NEEDS_VERIFICATION"]


def test_fact_check_disabled_returns_empty():
    with patch.dict(os.environ, {"FACT_CHECK_ENABLED": "false"}, clear=False):
        results = fact_check_claims("60% PYMEs.", mock_mode=False)
        assert results == []


def test_count_unsupported():
    claims = [Claim(text=f"{i}%", context=f"ctx{i}") for i in range(4)]
    results = [
        FactCheckResult(claims[0], "SUPPORTED", "ok", "mock"),
        FactCheckResult(claims[1], "UNSUPPORTED", "bad", "mock"),
        FactCheckResult(claims[2], "UNSUPPORTED", "bad", "mock"),
        FactCheckResult(claims[3], "NEEDS_VERIFICATION", "unsure", "mock"),
    ]
    assert count_unsupported(results) == 2


def test_empty_text_returns_empty_claims():
    assert fact_check_claims("", mock_mode=True) == []
    assert fact_check_claims("", mock_mode=False) == []
