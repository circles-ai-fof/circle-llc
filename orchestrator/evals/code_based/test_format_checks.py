"""
test_format_checks.py — Format and safety validation for golden cases.

Checks:
- No PII in inputs (emails, phone numbers, RUC/tax IDs)
- topic fields in idea_hunter are not empty strings
- All files are valid UTF-8
- No binary garbage in string fields
- Adversarial cases are properly labeled
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

GOLDEN_DIR = Path(__file__).parent.parent / "golden_cases"

# PII patterns — we don't want real PII embedded in golden cases
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
# Ecuadorian/LATAM phone patterns: +593, 09x, 04x etc.
_PHONE_RE = re.compile(r"(?<!\w)(\+?593|0[2-9])\s?[\d\s\-]{7,12}(?!\d)")
# RUC Ecuador: 13-digit number
_RUC_EC_RE = re.compile(r"\b\d{13}\b")
# CPF-style (Brazilian): 000.000.000-00
_CPF_RE = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
# Generic credit card: 16 digits with optional separators
# Exclude UUID patterns (8-4-4-4-12 hex) to avoid false positives on UUID fields
_CC_RE = re.compile(r"(?<![0-9a-fA-F-])\b(?:\d{4}[- ]?){3}\d{4}\b(?![0-9a-fA-F-])")
# UUID pattern for exclusion
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _load_jsonl_raw(filename: str) -> tuple[list[dict], list[str]]:
    """Load JSONL and return (cases, raw_lines)."""
    path = GOLDEN_DIR / filename
    cases = []
    raw_lines = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            raw_lines.append(line)
            stripped = line.strip()
            if not stripped:
                continue
            try:
                cases.append(json.loads(stripped))
            except json.JSONDecodeError as e:
                pytest.fail(f"{filename}:{lineno} invalid JSON: {e}")
    return cases, raw_lines


def _extract_all_strings(obj, path="") -> list[tuple[str, str]]:
    """Recursively extract all string values from a nested dict/list with their paths."""
    results = []
    if isinstance(obj, str):
        results.append((path, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            results.extend(_extract_all_strings(v, f"{path}.{k}" if path else k))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            results.extend(_extract_all_strings(item, f"{path}[{i}]"))
    return results


def _has_pii(text: str) -> list[str]:
    """Return list of PII types found in text."""
    found = []
    # Skip adversarial injection attempts — they're intentionally testing injection
    # but we still don't want REAL PII (real emails/phones of actual people)
    if _EMAIL_RE.search(text):
        # Allow example.com, test.com, placeholder emails
        emails = _EMAIL_RE.findall(text)
        real_emails = [e for e in emails if not any(
            placeholder in e.lower() for placeholder in
            ["example", "test", "placeholder", "fake", "dummy", "noreply"]
        )]
        if real_emails:
            found.append(f"email: {real_emails}")
    if _PHONE_RE.search(text):
        found.append("phone")
    if _RUC_EC_RE.search(text):
        found.append("ruc_ec")
    if _CPF_RE.search(text):
        found.append("cpf")
    if _CC_RE.search(text):
        found.append("credit_card")
    return found


AGENTS = [
    "idea_hunter.jsonl",
    "idea_maturer.jsonl",
    "market_validator.jsonl",
    "landing_generator.jsonl",
    "gate_decider.jsonl",
]


# ---------------------------------------------------------------------------
# UTF-8 encoding validation
# ---------------------------------------------------------------------------

class TestUtf8Encoding:
    @pytest.mark.parametrize("filename", AGENTS)
    def test_file_is_valid_utf8(self, filename):
        path = GOLDEN_DIR / filename
        try:
            content = path.read_bytes().decode("utf-8")
            assert len(content) > 0, f"{filename} is empty"
        except UnicodeDecodeError as e:
            pytest.fail(f"{filename} is not valid UTF-8: {e}")

    @pytest.mark.parametrize("filename", AGENTS)
    def test_no_null_bytes(self, filename):
        content = (GOLDEN_DIR / filename).read_bytes()
        assert b"\x00" not in content, f"{filename} contains null bytes"


# ---------------------------------------------------------------------------
# PII checks
# ---------------------------------------------------------------------------

class TestNoPII:
    @pytest.mark.parametrize("filename", AGENTS)
    def test_no_real_emails_in_inputs(self, filename):
        cases, _ = _load_jsonl_raw(filename)
        violations = []
        for case in cases:
            cid = case.get("id", "?")
            for path, value in _extract_all_strings(case.get("input", {})):
                pii = _has_pii(value)
                if pii:
                    violations.append(f"Case {cid} at {path}: {pii}")
        assert not violations, f"PII found in {filename}:\n" + "\n".join(violations)

    @pytest.mark.parametrize("filename", AGENTS)
    def test_no_credit_card_numbers(self, filename):
        cases, _ = _load_jsonl_raw(filename)
        for case in cases:
            cid = case.get("id", "?")
            raw_str = json.dumps(case)
            # Remove all UUID occurrences before checking for credit card patterns
            raw_str_no_uuid = _UUID_RE.sub("REDACTED_UUID", raw_str)
            assert not _CC_RE.search(raw_str_no_uuid), (
                f"Case {cid} in {filename} contains what looks like a credit card number"
            )


# ---------------------------------------------------------------------------
# idea_hunter specific: topic must not be empty in non-adversarial cases
# ---------------------------------------------------------------------------

class TestIdeaHunterTopicFormat:
    def test_non_adversarial_topics_not_empty(self):
        cases, _ = _load_jsonl_raw("idea_hunter.jsonl")
        empty_topic_ids = []
        for case in cases:
            if case.get("edge_case_type") == "adversarial":
                continue  # adversarial may have empty topic intentionally
            topic = case["input"].get("topic", "MISSING")
            if not topic or topic.strip() == "":
                empty_topic_ids.append(case.get("id", "?"))
        assert not empty_topic_ids, (
            f"Non-adversarial cases with empty topic: {empty_topic_ids}"
        )

    def test_adversarial_empty_topic_is_labeled(self):
        """If topic is empty string, case must be adversarial."""
        cases, _ = _load_jsonl_raw("idea_hunter.jsonl")
        violations = []
        for case in cases:
            topic = case["input"].get("topic", "NOT_EMPTY")
            if topic == "":
                if case.get("edge_case_type") != "adversarial":
                    violations.append(case.get("id", "?"))
        assert not violations, (
            f"Empty topic cases not labeled as adversarial: {violations}"
        )

    def test_topic_is_string_type(self):
        cases, _ = _load_jsonl_raw("idea_hunter.jsonl")
        for case in cases:
            cid = case.get("id", "?")
            topic = case["input"].get("topic")
            assert isinstance(topic, str), (
                f"Case {cid}: topic must be str, got {type(topic).__name__}"
            )


# ---------------------------------------------------------------------------
# expected_properties must be a non-empty list of strings
# ---------------------------------------------------------------------------

class TestExpectedPropertiesFormat:
    @pytest.mark.parametrize("filename", AGENTS)
    def test_expected_properties_is_list(self, filename):
        cases, _ = _load_jsonl_raw(filename)
        for case in cases:
            cid = case.get("id", "?")
            props = case.get("expected_properties")
            assert isinstance(props, list), (
                f"Case {cid} in {filename}: expected_properties must be a list"
            )
            assert len(props) > 0, (
                f"Case {cid} in {filename}: expected_properties must not be empty"
            )

    @pytest.mark.parametrize("filename", AGENTS)
    def test_expected_properties_items_are_strings(self, filename):
        cases, _ = _load_jsonl_raw(filename)
        for case in cases:
            cid = case.get("id", "?")
            for prop in case.get("expected_properties", []):
                assert isinstance(prop, str), (
                    f"Case {cid} in {filename}: property '{prop}' is not a string"
                )

    @pytest.mark.parametrize("filename", AGENTS)
    def test_expected_properties_no_duplicates(self, filename):
        cases, _ = _load_jsonl_raw(filename)
        for case in cases:
            cid = case.get("id", "?")
            props = case.get("expected_properties", [])
            assert len(props) == len(set(props)), (
                f"Case {cid} in {filename}: duplicate expected_properties"
            )


# ---------------------------------------------------------------------------
# gate_decider: no adversarial cases (Pydantic handles invalid data before agent)
# ---------------------------------------------------------------------------

class TestGateDeciderNoAdversarial:
    def test_gate_decider_has_no_adversarial_cases(self):
        """Per spec: gate_decider has 0 adversarial cases — Pydantic validates before agent."""
        cases, _ = _load_jsonl_raw("gate_decider.jsonl")
        adversarial = [c for c in cases if c.get("edge_case_type") == "adversarial"]
        assert len(adversarial) == 0, (
            f"gate_decider.jsonl should have 0 adversarial cases, found {len(adversarial)}: "
            f"{[c['id'] for c in adversarial]}"
        )


# ---------------------------------------------------------------------------
# All numeric fields in gate_decider metrics are numbers (not strings)
# ---------------------------------------------------------------------------

class TestGateDeciderMetricTypes:
    def test_metric_fields_are_numeric(self):
        cases, _ = _load_jsonl_raw("gate_decider.jsonl")
        numeric_fields = ["impressions", "clicks", "conversions", "cost_usd",
                          "ctr", "conversion_rate", "cost_per_conversion"]
        for case in cases:
            cid = case.get("id", "?")
            m = case["input"].get("metrics", {})
            for field in numeric_fields:
                val = m.get(field)
                if val is not None:
                    assert isinstance(val, (int, float)), (
                        f"Case {cid}: metrics.{field} = {val!r} is not numeric"
                    )


# ---------------------------------------------------------------------------
# Case IDs follow naming convention: agent-prefix + 3-digit number
# ---------------------------------------------------------------------------

class TestCaseIdConventions:
    _ID_PATTERNS = {
        "idea_hunter.jsonl": re.compile(r"^ih-\d{3}$"),
        "idea_maturer.jsonl": re.compile(r"^im-\d{3}$"),
        "market_validator.jsonl": re.compile(r"^mv-\d{3}$"),
        "landing_generator.jsonl": re.compile(r"^lg-\d{3}$"),
        "gate_decider.jsonl": re.compile(r"^gd-\d{3}$"),
    }

    @pytest.mark.parametrize("filename", AGENTS)
    def test_ids_follow_convention(self, filename):
        pattern = self._ID_PATTERNS[filename]
        cases, _ = _load_jsonl_raw(filename)
        for case in cases:
            cid = case.get("id", "")
            assert pattern.match(cid), (
                f"Case ID '{cid}' in {filename} does not match pattern {pattern.pattern}"
            )
