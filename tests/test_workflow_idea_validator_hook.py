"""
Tests for M11.4 — IdeaValidator workflow hook.

Pin down the three behaviors when validate_idea is called between
Step 2 (idea_maturer) and Step 3 (market_validator):

  - IDEA_VALIDATOR_ENABLED=false (default) → no-op, workflow runs full path
  - Verdict MATAR     → short-circuit, decision.verdict='kill', steps 3+ skipped
  - Verdict AVANZAR   → workflow continues as normal (test_design, landing, gate)
"""
from unittest.mock import patch


def test_workflow_skips_validator_when_disabled(monkeypatch):
    """Default behavior: no env set → workflow runs all 4 steps.

    Set a fake ANTHROPIC_API_KEY so the anthropic.Anthropic() construction
    in EvidenceGateWorkflow.__init__ doesn't crash; mock_mode=True still
    prevents any real API call inside the agents.
    """
    monkeypatch.delenv("IDEA_VALIDATOR_ENABLED", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-test-no-real-call")
    from orchestrator.workflows.evidence_gate import EvidenceGateWorkflow
    wf = EvidenceGateWorkflow(mock_mode=True)
    run = wf.run("test topic")
    # All 4 step outputs populated
    assert run.mature_idea is not None
    assert run.test_design is not None
    assert run.landing is not None
    assert run.decision is not None


def test_workflow_short_circuits_on_matar(monkeypatch):
    """When validator returns MATAR, market_validator + landing_generator +
    gate_decider must NOT run. test_design and landing stay None."""
    monkeypatch.setenv("IDEA_VALIDATOR_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-test-no-real-call")

    from orchestrator.agents.idea_validator import (
        ValidatorResult, LethalAssumption, ExperimentDesign, AttackVector,
    )
    fake_matar = ValidatorResult(
        verdict="MATAR",
        lethal_assumption=LethalAssumption(
            statement="No real demand for this niche",
            why_lethal="Without demand, nothing else matters",
        ),
        experiment=ExperimentDesign(
            description="Cold-email 20 prospects with the offer for 1 week",
            budget_usd=50.0, duration_days=7,
            success_criterion=">=3 of 20 reply asking for more",
        ),
        attack_vectors=[
            AttackVector(name="DEMANDA", finding="Tibia", is_blocker=True),
        ],
        provider="mock-test",
    )

    with patch(
        "orchestrator.agents.idea_validator.validate_idea",
        return_value=fake_matar,
    ):
        from orchestrator.workflows.evidence_gate import EvidenceGateWorkflow
        wf = EvidenceGateWorkflow(mock_mode=True)
        run = wf.run("a doomed idea")

    assert run.decision is not None
    assert run.decision.verdict.value == "kill"
    # Subsequent steps DID NOT run
    assert run.test_design is None
    assert run.landing is None
    # Validator rationale surfaced in the decision
    assert "MATAR" in run.decision.rationale
    assert "No real demand" in run.decision.rationale


def test_workflow_continues_on_avanzar(monkeypatch):
    """When validator returns AVANZAR_CON_EVIDENCIA, the workflow runs the
    full pipeline as before."""
    monkeypatch.setenv("IDEA_VALIDATOR_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-test-no-real-call")

    from orchestrator.agents.idea_validator import (
        ValidatorResult, LethalAssumption, ExperimentDesign,
    )
    fake_avanzar = ValidatorResult(
        verdict="AVANZAR_CON_EVIDENCIA",
        lethal_assumption=LethalAssumption(statement="x", why_lethal="y"),
        experiment=ExperimentDesign(description="z"),
        provider="mock-test",
    )

    with patch(
        "orchestrator.agents.idea_validator.validate_idea",
        return_value=fake_avanzar,
    ):
        from orchestrator.workflows.evidence_gate import EvidenceGateWorkflow
        wf = EvidenceGateWorkflow(mock_mode=True)
        run = wf.run("a promising idea")

    assert run.test_design is not None
    assert run.landing is not None
    assert run.decision is not None
    # Decision is from gate_decider in mock mode, NOT from validator
    assert "MATAR" not in (run.decision.rationale or "")


def test_workflow_continues_when_validator_raises(monkeypatch):
    """If validate_idea raises (e.g. import error, runtime bug), the
    workflow must NOT crash — it logs and continues with the original path."""
    monkeypatch.setenv("IDEA_VALIDATOR_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-test-no-real-call")

    with patch(
        "orchestrator.agents.idea_validator.validate_idea",
        side_effect=RuntimeError("boom in validator"),
    ):
        from orchestrator.workflows.evidence_gate import EvidenceGateWorkflow
        wf = EvidenceGateWorkflow(mock_mode=True)
        run = wf.run("survives validator crash")
    # Workflow completed as if validator hadn't been called
    assert run.test_design is not None
    assert run.decision is not None
