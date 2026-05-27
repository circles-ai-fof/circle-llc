"""
Closed-beta authentication (R27 / ADR-010).

Email-only allowlist auth. No passwords, no SMTP. The 3 beta emails are
configured via the ALLOWED_EMAILS env var. Anyone whose email is in the
allowlist gets a session token; anyone else gets 403 — but EVERY attempt
(allowed or rejected) is logged with IP, user-agent, timestamp so we can
later see who tried to access, from what country (by IP geo-lookup).

This is intentionally minimal — fine for a 3-user closed beta. Migration
to SSO/magic-links happens when we open to public beta.
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# Session token lifetime — 7 days
SESSION_TTL_SECONDS = 7 * 24 * 3600


@dataclass
class AuthAttempt:
    email: str
    ip: Optional[str]
    user_agent: Optional[str]
    ts: int
    allowed: bool
    reason: str  # short tag: "ok", "not_allowlisted", "malformed_email"


@dataclass
class Session:
    token: str
    email: str
    expires_at: int  # unix seconds


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------


def _normalize(email: str) -> str:
    return email.strip().lower()


def allowed_emails() -> set[str]:
    """Parse the ALLOWED_EMAILS env var into a normalized set."""
    raw = os.getenv("ALLOWED_EMAILS", "")
    return {
        _normalize(e)
        for e in raw.split(",")
        if e.strip() and "@" in e
    }


def is_allowed(email: str) -> bool:
    return _normalize(email) in allowed_emails()


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------


def new_token() -> str:
    """64-char URL-safe random token. Cryptographically secure."""
    return secrets.token_urlsafe(48)


def session_expiry() -> int:
    return int(time.time()) + SESSION_TTL_SECONDS


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def looks_like_email(email: str) -> bool:
    """Cheap shape check. Real validation happens via the allowlist."""
    if not isinstance(email, str):
        return False
    e = email.strip()
    if len(e) < 5 or len(e) > 200:
        return False
    if "@" not in e:
        return False
    local, _, domain = e.partition("@")
    if not local or not domain or "." not in domain:
        return False
    return True


__all__ = [
    "AuthAttempt",
    "Session",
    "SESSION_TTL_SECONDS",
    "allowed_emails",
    "is_allowed",
    "new_token",
    "session_expiry",
    "looks_like_email",
]
