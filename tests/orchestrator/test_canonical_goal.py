"""
Tests for CanonicalGoal — R14 Canonical Goal Statement.
Ensures goal drift prevention infrastructure is correctly wired.
"""
import pytest
from uuid import uuid4

from orchestrator.core.canonical_goal import CanonicalGoal
from orchestrator.workflows.evidence_gate import EvidenceGateWorkflow


@pytest.fixture
def sample_goal():
    return CanonicalGoal(
        workflow_id=uuid4(),
        goal_statement="Validate whether a business idea has real market demand through a 14-day evidence test.",
        success_criteria=[
            "IdeaSpec generated with clear problem statement",
            "ICP defined with specific demographic and acquisition channel",
        ],
        out_of_scope=[
            "Building the actual product",
            "Writing production code",
        ],
    )


def test_canonical_goal_as_context_block_contains_required_sections(sample_goal):
    block = sample_goal.as_context_block()
    assert "<canonical_goal>" in block
    assert "</canonical_goal>" in block
    assert "Goal:" in block
    assert "Success criteria:" in block
    assert "Out of scope:" in block


def test_canonical_goal_context_block_includes_goal_statement(sample_goal):
    block = sample_goal.as_context_block()
    assert sample_goal.goal_statement in block


def test_canonical_goal_context_block_includes_all_criteria(sample_goal):
    block = sample_goal.as_context_block()
    for criterion in sample_goal.success_criteria:
        assert criterion in block


def test_canonical_goal_context_block_includes_all_out_of_scope(sample_goal):
    block = sample_goal.as_context_block()
    for item in sample_goal.out_of_scope:
        assert item in block


def test_canonical_goal_out_of_scope_not_empty(sample_goal):
    assert len(sample_goal.out_of_scope) > 0


def test_canonical_goal_success_criteria_not_empty(sample_goal):
    assert len(sample_goal.success_criteria) > 0


def test_evidence_gate_run_has_canonical_goal():
    wf = EvidenceGateWorkflow(mock_mode=True)
    run = wf.run("fintech para PYMEs Ecuador")
    assert run.canonical_goal is not None
    assert isinstance(run.canonical_goal, CanonicalGoal)


def test_canonical_goal_workflow_id_matches_run_id():
    wf = EvidenceGateWorkflow(mock_mode=True)
    run = wf.run("edtech colegios bilingues")
    assert run.canonical_goal.workflow_id == run.run_id


def test_canonical_goal_goal_statement_not_empty():
    wf = EvidenceGateWorkflow(mock_mode=True)
    run = wf.run("marketplace servicios hogar")
    assert run.canonical_goal.goal_statement
    assert len(run.canonical_goal.goal_statement) > 20


def test_canonical_goal_out_of_scope_excludes_building_product():
    wf = EvidenceGateWorkflow(mock_mode=True)
    run = wf.run("logistics SaaS")
    out_of_scope_text = " ".join(run.canonical_goal.out_of_scope).lower()
    assert "building" in out_of_scope_text or "product" in out_of_scope_text
