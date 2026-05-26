"""Integration tests for /api/v1/leads endpoint (anti-bot)."""
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from orchestrator.api import _leads_store, app
from orchestrator.core import anti_bot


@pytest.fixture
def client():
    anti_bot.reset_stores()
    _leads_store.clear()
    # Test-friendly defaults: generous burst, tight enough to be testable
    anti_bot.TIERS["public_form"] = (5, 60, 30)
    anti_bot.MIN_FORM_DWELL_MS = 3000
    yield TestClient(app)
    anti_bot.reset_stores()
    _leads_store.clear()


def _payload(**overrides):
    base = {
        "slug": "techpulse-latam",
        "email": "founder@circles-ai.ai",
        "name": "Cris",
        "company_website": None,
        "dwell_ms": 5000,
        "turnstile_token": None,
    }
    base.update(overrides)
    return base


def test_lead_accepted_happy_path(client):
    r = client.post("/api/v1/leads", json=_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["accepted"] is True
    assert body["slug"] == "techpulse-latam"
    assert "techpulse-latam" in _leads_store
    assert _leads_store["techpulse-latam"][0]["email"] == "founder@circles-ai.ai"


def test_lead_honeypot_silent_accept(client):
    """When honeypot trips, we silent-accept so bots don't learn the trick.
    The lead is NOT actually stored."""
    r = client.post(
        "/api/v1/leads",
        json=_payload(company_website="http://spam-site.example"),
    )
    # API returns 201 to throw off the bot
    assert r.status_code == 201
    # But nothing is stored
    assert _leads_store["techpulse-latam"] == []


def test_lead_dwell_too_fast_blocked(client):
    r = client.post("/api/v1/leads", json=_payload(dwell_ms=200))
    assert r.status_code == 400
    assert "Retry-After" in r.headers
    assert _leads_store["techpulse-latam"] == []


def test_lead_disposable_email_blocked(client):
    r = client.post(
        "/api/v1/leads",
        json=_payload(email="throwaway@mailinator.com"),
    )
    assert r.status_code == 400
    assert "Disposable" in r.json()["detail"]
    assert _leads_store["techpulse-latam"] == []


def test_lead_rate_limit_enforced(client):
    anti_bot.TIERS["public_form"] = (2, 60, 30)
    client.post("/api/v1/leads", json=_payload(email="a@x.com"))
    client.post("/api/v1/leads", json=_payload(email="b@x.com"))
    r3 = client.post("/api/v1/leads", json=_payload(email="c@x.com"))
    assert r3.status_code == 429
    assert "Retry-After" in r3.headers


def test_lead_invalid_email_format_422(client):
    r = client.post("/api/v1/leads", json=_payload(email="x"))  # below min_length
    assert r.status_code == 422


def test_gate_run_secret_required_when_env_set(client, monkeypatch):
    monkeypatch.setenv("GATE_RUN_SECRET", "test-secret-123")
    r = client.post("/api/v1/gate/run", json={"topic": "test topic for gate"})
    assert r.status_code == 401


def test_gate_run_secret_accepts_correct_header(client, monkeypatch):
    """With the correct header set, the request should pass the secret gate.
    It may still rate-limit or 500 from the workflow — we only check it's NOT 401."""
    monkeypatch.setenv("GATE_RUN_SECRET", "test-secret-456")
    # Use a tier setup that allows the call
    anti_bot.TIERS["expensive_llm"] = (10, 300, 100)
    r = client.post(
        "/api/v1/gate/run",
        json={"topic": "fintech LATAM"},
        headers={"X-Gate-Secret": "test-secret-456"},
    )
    assert r.status_code != 401  # secret passed; downstream may 200/429/500


def test_gate_run_no_secret_when_env_unset(client, monkeypatch):
    monkeypatch.delenv("GATE_RUN_SECRET", raising=False)
    anti_bot.TIERS["expensive_llm"] = (10, 300, 100)
    r = client.post("/api/v1/gate/run", json={"topic": "fintech LATAM"})
    # Either accepted (mock) or rate-limited — but NOT 401
    assert r.status_code != 401
