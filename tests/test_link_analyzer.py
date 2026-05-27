"""Tests for LinkAnalyzerAgent (mock mode)."""
from orchestrator.agents.link_analyzer import LinkAnalysis, LinkAnalyzerAgent
from orchestrator.core.source_fetcher import FetchedItem


def _item(body: str = "real pain point text", title: str = "An idea about LATAM fintech") -> FetchedItem:
    return FetchedItem(
        source_kind="url", url="https://example.com/post",
        title=title, summary=body[:200], body=body,
    )


def test_analyze_empty_content_rejected():
    agent = LinkAnalyzerAgent(mock_mode=True)
    result = agent.analyze(_item(body="", title=""))
    assert result.status == "rejected"
    assert result.idea_summary is None
    assert "empty" in (result.rejection_reason or "").lower()


def test_analyze_off_topic_rejected():
    agent = LinkAnalyzerAgent(mock_mode=True)
    result = agent.analyze(_item(body="receta del dia para hacer pan casero"))
    assert result.status == "rejected"
    assert "off-topic" in (result.rejection_reason or "")


def test_analyze_idea_accepted():
    agent = LinkAnalyzerAgent(mock_mode=True)
    result = agent.analyze(_item(body="PYMEs Ecuador pierden 12 horas/semana en facturacion manual"))
    assert result.status == "analyzed"
    assert result.idea_summary is not None
    assert result.sector is not None
    assert result.area is not None
    assert result.rejection_reason is None


def test_link_analysis_dataclass_shape():
    a = LinkAnalysis(status="analyzed", idea_summary="x", sector="saas", area="y", rejection_reason=None)
    assert a.status == "analyzed"
