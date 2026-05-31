"""
M7.5 — Anti-orphan-endpoints test.

Garantía: cada endpoint registrado en la FastAPI app debe estar mencionado
en al menos un test. Si añadís un endpoint nuevo sin tests, este test lo
detecta y falla en CI.

Cómo decidimos "tiene test":
- Buscamos el path del endpoint (e.g. "/api/v1/runs") en cualquier archivo
  de tests/**.py o tests/api/*.py.
- Match es string-exact-substring después de normalizar `{path_param}` →
  `{`. Esto evita falsos positivos pero también permite tests parametrizados.

Si un endpoint NO debe testearse (caso rarísimo), añadirlo a EXEMPT_PATHS
abajo con un comentario explicando por qué.
"""
from pathlib import Path
from typing import Set


# Endpoints exentos del check. Mantener corto y justificado.
EXEMPT_PATHS: Set[str] = {
    # /openapi.json y /docs son auto-generados por FastAPI, no tests
    # propios. Su existencia se verifica indirectamente via 200 en /docs.
    "/openapi.json",
    "/docs",
    "/redoc",
    "/docs/oauth2-redirect",
}


def _collect_registered_endpoints() -> Set[str]:
    """Lee la app FastAPI y devuelve el set de paths registrados."""
    from orchestrator.api import app
    paths = set()
    for route in app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
    return paths


def _read_all_test_files() -> str:
    """Lee TODO el código de tests/ concatenado para grep."""
    tests_dir = Path(__file__).parent
    chunks = []
    for path in tests_dir.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
    return "\n".join(chunks)


def test_no_orphan_endpoints():
    """Cada endpoint registrado tiene al menos un test que lo menciona."""
    all_endpoints = _collect_registered_endpoints()
    all_test_code = _read_all_test_files()

    orphans = []
    for path in sorted(all_endpoints):
        if path in EXEMPT_PATHS:
            continue
        # Normalizar path params: "/runs/{run_id}" → "/runs/{"
        # para matchear tanto literal como format strings
        normalized = path
        if "{" in path:
            normalized = path.split("{")[0] + "{"

        if normalized not in all_test_code:
            orphans.append(path)

    assert not orphans, (
        f"{len(orphans)} endpoint(s) without any test mention:\n"
        + "\n".join(f"  - {p}" for p in orphans)
        + "\n\nAdd a test that uses these paths, or add to EXEMPT_PATHS with a comment."
    )


def test_exempt_list_is_minimal():
    """Sanity check: la lista de exenciones no crece sin control."""
    assert len(EXEMPT_PATHS) <= 10, (
        f"EXEMPT_PATHS got too big ({len(EXEMPT_PATHS)} entries). "
        "Auditá si están justificadas."
    )


def test_at_least_50_endpoints_registered():
    """Anti-regression: si bajamos drásticamente de endpoints, alguien
    rompió la registración. Floor conservador en 50."""
    all_endpoints = _collect_registered_endpoints()
    # Filtrar paths auto-FastAPI
    user_endpoints = {p for p in all_endpoints if p.startswith("/api/")}
    assert len(user_endpoints) >= 50, (
        f"Sólo {len(user_endpoints)} endpoints /api/* registrados. Esperaba ≥50. "
        f"Lista: {sorted(user_endpoints)}"
    )
