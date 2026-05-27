"""
test_length_bounds.py — Validates length constraints from Pydantic models.

Checks per model field (from orchestrator/core/models.py):
- LandingSpec.headline: max_length=80
- LandingSpec.subheadline: max_length=160
- LandingSpec.value_props: min_length=3, max_length=5 (list items)
- LandingSpec.cta_text: max_length=40
- EvidenceTestDesign.test_duration_days: ge=7, le=30
- EvidenceTestDesign.ad_budget_usd: ge=50.0, le=2000.0
- EvidenceTestDesign.target_ctr: ge=0.005, le=0.20
- EvidenceTestDesign.target_conversion_rate: ge=0.01, le=0.50
- GateDecision.confidence: ge=0.0, le=1.0
- MetricsSnapshot: all fields ge=0
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

GOLDEN_DIR = Path(__file__).parent.parent / "golden_cases"


def _load_jsonl(filename: str) -> list[dict]:
    path = GOLDEN_DIR / filename
    cases = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                cases.append(json.loads(stripped))
            except json.JSONDecodeError as e:
                pytest.fail(f"{filename}:{lineno} invalid JSON: {e}")
    return cases


@pytest.fixture(scope="module")
def landing_cases():
    return _load_jsonl("landing_generator.jsonl")


@pytest.fixture(scope="module")
def market_validator_cases():
    return _load_jsonl("market_validator.jsonl")


@pytest.fixture(scope="module")
def gate_decider_cases():
    return _load_jsonl("gate_decider.jsonl")


# ---------------------------------------------------------------------------
# LandingSpec length bounds (from golden case expected_output_shape + properties)
# ---------------------------------------------------------------------------

class TestLandingSpecBounds:
    """
    Landing generator golden cases must declare the correct length constraints
    in expected_properties. These tests verify the golden cases themselves
    correctly encode the constraints.
    """

    def test_all_cases_declare_headline_max_80(self, landing_cases):
        """Every landing case must assert headline fits in 80 chars."""
        missing = [
            case["id"] for case in landing_cases
            if "headline_max_80_chars" not in case.get("expected_properties", [])
        ]
        assert not missing, (
            f"Landing cases missing 'headline_max_80_chars' in expected_properties: {missing}"
        )

    def test_all_cases_declare_subheadline_max_160(self, landing_cases):
        """Every landing case must assert subheadline fits in 160 chars."""
        # Not every case may have it (edge cases may omit), so check happy_path only
        happy_cases = [c for c in landing_cases if c["edge_case_type"] == "happy_path"]
        missing = [
            case["id"] for case in happy_cases
            if "subheadline_max_160_chars" not in case.get("expected_properties", [])
        ]
        assert not missing, (
            f"Happy-path landing cases missing 'subheadline_max_160_chars': {missing}"
        )

    def test_all_cases_declare_value_props_3_to_5(self, landing_cases):
        """Every landing case must assert value_props has 3-5 items."""
        missing = [
            case["id"] for case in landing_cases
            if "value_props_3_to_5" not in case.get("expected_properties", [])
        ]
        assert not missing, (
            f"Landing cases missing 'value_props_3_to_5' in expected_properties: {missing}"
        )

    def test_all_cases_declare_cta_max_40(self, landing_cases):
        """Every landing case must assert cta_text fits in 40 chars."""
        missing = [
            case["id"] for case in landing_cases
            if "cta_max_40_chars" not in case.get("expected_properties", [])
        ]
        assert not missing, (
            f"Landing cases missing 'cta_max_40_chars' in expected_properties: {missing}"
        )

    def test_all_cases_declare_domain_slug_url_safe(self, landing_cases):
        """Every landing case must assert domain_slug is URL-safe."""
        missing = [
            case["id"] for case in landing_cases
            if "domain_slug_url_safe" not in case.get("expected_properties", [])
        ]
        assert not missing, (
            f"Landing cases missing 'domain_slug_url_safe' in expected_properties: {missing}"
        )

    def test_expected_output_shape_has_str_type_for_bounded_fields(self, landing_cases):
        """headline, subheadline, cta_text, domain_slug must be 'str' in output shape."""
        str_fields = ["headline", "subheadline", "cta_text", "social_proof", "domain_slug"]
        for case in landing_cases:
            cid = case["id"]
            shape = case.get("expected_output_shape", {})
            for field in str_fields:
                if field in shape:
                    assert shape[field] == "str", (
                        f"Case {cid}: expected_output_shape.{field} should be 'str', got '{shape[field]}'"
                    )

    def test_expected_output_shape_has_list_type_for_value_props(self, landing_cases):
        for case in landing_cases:
            cid = case["id"]
            shape = case.get("expected_output_shape", {})
            if "value_props" in shape:
                assert shape["value_props"] == "list", (
                    f"Case {cid}: expected_output_shape.value_props should be 'list'"
                )


# ---------------------------------------------------------------------------
# EvidenceTestDesign bounds (from golden cases)
# ---------------------------------------------------------------------------

class TestEvidenceTestDesignBounds:
    """
    market_validator golden cases must declare the correct numeric bounds
    in expected_properties. These tests verify the golden cases encode constraints.
    """

    def test_happy_path_cases_declare_duration_bounds(self, market_validator_cases):
        """Happy path cases should declare test_duration_7_to_30."""
        happy = [c for c in market_validator_cases if c["edge_case_type"] == "happy_path"]
        missing = [
            case["id"] for case in happy
            if "test_duration_7_to_30" not in case.get("expected_properties", [])
        ]
        assert not missing, (
            f"Happy-path market_validator cases missing 'test_duration_7_to_30': {missing}"
        )

    def test_happy_path_cases_declare_budget_bounds(self, market_validator_cases):
        """Happy path cases should declare ad_budget_50_to_2000."""
        happy = [c for c in market_validator_cases if c["edge_case_type"] == "happy_path"]
        missing = [
            case["id"] for case in happy
            if "ad_budget_50_to_2000" not in case.get("expected_properties", [])
        ]
        assert not missing, (
            f"Happy-path market_validator cases missing 'ad_budget_50_to_2000': {missing}"
        )

    def test_expected_output_shape_has_int_for_duration(self, market_validator_cases):
        for case in market_validator_cases:
            cid = case["id"]
            shape = case.get("expected_output_shape", {})
            if "test_duration_days" in shape:
                assert shape["test_duration_days"] == "int", (
                    f"Case {cid}: expected_output_shape.test_duration_days should be 'int'"
                )

    def test_expected_output_shape_has_float_for_budget(self, market_validator_cases):
        for case in market_validator_cases:
            cid = case["id"]
            shape = case.get("expected_output_shape", {})
            if "ad_budget_usd" in shape:
                assert shape["ad_budget_usd"] == "float", (
                    f"Case {cid}: expected_output_shape.ad_budget_usd should be 'float'"
                )

    def test_expected_output_shape_has_float_for_ctr(self, market_validator_cases):
        for case in market_validator_cases:
            cid = case["id"]
            shape = case.get("expected_output_shape", {})
            if "target_ctr" in shape:
                assert shape["target_ctr"] == "float", (
                    f"Case {cid}: expected_output_shape.target_ctr should be 'float'"
                )


# ---------------------------------------------------------------------------
# GateDecision bounds
# ---------------------------------------------------------------------------

class TestGateDecisionBounds:
    def test_expected_output_shape_has_float_for_confidence(self, gate_decider_cases):
        for case in gate_decider_cases:
            cid = case["id"]
            shape = case.get("expected_output_shape", {})
            if "confidence" in shape:
                assert shape["confidence"] == "float", (
                    f"Case {cid}: expected_output_shape.confidence should be 'float'"
                )

    def test_expected_output_shape_has_str_for_verdict(self, gate_decider_cases):
        for case in gate_decider_cases:
            cid = case["id"]
            shape = case.get("expected_output_shape", {})
            if "verdict" in shape:
                assert shape["verdict"] == "str", (
                    f"Case {cid}: expected_output_shape.verdict should be 'str'"
                )

    def test_expected_output_shape_has_list_for_evidence_and_steps(self, gate_decider_cases):
        for case in gate_decider_cases:
            cid = case["id"]
            shape = case.get("expected_output_shape", {})
            for list_field in ["key_evidence", "next_steps"]:
                if list_field in shape:
                    assert shape[list_field] == "list", (
                        f"Case {cid}: expected_output_shape.{list_field} should be 'list'"
                    )

    def test_metrics_ctr_is_float_in_0_to_1(self, gate_decider_cases):
        """CTR in golden case metrics must be between 0 and 1 (not percentage)."""
        for case in gate_decider_cases:
            cid = case["id"]
            ctr = case["input"]["metrics"].get("ctr", 0)
            assert 0.0 <= ctr <= 1.0, (
                f"Case {cid}: metrics.ctr = {ctr} is out of range [0, 1] "
                f"(should be fraction, not percentage)"
            )

    def test_metrics_conversion_rate_is_float_in_0_to_1(self, gate_decider_cases):
        """conversion_rate must be between 0 and 1."""
        for case in gate_decider_cases:
            cid = case["id"]
            cvr = case["input"]["metrics"].get("conversion_rate", 0)
            assert 0.0 <= cvr <= 1.0, (
                f"Case {cid}: metrics.conversion_rate = {cvr} out of range [0, 1]"
            )

    def test_metrics_impressions_gte_clicks(self, gate_decider_cases):
        """impressions must be >= clicks (logical constraint)."""
        for case in gate_decider_cases:
            cid = case["id"]
            m = case["input"]["metrics"]
            impressions = m.get("impressions", 0)
            clicks = m.get("clicks", 0)
            # Allow the anomaly case gd-027 which is intentionally testing data anomaly
            if "ConversionNoClicks" in str(case.get("input", {}).get("mature_idea", {}).get("idea", {}).get("title", "")):
                continue
            assert impressions >= clicks, (
                f"Case {cid}: impressions ({impressions}) < clicks ({clicks})"
            )

    def test_metrics_clicks_gte_conversions_for_normal_cases(self, gate_decider_cases):
        """clicks must be >= conversions for non-anomaly cases."""
        for case in gate_decider_cases:
            cid = case["id"]
            m = case["input"]["metrics"]
            clicks = m.get("clicks", 0)
            conversions = m.get("conversions", 0)
            # Skip the intentional anomaly case
            props = case.get("expected_properties", [])
            if "rationale_mentions_data_anomaly" in props:
                continue
            assert clicks >= conversions, (
                f"Case {cid}: clicks ({clicks}) < conversions ({conversions})"
            )


# ---------------------------------------------------------------------------
# Cross-file consistency: all 5 JSONL files exist and are non-empty
# ---------------------------------------------------------------------------

class TestGoldenCasesExistence:
    @pytest.mark.parametrize("filename", [
        "idea_hunter.jsonl",
        "idea_maturer.jsonl",
        "market_validator.jsonl",
        "landing_generator.jsonl",
        "gate_decider.jsonl",
        "idea_analyzer.jsonl",
    ])
    def test_file_exists_and_nonempty(self, filename):
        path = GOLDEN_DIR / filename
        assert path.exists(), f"{filename} does not exist at {path}"
        assert path.stat().st_size > 100, f"{filename} appears empty or too small"

    def test_total_golden_cases_at_least_180(self):
        """Sum of all golden cases across all agents must be ≥ 180 (6 agents × 30)."""
        total = 0
        for filename in ["idea_hunter.jsonl", "idea_maturer.jsonl",
                         "market_validator.jsonl", "landing_generator.jsonl",
                         "gate_decider.jsonl", "idea_analyzer.jsonl"]:
            cases = _load_jsonl(filename)
            total += len(cases)
        assert total >= 180, f"Total golden cases = {total}, expected ≥ 180"
