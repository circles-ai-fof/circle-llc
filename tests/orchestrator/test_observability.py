"""
Tests for Langfuse observability integration in BaseAgent.

Verifies opt-in behavior: agents must work identically whether or not
LANGFUSE_PUBLIC_KEY is present in the environment.

Rule R06: mock_mode=True mandatory in CI — these tests never hit real APIs.
"""
from __future__ import annotations

import importlib
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper: reload base_agent with a controlled environment
# ---------------------------------------------------------------------------

def _reload_base_agent_with_env(**env_overrides):
    """
    Reload orchestrator.core.base_agent with the given env vars set.
    Returns the freshly-imported module so we can inspect module-level state.
    """
    # Remove cached module so the module-level code re-executes
    for key in list(sys.modules.keys()):
        if "orchestrator.core.base_agent" in key:
            del sys.modules[key]

    with patch.dict(os.environ, env_overrides, clear=False):
        module = importlib.import_module("orchestrator.core.base_agent")
    return module


# ---------------------------------------------------------------------------
# Test 1: agents run in mock_mode without Langfuse keys
# ---------------------------------------------------------------------------

def test_agent_works_without_langfuse_keys():
    """
    Without LANGFUSE_PUBLIC_KEY agents should run in mock_mode without error.
    The absence of the key must not raise any exception during instantiation
    or during a _mock_*() call on a concrete subclass.
    """
    env = {k: v for k, v in os.environ.items() if k != "LANGFUSE_PUBLIC_KEY"}
    with patch.dict(os.environ, {}, clear=True):
        os.environ.update(env)
        os.environ.pop("LANGFUSE_PUBLIC_KEY", None)

        # Import the workflow (which uses BaseAgent-derived classes) in mock_mode
        # Re-import to pick up env change
        for key in list(sys.modules.keys()):
            if "orchestrator" in key:
                del sys.modules[key]

        from orchestrator.workflows.evidence_gate import EvidenceGateWorkflow

        wf = EvidenceGateWorkflow(mock_mode=True)
        run = wf.run("test idea sin langfuse")

    assert run.idea.title, "idea.title should be populated in mock mode"
    assert run.decision.verdict is not None, "decision.verdict should not be None"


# ---------------------------------------------------------------------------
# Test 2: _LANGFUSE_ENABLED is False when key is absent or empty
# ---------------------------------------------------------------------------

def test_langfuse_enabled_flag_respects_env_missing_key():
    """
    When LANGFUSE_PUBLIC_KEY is not set, _LANGFUSE_ENABLED must be False.
    """
    module = _reload_base_agent_with_env()
    # Remove key explicitly after reload to simulate absent key
    env_without_key = {k: v for k, v in os.environ.items() if k != "LANGFUSE_PUBLIC_KEY"}
    with patch.dict(os.environ, env_without_key, clear=True):
        module2 = _reload_base_agent_with_env()
    assert module2._LANGFUSE_ENABLED is False, (
        "_LANGFUSE_ENABLED should be False when LANGFUSE_PUBLIC_KEY is absent"
    )


def test_langfuse_enabled_flag_respects_env_empty_key():
    """
    When LANGFUSE_PUBLIC_KEY is an empty string, _LANGFUSE_ENABLED must be False.
    An empty string is falsy in Python — this is intentional to avoid
    accidentally hitting Langfuse with an invalid key.
    """
    module = _reload_base_agent_with_env(LANGFUSE_PUBLIC_KEY="")
    assert module._LANGFUSE_ENABLED is False, (
        "_LANGFUSE_ENABLED should be False when LANGFUSE_PUBLIC_KEY is empty string"
    )


def test_langfuse_enabled_flag_true_when_key_is_set():
    """
    When LANGFUSE_PUBLIC_KEY is a non-empty string, _LANGFUSE_ENABLED must be True
    (assuming the langfuse package is installed).
    We mock the Langfuse class to avoid a real network call.
    """
    fake_langfuse_module = types.ModuleType("langfuse")
    fake_langfuse_module.Langfuse = MagicMock(return_value=MagicMock())

    with patch.dict(sys.modules, {"langfuse": fake_langfuse_module}):
        module = _reload_base_agent_with_env(
            LANGFUSE_PUBLIC_KEY="pk-lf-test-key",
            LANGFUSE_SECRET_KEY="sk-lf-test-key",
        )

    assert module._LANGFUSE_ENABLED is True, (
        "_LANGFUSE_ENABLED should be True when LANGFUSE_PUBLIC_KEY is set and langfuse is installed"
    )


# ---------------------------------------------------------------------------
# Test 3: base_agent.py has the Langfuse integration symbols
# ---------------------------------------------------------------------------

def test_base_agent_has_langfuse_integration():
    """
    Verifies that base_agent.py exports the module-level symbols introduced
    by the Langfuse integration. This is a structural check — it ensures
    the integration code was not accidentally removed during a refactor.
    """
    import orchestrator.core.base_agent as ba

    assert hasattr(ba, "_LANGFUSE_ENABLED"), (
        "base_agent must define _LANGFUSE_ENABLED at module level"
    )
    assert hasattr(ba, "_langfuse_client"), (
        "base_agent must define _langfuse_client at module level"
    )
    assert isinstance(ba._LANGFUSE_ENABLED, bool), (
        "_LANGFUSE_ENABLED must be a bool"
    )


def test_base_agent_langfuse_client_is_none_without_key():
    """
    When LANGFUSE_PUBLIC_KEY is absent, _langfuse_client must be None.
    No Langfuse instance should be created without a key.
    """
    module = _reload_base_agent_with_env()
    env_without_key = {k: v for k, v in os.environ.items() if k != "LANGFUSE_PUBLIC_KEY"}
    with patch.dict(os.environ, env_without_key, clear=True):
        module2 = _reload_base_agent_with_env()

    assert module2._langfuse_client is None, (
        "_langfuse_client must be None when LANGFUSE_PUBLIC_KEY is absent"
    )


# ---------------------------------------------------------------------------
# Test 4: Langfuse import failure degrades gracefully
# ---------------------------------------------------------------------------

def test_graceful_degradation_when_langfuse_not_installed():
    """
    If the langfuse package is not installed (ImportError), _LANGFUSE_ENABLED
    must be False and _langfuse_client must be None. The module must load
    without raising any exception.
    """
    # Simulate langfuse not being installed by temporarily hiding it
    with patch.dict(sys.modules, {"langfuse": None}):
        module = _reload_base_agent_with_env(LANGFUSE_PUBLIC_KEY="pk-lf-test")

    assert module._LANGFUSE_ENABLED is False, (
        "_LANGFUSE_ENABLED must be False when langfuse package is not installed"
    )
    assert module._langfuse_client is None, (
        "_langfuse_client must be None when langfuse package is not installed"
    )
