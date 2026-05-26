"""
Tests for BudgetTracker and trajectory_budget — R13 Step Budget + R17 Cost Alert.
"""
import logging
import pytest

from orchestrator.core.step_budget import (
    ALERT_THRESHOLD,
    BudgetTracker,
    DEFAULT_COST_CAP_USD,
    DEFAULT_MAX_STEPS,
    TrajectoryBudgetExceededError,
    trajectory_budget,
)
from orchestrator.workflows.evidence_gate import EvidenceGateWorkflow


def test_tracker_records_steps():
    tracker = BudgetTracker()
    assert tracker.steps_used == 0
    tracker.record_step(cost_usd=0.50)
    assert tracker.steps_used == 1
    assert tracker.cost_used_usd == pytest.approx(0.50)
    tracker.record_step(cost_usd=1.00)
    assert tracker.steps_used == 2
    assert tracker.cost_used_usd == pytest.approx(1.50)


def test_tracker_raises_on_step_overflow():
    tracker = BudgetTracker(max_steps=3)
    tracker.record_step()
    tracker.record_step()
    tracker.record_step()
    with pytest.raises(TrajectoryBudgetExceededError, match="Step budget exceeded"):
        tracker.record_step()


def test_tracker_raises_on_cost_overflow():
    tracker = BudgetTracker(cost_cap_usd=1.0)
    tracker.record_step(cost_usd=0.50)
    tracker.record_step(cost_usd=0.45)
    with pytest.raises(TrajectoryBudgetExceededError, match="Cost cap exceeded"):
        tracker.record_step(cost_usd=0.10)


def test_tracker_fires_alert_at_80_percent(caplog):
    tracker = BudgetTracker(cost_cap_usd=1.0)
    with caplog.at_level(logging.WARNING):
        # 75% — no alert yet
        tracker.record_step(cost_usd=0.75)
        assert tracker._alert_fired is False
        assert "Cost alert" not in caplog.text

        # 75% + 10% = 85% — crosses 80% threshold, alert fires
        tracker.record_step(cost_usd=0.10)
        assert tracker._alert_fired is True
        assert "Cost alert (R17)" in caplog.text


def test_tracker_does_not_alert_twice(caplog):
    tracker = BudgetTracker(cost_cap_usd=1.0)
    with caplog.at_level(logging.WARNING):
        tracker.record_step(cost_usd=0.80)
        assert tracker._alert_fired is True
        first_count = caplog.text.count("Cost alert (R17)")

        # Another step beyond threshold — alert should NOT fire again
        tracker.record_step(cost_usd=0.05)
        second_count = caplog.text.count("Cost alert (R17)")
        assert second_count == first_count


def test_trajectory_budget_context_manager_yields_tracker():
    with trajectory_budget(max_steps=10, cost_cap_usd=2.0) as tracker:
        assert isinstance(tracker, BudgetTracker)
        assert tracker.max_steps == 10
        assert tracker.cost_cap_usd == pytest.approx(2.0)
        assert tracker.steps_used == 0
        tracker.record_step(cost_usd=0.10)
        assert tracker.steps_used == 1


def test_trajectory_budget_defaults():
    with trajectory_budget() as tracker:
        assert tracker.max_steps == DEFAULT_MAX_STEPS
        assert tracker.cost_cap_usd == pytest.approx(DEFAULT_COST_CAP_USD)


def test_trajectory_budget_propagates_exception():
    with pytest.raises(TrajectoryBudgetExceededError):
        with trajectory_budget(max_steps=1) as tracker:
            tracker.record_step()
            tracker.record_step()  # exceeds max_steps=1


def test_evidence_gate_run_has_budget_tracker():
    wf = EvidenceGateWorkflow(mock_mode=True)
    run = wf.run("app de salud mental")
    assert run.budget_tracker is not None
    assert isinstance(run.budget_tracker, BudgetTracker)


def test_evidence_gate_budget_tracker_records_5_steps():
    """EvidenceGateWorkflow has 5 agent steps — tracker should show exactly 5."""
    wf = EvidenceGateWorkflow(mock_mode=True)
    run = wf.run("marketplace de servicios")
    assert run.budget_tracker.steps_used == 5


def test_evidence_gate_budget_tracker_total_cost():
    """5 steps at $0.01 each = $0.05 total in mock mode."""
    wf = EvidenceGateWorkflow(mock_mode=True)
    run = wf.run("edtech para colegios")
    assert run.budget_tracker.cost_used_usd == pytest.approx(0.05)


def test_budget_tracker_alert_threshold_constant():
    assert ALERT_THRESHOLD == 0.80
