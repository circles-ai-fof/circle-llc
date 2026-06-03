"""
Tests for M11.3 — IdeaValidator red-team pre-test gate.

Contract:
  - Mock mode (no API key) returns deterministic MATAR placeholder
  - Empty input returns MATAR with error
  - LLM error returns MATAR with error (fail closed)
  - JSON block at end of response is parsed
  - Invalid verdict defaults to MATAR (fail closed)
  - Long prose + structured JSON both surface in ValidatorResult
  - web_search tool only attached when IDEA_VALIDATOR_RESEARCH=true
  - HTTP endpoint requires topic, returns full result
"""
import json
from unittest.mock import patch


_GOOD_RESPONSE = (
    "Análisis prose aquí...\n\n"
    "Vector DEMANDA: Existe pero tibio — usuarios usan Excel hoy y no se quejan.\n"
    "Vector WTP: Nadie paga >$10/mes por algo así actualmente.\n\n"
    "```json\n"
    + json.dumps({
        "verdict": "AVANZAR_CON_EVIDENCIA",
        "lethal_assumption": {
            "statement": "PYMEs Ecuador pagan SaaS recurrente $30+/mes",
            "why_lethal": "Si falla, no hay LTV viable",
        },
        "experiment": {
            "description": "Landing + ads Meta a 5 segmentos PYMEs Ecuador, 1 semana",
            "budget_usd": 50.0,
            "duration_days": 7,
            "success_criterion": "CTR >= 1.5% AND conv >= 0.5%",
        },
        "precondition": "Validar precio en landing test, no offer free trial",
        "attack_vectors": [
            {"name": "DEMANDA", "finding": "Tibia", "is_blocker": False},
            {"name": "WTP", "finding": "Probable bajo", "is_blocker": True},
        ],
        "pre_mortem_60d": [
            "Anuncios con CTR <0.5% por mensaje genérico",
            "Conversiones a leads pero ninguno paga",
        ],
        "real_buyer": "Contador externo de PYME 10-30 empleados, gerentes 35-50 años",
        "economic_impact": "Si 1% del 200K PYMEs Ecuador convierte: $720K ARR",
        "sources": ["https://example.com/source1", "https://example.com/source2"],
    })
    + "\n```"
)


_MATAR_RESPONSE = (
    "Análisis brutal...\n\n"
    + json.dumps({
        "verdict": "MATAR",
        "lethal_assumption": {
            "statement": "Hay >100 competidores gratis con la misma feature",
            "why_lethal": "No defensible, no diferenciador",
        },
        "experiment": {
            "description": "buscar competidores",
            "budget_usd": 0,
            "duration_days": 1,
            "success_criterion": "encontrar 5 gratis",
        },
        "attack_vectors": [],
        "pre_mortem_60d": ["Competencia gratis lo aplasta"],
        "real_buyer": "Nadie",
        "economic_impact": "0 — mercado saturado",
        "sources": [],
    })
)


# ---------------------------------------------------------------------------
# Mock mode
# ---------------------------------------------------------------------------

def test_validate_idea_mock_mode_returns_safe_default(monkeypatch):
    """No API key → returns MATAR placeholder, never crashes."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from orchestrator.agents.idea_validator import validate_idea
    r = validate_idea(topic="fintech for SMBs Ecuador")
    assert r.verdict == "MATAR"
    assert "mock_mode" in r.lethal_assumption.statement.lower()
    assert r.provider == "mock"


def test_validate_idea_empty_input_fails_closed(monkeypatch):
    """No topic + no value_prop → MATAR with explicit error."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from orchestrator.agents.idea_validator import validate_idea
    r = validate_idea(topic="", value_prop="")
    assert r.verdict == "MATAR"
    assert r.error == "empty input"


# ---------------------------------------------------------------------------
# JSON parsing of LLM response
# ---------------------------------------------------------------------------

def test_validate_idea_parses_avanzar_verdict(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    with patch(
        "orchestrator.agents.idea_validator._call_claude",
        return_value=_GOOD_RESPONSE,
    ):
        from orchestrator.agents.idea_validator import validate_idea
        r = validate_idea(topic="fintech PYMEs Ecuador",
                          value_prop="Open Banking reconciliation")
    assert r.verdict == "AVANZAR_CON_EVIDENCIA"
    assert "PYMEs Ecuador pagan SaaS" in r.lethal_assumption.statement
    assert r.experiment.budget_usd == 50.0
    assert r.experiment.duration_days == 7
    assert len(r.attack_vectors) == 2
    assert r.attack_vectors[1].is_blocker is True
    assert len(r.pre_mortem_60d) == 2
    assert "Contador externo" in r.real_buyer
    assert "200K PYMEs" in r.economic_impact
    assert len(r.sources) == 2
    assert r.provider == "claude"


def test_validate_idea_parses_matar_verdict(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    with patch(
        "orchestrator.agents.idea_validator._call_claude",
        return_value=_MATAR_RESPONSE,
    ):
        from orchestrator.agents.idea_validator import validate_idea
        r = validate_idea(topic="another todo app")
    assert r.verdict == "MATAR"
    assert ">100 competidores" in r.lethal_assumption.statement


def test_validate_idea_invalid_verdict_defaults_to_matar(monkeypatch):
    """If the LLM hallucinates 'SLAY' as verdict, we fail closed to MATAR."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    bad = json.dumps({"verdict": "SLAY", "lethal_assumption": {"statement": "x"}})
    with patch(
        "orchestrator.agents.idea_validator._call_claude",
        return_value="prose...\n" + bad,
    ):
        from orchestrator.agents.idea_validator import validate_idea
        r = validate_idea(topic="t")
    assert r.verdict == "MATAR"


def test_validate_idea_missing_json_fails_closed(monkeypatch):
    """No JSON block at end of response → can't trust the verdict, return MATAR."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    with patch(
        "orchestrator.agents.idea_validator._call_claude",
        return_value="I think this idea is fine actually, no objections.",
    ):
        from orchestrator.agents.idea_validator import validate_idea
        r = validate_idea(topic="t")
    assert r.verdict == "MATAR"
    assert r.error == "json parse failed"


def test_validate_idea_llm_returns_none_fails_closed(monkeypatch):
    """If _call_claude returns None (API down), default to MATAR with error."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    with patch(
        "orchestrator.agents.idea_validator._call_claude",
        return_value=None,
    ):
        from orchestrator.agents.idea_validator import validate_idea
        r = validate_idea(topic="t")
    assert r.verdict == "MATAR"
    assert r.error == "LLM unavailable"


# ---------------------------------------------------------------------------
# Activation gating + web_search wiring
# ---------------------------------------------------------------------------

def test_validator_enabled_default_off(monkeypatch):
    """IDEA_VALIDATOR_ENABLED defaults to OFF — opt-in only."""
    monkeypatch.delenv("IDEA_VALIDATOR_ENABLED", raising=False)
    from orchestrator.agents.idea_validator import validator_enabled
    assert validator_enabled() is False


def test_validator_enabled_via_env(monkeypatch):
    monkeypatch.setenv("IDEA_VALIDATOR_ENABLED", "true")
    from orchestrator.agents.idea_validator import validator_enabled
    assert validator_enabled() is True


def test_research_disabled_by_default_no_web_search_tool(monkeypatch):
    """Without IDEA_VALIDATOR_RESEARCH=true, the LLM call must NOT include
    the web_search tool. Costs +3x with research, defaults to cheap."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.delenv("IDEA_VALIDATOR_RESEARCH", raising=False)

    captured: dict = {}

    class _R:
        class _C:
            text = _GOOD_RESPONSE
        content = [_C()]

    def _fake_create(**kw):
        captured.update(kw)
        return _R()

    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.create.side_effect = _fake_create
        from orchestrator.agents.idea_validator import _call_claude
        _call_claude("t", "v", "i", "e")

    assert "tools" not in captured


def test_research_enabled_attaches_web_search_tool(monkeypatch):
    """With IDEA_VALIDATOR_RESEARCH=true, web_search must be in tools list."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setenv("IDEA_VALIDATOR_RESEARCH", "true")

    captured: dict = {}

    class _R:
        class _C:
            text = _GOOD_RESPONSE
        content = [_C()]

    def _fake_create(**kw):
        captured.update(kw)
        return _R()

    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.create.side_effect = _fake_create
        from orchestrator.agents.idea_validator import _call_claude
        _call_claude("t", "v", "i", "e")

    assert "tools" in captured
    tools = captured["tools"]
    assert any(t.get("name") == "web_search" for t in tools)


# ---------------------------------------------------------------------------
# JSON extraction edge cases
# ---------------------------------------------------------------------------

def test_extract_json_block_picks_last_valid_object(monkeypatch):
    """If the LLM writes multiple JSON-ish objects, the one with a valid
    verdict wins. Spec mandates the structured verdict at the END."""
    from orchestrator.agents.idea_validator import _extract_json_block
    raw = (
        "First a small json: {\"random\": 1}\n"
        "Then prose...\n"
        + json.dumps({
            "verdict": "PIVOTAR",
            "lethal_assumption": {"statement": "x", "why_lethal": "y"},
            "experiment": {"description": "z"},
        })
    )
    data = _extract_json_block(raw)
    assert data is not None
    assert data["verdict"] == "PIVOTAR"


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------

def test_validate_endpoint_requires_topic():
    import os
    from fastapi.testclient import TestClient
    os.environ["ALLOWED_EMAILS"] = "test@example.com"
    from orchestrator.api import app
    c = TestClient(app)
    t = c.post("/api/v1/auth/login", json={"email": "test@example.com"}).json()["token"]
    h = {"Authorization": f"Bearer {t}"}
    r = c.post("/api/v1/ideas/validate", headers=h, json={})
    assert r.status_code == 400


def test_validate_endpoint_returns_full_result(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    import os
    from fastapi.testclient import TestClient
    os.environ["ALLOWED_EMAILS"] = "test@example.com"
    from orchestrator.api import app
    with patch(
        "orchestrator.agents.idea_validator._call_claude",
        return_value=_GOOD_RESPONSE,
    ):
        c = TestClient(app)
        t = c.post("/api/v1/auth/login", json={"email": "test@example.com"}).json()["token"]
        h = {"Authorization": f"Bearer {t}"}
        r = c.post(
            "/api/v1/ideas/validate", headers=h,
            json={
                "topic": "fintech PYMEs Ecuador",
                "value_prop": "Open Banking reconciliation",
                "icp": "PYMEs 5-50 empleados",
                "evidence": "Mercado de ~200K PYMEs en Ecuador",
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == "AVANZAR_CON_EVIDENCIA"
    assert body["experiment"]["budget_usd"] == 50.0
    assert "PYMEs Ecuador pagan" in body["lethal_assumption"]["statement"]
    assert len(body["attack_vectors"]) == 2
    assert len(body["sources"]) == 2
