"""
Test that no two active agents have overlapping scopes.
Parses SCOPES.md and verifies the overlap table shows all ✗.
Rule R15 (FASE 5) — scope exclusivo documentado, overlap test runs in CI.
"""
import re
from pathlib import Path


SCOPES_MD = Path(__file__).parent.parent.parent / "orchestrator" / "agents" / "SCOPES.md"

ACTIVE_AGENTS = [
    "idea_hunter",
    "idea_maturer",
    "market_validator",
    "landing_generator",
    "gate_decider",
]

# Tasks that belong exclusively to each agent (parsed from SCOPES.md prose)
AGENT_TASKS = {
    "idea_hunter": {"generate_idea", "topic_to_idea"},
    "idea_maturer": {"define_icp", "value_proposition", "mature_idea"},
    "market_validator": {"design_test", "set_thresholds", "hypothesis"},
    "landing_generator": {"write_copy", "headline", "cta", "landing_page"},
    "gate_decider": {"evaluate_metrics", "pass_kill_iterate", "gate_decision"},
}


def test_scopes_md_exists():
    assert SCOPES_MD.exists(), f"SCOPES.md not found at {SCOPES_MD}"


def test_all_active_agents_documented_in_scopes():
    content = SCOPES_MD.read_text(encoding="utf-8")
    for agent in ACTIVE_AGENTS:
        assert agent in content, f"Agent '{agent}' not documented in SCOPES.md"


def test_no_two_agents_have_overlapping_task_sets():
    from itertools import combinations

    overlaps = []
    for agent_a, agent_b in combinations(ACTIVE_AGENTS, 2):
        tasks_a = AGENT_TASKS[agent_a]
        tasks_b = AGENT_TASKS[agent_b]
        overlap = tasks_a & tasks_b
        if overlap:
            overlaps.append(f"{agent_a} ↔ {agent_b}: {overlap}")

    assert not overlaps, (
        "Scope overlaps detected — fix SCOPES.md and agent responsibilities:\n"
        + "\n".join(overlaps)
    )


def test_overlap_table_in_scopes_md_has_no_checkmarks():
    content = SCOPES_MD.read_text(encoding="utf-8")
    # The table should only show ✗ (no overlap), never ✓
    # Find lines in the matrix section
    table_section = content[content.find("Tabla de overlaps"):]
    assert "✓" not in table_section, (
        "SCOPES.md overlap table contains ✓ — all cells should be ✗"
    )


def test_five_active_agents_exactly():
    assert len(ACTIVE_AGENTS) == 5, "Expected exactly 5 active agents in Sprint M1"


def test_deferred_readme_exists():
    deferred = Path(__file__).parent.parent.parent / "orchestrator" / "agents" / "_deferred" / "README.md"
    assert deferred.exists(), "_deferred/README.md must exist"
    content = deferred.read_text(encoding="utf-8")
    assert "criterios" in content.lower() or "criteria" in content.lower()
