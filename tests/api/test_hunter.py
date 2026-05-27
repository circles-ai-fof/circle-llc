"""Integration tests for hunter endpoints (sources / scan / signals)."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from orchestrator.api import app


def _auth_token(client):
    """Helper: login as the first allowed email, return Bearer header."""
    from orchestrator.core import auth as ab_auth
    # Hardcode an allowlisted email for tests
    import os
    os.environ["ALLOWED_EMAILS"] = "test@circles-ai.ai"
    r = client.post("/api/v1/auth/login", json={"email": "test@circles-ai.ai"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth(client):
    return _auth_token(client)


def test_list_sources_empty(client, auth):
    r = client.get("/api/v1/sources", headers=auth)
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_add_source_then_list(client, auth):
    r = client.post(
        "/api/v1/sources",
        headers=auth,
        json={"kind": "hn", "target": "", "name": "Hacker News"},
    )
    assert r.status_code == 201
    sid = r.json()["id"]
    assert sid >= 1
    r2 = client.get("/api/v1/sources", headers=auth)
    assert r2.status_code == 200
    assert r2.json()["total"] == 1
    assert r2.json()["items"][0]["kind"] == "hn"


def test_add_source_invalid_kind_422(client, auth):
    r = client.post(
        "/api/v1/sources",
        headers=auth,
        json={"kind": "invalid_kind", "target": "", "name": "X"},
    )
    assert r.status_code == 422


def test_delete_source(client, auth):
    r = client.post("/api/v1/sources", headers=auth, json={"kind": "rss", "target": "https://x.test/feed", "name": "X"})
    sid = r.json()["id"]
    d = client.delete(f"/api/v1/sources/{sid}", headers=auth)
    assert d.status_code == 204
    assert client.get("/api/v1/sources", headers=auth).json()["total"] == 0


def test_sources_endpoints_require_auth(client):
    assert client.get("/api/v1/sources").status_code == 401
    assert client.post("/api/v1/sources", json={"kind": "hn", "target": "", "name": "x"}).status_code == 401


def test_scan_with_no_sources_returns_zero(client, auth):
    r = client.post("/api/v1/sources/scan", headers=auth, json={})
    assert r.status_code == 200
    data = r.json()
    assert data["scanned_sources"] == 0
    assert data["signals_created"] == 0


def test_scan_mock_creates_signal(client, auth):
    """With mock_mode workflow, scanner mock produces 1 signal per source with 2+ items."""
    # Add a source
    add = client.post("/api/v1/sources", headers=auth, json={"kind": "rss", "target": "https://x.test/feed", "name": "Feed"})
    sid = add.json()["id"]

    # Stub fetch_by_kind to return 3 items
    from orchestrator.core.source_fetcher import FetchedItem
    fake_items = [
        FetchedItem(source_kind="rss", url=f"https://x.test/{i}", title=f"t{i}", summary=f"s{i}", body=f"b{i}")
        for i in range(3)
    ]
    with patch("orchestrator.api.fetch_by_kind", return_value=fake_items, create=True):
        # patch the imported name inside api.py — since it's imported lazily inside
        # the endpoint we patch the module path it'll be looked up through.
        with patch("orchestrator.core.source_fetcher.fetch_by_kind", return_value=fake_items):
            r = client.post(
                "/api/v1/sources/scan",
                headers=auth,
                json={"source_ids": [sid], "auto_promote_threshold": 0},
            )
    assert r.status_code == 200
    data = r.json()
    assert data["scanned_sources"] == 1
    # Mock scanner: 1 signal when >=2 items
    assert data["signals_created"] == 1


def test_list_signals_empty(client, auth):
    r = client.get("/api/v1/signals", headers=auth)
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_signal_feedback(client, auth):
    # Insert a signal directly
    from orchestrator.core.storage import signals_store
    sid = signals_store.add(
        source_id=None, source_kind="hn", theme="Test theme", score=0.8,
        excerpt="An excerpt", evidence_urls=["https://x.test/a"],
        suggested_topic="Test topic",
    )
    r = client.post(
        f"/api/v1/signals/{sid}/feedback",
        headers=auth,
        json={"feedback": "up"},
    )
    assert r.status_code == 200
    assert r.json()["feedback"] == "up"
    # Clear it
    r2 = client.post(
        f"/api/v1/signals/{sid}/feedback",
        headers=auth,
        json={"feedback": "clear"},
    )
    assert r2.status_code == 200
    assert r2.json()["feedback"] is None


def test_signal_feedback_404(client, auth):
    r = client.post("/api/v1/signals/99999/feedback", headers=auth, json={"feedback": "up"})
    assert r.status_code == 404


def test_run_from_sources_requires_at_least_one_input(client, auth):
    r = client.post("/api/v1/gate/run-from-sources", headers=auth, json={})
    assert r.status_code == 422


def test_run_from_sources_with_topic_works(client, auth):
    """Mock-mode workflow: should accept and return a RunGateResponse."""
    r = client.post(
        "/api/v1/gate/run-from-sources",
        headers=auth,
        json={"topic": "marketplace de servicios"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "completed"
    assert body["verdict"] in ("pass", "kill", "iterate")


# ---------------------------------------------------------------------------
# M3.1 — Source quality scoring (R29)
# ---------------------------------------------------------------------------


def test_sources_quality_empty_when_no_sources(client, auth):
    r = client.get("/api/v1/sources/quality", headers=auth)
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_sources_quality_aggregates_feedback(client, auth):
    # Create one source
    add = client.post(
        "/api/v1/sources", headers=auth,
        json={"kind": "rss", "target": "https://x.test/feed", "name": "Feed One"},
    )
    sid = add.json()["id"]
    # Inject signals tied to that source with mixed feedback
    from orchestrator.core.storage import signals_store
    s1 = signals_store.add(sid, "rss", "Tema A", 0.7, "ex", ["u1"], "topic A")
    s2 = signals_store.add(sid, "rss", "Tema B", 0.6, "ex", ["u2"], "topic B")
    s3 = signals_store.add(sid, "rss", "Tema C", 0.8, "ex", ["u3"], "topic C")
    signals_store.set_feedback(s1, "up")
    signals_store.set_feedback(s2, "up")
    signals_store.set_feedback(s3, "down")
    signals_store.mark_promoted(s1, "run-abc")

    r = client.get("/api/v1/sources/quality", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    q = items[0]
    assert q["source_id"] == sid
    assert q["signals_total"] == 3
    assert q["signals_up"] == 2
    assert q["signals_down"] == 1
    assert q["signals_promoted"] == 1
    assert 0.0 <= q["quality_score"] <= 1.0


def test_sources_quality_requires_auth(client):
    r = client.get("/api/v1/sources/quality")
    assert r.status_code == 401


def test_signals_listed_with_trend_score(client, auth):
    """Signals API returns trend_score field (default 0)."""
    from orchestrator.core.storage import signals_store
    signals_store.add(None, "hn", "Some theme keyword", 0.7, "ex", ["u"], "topic")
    r = client.get("/api/v1/signals", headers=auth)
    items = r.json()["items"]
    assert items
    assert "trend_score" in items[0]
    assert items[0]["trend_score"] == 0  # first signal -> no prior signals
