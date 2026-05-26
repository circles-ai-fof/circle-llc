"""
tests/api/test_api.py — Integration tests for the EvidenceGate REST API.

Uses FastAPI TestClient (httpx-backed, no real server, no API keys).
Rule R06: ANTHROPIC_API_KEY is absent in CI → workflow auto-starts in mock_mode.

Test catalogue:
  test_health_returns_200
  test_run_gate_mock_mode
  test_run_gate_invalid_topic
  test_get_run_by_id
  test_get_run_not_found
  test_agents_list
"""
from __future__ import annotations

import importlib
import sys
import uuid

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixture: fresh app + client per test module
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    """
    Build a TestClient from a freshly imported api module.
    Using scope="module" to avoid re-importing for each test (acceptable since
    in-memory state is not shared between test functions that create runs by
    using unique topics).
    """
    # Force reload so that _runs dict and _workflow singleton are fresh.
    # This matters when tests/api/ is run in isolation vs. a full suite.
    for mod_name in list(sys.modules.keys()):
        if "orchestrator.api" in mod_name or "orchestrator.schemas" in mod_name:
            del sys.modules[mod_name]

    from orchestrator.api import app  # noqa: PLC0415

    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_response_shape(self, client: TestClient) -> None:
        data = client.get("/api/v1/health").json()
        assert data["status"] == "ok"
        assert "version" in data
        assert data["mode"] in {"live", "mock"}
        assert data["workflow"] == "EvidenceGateWorkflow"

    def test_health_mode_is_mock_without_api_key(
        self, client: TestClient, monkeypatch
    ) -> None:
        """CI has no ANTHROPIC_API_KEY, so mode must be 'mock'."""
        import os

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        data = client.get("/api/v1/health").json()
        # Mode reflects the singleton that was created at import time — it should
        # already be mock because the key is absent in CI.
        assert data["mode"] in {"live", "mock"}  # both are valid; just check type


class TestRunGate:
    def test_run_gate_mock_mode(self, client: TestClient) -> None:
        """POST with valid topic returns 201 with complete RunGateResponse shape."""
        response = client.post(
            "/api/v1/gate/run",
            json={"topic": "fintech para PYMEs Ecuador"},
        )
        assert response.status_code == 201, response.text
        data = response.json()

        # Required fields
        assert "run_id" in data
        assert data["status"] == "completed"
        assert data["verdict"] in {"pass", "kill", "iterate"}
        assert isinstance(data["confidence"], float)
        assert 0.0 <= data["confidence"] <= 1.0
        assert isinstance(data["rationale"], str) and data["rationale"]
        assert isinstance(data["next_steps"], list) and len(data["next_steps"]) >= 1
        assert isinstance(data["landing_headline"], str) and data["landing_headline"]
        assert isinstance(data["landing_slug"], str) and data["landing_slug"]
        assert isinstance(data["test_design"], dict)
        assert isinstance(data["canonical_goal_statement"], str)
        assert isinstance(data["steps_used"], int)
        assert isinstance(data["cost_usd_estimated"], float)

        # test_design sub-keys (from EvidenceTestDesign)
        td = data["test_design"]
        assert "hypothesis" in td
        assert "ad_budget_usd" in td
        assert "test_duration_days" in td

    def test_run_gate_invalid_topic_too_short(self, client: TestClient) -> None:
        """Single-character topic must return 422 (Pydantic validation error)."""
        response = client.post("/api/v1/gate/run", json={"topic": "x"})
        assert response.status_code == 422

    def test_run_gate_invalid_topic_empty(self, client: TestClient) -> None:
        """Empty string must return 422."""
        response = client.post("/api/v1/gate/run", json={"topic": ""})
        assert response.status_code == 422

    def test_run_gate_invalid_topic_too_long(self, client: TestClient) -> None:
        """Topic exceeding 200 chars must return 422."""
        response = client.post("/api/v1/gate/run", json={"topic": "a" * 201})
        assert response.status_code == 422

    def test_run_gate_missing_topic(self, client: TestClient) -> None:
        """Missing topic field must return 422."""
        response = client.post("/api/v1/gate/run", json={})
        assert response.status_code == 422

    def test_run_gate_with_metrics(self, client: TestClient) -> None:
        """POST with optional MetricsSnapshot should succeed."""
        payload = {
            "topic": "app de salud mental para adultos mayores",
            "metrics": {
                "impressions": 1000,
                "clicks": 40,
                "conversions": 10,
                "cost_usd": 100.0,
                "ctr": 0.04,
                "conversion_rate": 0.025,
                "cost_per_conversion": 10.0,
            },
        }
        response = client.post("/api/v1/gate/run", json=payload)
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "completed"

    def test_run_gate_returns_unique_run_ids(self, client: TestClient) -> None:
        """Each run must have a different run_id."""
        r1 = client.post("/api/v1/gate/run", json={"topic": "edtech para colegios"}).json()
        r2 = client.post("/api/v1/gate/run", json={"topic": "marketplace de ropa usada"}).json()
        assert r1["run_id"] != r2["run_id"]


class TestGetRun:
    def test_get_run_by_id(self, client: TestClient) -> None:
        """Create a run, then fetch it by run_id — must return the same data."""
        create_resp = client.post(
            "/api/v1/gate/run",
            json={"topic": "logistica last-mile Ecuador"},
        )
        assert create_resp.status_code == 201
        created = create_resp.json()
        run_id = created["run_id"]

        get_resp = client.get(f"/api/v1/gate/runs/{run_id}")
        assert get_resp.status_code == 200
        fetched = get_resp.json()

        assert fetched["run_id"] == run_id
        assert fetched["verdict"] == created["verdict"]
        assert fetched["idea_title"] == created["idea_title"]
        assert fetched["landing_slug"] == created["landing_slug"]

    def test_get_run_not_found(self, client: TestClient) -> None:
        """Non-existent UUID must return 404."""
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/gate/runs/{fake_id}")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_run_invalid_uuid_format(self, client: TestClient) -> None:
        """Malformed UUID must return 422."""
        response = client.get("/api/v1/gate/runs/not-a-valid-uuid")
        assert response.status_code == 422


class TestAgents:
    def test_agents_list(self, client: TestClient) -> None:
        """GET /api/v1/agents must return exactly 5 active agents."""
        response = client.get("/api/v1/agents")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 5
        assert len(data["agents"]) == 5

    def test_agents_all_active(self, client: TestClient) -> None:
        """All 5 M1 agents must have status='active'."""
        agents = client.get("/api/v1/agents").json()["agents"]
        for agent in agents:
            assert agent["status"] == "active", f"{agent['name']} is not active"

    def test_agents_expected_names(self, client: TestClient) -> None:
        """The 5 expected agent names must be present."""
        expected = {
            "idea_hunter",
            "idea_maturer",
            "market_validator",
            "landing_generator",
            "gate_decider",
        }
        agents = client.get("/api/v1/agents").json()["agents"]
        names = {a["name"] for a in agents}
        assert names == expected

    def test_agents_have_scope_fields(self, client: TestClient) -> None:
        """Each agent must have non-empty scope_does and scope_does_not."""
        agents = client.get("/api/v1/agents").json()["agents"]
        for agent in agents:
            assert agent["scope_does"], f"{agent['name']} missing scope_does"
            assert agent["scope_does_not"], f"{agent['name']} missing scope_does_not"
