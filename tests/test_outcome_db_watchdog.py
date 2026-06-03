"""
Tests for M11.2 — Outcome DB watchdog + snapshot endpoint.

Two endpoints:
  GET /api/v1/admin/outcome-db-trigger — counts factories, returns status
  GET /api/v1/admin/db-snapshot       — streams the SQLite file for backup

We don't exercise the R2 upload here (that lives in the GH Actions
workflow); we just pin the local behavior:
  - Status grades correctly at thresholds 0 / 2 / 3+
  - Snapshot returns 404 when DATABASE_PATH is empty (memory mode)
  - Auth required on both endpoints
"""
import os
from fastapi.testclient import TestClient


def _client_with_auth() -> tuple[TestClient, dict]:
    os.environ["ALLOWED_EMAILS"] = "test@example.com,cristian.molina.ia.soporte@gmail.com"
    from orchestrator.api import app
    c = TestClient(app)
    t = c.post("/api/v1/auth/login", json={"email": "test@example.com"}).json()["token"]
    return c, {"Authorization": f"Bearer {t}"}


# ---------------------------------------------------------------------------
# Watchdog
# ---------------------------------------------------------------------------

def test_watchdog_returns_ok_with_no_factories():
    from orchestrator.core.storage import runs_store
    runs_store.clear()
    c, h = _client_with_auth()
    r = c.get("/api/v1/admin/outcome-db-trigger", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["current_factories"] == 0
    assert body["trigger_threshold"] == 3


def _put_run(run_id: str, verdict: str | None = None):
    """Helper: insert a run row via the dict-like RunsStore API."""
    from orchestrator.core.storage import runs_store
    runs_store[run_id] = {
        "run_id": run_id,
        "topic": "test",
        "verdict": verdict,
        "created_at": 1780000000,
        "summary": "test",
    }


def test_watchdog_returns_warning_at_n2():
    """When N=2, status flips to warning so the operator preps the migration
    branch BEFORE N=3 forces action."""
    from orchestrator.core.storage import runs_store
    runs_store.clear()
    _put_run("run-1", "pass")
    _put_run("run-2", "kill")

    c, h = _client_with_auth()
    r = c.get("/api/v1/admin/outcome-db-trigger", headers=h)
    body = r.json()
    assert body["status"] == "warning"
    assert body["current_factories"] == 2


def test_watchdog_returns_action_at_n3():
    """At N>=3 the operator MUST migrate; the message includes the
    branch + doc to follow."""
    from orchestrator.core.storage import runs_store
    runs_store.clear()
    for i, v in enumerate(("pass", "kill", "iterate")):
        _put_run(f"run-{i}", v)

    c, h = _client_with_auth()
    r = c.get("/api/v1/admin/outcome-db-trigger", headers=h)
    body = r.json()
    assert body["status"] == "action"
    assert body["current_factories"] == 3
    assert "migration" in body["message"].lower()


def test_watchdog_ignores_unfinished_runs():
    """Runs without a verdict (still in flight) don't count as factories.
    Only completed gates of any verdict count."""
    from orchestrator.core.storage import runs_store
    runs_store.clear()
    _put_run("done-1", "pass")
    _put_run("done-2", "kill")
    _put_run("in-flight", None)  # no verdict yet

    c, h = _client_with_auth()
    r = c.get("/api/v1/admin/outcome-db-trigger", headers=h)
    body = r.json()
    assert body["current_factories"] == 2  # only the finished ones


def test_watchdog_requires_auth():
    from orchestrator.api import app
    c = TestClient(app)
    r = c.get("/api/v1/admin/outcome-db-trigger")
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Snapshot endpoint
# ---------------------------------------------------------------------------

def test_snapshot_404_when_no_database_path(monkeypatch):
    """Memory-mode (no DATABASE_PATH) cannot snapshot — must return 404."""
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    c, h = _client_with_auth()
    r = c.get("/api/v1/admin/db-snapshot", headers=h)
    assert r.status_code == 404
    assert "memory" in r.json()["detail"].lower()


def test_snapshot_requires_auth():
    from orchestrator.api import app
    c = TestClient(app)
    r = c.get("/api/v1/admin/db-snapshot")
    assert r.status_code in (401, 403)


def test_snapshot_streams_sqlite_file(tmp_path, monkeypatch):
    """When DATABASE_PATH points to a real SQLite file, snapshot streams
    its bytes with the SQLite magic header."""
    import sqlite3
    db_file = tmp_path / "circle.db"
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute("CREATE TABLE x (a INTEGER)")
        conn.execute("INSERT INTO x VALUES (42)")
        conn.commit()
    monkeypatch.setenv("DATABASE_PATH", str(db_file))

    c, h = _client_with_auth()
    r = c.get("/api/v1/admin/db-snapshot", headers=h)
    assert r.status_code == 200
    # SQLite files start with this magic string
    assert r.content.startswith(b"SQLite format 3")
    # And the content-disposition tells the client to save it
    assert "attachment" in r.headers.get("content-disposition", "")
