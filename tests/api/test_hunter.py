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


# ---------------------------------------------------------------------------
# M3.2 follow-up — published_at + source_name + prompt potenciado (ADR-014)
# ---------------------------------------------------------------------------


def test_signals_include_published_at_and_source_name(client, auth):
    """list_signals must surface published_at + source_name (joined from sources)."""
    from orchestrator.core.storage import signals_store, sources_store

    sid = sources_store.add("rss", "https://startupeable.test/feed", "Startupeable LATAM")
    pub_ts = 1_700_000_000  # arbitrary fixed unix ts
    signals_store.add(
        sid, "rss", "Theme con fecha", 0.75, "excerpt",
        ["https://x.test/a"], "topic potencial", published_at=pub_ts,
    )
    # And one without source/published_at, to confirm Optional handling.
    signals_store.add(None, "hn", "Theme sin fuente", 0.6, "ex2", [], "topic 2")

    r = client.get("/api/v1/signals", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    by_theme = {it["theme"]: it for it in items}

    with_source = by_theme["Theme con fecha"]
    assert with_source["source_name"] == "Startupeable LATAM"
    assert with_source["published_at"] == pub_ts

    without_source = by_theme["Theme sin fuente"]
    assert without_source["source_name"] is None
    assert without_source["published_at"] is None


def test_parse_rfc822_or_iso_handles_common_formats():
    """RFC 822 (RSS pubDate) and ISO 8601 (Atom updated) both parse to unix ts."""
    from orchestrator.core.source_fetcher import _parse_rfc822_or_iso

    # RFC 822 — RSS pubDate
    rfc = _parse_rfc822_or_iso("Wed, 27 May 2026 14:30:00 +0000")
    assert rfc is not None and rfc > 1_700_000_000

    # ISO 8601 with Z suffix — Atom updated
    iso = _parse_rfc822_or_iso("2026-05-27T14:30:00Z")
    assert iso is not None and iso > 1_700_000_000

    # ISO 8601 with explicit offset
    iso2 = _parse_rfc822_or_iso("2026-05-27T09:30:00-05:00")
    assert iso2 is not None

    # Same UTC instant — RFC and ISO should align (±2s tolerance for ts precision)
    assert abs(rfc - iso) <= 2
    assert abs(rfc - iso2) <= 2

    # Garbage / empty inputs return None gracefully (never raise)
    assert _parse_rfc822_or_iso("") is None
    assert _parse_rfc822_or_iso("not a date") is None
    assert _parse_rfc822_or_iso("   ") is None


def test_run_from_sources_with_signal_id_injects_potentiated_prompt(client, auth):
    """Promoting a signal must inject a '=== SEÑAL DEL CAZADOR ===' block as
    evidence_context to idea_hunter — that's what makes the prompt 'potenciado'."""
    from orchestrator.core.storage import signals_store, sources_store

    sid = sources_store.add("rss", "https://startupeable.test/feed", "Startupeable LATAM")
    pub_ts = 1_700_000_000
    signal_id = signals_store.add(
        sid, "rss",
        "Lanzan plataforma B2B de gestión de inventarios",
        0.82, "Resumen del item con contexto rico",
        [],  # no evidence URLs — we don't want network fetches in the test
        "marketplace b2b inventarios latam",
        published_at=pub_ts,
    )

    # Spy on idea_hunter.generate to capture the evidence_context kwarg.
    # NOTE: test_api.py and test_observability.py delete orchestrator.* from
    # sys.modules, so `from orchestrator.api import _workflow` would return a
    # different singleton than the one this TestClient's `app` was wired to.
    # Resolve the workflow via the route function's own __globals__ — that's
    # the dict the running endpoint actually consults.
    route_workflow = None
    for route in app.routes:
        ep = getattr(route, "endpoint", None)
        if ep is not None and getattr(ep, "__name__", "") == "run_gate_from_sources":
            route_workflow = ep.__globals__["_workflow"]
            break
    assert route_workflow is not None, "could not locate live _workflow for endpoint"

    captured: dict = {}
    workflow = route_workflow
    original_generate = workflow._idea_hunter.generate

    def _spy(topic, feedback=None, evidence_context=None, **kw):
        captured["topic"] = topic
        captured["evidence_context"] = evidence_context
        return original_generate(topic, feedback=feedback, evidence_context=evidence_context, **kw)

    workflow._idea_hunter.generate = _spy  # type: ignore
    try:
        r = client.post(
            "/api/v1/gate/run-from-sources",
            headers=auth,
            json={"signal_id": signal_id},
        )
    finally:
        workflow._idea_hunter.generate = original_generate  # restore

    assert r.status_code == 201, r.text

    # Topic should carry the signal context, not just the raw theme.
    assert "Startupeable LATAM" in captured["topic"]

    # Evidence context must contain the structured "SEÑAL DEL CAZADOR" block
    # with all the fields the founder cares about.
    ec = captured["evidence_context"] or ""
    assert "=== SEÑAL DEL CAZADOR ===" in ec
    assert "Startupeable LATAM" in ec  # source name
    assert "rss" in ec  # source kind
    assert "0.82" in ec  # detection score
    assert "Lanzan plataforma B2B de gestión de inventarios" in ec  # theme
    assert "Resumen del item con contexto rico" in ec  # excerpt

    # And the signal must be marked as promoted afterwards
    sig_after = signals_store.get(signal_id)
    assert sig_after is not None
    assert sig_after["promoted_run_id"] == r.json()["run_id"]


def test_run_from_sources_signal_id_unknown_returns_404(client, auth):
    """Promoting a non-existent signal_id must 404, not 500."""
    r = client.post(
        "/api/v1/gate/run-from-sources",
        headers=auth,
        json={"signal_id": 99_999},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# M3.3 — list sort + kind filter + cleanup endpoint
# ---------------------------------------------------------------------------


def test_list_signals_sort_by_score_desc(client, auth):
    """sort=score returns highest score first."""
    from orchestrator.core.storage import signals_store
    signals_store.add(None, "rss", "low", 0.3, "ex", [], "topic")
    signals_store.add(None, "rss", "high", 0.9, "ex", [], "topic")
    signals_store.add(None, "rss", "mid", 0.6, "ex", [], "topic")

    r = client.get("/api/v1/signals?sort=score", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    scores = [it["score"] for it in items]
    assert scores == sorted(scores, reverse=True)
    assert items[0]["theme"] == "high"


def test_list_signals_filter_by_kind(client, auth):
    """kind=hn returns only hn signals."""
    from orchestrator.core.storage import signals_store
    signals_store.add(None, "rss", "rss-one", 0.5, "ex", [], "topic")
    signals_store.add(None, "hn", "hn-one", 0.5, "ex", [], "topic")
    signals_store.add(None, "reddit", "rd-one", 0.5, "ex", [], "topic")

    r = client.get("/api/v1/signals?kind=hn", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["source_kind"] == "hn"


def test_list_signals_sort_invalid_value_422(client, auth):
    r = client.get("/api/v1/signals?sort=banana", headers=auth)
    assert r.status_code == 422


def test_signals_cleanup_removes_stale_but_keeps_touched(client, auth):
    """Cleanup must purge old untouched signals but preserve any signal
    with feedback or a promoted_run_id (audit trail)."""
    import time
    from orchestrator.core.storage import signals_store

    # Inject 4 signals, then backdate created_at on 3 of them.
    stale_untouched = signals_store.add(None, "rss", "stale untouched", 0.5, "ex", [], "topic")
    stale_with_up = signals_store.add(None, "rss", "stale with up", 0.5, "ex", [], "topic")
    stale_promoted = signals_store.add(None, "rss", "stale promoted", 0.5, "ex", [], "topic")
    fresh_untouched = signals_store.add(None, "rss", "fresh untouched", 0.5, "ex", [], "topic")

    # Tag two of the stale ones so they should survive cleanup
    signals_store.set_feedback(stale_with_up, "up")
    signals_store.mark_promoted(stale_promoted, "run-fake-uuid")

    # Backdate three signals to 60 days ago
    cutoff = int(time.time()) - 60 * 86_400
    from orchestrator.core import storage as st
    if st._db_path:
        with st._conn() as c:
            c.executemany(
                "UPDATE signals SET created_at=? WHERE id=?",
                [(cutoff, stale_untouched), (cutoff, stale_with_up), (cutoff, stale_promoted)],
            )
    else:
        for r in st._memory_signals:
            if r["id"] in (stale_untouched, stale_with_up, stale_promoted):
                r["created_at"] = cutoff

    # Run cleanup with default 30-day threshold
    resp = client.post("/api/v1/signals/cleanup?older_than_days=30", headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted"] == 1  # only the stale_untouched one
    assert body["survivors_kept_with_feedback"] == 2  # the up + promoted ones

    # Verify the survivors are still there
    remaining = {s["theme"] for s in signals_store.list(limit=100)}
    assert "stale untouched" not in remaining
    assert "stale with up" in remaining
    assert "stale promoted" in remaining
    assert "fresh untouched" in remaining


def test_signals_cleanup_threshold_bounds(client, auth):
    """older_than_days must be 7-365."""
    assert client.post("/api/v1/signals/cleanup?older_than_days=3", headers=auth).status_code == 422
    assert client.post("/api/v1/signals/cleanup?older_than_days=1000", headers=auth).status_code == 422


def test_signals_cleanup_requires_auth(client):
    assert client.post("/api/v1/signals/cleanup").status_code == 401


# ---------------------------------------------------------------------------
# Autoscan loop status + resilience of _run_scan_internal
# ---------------------------------------------------------------------------


def test_autoscan_status_endpoint_default_disabled(client, auth):
    """In test env autoscan startup is skipped — endpoint reports disabled."""
    r = client.get("/api/v1/autoscan/status", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["interval_minutes"] == 0
    assert body["runs_completed"] == 0


def test_autoscan_status_requires_auth(client):
    assert client.get("/api/v1/autoscan/status").status_code == 401


def test_list_promoted_signals_returns_only_promoted(client, auth):
    """GET /api/v1/signals/promoted lists only signals with a promoted_run_id,
    newest first, with source_name joined."""
    from orchestrator.core.storage import signals_store, sources_store

    sid = sources_store.add("rss", "https://x.test/feed", "Test Feed")
    not_promoted = signals_store.add(sid, "rss", "Sin promover", 0.6, "ex", [], "topic")
    promoted_a = signals_store.add(sid, "rss", "Promovida A", 0.8, "ex", [], "topic")
    promoted_b = signals_store.add(sid, "rss", "Promovida B", 0.7, "ex", [], "topic")
    signals_store.mark_promoted(promoted_a, "run-aaa-uuid")
    signals_store.mark_promoted(promoted_b, "run-bbb-uuid")

    r = client.get("/api/v1/signals/promoted", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    themes = {it["theme"] for it in items}
    assert themes == {"Promovida A", "Promovida B"}
    assert "Sin promover" not in themes
    # source_name joined
    assert all(it["source_name"] == "Test Feed" for it in items)
    assert all(it["promoted_run_id"] for it in items)
    _ = not_promoted  # silence unused


def test_list_promoted_signals_requires_auth(client):
    assert client.get("/api/v1/signals/promoted").status_code == 401


def test_list_promoted_signals_invalid_limit_422(client, auth):
    assert client.get("/api/v1/signals/promoted?limit=0", headers=auth).status_code == 422
    assert client.get("/api/v1/signals/promoted?limit=999", headers=auth).status_code == 422


def test_run_scan_internal_swallows_fetch_errors(client, auth):
    """A misbehaving fetcher must not crash the scan — the loop relies on this."""
    from unittest.mock import patch
    # Add one source so _run_scan_internal has something to iterate
    add = client.post(
        "/api/v1/sources", headers=auth,
        json={"kind": "rss", "target": "https://x.test/feed", "name": "Broken Feed"},
    )
    assert add.status_code == 201

    # Locate the live api module via the route function (resilient to sys.modules swaps)
    api_mod = None
    for route in app.routes:
        ep = getattr(route, "endpoint", None)
        if ep is not None and getattr(ep, "__name__", "") == "scan_sources":
            api_mod = __import__(ep.__module__, fromlist=["_run_scan_internal"])
            break
    assert api_mod is not None

    def _boom(*args, **kw):
        raise RuntimeError("upstream is down")

    with patch.object(api_mod, "_workflow", api_mod._workflow):
        # Patch fetch_by_kind so the scan hits the failure branch
        with patch("orchestrator.core.source_fetcher.fetch_by_kind", side_effect=_boom):
            result = api_mod._run_scan_internal()

    # Did NOT raise. Scanned the source but produced 0 signals.
    assert result["scanned_sources"] == 1
    assert result["signals_created"] == 0
    assert result["items_fetched"] == 0
