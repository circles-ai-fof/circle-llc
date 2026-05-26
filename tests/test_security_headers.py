"""Tests for the FastAPI security headers middleware."""
import pytest
from fastapi.testclient import TestClient

from orchestrator.api import app


@pytest.fixture
def client():
    return TestClient(app)


def test_x_content_type_options(client):
    r = client.get("/api/v1/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


def test_x_frame_options(client):
    r = client.get("/api/v1/health")
    assert r.headers.get("X-Frame-Options") == "DENY"


def test_referrer_policy(client):
    r = client.get("/api/v1/health")
    assert "strict-origin" in r.headers.get("Referrer-Policy", "")


def test_permissions_policy(client):
    r = client.get("/api/v1/health")
    pp = r.headers.get("Permissions-Policy", "")
    assert "geolocation=()" in pp
    assert "camera=()" in pp


def test_hsts(client):
    r = client.get("/api/v1/health")
    assert "max-age" in r.headers.get("Strict-Transport-Security", "")


def test_csp_locks_down_api(client):
    r = client.get("/api/v1/health")
    csp = r.headers.get("Content-Security-Policy", "")
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def test_cors_rejects_disallowed_origin(client):
    """A non-whitelisted origin must NOT get an Access-Control-Allow-Origin echo."""
    r = client.get(
        "/api/v1/health",
        headers={"Origin": "https://evil.example.com"},
    )
    assert r.headers.get("Access-Control-Allow-Origin") != "https://evil.example.com"


def test_cors_allows_circles_origin(client):
    r = client.get(
        "/api/v1/health",
        headers={"Origin": "https://circles-ai.ai"},
    )
    assert r.headers.get("Access-Control-Allow-Origin") == "https://circles-ai.ai"
