"""
Tests for M9.1 — UserSettingsStore + /api/v1/settings endpoints.

Pin down:
  - Default settings (LATAM-friendly: es-EC / Guayaquil / 24h / USD)
  - Partial PATCH semantics (unknown fields ignored, unsent fields preserved)
  - List fields (preferred_regions, preferred_topics, excluded_topics) round-trip
  - JSON encoding of list fields in storage
  - Boolean field auto_discovery_enabled stored as 0/1
  - Validation: time_format pattern, max_new_sources_per_week range
  - Re-import safety: settings survive across SignalsStore.add() calls

Translation hook is tested in test_translator_hook.py.
"""
from fastapi.testclient import TestClient


def _auth_token(client: TestClient) -> str:
    """Login an allowlisted email and return the bearer token.

    Force-set ALLOWED_EMAILS rather than setdefault: other tests in the suite
    set it to different values, and setdefault is a no-op once the var exists.
    """
    import os
    os.environ["ALLOWED_EMAILS"] = (
        "test@example.com,cristian.molina.ia.soporte@gmail.com"
    )
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com"},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _client_with_auth() -> tuple[TestClient, dict]:
    """Build a fresh TestClient + auth header per test.

    We import `app` INSIDE the helper because some tests in the suite delete
    `orchestrator.*` from sys.modules (test_observability reloads base_agent,
    etc). A module-level import here would freeze a stale `app` reference and
    the endpoints would 404 mysteriously when run in the full suite. The
    same pattern is documented in tests/test_multi_llm_4way.py.
    """
    from orchestrator.api import app
    c = TestClient(app)
    t = _auth_token(c)
    return c, {"Authorization": f"Bearer {t}"}


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def test_settings_defaults_are_latam_friendly():
    from orchestrator.core.storage import user_settings_store
    user_settings_store.clear()
    s = user_settings_store.get()
    assert s["locale"] == "es-EC"
    assert s["timezone"] == "America/Guayaquil"
    assert s["date_format"] == "DD/MM/YYYY"
    assert s["time_format"] == "24h"
    assert s["currency"] == "USD"
    assert s["number_format"] == "es"
    assert s["auto_translate_to"] == "es"
    assert s["auto_discovery_enabled"] in (0, False)
    assert s["max_new_sources_per_week"] == 5
    assert s["preferred_regions"] == ["EC", "CO", "PE", "MX"]
    assert s["preferred_topics"] == []
    assert s["excluded_topics"] == []


# ---------------------------------------------------------------------------
# Partial update semantics
# ---------------------------------------------------------------------------

def test_update_only_changes_provided_fields():
    """PATCH-style: omitted fields stay at their current value."""
    from orchestrator.core.storage import user_settings_store
    user_settings_store.clear()

    before = user_settings_store.get()
    after = user_settings_store.update({"timezone": "America/Mexico_City"})
    assert after["timezone"] == "America/Mexico_City"
    # Other fields unchanged
    assert after["locale"] == before["locale"]
    assert after["currency"] == before["currency"]


def test_update_ignores_unknown_fields():
    """Defense against client typos — unknown keys must not raise."""
    from orchestrator.core.storage import user_settings_store
    user_settings_store.clear()

    after = user_settings_store.update({
        "bogus_field": "x",
        "another_typo": 42,
        "timezone": "UTC",
    })
    assert after["timezone"] == "UTC"
    assert "bogus_field" not in after


def test_update_list_fields_roundtrip():
    """Lists store as JSON internally but expose as native lists to callers."""
    from orchestrator.core.storage import user_settings_store
    user_settings_store.clear()

    after = user_settings_store.update({
        "preferred_topics": ["fintech", "agtech", "saas"],
        "excluded_topics": ["crypto", "nft"],
        "preferred_regions": ["EC", "CO"],
    })
    assert after["preferred_topics"] == ["fintech", "agtech", "saas"]
    assert after["excluded_topics"] == ["crypto", "nft"]
    assert after["preferred_regions"] == ["EC", "CO"]


def test_update_boolean_field():
    from orchestrator.core.storage import user_settings_store
    user_settings_store.clear()
    after = user_settings_store.update({"auto_discovery_enabled": True})
    # We accept truthy/falsy on input, but the get() output coerces to bool/int.
    assert bool(after["auto_discovery_enabled"]) is True
    after2 = user_settings_store.update({"auto_discovery_enabled": False})
    assert bool(after2["auto_discovery_enabled"]) is False


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------

def test_get_settings_endpoint_returns_defaults():
    from orchestrator.core.storage import user_settings_store
    user_settings_store.clear()

    c, h = _client_with_auth()
    r = c.get("/api/v1/settings", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["locale"] == "es-EC"
    assert body["preferred_regions"] == ["EC", "CO", "PE", "MX"]
    assert isinstance(body["auto_discovery_enabled"], bool)


def test_put_settings_endpoint_updates_partial():
    from orchestrator.core.storage import user_settings_store
    user_settings_store.clear()

    c, h = _client_with_auth()
    r = c.put(
        "/api/v1/settings",
        headers=h,
        json={
            "timezone": "America/Mexico_City",
            "currency": "MXN",
            "preferred_topics": ["foodtech"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["timezone"] == "America/Mexico_City"
    assert body["currency"] == "MXN"
    assert body["preferred_topics"] == ["foodtech"]
    # Unchanged
    assert body["locale"] == "es-EC"


def test_post_alias_works_like_put():
    """POST /api/v1/settings exists for browsers/proxies that block PUT
    (same fix pattern as autonomy POST alias in M4.5)."""
    from orchestrator.core.storage import user_settings_store
    user_settings_store.clear()
    c, h = _client_with_auth()
    r = c.post("/api/v1/settings", headers=h, json={"locale": "en-US"})
    assert r.status_code == 200, r.text
    assert r.json()["locale"] == "en-US"


def test_put_rejects_invalid_time_format():
    """Pydantic pattern validation: time_format must be 12h or 24h."""
    from orchestrator.core.storage import user_settings_store
    user_settings_store.clear()
    c, h = _client_with_auth()
    r = c.put("/api/v1/settings", headers=h, json={"time_format": "36h"})
    assert r.status_code in (422, 400), r.text


def test_put_rejects_negative_max_sources():
    """max_new_sources_per_week is bounded [0, 50]."""
    from orchestrator.core.storage import user_settings_store
    user_settings_store.clear()
    c, h = _client_with_auth()
    r = c.put(
        "/api/v1/settings", headers=h,
        json={"max_new_sources_per_week": -1},
    )
    assert r.status_code in (422, 400)


def test_get_settings_requires_auth():
    from orchestrator.api import app
    c = TestClient(app)
    r = c.get("/api/v1/settings")
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Persistence across signal saves (regression guard for the translation hook)
# ---------------------------------------------------------------------------

def test_settings_survive_signals_add():
    """Adding signals must not reset settings — proves the auto_translate_to
    lookup inside SignalsStore.add doesn't accidentally wipe the row."""
    from orchestrator.core.storage import user_settings_store, signals_store
    user_settings_store.clear()
    user_settings_store.update({"timezone": "Europe/Madrid"})
    signals_store.clear()
    signals_store.add(
        source_id=1, source_kind="rss", theme="x", score=0.5, excerpt="y",
        evidence_urls=["https://a.com"], suggested_topic="t",
    )
    after = user_settings_store.get()
    assert after["timezone"] == "Europe/Madrid"
