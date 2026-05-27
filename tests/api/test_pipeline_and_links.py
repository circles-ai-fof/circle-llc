"""Integration tests for /api/v1/pipeline + /api/v1/links + import-file."""
import io
import os

import pytest
from fastapi.testclient import TestClient

from orchestrator.api import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth(client):
    os.environ["ALLOWED_EMAILS"] = "test@circles-ai.ai"
    r = client.post("/api/v1/auth/login", json={"email": "test@circles-ai.ai"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ---------------------------------------------------------------------------
# Pipeline endpoint
# ---------------------------------------------------------------------------


def test_pipeline_empty_returns_5_columns(client, auth):
    r = client.get("/api/v1/pipeline", headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert data["total_runs"] == 0
    assert len(data["columns"]) == 5
    phases = [c["phase"] for c in data["columns"]]
    assert phases == ["pending_review", "iterate", "pass", "kill", "overridden"]


def test_pipeline_requires_auth(client):
    r = client.get("/api/v1/pipeline")
    assert r.status_code == 401


def test_pipeline_buckets_runs_correctly(client, auth):
    from orchestrator.api import _runs
    from orchestrator.schemas.api import RunGateResponse

    def mk(run_id: str, verdict: str, needs_review: bool = False, override: bool = False) -> RunGateResponse:
        return RunGateResponse(
            run_id=run_id, status="completed",
            idea_title=f"Idea {run_id}", verdict=verdict, confidence=0.7,
            rationale="r", next_steps=[], landing_headline="H", landing_slug=run_id,
            test_design={}, canonical_goal_statement="g", steps_used=6,
            cost_usd_estimated=0.06,
            needs_human_review=needs_review,
            review_reason="x" if needs_review else None,
            ensemble_votes=None,
            human_override={"override_verdict": "pass", "decided_by": "x", "decided_at": "now",
                            "original_verdict": verdict, "reason": "manual"} if override else None,
        )

    _runs["aaaaaaaa-0000-0000-0000-000000000001"] = mk("aaaaaaaa-0000-0000-0000-000000000001", "pass")
    _runs["aaaaaaaa-0000-0000-0000-000000000002"] = mk("aaaaaaaa-0000-0000-0000-000000000002", "kill")
    _runs["aaaaaaaa-0000-0000-0000-000000000003"] = mk("aaaaaaaa-0000-0000-0000-000000000003", "iterate")
    _runs["aaaaaaaa-0000-0000-0000-000000000004"] = mk("aaaaaaaa-0000-0000-0000-000000000004", "iterate", needs_review=True)
    _runs["aaaaaaaa-0000-0000-0000-000000000005"] = mk("aaaaaaaa-0000-0000-0000-000000000005", "iterate", override=True)

    r = client.get("/api/v1/pipeline", headers=auth)
    data = r.json()
    counts = {c["phase"]: c["count"] for c in data["columns"]}
    assert counts == {
        "pass": 1,
        "kill": 1,
        "iterate": 1,
        "pending_review": 1,
        "overridden": 1,
    }
    assert data["total_runs"] == 5


# ---------------------------------------------------------------------------
# Links bitácora
# ---------------------------------------------------------------------------


def test_links_empty(client, auth):
    r = client.get("/api/v1/links", headers=auth)
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_links_filter_invalid_status(client, auth):
    r = client.get("/api/v1/links?status_filter=invalid", headers=auth)
    assert r.status_code == 422


def test_links_requires_auth(client):
    assert client.get("/api/v1/links").status_code == 401


# ---------------------------------------------------------------------------
# Import file
# ---------------------------------------------------------------------------


def test_import_file_extracts_urls_from_whatsapp_chat(client, auth):
    chat_text = """[12/05/26 09:32] Cristian: mira esto https://techcrunch.com/x
[12/05/26 09:33] JF: y https://www.elcomercio.com/y
[12/05/26 09:35] Cristian: nada aquí (sin link)"""
    files = {"file": ("chat-whatsapp.txt", io.BytesIO(chat_text.encode()), "text/plain")}
    r = client.post("/api/v1/sources/import-file", files=files, headers=auth)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["urls_found"] == 2
    assert data["urls_added"] == 2
    assert data["sources_created"] == 2
    # Verify the bitacora and sources were populated
    links = client.get("/api/v1/links", headers=auth).json()
    assert links["total"] == 2
    assert all(l["source_file"] == "chat-whatsapp.txt" for l in links["items"])
    srcs = client.get("/api/v1/sources", headers=auth).json()
    assert srcs["total"] >= 2


def test_import_file_dedups_urls(client, auth):
    """Same URL twice in the file is only added once."""
    text = "first https://x.com, second mention https://x.com, third https://y.com"
    files = {"file": ("notes.txt", io.BytesIO(text.encode()), "text/plain")}
    r = client.post("/api/v1/sources/import-file", files=files, headers=auth)
    data = r.json()
    assert data["urls_found"] == 2
    assert data["sources_created"] == 2


def test_import_file_rejects_disallowed_extension(client, auth):
    files = {"file": ("hax.exe", io.BytesIO(b"binary"), "application/octet-stream")}
    r = client.post("/api/v1/sources/import-file", files=files, headers=auth)
    assert r.status_code == 400
    assert "txt" in r.json()["detail"].lower() or "docx" in r.json()["detail"].lower()


def test_import_file_rejects_empty(client, auth):
    files = {"file": ("empty.txt", io.BytesIO(b""), "text/plain")}
    r = client.post("/api/v1/sources/import-file", files=files, headers=auth)
    assert r.status_code == 400


def test_import_file_requires_auth(client):
    files = {"file": ("x.txt", io.BytesIO(b"hello"), "text/plain")}
    r = client.post("/api/v1/sources/import-file", files=files)
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Analyze batch
# ---------------------------------------------------------------------------


def test_analyze_batch_with_no_pending_does_nothing(client, auth):
    r = client.post("/api/v1/links/analyze", json={}, headers=auth)
    assert r.status_code == 200
    d = r.json()
    assert d["analyzed"] == 0
    assert d["rejected"] == 0


def test_analyze_batch_mock_mode_rejects_without_real_fetch(client, auth):
    """In mock_mode, fetch_url returns None on real URLs (we don't hit the net)
    but the endpoint should not crash — links get marked rejected."""
    from orchestrator.core.storage import links_log_store
    links_log_store.add("https://nonexistent-host-circles-test.invalid", "test.txt")
    r = client.post(
        "/api/v1/links/analyze",
        json={"max_to_analyze": 5},
        headers=auth,
    )
    assert r.status_code == 200
    # Either rejected (couldn't fetch) or analyzed (if cache hit; unlikely)
    assert r.json()["analyzed"] + r.json()["rejected"] + r.json()["errors"] >= 1
