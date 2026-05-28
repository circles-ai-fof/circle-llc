"""
Outbound webhooks — fire-and-forget notifications for events the founder
cares about while away from the dashboard.

Supported event types:
  - signal.high_trend         — a signal's trend_score crossed the threshold
  - signal.analyzed.promote   — IdeaAnalyzer recommended promote
  - signal.auto_promoted      — a signal was auto-promoted (high trend)
  - run.completed             — a gate run finished (pass/kill/iterate)
  - run.pending_review        — a run was flagged for human review

Endpoint URLs come from env vars (no DB needed for M1):
  WEBHOOK_URL_SLACK       — Slack-incoming-webhook URL (or compatible)
  WEBHOOK_URL_GENERIC     — generic POST endpoint (Zapier, n8n, etc)
  WEBHOOK_MIN_TREND       — only fire signal.high_trend if trend >= this (default 5)
  WEBHOOK_EVENTS          — comma-separated event types to enable (default: all)

Never raises — webhook failures are logged but don't break the running flow.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger(__name__)


_TIMEOUT_SEC = 5


def _enabled_events() -> set:
    raw = os.getenv("WEBHOOK_EVENTS", "").strip()
    if not raw:
        # Default: only the high-signal events. run.completed is too noisy.
        return {
            "signal.high_trend",
            "signal.analyzed.promote",
            "signal.auto_promoted",
            "run.pending_review",
        }
    return {e.strip() for e in raw.split(",") if e.strip()}


def _post_json(url: str, payload: Dict[str, Any]) -> None:
    """POST JSON. Returns nothing — errors are logged, never raised."""
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
            if 200 <= resp.status < 300:
                logger.debug("webhook POST %s → %d", url, resp.status)
            else:
                logger.warning("webhook POST %s → %d", url, resp.status)
    except urllib.error.HTTPError as exc:
        logger.warning("webhook HTTPError %s: %s", url, exc.code)
    except urllib.error.URLError as exc:
        logger.warning("webhook URLError %s: %s", url, exc.reason)
    except Exception as exc:  # noqa: BLE001
        logger.warning("webhook unexpected error %s: %s", url, exc)


def _slack_payload(event: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Format the event as a Slack 'incoming webhook' message (text + blocks).

    Slack accepts {"text": "..."} as a fallback for clients without block-kit.
    """
    title = {
        "signal.high_trend": f"🔥 Señal con trend alto +{body.get('trend_score', 0)}",
        "signal.analyzed.promote": "🟢 IdeaAnalyzer recomienda PROMOVER",
        "signal.auto_promoted": "→ Señal auto-promovida a workflow completo",
        "run.completed": f"✓ Run completado · verdict={body.get('verdict', '?')}",
        "run.pending_review": "⚠️ Run requiere revisión humana",
    }.get(event, f"Evento: {event}")

    summary_lines = []
    if body.get("theme"):
        summary_lines.append(f"*Tema:* {body['theme'][:120]}")
    if body.get("source_name"):
        summary_lines.append(f"*Fuente:* {body['source_name']}")
    if body.get("recommendation"):
        summary_lines.append(f"*Recomendación:* {body['recommendation']}")
    if body.get("verdict"):
        summary_lines.append(f"*Verdict:* {body['verdict']}  (confidence {body.get('confidence', 0):.2f})")
    if body.get("dashboard_url"):
        summary_lines.append(f"<{body['dashboard_url']}|Ver en dashboard>")

    text = title + ("\n" + "\n".join(summary_lines) if summary_lines else "")
    return {"text": text}


def emit(event: str, body: Dict[str, Any]) -> None:
    """Public entry point. Fire-and-forget.

    `event` is one of the documented event strings. `body` is a dict with
    payload-specific fields (theme, source_name, recommendation, verdict,
    confidence, run_id, signal_id, trend_score, dashboard_url, ...).
    """
    enabled = _enabled_events()
    if event not in enabled:
        return

    slack_url = (os.getenv("WEBHOOK_URL_SLACK") or "").strip()
    generic_url = (os.getenv("WEBHOOK_URL_GENERIC") or "").strip()

    if event == "signal.high_trend":
        try:
            min_trend = int(os.getenv("WEBHOOK_MIN_TREND", "5"))
        except ValueError:
            min_trend = 5
        if (body.get("trend_score") or 0) < min_trend:
            return

    if slack_url:
        _post_json(slack_url, _slack_payload(event, body))
    if generic_url:
        # Generic webhook gets the raw event + body — recipient decides format
        _post_json(generic_url, {"event": event, "body": body})


def emit_signal_event(event: str, signal: Dict[str, Any], source_name: Optional[str] = None) -> None:
    """Convenience wrapper that maps a signal dict to a webhook body."""
    emit(event, {
        "signal_id": signal.get("id"),
        "theme": signal.get("theme", ""),
        "source_name": source_name or signal.get("source_name") or signal.get("source_kind"),
        "score": signal.get("score"),
        "trend_score": signal.get("trend_score"),
        "recommendation": (signal.get("analysis") or {}).get("recommendation"),
        "dashboard_url": _signal_url(signal.get("id")),
    })


def _signal_url(signal_id: Optional[int]) -> Optional[str]:
    base = (os.getenv("DASHBOARD_BASE_URL") or "").rstrip("/")
    if not base or not signal_id:
        return None
    return f"{base}/cazar/senales/{signal_id}"


def list_enabled_events() -> Iterable[str]:
    """For diagnostics."""
    return sorted(_enabled_events())


def is_configured() -> bool:
    """True if at least one webhook URL is set."""
    return bool((os.getenv("WEBHOOK_URL_SLACK") or os.getenv("WEBHOOK_URL_GENERIC") or "").strip())
