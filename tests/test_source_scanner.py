"""Tests for the SourceScannerAgent."""
from orchestrator.agents.source_scanner import Signal, SourceScannerAgent
from orchestrator.core.source_fetcher import FetchedItem


def _items(n: int, kind: str = "hn") -> list[FetchedItem]:
    return [
        FetchedItem(
            source_kind=kind,
            url=f"https://x.test/{i}",
            title=f"Item {i}",
            summary=f"Summary {i}",
            body=f"Body content {i}",
        )
        for i in range(n)
    ]


def test_scan_empty_returns_empty():
    agent = SourceScannerAgent(mock_mode=True)
    assert agent.scan([]) == []


def test_scan_mock_returns_signal_for_2plus_items():
    agent = SourceScannerAgent(mock_mode=True)
    sigs = agent.scan(_items(3, kind="hn"))
    assert len(sigs) == 1
    s = sigs[0]
    assert isinstance(s, Signal)
    assert s.score >= 0.5
    assert s.source_kind == "hn"
    assert s.items_seen == 3
    assert len(s.evidence_urls) <= 3


def test_scan_mock_single_item_returns_empty():
    agent = SourceScannerAgent(mock_mode=True)
    assert agent.scan(_items(1)) == []


def test_signal_dataclass_defaults():
    s = Signal(theme="t", score=0.6, excerpt="e", evidence_urls=[], suggested_topic="x")
    assert s.source_kind == ""
    assert s.items_seen == 0
