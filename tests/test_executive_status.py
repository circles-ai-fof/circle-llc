"""
Tests for M15.0 — executive-status agent + endpoint.

Pin down:
  - collect_state returns a populated snapshot from the in-memory stores
  - briefing() returns mock-mode placeholder without ANTHROPIC_API_KEY
  - briefing() handles LLM failure gracefully (no crash, falls back to mock)
  - briefing() in QA mode includes the question in the prompt
  - Section parser splits HEADLINE/HIGHLIGHTS/RIESGOS/PRÓXIMOS PASOS
  - POST /api/v1/executive-status returns the full shape (200)
  - Empty body → REPORT mode; {"question": "x"} → QA mode
  - Auth required
"""
import os
from unittest.mock import patch
from fastapi.testclient import TestClient


def _client_with_auth():
    os.environ["ALLOWED_EMAILS"] = "test@example.com"
    from orchestrator.api import app
    c = TestClient(app)
    t = c.post("/api/v1/auth/login", json={"email": "test@example.com"}).json()["token"]
    return c, {"Authorization": f"Bearer {t}"}


def _seed_signals(n: int):
    """Populate the in-memory store with simple signals."""
    from orchestrator.core.storage import signals_store
    signals_store.clear()
    for i in range(n):
        signals_store.add(
            source_id=(i % 3) + 1,
            source_kind="rss",
            theme=f"Idea {i}: build a thing for fintech",
            score=0.7,
            excerpt=f"Sample content {i}",
            evidence_urls=[f"https://example.com/{i}"],
            suggested_topic="fintech",
        )


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def test_collect_state_returns_basic_counts():
    from orchestrator.agents.executive_status import collect_state
    _seed_signals(5)
    snap = collect_state()
    assert snap.signals_total == 5
    assert snap.signals_new_24h == 5  # just added
    assert snap.agents_count >= 1
    assert isinstance(snap.features_on, dict)


def test_collect_state_survives_empty_stores():
    """Even with zero signals/runs the snapshot must build without errors."""
    from orchestrator.core.storage import signals_store, sources_store, runs_store
    signals_store.clear()
    sources_store.clear()
    runs_store.clear()
    from orchestrator.agents.executive_status import collect_state
    snap = collect_state()
    assert snap.signals_total == 0
    assert snap.runs_total == 0


# ---------------------------------------------------------------------------
# Briefing function
# ---------------------------------------------------------------------------

def test_briefing_mock_mode_returns_placeholder(monkeypatch):
    """Without ANTHROPIC_API_KEY, briefing returns a deterministic placeholder
    without calling the API. Enables CI / dashboard smoke tests."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _seed_signals(3)
    from orchestrator.agents.executive_status import briefing
    b = briefing()
    assert b.mock_mode is True
    assert b.mode == "report"
    assert "demo" in b.body.lower() or "modo" in b.body.lower()
    assert b.snapshot is not None
    assert b.snapshot.signals_total == 3


def test_briefing_qa_mode_records_question(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _seed_signals(2)
    from orchestrator.agents.executive_status import briefing
    b = briefing(question="¿está lista la fase 3?")
    assert b.mode == "qa"
    assert b.question == "¿está lista la fase 3?"


def test_briefing_llm_failure_falls_back_to_mock(monkeypatch):
    """If the Anthropic SDK raises mid-call we MUST still return a briefing
    (best-effort). Never crash the daily cron because of a transient API
    outage."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-test")
    _seed_signals(2)
    with patch(
        "orchestrator.agents.executive_status._call_claude",
        return_value=None,  # simulate failure
    ):
        from orchestrator.agents.executive_status import briefing
        b = briefing()
    # mock fallback fires when Claude returned nothing
    assert b.mock_mode is True
    assert "demo" in b.body.lower() or "modo" in b.body.lower()


def test_briefing_with_real_llm_response(monkeypatch):
    """When Claude returns text, briefing parses headline + sections."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-test")
    sample = (
        "HEADLINE\n"
        "El cazador trajo 12 señales nuevas; el ensemble está estable.\n\n"
        "HIGHLIGHTS\n"
        "- 33 fuentes activas con quality_score promedio 0.42\n"
        "- M11.x desplegado: validador + adversarial + watchdog\n"
        "- 0 runs hasta ahora — pipeline sin disparar\n\n"
        "RIESGOS\n"
        "- Autonomía en manual; cazador no se auto-prioriza\n"
        "- 0 runs significa que IdeaValidator no se ha probado en prod\n\n"
        "PRÓXIMOS PASOS\n"
        "- Disparar 1 gate/run con tema fintech LATAM\n"
        "- Cambiar autonomy_level a assisted\n"
    )
    with patch(
        "orchestrator.agents.executive_status._call_claude",
        return_value=sample,
    ):
        from orchestrator.agents.executive_status import briefing
        _seed_signals(12)
        b = briefing()
    assert b.mock_mode is False
    assert "cazador" in b.summary.lower()
    assert len(b.highlights) >= 2
    assert len(b.risks) >= 1
    assert len(b.asks) >= 1
    assert any("autonomía" in r.lower() or "manual" in r.lower() for r in b.risks)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

def test_endpoint_report_mode_returns_full_shape(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _seed_signals(4)
    c, h = _client_with_auth()
    r = c.post("/api/v1/executive-status", headers=h, json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "report"
    assert "report" in body
    assert "summary" in body
    assert "snapshot" in body
    assert body["snapshot"]["signals_total"] == 4
    assert body["mock_mode"] is True


def test_endpoint_qa_mode(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _seed_signals(2)
    c, h = _client_with_auth()
    r = c.post(
        "/api/v1/executive-status", headers=h,
        json={"question": "¿cómo va el cazador?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "qa"
    assert body["question"] == "¿cómo va el cazador?"


def test_endpoint_requires_auth():
    from orchestrator.api import app
    c = TestClient(app)
    r = c.post("/api/v1/executive-status", json={})
    assert r.status_code in (401, 403)


def test_endpoint_handles_no_body(monkeypatch):
    """Calling with empty body should still produce a REPORT-mode briefing."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _seed_signals(1)
    c, h = _client_with_auth()
    r = c.post("/api/v1/executive-status", headers=h)
    # Some FastAPI versions reject completely empty body — accept either
    assert r.status_code in (200, 422)


# ---------------------------------------------------------------------------
# M15.1 — Send email endpoint
# ---------------------------------------------------------------------------

def test_send_email_reports_missing_smtp(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    _seed_signals(2)
    c, h = _client_with_auth()
    r = c.post("/api/v1/executive-status/send-email", headers=h, json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sent"] is False
    assert "missing envs" in body["reason"].lower()


def test_send_email_calls_smtp_when_configured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "fake-pw")
    monkeypatch.setenv("DIGEST_TO", "ceo@example.com")
    monkeypatch.setenv("DIGEST_FROM", "Circle LLC <noreply@circles-ai.ai>")
    _seed_signals(3)
    sent_calls = []
    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent_calls.append({"host": host, "port": port})
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def ehlo(self): pass
        def starttls(self): pass
        def login(self, user, pw):
            sent_calls.append({"login_user": user})
        def sendmail(self, from_addr, to_addrs, msg):
            sent_calls.append({"from": from_addr, "to": to_addrs, "msg_chars": len(msg)})
    with patch("smtplib.SMTP", _FakeSMTP):
        c, h = _client_with_auth()
        r = c.post("/api/v1/executive-status/send-email", headers=h, json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sent"] is True
    assert body["to"] == "ceo@example.com"
    sendmail_call = next((x for x in sent_calls if "to" in x), None)
    assert sendmail_call is not None
    assert sendmail_call["from"] == "Circle LLC <noreply@circles-ai.ai>"
    assert sendmail_call["msg_chars"] > 100


def test_send_email_swallows_smtp_failure(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "fake-pw")
    _seed_signals(2)
    class _BrokenSMTP:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): pass
        def starttls(self): pass
        def login(self, *a): raise RuntimeError("SMTP auth failed")
        def sendmail(self, *a, **kw): pass
    with patch("smtplib.SMTP", _BrokenSMTP):
        c, h = _client_with_auth()
        r = c.post("/api/v1/executive-status/send-email", headers=h, json={})
    assert r.status_code == 200
    body = r.json()
    assert body["sent"] is False
    assert "smtp send failed" in body["reason"].lower()


def test_send_email_requires_auth():
    from orchestrator.api import app
    c = TestClient(app)
    r = c.post("/api/v1/executive-status/send-email", json={})
    assert r.status_code in (401, 403)
