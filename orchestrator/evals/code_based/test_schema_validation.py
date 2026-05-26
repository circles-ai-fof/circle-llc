"""
test_schema_validation.py — Validates that golden case inputs and expected_output_shapes
are consistent with the Pydantic models defined in orchestrator/core/models.py

Rules:
- R07: schema validation on agent outputs (Pydantic)
- R12: ≥30 golden cases before activating new agent
- No API calls — pure structural validation
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GOLDEN_DIR = Path(__file__).parent.parent / "golden_cases"

IDEA_SPEC_REQUIRED_FIELDS = {
    "title", "description", "target_market",
    "problem_statement", "proposed_solution", "vertical_category",
}

MATURE_IDEA_REQUIRED_FIELDS = {
    "idea", "icp", "value_proposition", "unfair_advantage", "key_risks",
}

ICP_REQUIRED_FIELDS = {
    "demographic", "psychographic", "pain_points",
    "willingness_to_pay", "acquisition_channel",
}

EVIDENCE_TEST_REQUIRED_FIELDS = {
    "hypothesis", "success_metrics", "failure_metrics",
    "test_duration_days", "ad_budget_usd", "target_ctr", "target_conversion_rate",
}

LANDING_SPEC_REQUIRED_FIELDS = {
    "headline", "subheadline", "value_props", "cta_text", "social_proof", "domain_slug",
}

GATE_DECISION_REQUIRED_FIELDS = {
    "verdict", "confidence", "rationale", "key_evidence", "next_steps",
}

VALID_VERTICAL_CATEGORIES = {
    "saas", "marketplace", "community", "ecommerce",
    "fintech", "healthtech", "edtech", "other",
}

VALID_GATE_VERDICTS = {"pass", "kill", "iterate"}


def _load_jsonl(filename: str) -> list[dict]:
    path = GOLDEN_DIR / filename
    cases = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as e:
                pytest.fail(f"{filename}:{lineno} — invalid JSON: {e}")
    return cases


@pytest.fixture(scope="module")
def idea_hunter_cases() -> list[dict]:
    return _load_jsonl("idea_hunter.jsonl")


@pytest.fixture(scope="module")
def idea_maturer_cases() -> list[dict]:
    return _load_jsonl("idea_maturer.jsonl")


@pytest.fixture(scope="module")
def market_validator_cases() -> list[dict]:
    return _load_jsonl("market_validator.jsonl")


@pytest.fixture(scope="module")
def landing_generator_cases() -> list[dict]:
    return _load_jsonl("landing_generator.jsonl")


@pytest.fixture(scope="module")
def gate_decider_cases() -> list[dict]:
    return _load_jsonl("gate_decider.jsonl")


# ---------------------------------------------------------------------------
# R12: Ensure minimum 30 golden cases per agent
# ---------------------------------------------------------------------------

class TestMinimumCaseCounts:
    def test_idea_hunter_has_30_cases(self, idea_hunter_cases):
        assert len(idea_hunter_cases) >= 30, (
            f"idea_hunter.jsonl has {len(idea_hunter_cases)} cases — R12 requires ≥30"
        )

    def test_idea_maturer_has_30_cases(self, idea_maturer_cases):
        assert len(idea_maturer_cases) >= 30, (
            f"idea_maturer.jsonl has {len(idea_maturer_cases)} cases — R12 requires ≥30"
        )

    def test_market_validator_has_30_cases(self, market_validator_cases):
        assert len(market_validator_cases) >= 30, (
            f"market_validator.jsonl has {len(market_validator_cases)} cases — R12 requires ≥30"
        )

    def test_landing_generator_has_30_cases(self, landing_generator_cases):
        assert len(landing_generator_cases) >= 30, (
            f"landing_generator.jsonl has {len(landing_generator_cases)} cases — R12 requires ≥30"
        )

    def test_gate_decider_has_30_cases(self, gate_decider_cases):
        assert len(gate_decider_cases) >= 30, (
            f"gate_decider.jsonl has {len(gate_decider_cases)} cases — R12 requires ≥30"
        )


# ---------------------------------------------------------------------------
# idea_hunter — input: {topic: str}, output shape: IdeaSpec fields
# ---------------------------------------------------------------------------

class TestIdeaHunterSchema:
    def test_all_cases_have_required_top_level_keys(self, idea_hunter_cases):
        required = {"id", "input", "expected_output_shape", "expected_properties", "edge_case_type"}
        for case in idea_hunter_cases:
            missing = required - set(case.keys())
            assert not missing, f"Case {case.get('id')} missing keys: {missing}"

    def test_input_has_topic_field(self, idea_hunter_cases):
        """idea_hunter takes a topic string as input."""
        for case in idea_hunter_cases:
            cid = case.get("id", "?")
            assert "topic" in case["input"], f"Case {cid}: input missing 'topic' field"

    def test_expected_output_shape_covers_ideaspec_fields(self, idea_hunter_cases):
        """expected_output_shape must include all IdeaSpec required fields."""
        for case in idea_hunter_cases:
            cid = case.get("id", "?")
            shape_fields = set(case["expected_output_shape"].keys())
            missing = IDEA_SPEC_REQUIRED_FIELDS - shape_fields
            assert not missing, f"Case {cid}: expected_output_shape missing IdeaSpec fields: {missing}"

    def test_edge_case_type_is_valid(self, idea_hunter_cases):
        valid_types = {"happy_path", "edge_case", "adversarial"}
        for case in idea_hunter_cases:
            cid = case.get("id", "?")
            assert case["edge_case_type"] in valid_types, (
                f"Case {cid}: invalid edge_case_type '{case['edge_case_type']}'"
            )

    def test_case_ids_are_unique(self, idea_hunter_cases):
        ids = [c["id"] for c in idea_hunter_cases]
        assert len(ids) == len(set(ids)), "idea_hunter.jsonl has duplicate case IDs"

    def test_distribution_60_30_10(self, idea_hunter_cases):
        """60% happy_path, 30% edge_case, 10% adversarial (approximate)."""
        happy = sum(1 for c in idea_hunter_cases if c["edge_case_type"] == "happy_path")
        edge = sum(1 for c in idea_hunter_cases if c["edge_case_type"] == "edge_case")
        adversarial = sum(1 for c in idea_hunter_cases if c["edge_case_type"] == "adversarial")
        total = len(idea_hunter_cases)
        assert happy >= total * 0.55, f"Expected ≥55% happy_path, got {happy}/{total}"
        assert edge >= total * 0.25, f"Expected ≥25% edge_case, got {edge}/{total}"
        assert adversarial >= 2, f"Expected ≥2 adversarial cases, got {adversarial}"


# ---------------------------------------------------------------------------
# idea_maturer — input: {idea: IdeaSpec}, output shape: MatureIdeaSpec fields
# ---------------------------------------------------------------------------

class TestIdeaMaturerSchema:
    def test_all_cases_have_required_top_level_keys(self, idea_maturer_cases):
        required = {"id", "input", "expected_output_shape", "expected_properties", "edge_case_type"}
        for case in idea_maturer_cases:
            missing = required - set(case.keys())
            assert not missing, f"Case {case.get('id')} missing keys: {missing}"

    def test_input_has_idea_field(self, idea_maturer_cases):
        for case in idea_maturer_cases:
            cid = case.get("id", "?")
            assert "idea" in case["input"], f"Case {cid}: input missing 'idea' field"

    def test_input_idea_has_required_fields(self, idea_maturer_cases):
        """The embedded IdeaSpec in input must have all required fields."""
        for case in idea_maturer_cases:
            cid = case.get("id", "?")
            idea = case["input"]["idea"]
            missing = IDEA_SPEC_REQUIRED_FIELDS - set(idea.keys())
            assert not missing, f"Case {cid}: input.idea missing fields: {missing}"

    def test_expected_output_shape_covers_matureideasspec_fields(self, idea_maturer_cases):
        for case in idea_maturer_cases:
            cid = case.get("id", "?")
            shape_fields = set(case["expected_output_shape"].keys())
            missing = MATURE_IDEA_REQUIRED_FIELDS - shape_fields
            assert not missing, f"Case {cid}: expected_output_shape missing MatureIdeaSpec fields: {missing}"

    def test_vertical_categories_valid(self, idea_maturer_cases):
        for case in idea_maturer_cases:
            cid = case.get("id", "?")
            vc = case["input"]["idea"].get("vertical_category", "")
            assert vc in VALID_VERTICAL_CATEGORIES, (
                f"Case {cid}: invalid vertical_category '{vc}'"
            )

    def test_case_ids_are_unique(self, idea_maturer_cases):
        ids = [c["id"] for c in idea_maturer_cases]
        assert len(ids) == len(set(ids)), "idea_maturer.jsonl has duplicate case IDs"


# ---------------------------------------------------------------------------
# market_validator — input: {mature_idea: MatureIdeaSpec}, output: EvidenceTestDesign
# ---------------------------------------------------------------------------

class TestMarketValidatorSchema:
    def test_all_cases_have_required_top_level_keys(self, market_validator_cases):
        required = {"id", "input", "expected_output_shape", "expected_properties", "edge_case_type"}
        for case in market_validator_cases:
            missing = required - set(case.keys())
            assert not missing, f"Case {case.get('id')} missing keys: {missing}"

    def test_input_has_mature_idea_field(self, market_validator_cases):
        for case in market_validator_cases:
            cid = case.get("id", "?")
            assert "mature_idea" in case["input"], f"Case {cid}: input missing 'mature_idea' field"

    def test_input_mature_idea_has_required_fields(self, market_validator_cases):
        for case in market_validator_cases:
            cid = case.get("id", "?")
            mi = case["input"]["mature_idea"]
            missing = {"idea", "icp", "value_proposition", "unfair_advantage", "key_risks"} - set(mi.keys())
            assert not missing, f"Case {cid}: mature_idea missing fields: {missing}"

    def test_expected_output_shape_covers_evidencetestdesign(self, market_validator_cases):
        for case in market_validator_cases:
            cid = case.get("id", "?")
            shape_fields = set(case["expected_output_shape"].keys())
            missing = EVIDENCE_TEST_REQUIRED_FIELDS - shape_fields
            assert not missing, f"Case {cid}: expected_output_shape missing EvidenceTestDesign fields: {missing}"

    def test_case_ids_are_unique(self, market_validator_cases):
        ids = [c["id"] for c in market_validator_cases]
        assert len(ids) == len(set(ids)), "market_validator.jsonl has duplicate case IDs"


# ---------------------------------------------------------------------------
# landing_generator — input: {mature_idea: MatureIdeaSpec}, output: LandingSpec
# ---------------------------------------------------------------------------

class TestLandingGeneratorSchema:
    def test_all_cases_have_required_top_level_keys(self, landing_generator_cases):
        required = {"id", "input", "expected_output_shape", "expected_properties", "edge_case_type"}
        for case in landing_generator_cases:
            missing = required - set(case.keys())
            assert not missing, f"Case {case.get('id')} missing keys: {missing}"

    def test_input_has_mature_idea_field(self, landing_generator_cases):
        for case in landing_generator_cases:
            cid = case.get("id", "?")
            assert "mature_idea" in case["input"], f"Case {cid}: input missing 'mature_idea' field"

    def test_expected_output_shape_covers_landingspec(self, landing_generator_cases):
        for case in landing_generator_cases:
            cid = case.get("id", "?")
            shape_fields = set(case["expected_output_shape"].keys())
            missing = LANDING_SPEC_REQUIRED_FIELDS - shape_fields
            assert not missing, f"Case {cid}: expected_output_shape missing LandingSpec fields: {missing}"

    def test_case_ids_are_unique(self, landing_generator_cases):
        ids = [c["id"] for c in landing_generator_cases]
        assert len(ids) == len(set(ids)), "landing_generator.jsonl has duplicate case IDs"

    def test_adversarial_cases_present(self, landing_generator_cases):
        adversarial = [c for c in landing_generator_cases if c["edge_case_type"] == "adversarial"]
        assert len(adversarial) >= 3, f"Expected ≥3 adversarial cases, got {len(adversarial)}"


# ---------------------------------------------------------------------------
# gate_decider — input: {mature_idea, test_design, metrics}, output: GateDecision
# ---------------------------------------------------------------------------

class TestGateDeciderSchema:
    def test_all_cases_have_required_top_level_keys(self, gate_decider_cases):
        required = {"id", "input", "expected_output_shape", "expected_properties", "edge_case_type"}
        for case in gate_decider_cases:
            missing = required - set(case.keys())
            assert not missing, f"Case {case.get('id')} missing keys: {missing}"

    def test_input_has_all_required_fields(self, gate_decider_cases):
        required_input_keys = {"mature_idea", "test_design", "metrics"}
        for case in gate_decider_cases:
            cid = case.get("id", "?")
            missing = required_input_keys - set(case["input"].keys())
            assert not missing, f"Case {cid}: input missing fields: {missing}"

    def test_metrics_has_required_fields(self, gate_decider_cases):
        metrics_fields = {
            "impressions", "clicks", "conversions", "cost_usd",
            "ctr", "conversion_rate", "cost_per_conversion",
        }
        for case in gate_decider_cases:
            cid = case.get("id", "?")
            m = case["input"]["metrics"]
            missing = metrics_fields - set(m.keys())
            assert not missing, f"Case {cid}: metrics missing fields: {missing}"

    def test_expected_output_shape_covers_gatedecision(self, gate_decider_cases):
        for case in gate_decider_cases:
            cid = case.get("id", "?")
            shape_fields = set(case["expected_output_shape"].keys())
            missing = GATE_DECISION_REQUIRED_FIELDS - shape_fields
            assert not missing, f"Case {cid}: expected_output_shape missing GateDecision fields: {missing}"

    def test_expected_verdict_is_valid_if_specified(self, gate_decider_cases):
        """Cases that assert verdict_is_pass/kill/iterate must use valid verdicts."""
        for case in gate_decider_cases:
            cid = case.get("id", "?")
            for prop in case.get("expected_properties", []):
                if prop.startswith("verdict_is_"):
                    expected_verdict = prop.replace("verdict_is_", "")
                    assert expected_verdict in VALID_GATE_VERDICTS, (
                        f"Case {cid}: invalid expected verdict '{expected_verdict}' in {prop}"
                    )

    def test_pass_kill_iterate_distribution(self, gate_decider_cases):
        """gate_decider must have: ≥8 pass, ≥6 kill, ≥4 iterate, ≥4 edge."""
        pass_cases = [c for c in gate_decider_cases
                      if any("verdict_is_pass" in p for p in c.get("expected_properties", []))]
        kill_cases = [c for c in gate_decider_cases
                      if any("verdict_is_kill" in p for p in c.get("expected_properties", []))]
        iterate_cases = [c for c in gate_decider_cases
                         if any("verdict_is_iterate" in p for p in c.get("expected_properties", []))]
        edge_cases = [c for c in gate_decider_cases if c["edge_case_type"] == "edge_case"]

        assert len(pass_cases) >= 8, f"Expected ≥8 PASS cases, got {len(pass_cases)}"
        assert len(kill_cases) >= 6, f"Expected ≥6 KILL cases, got {len(kill_cases)}"
        assert len(iterate_cases) >= 4, f"Expected ≥4 ITERATE cases, got {len(iterate_cases)}"
        assert len(edge_cases) >= 4, f"Expected ≥4 edge cases, got {len(edge_cases)}"

    def test_case_ids_are_unique(self, gate_decider_cases):
        ids = [c["id"] for c in gate_decider_cases]
        assert len(ids) == len(set(ids)), "gate_decider.jsonl has duplicate case IDs"

    def test_metrics_non_negative(self, gate_decider_cases):
        """MetricsSnapshot fields must be ≥ 0."""
        numeric_fields = ["impressions", "clicks", "conversions", "cost_usd",
                          "ctr", "conversion_rate", "cost_per_conversion"]
        for case in gate_decider_cases:
            cid = case.get("id", "?")
            m = case["input"]["metrics"]
            for field in numeric_fields:
                if field in m:
                    assert m[field] >= 0, f"Case {cid}: metrics.{field} = {m[field]} is negative"
