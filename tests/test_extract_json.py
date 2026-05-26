"""Tests for BaseAgent._extract_json robustness."""
import pytest
from orchestrator.core.base_agent import BaseAgent


def extract(raw: str) -> dict:
    return BaseAgent._extract_json(raw)


def test_plain_json():
    assert extract('{"a": 1}') == {"a": 1}


def test_json_with_fenced_block():
    raw = '```json\n{"verdict": "pass", "confidence": 0.9}\n```'
    assert extract(raw) == {"verdict": "pass", "confidence": 0.9}


def test_json_with_prose_before():
    raw = 'Here is the output:\n{"title": "MiApp", "score": 4}'
    assert extract(raw) == {"title": "MiApp", "score": 4}


def test_json_with_prose_after():
    raw = '{"title": "MiApp"}\nLet me know if you need more.'
    assert extract(raw) == {"title": "MiApp"}


def test_json_fenced_no_lang():
    raw = "```\n{\"key\": \"value\"}\n```"
    assert extract(raw) == {"key": "value"}


def test_invalid_raises():
    with pytest.raises(ValueError):
        extract("no json here at all")


def test_empty_raises():
    with pytest.raises(ValueError):
        extract("")


def test_nested_json():
    raw = '{"icp": {"role": "CFO", "size": "PYME"}, "risks": ["r1", "r2"]}'
    result = extract(raw)
    assert result["icp"]["role"] == "CFO"
    assert len(result["risks"]) == 2
