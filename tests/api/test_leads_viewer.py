"""Tests for /api/v1/leads/{slug} and /api/v1/leads/stats endpoints."""
import os

import pytest
from fastapi.testclient import TestClient

from orchestrator.api import app
from orchestrator.core import anti_bot
def _store():
    """Live reference — survives sys.modules reloads from other tests."""
    from orchestrator.core.storage import leads_store as s
    return s


@pytest.fixture
def client():
    anti_bot.reset_stores()
    _store().clear()
    anti_bot.TIERS["public_form"] = (1000, 60, 10000)
    yield TestClient(app)
    _store().clear()
    anti_bot.reset_stores()


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def test_stats_returns_zero_when_no_leads(client):
    r = client.get("/api/v1/leads/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_leads"] == 0
    assert {s["slug"]: s["count"] for s in data["by_slug"]} == {
        "techpulse-latam": 0,
        "opscore-ai": 0,
    }


def test_stats_aggregates_counts(client):
    _store().add("techpulse-latam", "a@x.com", "A", "1.1.1.1")
    _store().add("techpulse-latam", "b@x.com", "B", "2.2.2.2")
    _store().add("opscore-ai", "c@x.com", None, "3.3.3.3")
    r = client.get("/api/v1/leads/stats")
    data = r.json()
    assert data["total_leads"] == 3
    counts = {s["slug"]: s["count"] for s in data["by_slug"]}
    assert counts["techpulse-latam"] == 2
    assert counts["opscore-ai"] == 1


# ---------------------------------------------------------------------------
# List leads — masking
# ---------------------------------------------------------------------------


def test_list_leads_masks_email_without_secret(client, monkeypatch):
    monkeypatch.setenv("GATE_RUN_SECRET", "the-secret-123")
    _store().add("techpulse-latam", "founder@circles-ai.ai", "F", "1.2.3.4")
    r = client.get("/api/v1/leads/techpulse-latam")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert data["masked"] is True
    # 'founder' becomes 'fo***'
    assert data["leads"][0]["email"] == "fo***@circles-ai.ai"
    # IP last octet masked
    assert data["leads"][0]["ip_masked"] == "1.2.3.xxx"


def test_list_leads_full_email_with_secret(client, monkeypatch):
    monkeypatch.setenv("GATE_RUN_SECRET", "the-secret-123")
    _store().add("techpulse-latam", "founder@circles-ai.ai", "F", "1.2.3.4")
    r = client.get(
        "/api/v1/leads/techpulse-latam",
        headers={"X-Gate-Secret": "the-secret-123"},
    )
    data = r.json()
    assert data["masked"] is False
    assert data["leads"][0]["email"] == "founder@circles-ai.ai"


def test_list_leads_wrong_secret_treated_as_unprivileged(client, monkeypatch):
    monkeypatch.setenv("GATE_RUN_SECRET", "the-secret-123")
    _store().add("techpulse-latam", "founder@circles-ai.ai", "F", "1.2.3.4")
    r = client.get(
        "/api/v1/leads/techpulse-latam",
        headers={"X-Gate-Secret": "wrong"},
    )
    data = r.json()
    assert data["masked"] is True
    assert "fo***" in data["leads"][0]["email"]


def test_list_leads_no_secret_configured_always_masks(client, monkeypatch):
    """If GATE_RUN_SECRET is not set, no caller is admin -> always masked."""
    monkeypatch.delenv("GATE_RUN_SECRET", raising=False)
    _store().add("techpulse-latam", "founder@circles-ai.ai", "F", "1.2.3.4")
    r = client.get(
        "/api/v1/leads/techpulse-latam",
        headers={"X-Gate-Secret": "anything"},
    )
    data = r.json()
    assert data["masked"] is True


def test_list_leads_short_local_part_masked(client, monkeypatch):
    monkeypatch.setenv("GATE_RUN_SECRET", "x")
    _store().add("techpulse-latam", "ab@y.com", None, "1.1.1.1")
    r = client.get("/api/v1/leads/techpulse-latam")
    # 'ab' (2 chars) -> 'a***@y.com'
    assert r.json()["leads"][0]["email"] == "a***@y.com"


def test_list_leads_empty_slug_returns_empty(client):
    r = client.get("/api/v1/leads/nonexistent-slug")
    assert r.status_code == 200
    assert r.json()["count"] == 0
    assert r.json()["leads"] == []


def test_list_leads_respects_limit_param(client):
    for i in range(10):
        _store().add("techpulse-latam", f"u{i}@x.com", None, "1.1.1.1")
    r = client.get("/api/v1/leads/techpulse-latam?limit=3")
    data = r.json()
    assert data["count"] == 10  # total stored
    assert len(data["leads"]) == 3  # but only 3 returned


def test_list_leads_invalid_limit_422(client):
    r = client.get("/api/v1/leads/techpulse-latam?limit=9999")
    assert r.status_code == 422
