"""
Golden regression tests for the 4-LLM ensemble — M9.0.

When Grok was added as the 4th voter alongside Claude + GPT + Gemini, the
voting math had to handle two new edge cases:

  1. **2-2 ties** — Counter.most_common returns insertion-order on ties, so
     without explicit tie-break logic the "winner" was an arbitrary LLM. The
     safer policy is: forced ITERATE (asks for more evidence, never picks).
  2. **Three-way splits (1-1-2 with iterate)** — the iterate verdict should
     still win even though one of the *other* verdicts could be tied with it.

The tests below pin down both cases and prevent regressions if the voting
logic is refactored. They also document the expected provider-naming
convention for all four LLMs ("claude", "openai", "google", "xai") so any
rename downstream is caught immediately.

These tests run fully offline — every LLM call is mocked.

NOTE on import strategy: some other tests in the suite delete
`orchestrator.*` from sys.modules (e.g. test_observability reloads). If we
imported `gate_ensemble_vote` at module top, our reference would become
stale relative to the module that gets patched. We therefore re-import it
inside every test so the patched module matches the called function.
"""
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _vote(verdict, confidence=0.8, provider="stub"):
    """Build an EnsembleVote with sensible defaults so the test reads
    closer to a verdict matrix than a chain of constructor calls."""
    from orchestrator.core.multi_llm import EnsembleVote
    return EnsembleVote(
        provider=provider,
        model="mock-model",
        verdict=verdict,
        confidence=confidence,
        rationale=f"mock {verdict} rationale",
    )


def _run_ensemble(claude=None, openai=None, gemini=None, grok=None):
    """
    Patch the 4 voter functions and invoke gate_ensemble_vote.

    Re-imports the module inside the call so that any prior test that
    deleted `orchestrator.core.multi_llm` from sys.modules doesn't leave
    us with a stale reference.
    """
    # Force fresh import so patch() and gate_ensemble_vote agree on the
    # module object — see module docstring for context.
    import importlib
    import orchestrator.core.multi_llm as multi_llm
    multi_llm = importlib.reload(multi_llm)

    with patch.object(multi_llm, "_vote_claude", return_value=claude), \
         patch.object(multi_llm, "_vote_openai", return_value=openai), \
         patch.object(multi_llm, "_vote_gemini", return_value=gemini), \
         patch.object(multi_llm, "_vote_grok", return_value=grok):
        return multi_llm.gate_ensemble_vote("p", "s")


# ---------------------------------------------------------------------------
# Provider naming convention (M9.0 contract)
# ---------------------------------------------------------------------------

def test_4way_provider_names_are_canonical():
    """The 4 voters must publish under stable provider strings; downstream
    log queries, billing attribution, and dashboard charts depend on them."""
    r = _run_ensemble(
        claude=_vote("pass", 0.9, provider="claude"),
        openai=_vote("pass", 0.8, provider="openai"),
        gemini=_vote("pass", 0.7, provider="google"),
        grok=_vote("pass", 0.85, provider="xai"),
    )
    assert {v.provider for v in r.votes} == {"claude", "openai", "google", "xai"}


# ---------------------------------------------------------------------------
# Unanimous votes (4-of-4)
# ---------------------------------------------------------------------------

def test_4way_unanimous_pass():
    """All 4 agree → highest possible confidence + 100% agreement."""
    r = _run_ensemble(
        claude=_vote("pass", 0.9),
        openai=_vote("pass", 0.8),
        gemini=_vote("pass", 0.7),
        grok=_vote("pass", 0.85),
    )
    assert r.final_verdict == "pass"
    assert r.agreement_pct == 1.0
    assert r.unanimous is True
    assert len(r.votes) == 4
    # avg(0.9+0.8+0.7+0.85)/4 = 0.8125 * 1.0 agreement = ~0.81
    assert r.final_confidence == pytest.approx(0.8125, abs=0.01)


def test_4way_unanimous_kill():
    r = _run_ensemble(
        claude=_vote("kill", 0.95),
        openai=_vote("kill", 0.85),
        gemini=_vote("kill", 0.90),
        grok=_vote("kill", 0.80),
    )
    assert r.final_verdict == "kill"
    assert r.unanimous


# ---------------------------------------------------------------------------
# 3-of-4 majority
# ---------------------------------------------------------------------------

def test_4way_3of4_majority_kill_with_grok_dissent():
    """Grok says pass, others KILL — majority wins. Confidence reduced by
    agreement penalty (3/4 = 0.75x)."""
    r = _run_ensemble(
        claude=_vote("kill", 0.9),
        openai=_vote("kill", 0.8),
        gemini=_vote("kill", 0.7),
        grok=_vote("pass", 0.85),
    )
    assert r.final_verdict == "kill"
    assert r.agreement_pct == 0.75
    # avg of kill voters = (0.9+0.8+0.7)/3 = 0.8 * 0.75 = 0.6
    assert r.final_confidence == pytest.approx(0.6, abs=0.01)


def test_4way_3of4_majority_iterate():
    """Iterate verdict can also win by 3-of-4 majority."""
    r = _run_ensemble(
        claude=_vote("iterate", 0.8),
        openai=_vote("iterate", 0.7),
        gemini=_vote("iterate", 0.6),
        grok=_vote("kill", 0.9),
    )
    assert r.final_verdict == "iterate"
    assert r.agreement_pct == 0.75


# ---------------------------------------------------------------------------
# 2-2 tie → forced ITERATE (M9.0 policy)
# ---------------------------------------------------------------------------

def test_4way_tie_pass_vs_kill_forces_iterate():
    """The most dangerous case: 2 say PASS, 2 say KILL. We MUST NOT pick a
    winner based on insertion order — that would be silently arbitrary.
    Force ITERATE so the workflow gathers more evidence."""
    r = _run_ensemble(
        claude=_vote("pass", 0.9),
        openai=_vote("pass", 0.8),
        gemini=_vote("kill", 0.7),
        grok=_vote("kill", 0.85),
    )
    assert r.final_verdict == "iterate"
    # No voters actually said iterate, so confidence falls back to penalised.
    # Math: top_count for "iterate" defaults to 1 → agreement = 1/4 = 0.25
    assert r.final_confidence < 0.5


def test_4way_tie_iterate_vs_kill_picks_iterate():
    """If the tie INCLUDES iterate (2 iterate, 2 kill), iterate should still
    win — it's the safer verdict and one of the tied options."""
    r = _run_ensemble(
        claude=_vote("iterate", 0.8),
        openai=_vote("iterate", 0.7),
        gemini=_vote("kill", 0.9),
        grok=_vote("kill", 0.85),
    )
    assert r.final_verdict == "iterate"


# ---------------------------------------------------------------------------
# Backward compatibility — legacy 3-LLM (no XAI key)
# ---------------------------------------------------------------------------

def test_4way_degrades_to_3_when_grok_missing():
    """Most existing deployments don't have XAI_API_KEY yet. The ensemble
    must keep working with the original 3 providers — no breaking changes."""
    r = _run_ensemble(
        claude=_vote("pass", 0.9),
        openai=_vote("pass", 0.8),
        gemini=_vote("pass", 0.7),
        grok=None,  # XAI_API_KEY absent
    )
    assert r.final_verdict == "pass"
    assert len(r.votes) == 3
    assert r.agreement_pct == 1.0


def test_4way_degrades_to_2_with_only_claude_and_grok():
    """Even if 2 providers are missing, the ensemble produces a verdict from
    what's available."""
    r = _run_ensemble(
        claude=_vote("kill", 0.9),
        openai=None,
        gemini=None,
        grok=_vote("kill", 0.85),
    )
    assert r.final_verdict == "kill"
    assert len(r.votes) == 2
    assert r.agreement_pct == 1.0


def test_4way_solo_grok_works():
    """Pathological: only Grok has a key. The single vote wins."""
    r = _run_ensemble(
        claude=None,
        openai=None,
        gemini=None,
        grok=_vote("iterate", 0.6),
    )
    assert r.final_verdict == "iterate"
    assert len(r.votes) == 1


# ---------------------------------------------------------------------------
# Three-way splits (1-1-2 with iterate winning)
# ---------------------------------------------------------------------------

def test_4way_split_pass_kill_iterate_iterate_picks_iterate():
    """Different verdicts: pass, kill, iterate, iterate. Iterate wins with 2."""
    r = _run_ensemble(
        claude=_vote("pass", 0.9),
        openai=_vote("kill", 0.8),
        gemini=_vote("iterate", 0.7),
        grok=_vote("iterate", 0.85),
    )
    assert r.final_verdict == "iterate"
    assert r.agreement_pct == 0.5  # 2/4


# ---------------------------------------------------------------------------
# Empty case (all providers unavailable)
# ---------------------------------------------------------------------------

def test_4way_no_providers_returns_safe_iterate():
    """All 4 keys missing → fallback iterate with 0 confidence so caller
    knows to use the single-LLM path."""
    r = _run_ensemble(claude=None, openai=None, gemini=None, grok=None)
    assert r.final_verdict == "iterate"
    assert r.final_confidence == 0.0
    assert r.votes == []
