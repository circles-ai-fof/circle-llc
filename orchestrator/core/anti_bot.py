"""
Anti-bot defenses (R26).

Layered defenses against bot saturation of expensive endpoints:

  Layer 1: per-IP burst rate limit (cheap, in-process)
  Layer 2: per-IP daily budget (expensive endpoints only)
  Layer 3: honeypot + time-on-page for form submissions
  Layer 4: Cloudflare Turnstile token verification (opt-in)
  Layer 5: disposable-email blocklist (opt-in)
  Layer 6: optional shared-secret header for /gate/run

Tier definitions:
  - "public_form"  — landing forms (cheap, public, expect humans)
  - "expensive_llm" — /gate/run (costs $0.06 per call)

Each tier has its own quotas; defenses compose.
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier quotas (overridable via env vars for ops emergencies)
# ---------------------------------------------------------------------------

TIERS: Dict[str, Tuple[int, int, int]] = {
    # (burst_max, burst_window_s, daily_max)
    "public_form": (
        int(os.getenv("RL_FORM_BURST_MAX", "5")),
        int(os.getenv("RL_FORM_BURST_WINDOW_S", "60")),
        int(os.getenv("RL_FORM_DAILY_MAX", "30")),
    ),
    "expensive_llm": (
        int(os.getenv("RL_LLM_BURST_MAX", "2")),
        int(os.getenv("RL_LLM_BURST_WINDOW_S", "300")),  # 2 calls per 5 min
        int(os.getenv("RL_LLM_DAILY_MAX", "10")),  # 10 calls per IP per day
    ),
}

# Per-IP timestamp store: {tier: {ip: [timestamps]}}
_burst_store: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
_daily_store: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

_DAY_SECONDS = 86_400


@dataclass
class RateLimitVerdict:
    allowed: bool
    reason: Optional[str] = None
    retry_after_s: Optional[int] = None


def check_rate_limit(ip: str, tier: str) -> RateLimitVerdict:
    """Per-IP burst + daily quotas. Both must pass."""
    if tier not in TIERS:
        # Unknown tier: fail safe (don't block, but log)
        logger.warning("anti_bot: unknown tier %r — bypassing", tier)
        return RateLimitVerdict(True)

    burst_max, burst_window_s, daily_max = TIERS[tier]
    now = time.monotonic()

    # Burst (short window)
    timestamps = _burst_store[tier][ip]
    timestamps[:] = [t for t in timestamps if t > now - burst_window_s]
    if len(timestamps) >= burst_max:
        retry = int(burst_window_s - (now - timestamps[0]) + 1)
        return RateLimitVerdict(
            False,
            f"Burst rate limit ({burst_max}/{burst_window_s}s) exceeded",
            retry,
        )

    # Daily
    day_timestamps = _daily_store[tier][ip]
    day_timestamps[:] = [t for t in day_timestamps if t > now - _DAY_SECONDS]
    if len(day_timestamps) >= daily_max:
        retry = int(_DAY_SECONDS - (now - day_timestamps[0]) + 1)
        return RateLimitVerdict(
            False,
            f"Daily quota ({daily_max}/day) exceeded for this IP",
            retry,
        )

    # Allowed — record
    timestamps.append(now)
    day_timestamps.append(now)
    return RateLimitVerdict(True)


# ---------------------------------------------------------------------------
# Honeypot + time-on-page (Layer 3)
# ---------------------------------------------------------------------------

# Field name MUST match the hidden input in LeadForm.tsx.
# Renaming requires changing both sides.
HONEYPOT_FIELD = "company_website"
MIN_FORM_DWELL_MS = int(os.getenv("MIN_FORM_DWELL_MS", "3000"))


def check_honeypot(submitted_form: dict) -> RateLimitVerdict:
    """
    A bot crawler usually fills every input field, including the hidden
    `company_website`. A real human never sees it.
    """
    value = submitted_form.get(HONEYPOT_FIELD)
    if value:
        return RateLimitVerdict(
            False,
            "honeypot triggered",
            retry_after_s=3600,
        )
    return RateLimitVerdict(True)


def check_dwell(dwell_ms: Optional[int]) -> RateLimitVerdict:
    """
    Humans take >3s to read + fill a form. Bots submit < 1s.
    Missing dwell_ms is treated as suspicious but allowed (older clients).
    """
    if dwell_ms is None:
        return RateLimitVerdict(True)
    if dwell_ms < MIN_FORM_DWELL_MS:
        return RateLimitVerdict(
            False,
            f"form submitted too quickly ({dwell_ms}ms < {MIN_FORM_DWELL_MS}ms)",
            retry_after_s=10,
        )
    return RateLimitVerdict(True)


# ---------------------------------------------------------------------------
# Cloudflare Turnstile (Layer 4) — opt-in
# ---------------------------------------------------------------------------


def turnstile_required() -> bool:
    return bool(os.getenv("TURNSTILE_SECRET_KEY"))


def verify_turnstile_token(token: Optional[str], remote_ip: str) -> RateLimitVerdict:
    """
    Verify a Cloudflare Turnstile widget token. Free, no PII, no user friction.
    Only fires if TURNSTILE_SECRET_KEY is configured.
    Falls open (allows) on network errors so a Cloudflare outage doesn't break us.
    """
    secret = os.getenv("TURNSTILE_SECRET_KEY")
    if not secret:
        return RateLimitVerdict(True)  # not configured -> skip
    if not token:
        return RateLimitVerdict(False, "missing turnstile token", retry_after_s=10)
    try:
        import urllib.request, urllib.parse, json
        data = urllib.parse.urlencode(
            {"secret": secret, "response": token, "remoteip": remote_ip}
        ).encode()
        req = urllib.request.Request(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data=data,
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            payload = json.loads(resp.read())
        if not payload.get("success"):
            return RateLimitVerdict(
                False,
                f"turnstile rejected: {payload.get('error-codes', [])}",
                retry_after_s=10,
            )
        return RateLimitVerdict(True)
    except Exception as e:  # noqa: BLE001
        logger.warning("anti_bot: turnstile network error -> fail-open: %s", e)
        return RateLimitVerdict(True)


# ---------------------------------------------------------------------------
# Disposable email blocklist (Layer 5)
# ---------------------------------------------------------------------------

# Hand-curated short list; full lists are 10k+ domains and don't need to live in code.
_DISPOSABLE_DOMAINS = {
    "mailinator.com",
    "tempmail.com",
    "10minutemail.com",
    "guerrillamail.com",
    "yopmail.com",
    "trashmail.com",
    "throwawaymail.com",
    "fakeinbox.com",
    "getnada.com",
    "maildrop.cc",
    "sharklasers.com",
    "0wnd.net",
    "dispostable.com",
}


def is_disposable_email(email: str) -> bool:
    if "@" not in email:
        return False
    domain = email.rsplit("@", 1)[-1].strip().lower()
    return domain in _DISPOSABLE_DOMAINS


# ---------------------------------------------------------------------------
# Shared-secret header (Layer 6) — opt-in for /gate/run
# ---------------------------------------------------------------------------


def gate_run_secret_required() -> bool:
    return bool(os.getenv("GATE_RUN_SECRET"))


def check_gate_run_secret(provided_header: Optional[str]) -> RateLimitVerdict:
    secret = os.getenv("GATE_RUN_SECRET")
    if not secret:
        return RateLimitVerdict(True)
    if not provided_header:
        return RateLimitVerdict(False, "missing X-Gate-Secret header", retry_after_s=None)
    if provided_header != secret:
        return RateLimitVerdict(False, "invalid X-Gate-Secret", retry_after_s=None)
    return RateLimitVerdict(True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def reset_stores() -> None:
    """Test-only helper to clear in-memory state between tests."""
    _burst_store.clear()
    _daily_store.clear()


__all__ = [
    "RateLimitVerdict",
    "HONEYPOT_FIELD",
    "MIN_FORM_DWELL_MS",
    "check_rate_limit",
    "check_honeypot",
    "check_dwell",
    "verify_turnstile_token",
    "turnstile_required",
    "is_disposable_email",
    "gate_run_secret_required",
    "check_gate_run_secret",
    "reset_stores",
]
