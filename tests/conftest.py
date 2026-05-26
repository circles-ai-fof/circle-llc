"""
Shared pytest fixtures for the circle-llc test suite.

Auto-reset anti-bot state between tests so per-IP rate limits and tier configs
don't leak across the suite.

Also defends against tests that delete `orchestrator.*` from sys.modules
(e.g. tests/orchestrator/test_observability.py reloads base_agent). After such
a reload, any reference to anti_bot held by a previous import becomes stale
relative to the freshly-imported module. The fixture below re-imports anti_bot
on every test so the reference is always live.
"""
import sys

import pytest


@pytest.fixture(autouse=True)
def _reset_anti_bot_state():
    """
    Around every test:
      1. Re-import anti_bot so we always reference the live module
      2. Snapshot tier config
      3. Apply generous test defaults so legitimate calls don't 429
      4. Clear in-memory burst/daily stores
    Teardown reverses (1) and (2).
    """
    # Force a fresh import — covers the case where another test deleted
    # orchestrator.* from sys.modules. Without this, our snapshot below
    # would be of a stale module and reset_stores would no-op against the
    # wrong dict.
    if "orchestrator.core.anti_bot" not in sys.modules:
        import importlib  # noqa: F401
    from orchestrator.core import anti_bot as ab

    _original_tiers = {k: v for k, v in ab.TIERS.items()}
    ab.TIERS["public_form"] = (1000, 60, 10000)
    ab.TIERS["expensive_llm"] = (1000, 300, 10000)
    ab.reset_stores()
    yield
    # Re-import again in case a test deleted modules mid-flight
    from orchestrator.core import anti_bot as ab2
    ab2.reset_stores()
    # Restore by mutating in place (don't replace the dict object)
    ab2.TIERS.clear()
    ab2.TIERS.update(_original_tiers)
