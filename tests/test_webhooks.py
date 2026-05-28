"""
Tests for outbound webhooks (orchestrator/core/webhooks.py).

Webhooks are fire-and-forget — we test that:
  - Events fire only when configured AND in the enabled-events set
  - URL formatting works for both Slack and generic endpoints
  - High-trend gate respects WEBHOOK_MIN_TREND
  - Errors never propagate (network failures must NOT break the caller)
"""
from __future__ import annotations

import importlib
from unittest.mock import patch


def _fresh_module():
    """Re-import the module so it picks up the current env vars."""
    import sys
    if "orchestrator.core.webhooks" in sys.modules:
        return importlib.reload(sys.modules["orchestrator.core.webhooks"])
    return importlib.import_module("orchestrator.core.webhooks")


def test_no_webhook_urls_means_no_post(monkeypatch):
    """Without any URL configured, emit() must be a no-op (no network call)."""
    monkeypatch.delenv("WEBHOOK_URL_SLACK", raising=False)
    monkeypatch.delenv("WEBHOOK_URL_GENERIC", raising=False)
    wh = _fresh_module()

    with patch.object(wh, "_post_json") as posted:
        wh.emit("signal.high_trend", {"theme": "X", "trend_score": 10})
    posted.assert_not_called()


def test_slack_url_triggers_slack_payload(monkeypatch):
    monkeypatch.setenv("WEBHOOK_URL_SLACK", "https://hooks.slack.com/test")
    monkeypatch.delenv("WEBHOOK_URL_GENERIC", raising=False)
    monkeypatch.setenv("WEBHOOK_MIN_TREND", "0")  # allow any
    wh = _fresh_module()

    with patch.object(wh, "_post_json") as posted:
        wh.emit("signal.high_trend", {
            "theme": "Telemedicina rural",
            "source_name": "Startupeable",
            "trend_score": 5,
        })

    assert posted.call_count == 1
    url, payload = posted.call_args.args
    assert url == "https://hooks.slack.com/test"
    assert "text" in payload
    assert "Telemedicina rural" in payload["text"]
    assert "+5" in payload["text"]
    assert "Startupeable" in payload["text"]


def test_generic_url_gets_raw_event_body(monkeypatch):
    monkeypatch.delenv("WEBHOOK_URL_SLACK", raising=False)
    monkeypatch.setenv("WEBHOOK_URL_GENERIC", "https://example.com/hook")
    wh = _fresh_module()

    with patch.object(wh, "_post_json") as posted:
        wh.emit("signal.auto_promoted", {
            "signal_id": 42, "theme": "Test", "verdict": "pass",
        })

    assert posted.call_count == 1
    url, payload = posted.call_args.args
    assert url == "https://example.com/hook"
    assert payload["event"] == "signal.auto_promoted"
    assert payload["body"]["signal_id"] == 42


def test_high_trend_min_threshold_filter(monkeypatch):
    """trend below WEBHOOK_MIN_TREND must not fire even if event is enabled."""
    monkeypatch.setenv("WEBHOOK_URL_SLACK", "https://hooks.slack.com/test")
    monkeypatch.setenv("WEBHOOK_MIN_TREND", "5")
    wh = _fresh_module()

    with patch.object(wh, "_post_json") as posted:
        wh.emit("signal.high_trend", {"theme": "X", "trend_score": 3})
    posted.assert_not_called()

    with patch.object(wh, "_post_json") as posted:
        wh.emit("signal.high_trend", {"theme": "Y", "trend_score": 7})
    posted.assert_called_once()


def test_disabled_event_not_fired(monkeypatch):
    """Events outside WEBHOOK_EVENTS allowlist are dropped silently."""
    monkeypatch.setenv("WEBHOOK_URL_GENERIC", "https://example.com/hook")
    monkeypatch.setenv("WEBHOOK_EVENTS", "signal.high_trend")  # only this
    wh = _fresh_module()

    with patch.object(wh, "_post_json") as posted:
        wh.emit("run.pending_review", {"verdict": "iterate"})
    posted.assert_not_called()


def test_emit_signal_event_helper(monkeypatch):
    monkeypatch.setenv("WEBHOOK_URL_GENERIC", "https://example.com/hook")
    monkeypatch.setenv("WEBHOOK_MIN_TREND", "0")
    wh = _fresh_module()

    signal = {
        "id": 99,
        "theme": "Mi señal",
        "score": 0.8,
        "trend_score": 3,
        "source_kind": "rss",
        "analysis": {"recommendation": "promote"},
    }
    with patch.object(wh, "_post_json") as posted:
        wh.emit_signal_event("signal.high_trend", signal, source_name="Mi Fuente")

    assert posted.call_count == 1
    _, payload = posted.call_args.args
    assert payload["body"]["signal_id"] == 99
    assert payload["body"]["source_name"] == "Mi Fuente"
    assert payload["body"]["recommendation"] == "promote"


def test_network_failure_does_not_raise(monkeypatch):
    """If the upstream is down, emit() must not raise — fire-and-forget."""
    monkeypatch.setenv("WEBHOOK_URL_SLACK", "https://example.invalid/never")
    monkeypatch.setenv("WEBHOOK_MIN_TREND", "0")
    wh = _fresh_module()

    # Should not raise even though the URL is unreachable
    wh.emit("signal.high_trend", {"theme": "X", "trend_score": 10})


def test_is_configured_reflects_env(monkeypatch):
    monkeypatch.delenv("WEBHOOK_URL_SLACK", raising=False)
    monkeypatch.delenv("WEBHOOK_URL_GENERIC", raising=False)
    wh = _fresh_module()
    assert wh.is_configured() is False

    monkeypatch.setenv("WEBHOOK_URL_SLACK", "https://x.test")
    wh = _fresh_module()
    assert wh.is_configured() is True
