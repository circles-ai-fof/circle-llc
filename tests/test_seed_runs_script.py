"""
M7.2 — tests del script scripts/seed-example-runs.py.

Validan estructura + dry-run + error handling SIN ejecutar runs reales
(cada run costaría $0.06 en LLM).
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "seed-example-runs.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("seed_runs_module", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_runs_script_exists():
    assert SCRIPT_PATH.exists()


def test_seed_runs_has_example_topics():
    module = _load_module()
    assert hasattr(module, "EXAMPLE_TOPICS")
    assert isinstance(module.EXAMPLE_TOPICS, list)
    assert len(module.EXAMPLE_TOPICS) >= 3
    # Cada topic > 20 chars (no strings vacíos ni "x")
    for t in module.EXAMPLE_TOPICS:
        assert len(t) > 20, f"Topic muy corto: {t!r}"


def test_seed_runs_topics_are_unique():
    """No queremos topics duplicados (idempotency se basa en title)."""
    module = _load_module()
    assert len(module.EXAMPLE_TOPICS) == len(set(module.EXAMPLE_TOPICS))


def test_seed_runs_dry_run_does_not_require_token():
    """--dry-run sale exit 0 sin BEARER_TOKEN ni hacer requests."""
    env = os.environ.copy()
    env.pop("BEARER_TOKEN", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT_PATH), "--dry-run"],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "DRY-RUN" in result.stdout
    assert "Would run" in result.stdout


def test_seed_runs_dry_run_respects_count_flag():
    """--count cambia cuántos topics se listan."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT_PATH), "--dry-run", "--count", "2"],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    # Debería listar exactamente 2 "Would run" lines
    assert result.stdout.count("Would run") == 2


def test_seed_runs_count_clamps_to_topics_available():
    """--count >8 se clampea al número de topics disponibles."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT_PATH), "--dry-run", "--count", "999"],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    module = _load_module()
    expected = len(module.EXAMPLE_TOPICS)
    assert result.stdout.count("Would run") == expected


def test_seed_runs_dry_run_shows_cost_estimate():
    """Dry-run muestra el costo estimado para que el usuario decida."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT_PATH), "--dry-run", "--count", "3"],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert "USD" in result.stdout
    assert "0.18" in result.stdout  # 3 × $0.06
