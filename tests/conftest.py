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
      1. Re-import anti_bot + storage so we always reference live modules
      2. Snapshot tier config
      3. Apply generous test defaults so legitimate calls don't 429
      4. Clear in-memory anti_bot stores + leads/runs stores
    Teardown reverses (1) and (2).
    """
    # Force fresh imports — covers the case where another test deleted
    # orchestrator.* from sys.modules. Without this, our snapshot below
    # would be of stale modules.
    from orchestrator.core import anti_bot as ab
    from orchestrator.core import storage as st

    _original_tiers = {k: v for k, v in ab.TIERS.items()}
    ab.TIERS["public_form"] = (1000, 60, 10000)
    ab.TIERS["expensive_llm"] = (1000, 300, 10000)
    ab.reset_stores()
    # Wipe all persisted stores so tests can't pollute each other
    st.leads_store.clear()
    st.runs_store.clear()
    st.auth_store.clear()
    st.sources_store.clear()
    st.signals_store.clear()
    st.links_log_store.clear()
    if hasattr(st, "connected_accounts_store"):
        st.connected_accounts_store.clear()
    # Also clear the legacy in-process rate-limit store inside api.py
    try:
        from orchestrator import api as _api
        _api._rate_limit_store.clear()
    except Exception:
        pass
    yield
    # Re-import again in case a test deleted modules mid-flight
    from orchestrator.core import anti_bot as ab2
    from orchestrator.core import storage as st2
    ab2.reset_stores()
    ab2.TIERS.clear()
    ab2.TIERS.update(_original_tiers)
    st2.leads_store.clear()
    st2.runs_store.clear()
    st2.auth_store.clear()
    st2.sources_store.clear()
    st2.signals_store.clear()
    st2.links_log_store.clear()
    if hasattr(st2, "connected_accounts_store"):
        st2.connected_accounts_store.clear()
    try:
        from orchestrator import api as _api2
        _api2._rate_limit_store.clear()
    except Exception:
        pass
