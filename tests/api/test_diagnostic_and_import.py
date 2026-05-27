"""Tests for /api/v1/diagnostic and /api/v1/admin/import-leads endpoints."""
import pytest
from fastapi.testclient import TestClient

from orchestrator.api import app


@pytest.fixture
def client():
    return TestClient(app)


def _store():
    from orchestrator.core.storage import leads_store as s
    return s


# ---------------------------------------------------------------------------
# Diagnostic
# ---------------------------------------------------------------------------


def test_diagnostic_returns_public_snapshot(client):
    r = client.get("/api/v1/diagnostic")
    assert r.status_code == 200
    data = r.json()
    assert "version" in data
    assert "sprint" in data
    assert data["mode"] in {"live", "mock"}
    assert isinstance(data["cors_allowed_origins"], list)
    assert "https://circles-ai.ai" in data["cors_allowed_origins"]
    assert isinstance(data["features"], dict)
    # Important feature flags must be reported
    for flag in ("ensemble_gate_enabled", "fact_check_enabled", "persistent_storage"):
        assert flag in data["features"]


def test_diagnostic_reflects_leads_count(client):
    _store().add("techpulse-latam", "a@x.com", None, "1.1.1.1")
    _store().add("techpulse-latam", "b@x.com", None, "2.2.2.2")
    r = client.get("/api/v1/diagnostic")
    assert r.json()["leads_count_total"] == 2


def test_diagnostic_no_secrets_leaked(client):
    """Make sure raw API keys never appear in the diagnostic payload."""
    r = client.get("/api/v1/diagnostic")
    body = r.text
    # API keys all start with these prefixes
    for prefix in ("sk-ant-", "sk-proj-", "AIzaSy"):
        assert prefix not in body


# ---------------------------------------------------------------------------
# Admin import
# ---------------------------------------------------------------------------


def test_import_leads_rejects_without_secret_env(client, monkeypatch):
    """When server has no GATE_RUN_SECRET configured, endpoint is fully disabled."""
    monkeypatch.delenv("GATE_RUN_SECRET", raising=False)
    r = client.post(
        "/api/v1/admin/import-leads",
        json={"leads": [{"slug": "x", "email": "a@x.com"}]},
    )
    assert r.status_code == 401


def test_import_leads_rejects_wrong_secret(client, monkeypatch):
    monkeypatch.setenv("GATE_RUN_SECRET", "right")
    r = client.post(
        "/api/v1/admin/import-leads",
        json={"leads": [{"slug": "x", "email": "a@x.com"}]},
        headers={"X-Gate-Secret": "wrong"},
    )
    assert r.status_code == 401


def test_import_leads_happy_path(client, monkeypatch):
    monkeypatch.setenv("GATE_RUN_SECRET", "the-secret")
    r = client.post(
        "/api/v1/admin/import-leads",
        json={
            "leads": [
                {"slug": "techpulse-latam", "email": "a@x.com", "name": "A"},
                {"slug": "techpulse-latam", "email": "b@x.com"},
                {"slug": "opscore-ai", "email": "c@x.com"},
            ]
        },
        headers={"X-Gate-Secret": "the-secret"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["imported"] == 3
    assert data["skipped_duplicates"] == 0
    assert data["by_slug"]["techpulse-latam"] == 2
    assert data["by_slug"]["opscore-ai"] == 1
    # Verify leads landed in the store
    assert len(_store().list_by_slug("techpulse-latam")) == 2


def test_import_leads_deduplicates(client, monkeypatch):
    monkeypatch.setenv("GATE_RUN_SECRET", "the-secret")
    _store().add("techpulse-latam", "existing@x.com", None, "1.1.1.1")
    r = client.post(
        "/api/v1/admin/import-leads",
        json={
            "leads": [
                {"slug": "techpulse-latam", "email": "existing@x.com"},  # dup
                {"slug": "techpulse-latam", "email": "new@x.com"},
            ]
        },
        headers={"X-Gate-Secret": "the-secret"},
    )
    data = r.json()
    assert data["imported"] == 1
    assert data["skipped_duplicates"] == 1


def test_import_leads_caps_at_500_entries(client, monkeypatch):
    monkeypatch.setenv("GATE_RUN_SECRET", "the-secret")
    payload = {
        "leads": [{"slug": "x", "email": f"u{i}@x.com"} for i in range(501)],
    }
    r = client.post(
        "/api/v1/admin/import-leads",
        json=payload,
        headers={"X-Gate-Secret": "the-secret"},
    )
    assert r.status_code == 422  # Pydantic max_length=500
