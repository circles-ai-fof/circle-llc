"""Tests for closed-beta auth (R27 / ADR-010)."""
import pytest
from fastapi.testclient import TestClient

from orchestrator.api import app


@pytest.fixture
def client():
    return TestClient(app)


def _auth_store():
    from orchestrator.core.storage import auth_store
    return auth_store


ALLOWED = "crisan312@hotmail.com,jfnunez@asiservy.com,cristian.molina.ia.soporte@gmail.com"


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_login_allowed_email_returns_token(client, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", ALLOWED)
    r = client.post("/api/v1/auth/login", json={"email": "crisan312@hotmail.com"})
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "crisan312@hotmail.com"
    assert len(data["token"]) >= 40
    assert data["expires_at"] > 0


def test_login_case_insensitive(client, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", ALLOWED)
    r = client.post("/api/v1/auth/login", json={"email": "CrIsAn312@Hotmail.com"})
    assert r.status_code == 200
    assert r.json()["email"] == "crisan312@hotmail.com"


def test_login_email_not_in_allowlist_403(client, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", ALLOWED)
    r = client.post("/api/v1/auth/login", json={"email": "random@stranger.com"})
    assert r.status_code == 403
    body = r.json()
    assert "lista de espera" in body["detail"].lower() or "beta" in body["detail"].lower()


def test_login_malformed_email_400(client, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", ALLOWED)
    r = client.post("/api/v1/auth/login", json={"email": "not-an-email"})
    assert r.status_code == 400


def test_login_logs_every_attempt(client, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", ALLOWED)
    client.post("/api/v1/auth/login", json={"email": "crisan312@hotmail.com"})
    client.post("/api/v1/auth/login", json={"email": "intruder@evil.com"})
    client.post("/api/v1/auth/login", json={"email": "malformed"})
    attempts = _auth_store().list_attempts()
    emails = [a["email"] for a in attempts]
    assert "crisan312@hotmail.com" in emails
    assert "intruder@evil.com" in emails
    # malformed email may be logged with the raw input
    assert any("malformed" in (a["reason"] or "") for a in attempts)


def test_login_with_empty_allowlist_rejects_all(client, monkeypatch):
    monkeypatch.delenv("ALLOWED_EMAILS", raising=False)
    r = client.post("/api/v1/auth/login", json={"email": "crisan312@hotmail.com"})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# /auth/me
# ---------------------------------------------------------------------------


def test_me_returns_user_with_valid_token(client, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", ALLOWED)
    login = client.post("/api/v1/auth/login", json={"email": "jfnunez@asiservy.com"})
    token = login.json()["token"]
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "jfnunez@asiservy.com"


def test_me_401_without_token(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_me_401_with_invalid_token(client):
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bogus-token-xxx"})
    assert r.status_code == 401


def test_me_401_with_malformed_authorization_header(client):
    r = client.get("/api/v1/auth/me", headers={"Authorization": "NotBearer xxx"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# /auth/logout
# ---------------------------------------------------------------------------


def test_logout_revokes_session(client, monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", ALLOWED)
    login = client.post("/api/v1/auth/login", json={"email": "crisan312@hotmail.com"})
    token = login.json()["token"]
    # Confirm session is valid
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    # Logout
    r = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["revoked"] is True
    # Token no longer valid
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_logout_without_token_returns_false(client):
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 200
    assert r.json()["revoked"] is False


# ---------------------------------------------------------------------------
# /admin/auth-attempts
# ---------------------------------------------------------------------------


def test_admin_auth_attempts_requires_secret(client, monkeypatch):
    monkeypatch.setenv("GATE_RUN_SECRET", "the-secret")
    r = client.get("/api/v1/admin/auth-attempts")
    assert r.status_code == 401


def test_admin_auth_attempts_with_secret(client, monkeypatch):
    monkeypatch.setenv("GATE_RUN_SECRET", "the-secret")
    monkeypatch.setenv("ALLOWED_EMAILS", ALLOWED)
    # Generate a few attempts
    client.post("/api/v1/auth/login", json={"email": "crisan312@hotmail.com"})
    client.post("/api/v1/auth/login", json={"email": "intruder@x.com"})
    r = client.get(
        "/api/v1/admin/auth-attempts",
        headers={"X-Gate-Secret": "the-secret"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 2
    assert len(data["items"]) >= 2
    # Most recent first
    emails_in_order = [it["email"] for it in data["items"]]
    assert "intruder@x.com" in emails_in_order
    assert "crisan312@hotmail.com" in emails_in_order


def test_admin_auth_attempts_disabled_without_secret_env(client, monkeypatch):
    monkeypatch.delenv("GATE_RUN_SECRET", raising=False)
    r = client.get(
        "/api/v1/admin/auth-attempts",
        headers={"X-Gate-Secret": "anything"},
    )
    assert r.status_code == 401
