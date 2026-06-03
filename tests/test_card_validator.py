"""
Tests for M11.0 — CardValidator (Claude vision).

The agent's contract:
  - Returns CardValidation(kind, confidence, rationale, image_url)
  - kind ∈ {real_app, mockup, unknown}
  - score_multiplier maps kind → 1.0 (real) / 0.3 (mockup) / 0.85 (unknown)
  - Mock mode (no ANTHROPIC_API_KEY) returns deterministic placeholder
  - API failures swallowed → "unknown" never raises
  - Batch cap honored

Live Anthropic calls are stubbed via patch so tests are deterministic.
"""
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Parse layer — pure function tests
# ---------------------------------------------------------------------------

def test_parse_verdict_extracts_three_fields():
    from orchestrator.agents.card_validator import _parse_verdict
    raw = (
        "KIND: mockup\n"
        "CONFIDENCE: 0.82\n"
        "RATIONALE: Lorem ipsum filler in every panel; uniform Figma shadows."
    )
    v = _parse_verdict(raw, "https://img.x/a.png")
    assert v.kind == "mockup"
    assert abs(v.confidence - 0.82) < 0.001
    assert "Lorem ipsum" in v.rationale
    assert v.image_url == "https://img.x/a.png"


def test_parse_verdict_handles_real_app():
    from orchestrator.agents.card_validator import _parse_verdict
    raw = (
        "KIND: real_app\n"
        "CONFIDENCE: 0.91\n"
        "RATIONALE: Real names, real transaction IDs, error states visible."
    )
    v = _parse_verdict(raw, "u")
    assert v.kind == "real_app"
    assert v.confidence > 0.9


def test_parse_verdict_handles_unknown_when_ambiguous():
    from orchestrator.agents.card_validator import _parse_verdict
    raw = (
        "KIND: unknown\n"
        "CONFIDENCE: 0.5\n"
        "RATIONALE: Just a logo; no UI shown."
    )
    v = _parse_verdict(raw, "u")
    assert v.kind == "unknown"


def test_parse_verdict_defaults_to_unknown_when_empty():
    from orchestrator.agents.card_validator import _parse_verdict
    v = _parse_verdict("", "u")
    assert v.kind == "unknown"
    assert v.confidence == 0.5


def test_parse_verdict_clamps_confidence_to_range():
    from orchestrator.agents.card_validator import _parse_verdict
    raw = "KIND: mockup\nCONFIDENCE: 2.5\nRATIONALE: x"
    v = _parse_verdict(raw, "u")
    assert v.confidence == 1.0
    raw2 = "KIND: mockup\nCONFIDENCE: -0.3\nRATIONALE: x"
    v2 = _parse_verdict(raw2, "u")
    assert v2.confidence == 0.0


def test_parse_verdict_tolerates_garbage_confidence():
    """If the model writes 'CONFIDENCE: high' we keep the default and don't crash."""
    from orchestrator.agents.card_validator import _parse_verdict
    raw = "KIND: real_app\nCONFIDENCE: high\nRATIONALE: clearly real."
    v = _parse_verdict(raw, "u")
    assert v.kind == "real_app"
    assert v.confidence == 0.5  # default preserved


# ---------------------------------------------------------------------------
# score_multiplier mapping
# ---------------------------------------------------------------------------

def test_score_multiplier_for_mockup_is_severe():
    from orchestrator.agents.card_validator import CardValidation, SCORE_MULTIPLIER_MOCKUP
    v = CardValidation(kind="mockup", confidence=0.9, rationale="x")
    assert v.score_multiplier == SCORE_MULTIPLIER_MOCKUP
    assert v.score_multiplier < 0.5


def test_score_multiplier_for_real_app_is_neutral():
    from orchestrator.agents.card_validator import CardValidation
    v = CardValidation(kind="real_app", confidence=0.9, rationale="x")
    assert v.score_multiplier == 1.0


def test_score_multiplier_for_unknown_is_mild_penalty():
    from orchestrator.agents.card_validator import CardValidation
    v = CardValidation(kind="unknown", confidence=0.5, rationale="x")
    # 0.85 — slightly penalize but don't kill
    assert 0.5 < v.score_multiplier < 1.0


# ---------------------------------------------------------------------------
# Mock mode (no API key) — must be safe + deterministic
# ---------------------------------------------------------------------------

def test_validate_card_mock_mode(monkeypatch):
    """Without ANTHROPIC_API_KEY, the validator must NOT crash and must
    return a sane placeholder so tests can keep running."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from orchestrator.agents.card_validator import validate_card
    v = validate_card("https://img.example.com/card.png")
    assert v.kind == "unknown"
    assert v.confidence == 0.5
    assert "[mock_mode]" in v.rationale


def test_validate_card_empty_url_returns_unknown(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from orchestrator.agents.card_validator import validate_card
    v = validate_card("")
    assert v.kind == "unknown"


# ---------------------------------------------------------------------------
# API failure swallowed (real key set, but client raises)
# ---------------------------------------------------------------------------

def test_validate_card_api_failure_returns_unknown(monkeypatch):
    """If the Anthropic SDK raises (network down, rate-limited, etc.) the
    validator must return 'unknown' instead of propagating — the cazador
    scan loop never breaks because of a bad image."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-test-key")
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.create.side_effect = RuntimeError(
            "vision API down"
        )
        from orchestrator.agents.card_validator import validate_card
        v = validate_card("https://x.com/img.png")
    assert v.kind == "unknown"
    assert "vision error" in v.rationale.lower()


def test_validate_card_calls_anthropic_with_image_url(monkeypatch):
    """Verify we hand the image URL to Claude vision (not download + base64)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-test-key")

    class _Resp:
        class _C:
            text = "KIND: real_app\nCONFIDENCE: 0.88\nRATIONALE: real ui."
        content = [_C()]

    captured: dict = {}

    def _fake_create(**kw):
        captured.update(kw)
        return _Resp()

    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.create.side_effect = _fake_create
        from orchestrator.agents.card_validator import validate_card
        v = validate_card("https://img.example.com/a.png")
    assert v.kind == "real_app"
    # The user message must include the image URL as source.url
    msgs = captured["messages"]
    user_content = msgs[0]["content"]
    image_block = next((b for b in user_content if b["type"] == "image"), None)
    assert image_block is not None
    assert image_block["source"]["url"] == "https://img.example.com/a.png"


# ---------------------------------------------------------------------------
# Batch + budget cap
# ---------------------------------------------------------------------------

def test_validate_cards_batch_honors_cap(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from orchestrator.agents.card_validator import validate_cards_batch
    urls = [f"https://x.com/{i}.png" for i in range(10)]
    out = validate_cards_batch(urls, max_validations=3)
    assert len(out) == 10
    # First 3 went through validate_card (mock returns unknown)
    # Last 7 hit the cap and got the 'batch cap reached' rationale
    capped = [v for v in out if "cap reached" in v.rationale]
    assert len(capped) == 7


def test_validate_cards_batch_empty_input():
    from orchestrator.agents.card_validator import validate_cards_batch
    assert validate_cards_batch([]) == []
    assert validate_cards_batch(None) == []


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------

def test_validate_card_endpoint_e2e():
    import os
    from fastapi.testclient import TestClient
    os.environ["ALLOWED_EMAILS"] = "test@example.com"
    from orchestrator.api import app
    from orchestrator.core.storage import signals_store
    signals_store.clear()
    sid = signals_store.add(
        source_id=1, source_kind="app_marketplace",
        theme="Vibe Coding Studio",
        score=0.7,
        excerpt="Build full-stack apps with prompts.",
        evidence_urls=["https://cdn.example.com/cards/vibe-studio.png"],
        suggested_topic="ai-builder",
    )
    c = TestClient(app)
    t = c.post("/api/v1/auth/login", json={"email": "test@example.com"}).json()["token"]
    h = {"Authorization": f"Bearer {t}"}
    r = c.post(f"/api/v1/signals/{sid}/validate-card", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["signal_id"] == sid
    assert body["kind"] in {"real_app", "mockup", "unknown"}
    assert 0.0 <= body["confidence"] <= 1.0
    assert body["score_multiplier"] in {0.3, 1.0, 0.85}


def test_validate_card_endpoint_404_for_missing_signal():
    import os
    from fastapi.testclient import TestClient
    os.environ["ALLOWED_EMAILS"] = "test@example.com"
    from orchestrator.api import app
    c = TestClient(app)
    t = c.post("/api/v1/auth/login", json={"email": "test@example.com"}).json()["token"]
    h = {"Authorization": f"Bearer {t}"}
    r = c.post("/api/v1/signals/999999/validate-card", headers=h)
    assert r.status_code == 404
