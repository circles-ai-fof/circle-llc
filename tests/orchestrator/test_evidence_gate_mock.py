"""
E2E test of EvidenceGateWorkflow in mock mode.
Zero real API calls. Safe for CI.
Rule R06: mock_mode=True mandatory in CI.
"""
import pytest

from orchestrator.core.models import (
    GateVerdict,
    MetricsSnapshot,
)
from orchestrator.workflows.evidence_gate import EvidenceGateWorkflow


@pytest.fixture
def workflow():
    return EvidenceGateWorkflow(mock_mode=True)


def test_full_run_returns_complete_result(workflow):
    run = workflow.run("fintech para PYMEs Ecuador")

    assert run.run_id is not None
    assert run.topic == "fintech para PYMEs Ecuador"
    assert run.idea.title
    assert run.idea.problem_statement
    assert run.mature_idea.icp.demographic
    assert run.mature_idea.value_proposition
    assert run.test_design.ad_budget_usd >= 50.0
    assert run.test_design.test_duration_days >= 7
    assert run.landing.headline
    assert len(run.landing.value_props) >= 3
    assert run.decision.verdict in GateVerdict
    assert 0.0 <= run.decision.confidence <= 1.0
    assert run.decision.rationale
    assert len(run.decision.next_steps) >= 1


def test_run_with_zero_metrics_returns_iterate_or_kill(workflow):
    metrics = MetricsSnapshot(
        impressions=0, clicks=0, conversions=0,
        cost_usd=0.0, ctr=0.0, conversion_rate=0.0, cost_per_conversion=0.0,
    )
    run = workflow.run("app de salud mental", metrics=metrics)
    # Zero metrics should not be a PASS
    assert run.decision.verdict in {GateVerdict.KILL, GateVerdict.ITERATE}


def test_run_with_passing_metrics_returns_pass(workflow):
    metrics = MetricsSnapshot(
        impressions=1500,
        clicks=60,
        conversions=30,
        cost_usd=150.0,
        ctr=0.04,           # above typical target of 0.02
        conversion_rate=0.05,  # above typical target of 0.03
        cost_per_conversion=5.0,
    )
    run = workflow.run("marketplace de servicios hogar", metrics=metrics)
    assert run.decision.verdict == GateVerdict.PASS
    assert run.decision.confidence >= 0.85


def test_run_with_dead_metrics_returns_kill(workflow):
    metrics = MetricsSnapshot(
        impressions=1200,
        clicks=3,
        conversions=0,
        cost_usd=200.0,
        ctr=0.0025,         # far below target
        conversion_rate=0.0,
        cost_per_conversion=0.0,
    )
    run = workflow.run("plataforma blockchain para notarías", metrics=metrics)
    assert run.decision.verdict == GateVerdict.KILL
    assert run.decision.confidence >= 0.85


def test_landing_slug_is_url_safe(workflow):
    run = workflow.run("EdTech para colegios bilingues")
    slug = run.landing.domain_slug
    import re
    assert re.match(r"^[a-z0-9][a-z0-9\-]+[a-z0-9]$", slug), f"Invalid slug: {slug!r}"


def test_run_summary_contains_verdict(workflow):
    run = workflow.run("logistics SaaS")
    summary = run.summary()
    assert run.decision.verdict.value.upper() in summary
    assert str(run.run_id) in summary


def test_multiple_topics_produce_different_run_ids(workflow):
    run1 = workflow.run("e-commerce fashion LATAM")
    run2 = workflow.run("telemedicina rural")
    assert run1.run_id != run2.run_id


def test_test_design_constraints(workflow):
    run = workflow.run("cualquier idea")
    assert 7 <= run.test_design.test_duration_days <= 30
    assert 50.0 <= run.test_design.ad_budget_usd <= 2000.0
    assert 0.005 <= run.test_design.target_ctr <= 0.20
    assert 0.01 <= run.test_design.target_conversion_rate <= 0.50
