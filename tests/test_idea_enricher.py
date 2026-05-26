"""Tests for IdeaEnricherAgent (mock mode)."""
from datetime import datetime
from uuid import uuid4

from orchestrator.agents.idea_enricher import IdeaEnricherAgent
from orchestrator.core.models import IdeaSpec, VerticalCategory


def _make_idea(market: str, problem: str) -> IdeaSpec:
    return IdeaSpec(
        id=uuid4(),
        title="Test Idea",
        description="A test idea for the enricher.",
        target_market=market,
        problem_statement=problem,
        proposed_solution="A SaaS platform with AI.",
        vertical_category=VerticalCategory.SAAS,
        created_at=datetime.utcnow(),
    )


def test_specific_idea_passes_unchanged():
    """A specific idea should pass through with high score and needs_refinement=False."""
    agent = IdeaEnricherAgent(mock_mode=True)
    idea = _make_idea(
        market="CFO PYMEs 10-50 empleados Ecuador manufactura",
        problem="60% PYMEs esperan 90+ dias para cobrar facturas",
    )
    refined, meta = agent.enrich(idea)
    assert meta["specificity_score"] >= 3.5
    assert meta["needs_refinement"] is False
    assert refined.target_market == idea.target_market
    assert refined.problem_statement == idea.problem_statement


def test_vague_idea_gets_refined():
    """An idea with vague keywords should be sharpened."""
    agent = IdeaEnricherAgent(mock_mode=True)
    idea = _make_idea(
        market="todas las empresas LATAM",
        problem="ayudar a manejar mejor las cosas",
    )
    refined, meta = agent.enrich(idea)
    assert meta["specificity_score"] < 3.5
    assert meta["needs_refinement"] is True
    assert "Ecuador" in refined.target_market or "PYMEs" in refined.target_market
    assert refined.id == idea.id  # id preserved
    assert meta["refinement_notes"] != "none"


def test_enrich_preserves_original_id():
    """The refined idea must keep the original UUID."""
    agent = IdeaEnricherAgent(mock_mode=True)
    idea = _make_idea("todas las empresas", "manejar procesos")
    refined, _ = agent.enrich(idea)
    assert refined.id == idea.id
