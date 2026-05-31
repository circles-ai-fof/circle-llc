"""
M7.1 — tests del seed script (scripts/seed-example-sources.py).

Validan la estructura del script (lista de fuentes, dry-run, etc.) SIN
hacer requests HTTP reales (eso queda al E2E manual).
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "seed-example-sources.py"


def _load_module():
    """Importa el script como módulo Python (tiene `-` en el nombre así que
    no se puede `import seed-example-sources` directo)."""
    spec = importlib.util.spec_from_file_location("seed_module", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_script_exists():
    assert SCRIPT_PATH.exists(), f"Script no encontrado en {SCRIPT_PATH}"


def test_seed_script_has_example_sources():
    module = _load_module()
    assert hasattr(module, "EXAMPLE_SOURCES")
    sources = module.EXAMPLE_SOURCES
    assert isinstance(sources, list)
    assert len(sources) >= 12, f"Esperaba >=12 fuentes, hay {len(sources)}"


def test_seed_script_covers_all_12_kinds():
    """El script debe cubrir los 12 source kinds soportados."""
    module = _load_module()
    kinds_in_seed = {kind for kind, _target, _name in module.EXAMPLE_SOURCES}
    expected_kinds = {
        "rss", "hn", "reddit", "github_trending", "product_hunt",
        "youtube", "bluesky", "telegram",
        "events", "sec_edgar", "google_trends",
        # "url" es para imports puntuales — no en el seed bulk
    }
    missing = expected_kinds - kinds_in_seed
    assert not missing, f"Kinds sin cubrir: {missing}"


def test_seed_sources_have_valid_target_for_required_kinds():
    """Los kinds que requieren target NO deben tener target vacío."""
    module = _load_module()
    KINDS_NEED_TARGET = {"rss", "reddit", "youtube", "bluesky", "telegram",
                         "events", "sec_edgar", "google_trends"}
    for kind, target, name in module.EXAMPLE_SOURCES:
        if kind in KINDS_NEED_TARGET:
            assert target, f"Kind {kind} en source {name!r} tiene target vacío"


def test_seed_sources_have_unique_names():
    """Nombres no deben duplicarse (la idempotencia depende de eso)."""
    module = _load_module()
    names = [name for _kind, _target, name in module.EXAMPLE_SOURCES]
    assert len(names) == len(set(names)), "Hay nombres duplicados en EXAMPLE_SOURCES"


def test_seed_script_dry_run_does_not_require_token():
    """`--dry-run` sale exit 0 sin BEARER_TOKEN."""
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
    assert "Would add" in result.stdout


def test_seed_script_without_token_fails_clearly():
    """Sin BEARER_TOKEN y sin --dry-run, sale exit 2 con mensaje claro."""
    env = os.environ.copy()
    env.pop("BEARER_TOKEN", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT_PATH)],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 2
    assert "BEARER_TOKEN" in result.stderr
