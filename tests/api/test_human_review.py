"""Tests for the human-in-the-loop review endpoints."""
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from orchestrator.api import _runs, app
from orchestrator.schemas.api import RunGateResponse


@pytest.fixture
def client():
    yield TestClient(app)
    _runs.clear()  # isolate tests


@pytest.fixture
def auth(client):
    """M3.12: review endpoints now require closed-beta auth."""
    os.environ["ALLOWED_EMAILS"] = "test@circles-ai.ai"
    r = client.post("/api/v1/auth/login", json={"email": "test@circles-ai.ai"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _make_stored_run(
    needs_review: bool = True,
    verdict: str = "iterate",
    override_verdict: str = None,
) -> str:
    """Inject a synthetic run into the in-memory store and return run_id."""
    run_id = str(uuid4())
    r = RunGateResponse(
        run_id=run_id,
        status="completed",
        idea_title="TestIdea",
        verdict=verdict,
        confidence=0.55,
        rationale="Ensemble disagreement",
        next_steps=["adjust copy"],
        landing_headline="Headline",
        landing_slug="testidea",
        test_design={"hypothesis": "..."},
        canonical_goal_statement="...",
        steps_used=6,
        cost_usd_estimated=0.06,
        needs_human_review=needs_review,
        review_reason=("Disagreement 67%" if needs_review else None),
        ensemble_votes=["claude/sonnet: pass (0.8)", "openai/gpt-4o-mini: iterate (0.7)", "google/gemini: iterate (0.7)"]
        if needs_review
        else None,
        human_override=(
            {
                "decided_by": "founder@test",
                "decided_at": "2026-05-26T12:00:00",
                "original_verdict": verdict,
                "override_verdict": override_verdict,
                "reason": "manual review",
            }
            if override_verdict
            else None
        ),
    )
    _runs[run_id] = r
    return run_id


def test_pending_review_returns_only_flagged_runs(client, auth):
    flagged = _make_stored_run(needs_review=True)
    _make_stored_run(needs_review=False)  # should NOT appear
    r = client.get("/api/v1/gate/pending-review", headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert data["pending_count"] == 1
    assert data["items"][0]["run_id"] == flagged


def test_pending_review_excludes_already_overridden(client, auth):
    _make_stored_run(needs_review=True, override_verdict="kill")
    r = client.get("/api/v1/gate/pending-review", headers=auth)
    assert r.json()["pending_count"] == 0


def test_pending_review_requires_auth(client):
    """M3.12: protected — no anonymous access to business decisions."""
    assert client.get("/api/v1/gate/pending-review").status_code == 401


def test_human_override_records_decision(client, auth):
    run_id = _make_stored_run(needs_review=True, verdict="iterate")
    r = client.post(
        f"/api/v1/gate/runs/{run_id}/human-override",
        headers=auth,
        json={
            "verdict": "pass",
            "reason": "saw a clear pattern in the conversion timing data",
            "decided_by": "cristian@circles-ai.ai",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["original_verdict"] == "iterate"
    assert data["override_verdict"] == "pass"
    assert data["decided_by"] == "cristian@circles-ai.ai"
    # The stored run is now updated
    stored = _runs[run_id]
    assert stored.verdict == "pass"
    assert stored.human_override is not None
    assert stored.human_override["reason"].startswith("saw a clear pattern")


def test_human_override_rejects_run_not_flagged(client, auth):
    run_id = _make_stored_run(needs_review=False)
    r = client.post(
        f"/api/v1/gate/runs/{run_id}/human-override",
        headers=auth,
        json={
            "verdict": "kill",
            "reason": "valid reason at least ten chars",
            "decided_by": "founder",
        },
    )
    assert r.status_code == 409


def test_human_override_rejects_double_override(client, auth):
    run_id = _make_stored_run(needs_review=True, override_verdict="pass")
    r = client.post(
        f"/api/v1/gate/runs/{run_id}/human-override",
        headers=auth,
        json={
            "verdict": "kill",
            "reason": "trying to override twice",
            "decided_by": "founder",
        },
    )
    assert r.status_code == 409


def test_human_override_rejects_invalid_verdict(client, auth):
    run_id = _make_stored_run(needs_review=True)
    r = client.post(
        f"/api/v1/gate/runs/{run_id}/human-override",
        headers=auth,
        json={
            "verdict": "MAYBE",  # not in pass|kill|iterate
            "reason": "valid reason here",
            "decided_by": "founder",
        },
    )
    assert r.status_code == 422


def test_human_override_rejects_unknown_run_id(client, auth):
    r = client.post(
        f"/api/v1/gate/runs/{uuid4()}/human-override",
        headers=auth,
        json={
            "verdict": "pass",
            "reason": "valid reason here at least ten",
            "decided_by": "founder",
        },
    )
    assert r.status_code == 404


def test_human_override_rejects_invalid_uuid_format(client, auth):
    r = client.post(
        "/api/v1/gate/runs/not-a-uuid/human-override",
        headers=auth,
        json={
            "verdict": "pass",
            "reason": "valid reason here at least ten",
            "decided_by": "founder",
        },
    )
    assert r.status_code == 422


def test_human_override_requires_auth(client):
    """M3.12: modifying business decisions must be authenticated."""
    run_id = _make_stored_run(needs_review=True)
    r = client.post(
        f"/api/v1/gate/runs/{run_id}/human-override",
        json={
            "verdict": "pass",
            "reason": "trying without auth",
            "decided_by": "anon",
        },
    )
    assert r.status_code == 401


def test_human_override_rejects_short_reason(client, auth):
    run_id = _make_stored_run(needs_review=True)
    r = client.post(
        f"/api/v1/gate/runs/{run_id}/human-override",
        headers=auth,
        json={
            "verdict": "pass",
            "reason": "too short",  # < 10 chars
            "decided_by": "founder",
        },
    )
    assert r.status_code == 422
