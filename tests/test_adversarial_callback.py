"""
Tests for M11.1 — Selective adversarial callback (per ADR-028).

The contract:
  - Skipped if ADVERSARIAL_CALLBACK_ENABLED is unset/false
  - Skipped if confidence is outside the band [0.6, 0.8] (defaults)
  - Calls Grok first, Claude fallback
  - JSON parsing tolerates fences + preamble
  - Degrades verdict -> "iterate" when >= MIN_OBJECTIONS strong objections
  - Weak objections don't degrade
  - No LLM available → no degradation (fails open)
  - Never raises — caller treats failure as "verdict unchanged"
"""
import json
from unittest.mock import patch


# A canned response shape from the adversarial reviewer
_RESPONSE_TWO_STRONG = json.dumps({
    "objections": [
        {"severity": "strong",
         "text": "Unit economics inverted: CAC $80, LTV $35 with 60% month-1 churn."},
        {"severity": "strong",
         "text": "Market is dead: cited niche has -40% YoY usage based on recent data."},
        {"severity": "weak",
         "text": "Could use stronger competitive differentiation."},
    ]
})

_RESPONSE_ONE_STRONG = json.dumps({
    "objections": [
        {"severity": "strong",
         "text": "Regulatory blocker: this requires a banking license."},
        {"severity": "weak", "text": "Minor branding concern."},
    ]
})

_RESPONSE_ALL_WEAK = json.dumps({
    "objections": [
        {"severity": "weak", "text": "x"},
        {"severity": "weak", "text": "y"},
        {"severity": "weak", "text": "z"},
    ]
})

_RESPONSE_NO_OBJECTIONS = json.dumps({"objections": []})


# ---------------------------------------------------------------------------
# Activation gating
# ---------------------------------------------------------------------------

def test_skipped_when_disabled(monkeypatch):
    monkeypatch.delenv("ADVERSARIAL_CALLBACK_ENABLED", raising=False)
    from orchestrator.core.adversarial import run_adversarial_check
    r = run_adversarial_check("pass", 0.7, "rationale", "evidence")
    assert r.degraded is False
    assert r.final_verdict == "pass"
    assert r.error == "ADVERSARIAL_CALLBACK_ENABLED=false"


def test_skipped_when_confidence_above_band(monkeypatch):
    """Strong PASS (>0.8) doesn't need second-guessing."""
    monkeypatch.setenv("ADVERSARIAL_CALLBACK_ENABLED", "true")
    from orchestrator.core.adversarial import run_adversarial_check
    r = run_adversarial_check("pass", 0.95, "r", "e")
    assert r.degraded is False
    assert r.error and "outside band" in r.error


def test_skipped_when_confidence_below_band(monkeypatch):
    """Clear KILL (<0.6) doesn't need second-guessing either."""
    monkeypatch.setenv("ADVERSARIAL_CALLBACK_ENABLED", "true")
    from orchestrator.core.adversarial import run_adversarial_check
    r = run_adversarial_check("kill", 0.4, "r", "e")
    assert r.degraded is False
    assert r.error and "outside band" in r.error


def test_in_borderline_band():
    from orchestrator.core.adversarial import in_borderline_band
    assert in_borderline_band(0.6) is True
    assert in_borderline_band(0.7) is True
    assert in_borderline_band(0.8) is True
    assert in_borderline_band(0.59) is False
    assert in_borderline_band(0.81) is False


# ---------------------------------------------------------------------------
# Degradation logic
# ---------------------------------------------------------------------------

def test_two_strong_objections_degrade_to_iterate(monkeypatch):
    monkeypatch.setenv("ADVERSARIAL_CALLBACK_ENABLED", "true")
    with patch(
        "orchestrator.core.adversarial._call_grok",
        return_value=_RESPONSE_TWO_STRONG,
    ):
        from orchestrator.core.adversarial import run_adversarial_check
        r = run_adversarial_check("pass", 0.7, "x", "y")
    assert r.degraded is True
    assert r.final_verdict == "iterate"
    assert r.original_verdict == "pass"
    assert r.strong_objection_count == 2
    assert r.provider == "xai"


def test_one_strong_objection_does_not_degrade(monkeypatch):
    """MIN_OBJECTIONS defaults to 2 — one strong reason isn't enough.
    Tunable via env M111_MIN_OBJECTIONS."""
    monkeypatch.setenv("ADVERSARIAL_CALLBACK_ENABLED", "true")
    with patch(
        "orchestrator.core.adversarial._call_grok",
        return_value=_RESPONSE_ONE_STRONG,
    ):
        from orchestrator.core.adversarial import run_adversarial_check
        r = run_adversarial_check("pass", 0.7, "x", "y")
    assert r.degraded is False
    assert r.final_verdict == "pass"
    assert r.strong_objection_count == 1


def test_all_weak_objections_do_not_degrade(monkeypatch):
    """Weak objections never count — only strong are deal-breakers."""
    monkeypatch.setenv("ADVERSARIAL_CALLBACK_ENABLED", "true")
    with patch(
        "orchestrator.core.adversarial._call_grok",
        return_value=_RESPONSE_ALL_WEAK,
    ):
        from orchestrator.core.adversarial import run_adversarial_check
        r = run_adversarial_check("pass", 0.7, "x", "y")
    assert r.degraded is False
    assert r.strong_objection_count == 0


def test_no_objections_returns_clean_pass(monkeypatch):
    monkeypatch.setenv("ADVERSARIAL_CALLBACK_ENABLED", "true")
    with patch(
        "orchestrator.core.adversarial._call_grok",
        return_value=_RESPONSE_NO_OBJECTIONS,
    ):
        from orchestrator.core.adversarial import run_adversarial_check
        r = run_adversarial_check("pass", 0.7, "x", "y")
    assert r.degraded is False
    assert r.objections == []


# ---------------------------------------------------------------------------
# Tuning knob — M111_MIN_OBJECTIONS
# ---------------------------------------------------------------------------

def test_min_objections_env_override(monkeypatch):
    """Setting M111_MIN_OBJECTIONS=1 should degrade on a single strong reason."""
    monkeypatch.setenv("ADVERSARIAL_CALLBACK_ENABLED", "true")
    monkeypatch.setenv("M111_MIN_OBJECTIONS", "1")
    with patch(
        "orchestrator.core.adversarial._call_grok",
        return_value=_RESPONSE_ONE_STRONG,
    ):
        from orchestrator.core.adversarial import run_adversarial_check
        r = run_adversarial_check("pass", 0.7, "x", "y")
    assert r.degraded is True
    assert r.final_verdict == "iterate"


def test_band_env_override(monkeypatch):
    """Operator can widen the band via env."""
    monkeypatch.setenv("ADVERSARIAL_CALLBACK_ENABLED", "true")
    monkeypatch.setenv("M111_ADV_BAND_LOW", "0.5")
    monkeypatch.setenv("M111_ADV_BAND_HIGH", "0.9")
    with patch(
        "orchestrator.core.adversarial._call_grok",
        return_value=_RESPONSE_NO_OBJECTIONS,
    ):
        from orchestrator.core.adversarial import run_adversarial_check
        # 0.85 outside default band (>0.8) but inside the widened one
        r = run_adversarial_check("pass", 0.85, "x", "y")
    assert r.error is None  # check ran (no band-skip)


# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------

def test_falls_back_to_claude_when_grok_unavailable(monkeypatch):
    monkeypatch.setenv("ADVERSARIAL_CALLBACK_ENABLED", "true")
    with patch(
        "orchestrator.core.adversarial._call_grok", return_value=None,
    ), patch(
        "orchestrator.core.adversarial._call_claude",
        return_value=_RESPONSE_TWO_STRONG,
    ):
        from orchestrator.core.adversarial import run_adversarial_check
        r = run_adversarial_check("pass", 0.7, "x", "y")
    assert r.provider == "claude"
    assert r.degraded is True


def test_no_llm_fails_open(monkeypatch):
    """If NEITHER Grok nor Claude can be called, the original verdict
    stands — never degrade based on missing data."""
    monkeypatch.setenv("ADVERSARIAL_CALLBACK_ENABLED", "true")
    with patch(
        "orchestrator.core.adversarial._call_grok", return_value=None,
    ), patch(
        "orchestrator.core.adversarial._call_claude", return_value=None,
    ):
        from orchestrator.core.adversarial import run_adversarial_check
        r = run_adversarial_check("pass", 0.7, "x", "y")
    assert r.degraded is False
    assert r.final_verdict == "pass"
    assert "no LLM" in (r.error or "")


# ---------------------------------------------------------------------------
# JSON parsing edge cases
# ---------------------------------------------------------------------------

def test_parse_handles_markdown_fences(monkeypatch):
    monkeypatch.setenv("ADVERSARIAL_CALLBACK_ENABLED", "true")
    fenced = "```json\n" + _RESPONSE_TWO_STRONG + "\n```"
    with patch(
        "orchestrator.core.adversarial._call_grok", return_value=fenced,
    ):
        from orchestrator.core.adversarial import run_adversarial_check
        r = run_adversarial_check("pass", 0.7, "x", "y")
    assert r.degraded is True


def test_parse_drops_invalid_severity(monkeypatch):
    monkeypatch.setenv("ADVERSARIAL_CALLBACK_ENABLED", "true")
    raw = json.dumps({"objections": [
        {"severity": "deadly", "text": "x"},  # invalid sev
        {"severity": "strong", "text": ""},   # empty text
        {"severity": "strong", "text": "ok one"},
    ]})
    with patch(
        "orchestrator.core.adversarial._call_grok", return_value=raw,
    ):
        from orchestrator.core.adversarial import run_adversarial_check
        r = run_adversarial_check("pass", 0.7, "x", "y")
    # Only 1 valid strong objection → no degradation (defaults need 2)
    assert r.strong_objection_count == 1
    assert r.degraded is False


def test_parse_handles_garbage_response(monkeypatch):
    """Model returns prose, not JSON. We get 0 objections, no crash."""
    monkeypatch.setenv("ADVERSARIAL_CALLBACK_ENABLED", "true")
    with patch(
        "orchestrator.core.adversarial._call_grok",
        return_value="I think this verdict is fine, actually.",
    ):
        from orchestrator.core.adversarial import run_adversarial_check
        r = run_adversarial_check("pass", 0.7, "x", "y")
    assert r.objections == []
    assert r.degraded is False


# ---------------------------------------------------------------------------
# HTTP endpoint /api/v1/admin/adversarial-check
# ---------------------------------------------------------------------------

def test_adversarial_endpoint_validates_verdict():
    """Missing/invalid verdict must reject with 400 instead of silently
    returning an empty result. Defense against client typos."""
    import os
    from fastapi.testclient import TestClient
    os.environ["ALLOWED_EMAILS"] = "test@example.com"
    from orchestrator.api import app
    c = TestClient(app)
    t = c.post("/api/v1/auth/login", json={"email": "test@example.com"}).json()["token"]
    h = {"Authorization": f"Bearer {t}"}
    r = c.post(
        "/api/v1/admin/adversarial-check", headers=h,
        json={"verdict": "definitely", "confidence": 0.7},
    )
    assert r.status_code == 400


def test_adversarial_endpoint_returns_result(monkeypatch):
    """Endpoint returns the AdversarialResult shape with degraded flag."""
    monkeypatch.setenv("ADVERSARIAL_CALLBACK_ENABLED", "true")
    import os
    from fastapi.testclient import TestClient
    os.environ["ALLOWED_EMAILS"] = "test@example.com"
    from orchestrator.api import app
    with patch(
        "orchestrator.core.adversarial._call_grok",
        return_value=_RESPONSE_TWO_STRONG,
    ):
        c = TestClient(app)
        t = c.post("/api/v1/auth/login", json={"email": "test@example.com"}).json()["token"]
        h = {"Authorization": f"Bearer {t}"}
        r = c.post(
            "/api/v1/admin/adversarial-check", headers=h,
            json={
                "verdict": "pass",
                "confidence": 0.72,
                "rationale": "ensemble said pass",
                "evidence": "CTR=2.1%, conv=0.6%, cost $0.42",
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["original_verdict"] == "pass"
    assert body["final_verdict"] == "iterate"
    assert body["degraded"] is True
    assert body["strong_objection_count"] == 2
