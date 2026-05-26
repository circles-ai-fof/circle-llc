"""Tests for the SQLite-backed storage layer (M2)."""
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def sqlite_db(monkeypatch):
    """Create a temp SQLite DB and rewire storage module to use it."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_PATH", path)
    # Reset module state so it picks up the env
    import orchestrator.core.storage as s
    s._initialised = False
    s._db_path = None
    s._memory_leads.clear()
    s._memory_runs.clear()
    yield path
    # Cleanup
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass
    # Restore in-memory mode
    s._initialised = False
    s._db_path = None


def test_leads_persist_to_sqlite(sqlite_db):
    from orchestrator.core.storage import LeadsStore
    store = LeadsStore()
    store.add("techpulse-latam", "a@x.com", "Alice", "1.1.1.1", "Mozilla/5.0")
    store.add("techpulse-latam", "b@x.com", "Bob", "2.2.2.2", None)
    store.add("opscore-ai", "c@x.com", None, "3.3.3.3", None)

    techpulse = store.list_by_slug("techpulse-latam")
    assert len(techpulse) == 2
    assert {l["email"] for l in techpulse} == {"a@x.com", "b@x.com"}

    opscore = store.list_by_slug("opscore-ai")
    assert len(opscore) == 1
    assert opscore[0]["email"] == "c@x.com"

    assert store.count() == 3


def test_leads_survive_new_instance(sqlite_db):
    """A new LeadsStore() in the same process must see persisted leads."""
    from orchestrator.core.storage import LeadsStore
    s1 = LeadsStore()
    s1.add("t1", "founder@x.com", "F", "1.1.1.1")
    # New instance, same DB
    s2 = LeadsStore()
    assert len(s2.list_by_slug("t1")) == 1
    assert s2.count() == 1


def test_runs_persist_to_sqlite(sqlite_db):
    from orchestrator.core.storage import RunsStore
    from orchestrator.schemas.api import RunGateResponse

    store = RunsStore()
    payload = RunGateResponse(
        run_id="11111111-2222-3333-4444-555555555555",
        status="completed",
        idea_title="Test",
        verdict="iterate",
        confidence=0.6,
        rationale="why",
        next_steps=["a"],
        landing_headline="H",
        landing_slug="t",
        test_design={},
        canonical_goal_statement="G",
        steps_used=6,
        cost_usd_estimated=0.06,
        needs_human_review=True,
        review_reason="ensemble disagreement",
        ensemble_votes=["claude: pass", "openai: iterate", "google: iterate"],
        human_override=None,
    )
    store[payload.run_id] = payload

    # Retrieve as RunGateResponse (attribute access works)
    fetched = store.get(payload.run_id)
    assert fetched is not None
    assert fetched.verdict == "iterate"
    assert fetched.needs_human_review is True
    assert len(fetched.ensemble_votes) == 3


def test_runs_values_lists_all(sqlite_db):
    from orchestrator.core.storage import RunsStore
    from orchestrator.schemas.api import RunGateResponse

    store = RunsStore()
    for i in range(3):
        store[f"00000000-0000-0000-0000-00000000000{i}"] = RunGateResponse(
            run_id=f"00000000-0000-0000-0000-00000000000{i}",
            status="completed",
            idea_title=f"Idea {i}",
            verdict="pass",
            confidence=0.8,
            rationale="r",
            next_steps=["x"],
            landing_headline="H",
            landing_slug=f"slug-{i}",
            test_design={},
            canonical_goal_statement="G",
            steps_used=6,
            cost_usd_estimated=0.06,
        )
    values = store.values()
    assert len(values) == 3
    titles = {v.idea_title for v in values}
    assert titles == {"Idea 0", "Idea 1", "Idea 2"}


def test_memory_mode_when_no_db_path():
    """Without DATABASE_PATH, store stays in-memory and tests still work."""
    import orchestrator.core.storage as s
    # Force in-memory mode
    s._initialised = False
    s._db_path = None
    s._memory_leads.clear()
    s._memory_runs.clear()
    os.environ.pop("DATABASE_PATH", None)

    from orchestrator.core.storage import LeadsStore
    store = LeadsStore()
    store.add("memory-test", "x@y.com", "X", "1.1.1.1")
    assert len(store.list_by_slug("memory-test")) == 1
