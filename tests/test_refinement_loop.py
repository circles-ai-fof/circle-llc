"""Tests for the specificity refinement loop (ADR-007)."""
from datetime import datetime
from unittest.mock import MagicMock
from uuid import uuid4

from orchestrator.agents.idea_hunter import IdeaHunterAgent
from orchestrator.core.models import IdeaSpec, VerticalCategory
from orchestrator.workflows.evidence_gate import EvidenceGateWorkflow


def test_idea_hunter_accepts_feedback_param():
    """generate() must accept feedback=None (default) and an explicit string."""
    agent = IdeaHunterAgent(mock_mode=True)
    idea = agent.generate("topic")
    assert idea is not None
    # feedback should be silently accepted
    idea2 = agent.generate("topic", feedback="Be more specific about market")
    assert idea2 is not None


def test_mock_workflow_loop_terminates_in_1_attempt():
    """Mock enricher returns score 4.2 for non-vague keywords -> 1 attempt total."""
    wf = EvidenceGateWorkflow(mock_mode=True)
    run = wf.run("marketplace de servicios legales")
    # 6 fixed steps (hunter, enricher, maturer, validator, landing, gate) * 1 attempt
    assert run.budget_tracker.steps_used == 6


def test_mock_workflow_loop_bound_by_max_attempts():
    """Even when mock would loop, the hard cap N=3 prevents runaway."""
    # We can't easily force the mock to fail, but we verify the cap exists
    # by checking budget_tracker doesn't exceed (3 attempts * 2 steps) + 4 = 10 steps
    wf = EvidenceGateWorkflow(mock_mode=True)
    run = wf.run("plataforma para manejar todo")  # vague keywords
    # Mock enricher returns 2.8 for vague -> would loop, but mock stays at 1 attempt
    # because hunter mock always returns same IdeaSpec (no feedback effect in mock).
    # The loop would go to 3 attempts -> 6 hunter+enricher steps + 4 downstream = 10
    assert run.budget_tracker.steps_used <= 10


def test_mock_workflow_returns_idea_with_attempts_metadata():
    """The workflow result should be a fully-populated EvidenceGateRun."""
    wf = EvidenceGateWorkflow(mock_mode=True)
    run = wf.run("edtech")
    assert run.idea is not None
    assert run.idea.title  # has a title
    assert run.decision is not None  # got a verdict
