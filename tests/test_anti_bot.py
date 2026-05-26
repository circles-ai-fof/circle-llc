"""Tests for the anti-bot module (R26).

Imports go through `ab` (live module reference) to survive the module
re-imports that other test files (e.g. test_observability.py) trigger.
"""
import os
from unittest.mock import patch

import pytest

# All access through `ab.X` — never bind top-level names to the module's
# functions or dicts, because they go stale when sys.modules is mutated.


# Note: tests/conftest.py auto-resets store + tier config around every test.


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------


def test_rate_limit_allows_under_burst():
    from orchestrator.core import anti_bot as ab
    ab.TIERS["public_form"] = (3, 60, 100)
    for _ in range(3):
        assert ab.check_rate_limit("1.1.1.1", "public_form").allowed


def test_rate_limit_blocks_at_burst_max():
    from orchestrator.core import anti_bot as ab
    ab.TIERS["public_form"] = (3, 60, 100)
    for _ in range(3):
        ab.check_rate_limit("2.2.2.2", "public_form")
    v = ab.check_rate_limit("2.2.2.2", "public_form")
    assert v.allowed is False
    assert "Burst" in (v.reason or "")
    assert v.retry_after_s is not None and v.retry_after_s > 0


def test_rate_limit_isolated_per_ip():
    from orchestrator.core import anti_bot as ab
    ab.TIERS["public_form"] = (2, 60, 100)
    ab.check_rate_limit("3.3.3.3", "public_form")
    ab.check_rate_limit("3.3.3.3", "public_form")
    # Same IP exceeds
    assert ab.check_rate_limit("3.3.3.3", "public_form").allowed is False
    # Different IP unaffected
    assert ab.check_rate_limit("4.4.4.4", "public_form").allowed is True


def test_rate_limit_daily_quota():
    from orchestrator.core import anti_bot as ab
    ab.TIERS["expensive_llm"] = (100, 60, 2)  # large burst, tiny daily
    assert ab.check_rate_limit("5.5.5.5", "expensive_llm").allowed
    assert ab.check_rate_limit("5.5.5.5", "expensive_llm").allowed
    v = ab.check_rate_limit("5.5.5.5", "expensive_llm")
    assert v.allowed is False
    assert "Daily" in (v.reason or "")


def test_rate_limit_unknown_tier_fails_open():
    from orchestrator.core import anti_bot as ab
    v = ab.check_rate_limit("6.6.6.6", "nonexistent_tier")
    assert v.allowed is True


# ---------------------------------------------------------------------------
# Honeypot
# ---------------------------------------------------------------------------


def test_honeypot_empty_passes():
    from orchestrator.core import anti_bot as ab
    assert ab.check_honeypot({ab.HONEYPOT_FIELD: ""}).allowed
    assert ab.check_honeypot({ab.HONEYPOT_FIELD: None}).allowed
    assert ab.check_honeypot({}).allowed  # missing key


def test_honeypot_filled_blocks():
    from orchestrator.core import anti_bot as ab
    v = ab.check_honeypot({ab.HONEYPOT_FIELD: "http://my-real-site.com"})
    assert v.allowed is False
    assert "honeypot" in (v.reason or "").lower()


# ---------------------------------------------------------------------------
# Dwell
# ---------------------------------------------------------------------------


def test_dwell_missing_passes():
    from orchestrator.core import anti_bot as ab
    assert ab.check_dwell(None).allowed


def test_dwell_too_fast_blocks():
    from orchestrator.core import anti_bot as ab
    ab.MIN_FORM_DWELL_MS = 3000
    v = ab.check_dwell(500)
    assert v.allowed is False
    assert "quickly" in (v.reason or "")


def test_dwell_slow_enough_passes():
    from orchestrator.core import anti_bot as ab
    ab.MIN_FORM_DWELL_MS = 3000
    assert ab.check_dwell(5000).allowed


# ---------------------------------------------------------------------------
# Disposable email
# ---------------------------------------------------------------------------


def test_disposable_email_blocked():
    from orchestrator.core import anti_bot as ab
    assert ab.is_disposable_email("user@mailinator.com")
    assert ab.is_disposable_email("test@10minutemail.com")
    assert ab.is_disposable_email("foo@YOPMAIL.com")  # case insensitive


def test_real_email_allowed():
    from orchestrator.core import anti_bot as ab
    assert not ab.is_disposable_email("user@gmail.com")
    assert not ab.is_disposable_email("foo@circles-ai.ai")
    assert not ab.is_disposable_email("legit@asiservy.com")


def test_malformed_email_not_disposable():
    from orchestrator.core import anti_bot as ab
    assert not ab.is_disposable_email("not-an-email")
    assert not ab.is_disposable_email("")


# ---------------------------------------------------------------------------
# Gate-run secret
# ---------------------------------------------------------------------------


def test_secret_not_required_when_unset():
    from orchestrator.core import anti_bot as ab
    with patch.dict(os.environ, {"GATE_RUN_SECRET": ""}, clear=False):
        assert ab.gate_run_secret_required() is False
        assert ab.check_gate_run_secret(None).allowed
        assert ab.check_gate_run_secret("anything").allowed


def test_secret_blocks_missing_header():
    from orchestrator.core import anti_bot as ab
    with patch.dict(os.environ, {"GATE_RUN_SECRET": "super-secret-123"}, clear=False):
        v = ab.check_gate_run_secret(None)
        assert v.allowed is False
        assert "missing" in (v.reason or "").lower()


def test_secret_blocks_wrong_header():
    from orchestrator.core import anti_bot as ab
    with patch.dict(os.environ, {"GATE_RUN_SECRET": "super-secret-123"}, clear=False):
        v = ab.check_gate_run_secret("wrong-value")
        assert v.allowed is False
        assert "invalid" in (v.reason or "").lower()


def test_secret_allows_correct_header():
    from orchestrator.core import anti_bot as ab
    with patch.dict(os.environ, {"GATE_RUN_SECRET": "super-secret-123"}, clear=False):
        assert ab.check_gate_run_secret("super-secret-123").allowed


# ---------------------------------------------------------------------------
# Turnstile
# ---------------------------------------------------------------------------


def test_turnstile_not_required_when_unset():
    from orchestrator.core import anti_bot as ab
    with patch.dict(os.environ, {"TURNSTILE_SECRET_KEY": ""}, clear=False):
        assert ab.turnstile_required() is False
