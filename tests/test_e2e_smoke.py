"""
M7.0 — End-to-end smoke test.

Simula el flujo principal del founder en una sola sesión:
1. Login con un email del allowlist → recibe token
2. Inicialmente DB vacío (autouse fixture lo limpia)
3. Añade una fuente RSS via POST /sources
4. Lista fuentes — debe estar la nueva
5. Inyecta señales sintéticas (vía storage directo, simula scan)
6. Verifica /signals las devuelve
7. Lista trend-gaps + niche-opportunities — devuelven estructura válida
8. Llama admin/status — todos los agentes presentes
9. Lista runs (vacío al inicio) → POST /gate/run → run aparece en lista
10. Verifica que el digest se genera sin errores

Cero LLM, todo mock_mode. Tiempo objetivo: <10 segundos.
"""
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Fresh TestClient para el módulo e2e."""
    # Garantizar mock_mode
    os.environ.pop("ANTHROPIC_API_KEY", None)
    from orchestrator.api import app
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def auth(client):
    """Login y devuelve headers Bearer."""
    os.environ["ALLOWED_EMAILS"] = "e2e@circles-ai.ai"
    r = client.post("/api/v1/auth/login", json={"email": "e2e@circles-ai.ai"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_e2e_full_journey(client, auth):
    """Flujo completo del founder en mock_mode."""

    # --- 1. Estado inicial: backend up ---
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    health = r.json()
    assert health["mode"] in ("live", "mock")

    # --- 2. Estado inicial: stats vacíos ---
    r = client.get("/api/v1/stats", headers=auth)
    assert r.status_code == 200
    stats0 = r.json()
    assert stats0["signals_total"] == 0
    assert stats0["sources_total"] == 0
    assert stats0["runs_total"] == 0

    # --- 3. Añadir fuente RSS ---
    r = client.post(
        "/api/v1/sources", headers=auth,
        json={"kind": "rss", "target": "https://example.com/feed.xml",
              "name": "Example RSS E2E"},
    )
    assert r.status_code in (200, 201), r.text
    source_id = r.json().get("id") or r.json().get("source_id")
    assert source_id

    # --- 4. Lista fuentes incluye la nueva ---
    r = client.get("/api/v1/sources", headers=auth)
    assert r.status_code == 200
    sources = r.json().get("items", [])
    assert any(s["name"] == "Example RSS E2E" for s in sources)

    # --- 5. Inyectar señales sintéticas (simulando un scan) ---
    from orchestrator.core.storage import signals_store
    signals_store.add(
        source_id=source_id, source_kind="rss",
        theme="Fintech SaaS para PYMEs Ecuador",
        score=0.75, excerpt="Idea sintética para E2E",
        evidence_urls=["https://example.com/article-1"],
        suggested_topic="fintech pymes ecuador",
        item_titles=["Fintech PYMEs"],
    )
    signals_store.add(
        source_id=source_id, source_kind="rss",
        theme="Edtech adultos mayores Brasil",
        score=0.65, excerpt="Otra idea sintética",
        evidence_urls=["https://example.com/article-2"],
        suggested_topic="edtech adultos brasil",
        item_titles=["Edtech adultos"],
    )

    # --- 6. /signals devuelve las 2 ---
    r = client.get("/api/v1/signals?min_score=0.5&limit=20", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 2

    # --- 7a. trend-gaps responde con estructura válida ---
    r = client.get("/api/v1/trend-gaps", headers=auth)
    assert r.status_code == 200
    assert "items" in r.json()

    # --- 7b. niche-opportunities responde con estructura válida ---
    r = client.get("/api/v1/niche-opportunities", headers=auth)
    assert r.status_code == 200
    assert "items" in r.json()

    # --- 7c. signals/stats-by-type funciona ---
    r = client.get("/api/v1/signals/stats-by-type", headers=auth)
    assert r.status_code == 200
    assert r.json()["total"] >= 2

    # --- 8. admin/status: los 13 agentes presentes ---
    r = client.get("/api/v1/admin/status", headers=auth)
    assert r.status_code == 200
    admin = r.json()
    assert len(admin["agents"]) >= 13
    agent_names = {a["name"] for a in admin["agents"]}
    assert "idea_hunter" in agent_names
    assert "trend_gap_analyzer" in agent_names
    assert "multi_agent_consensus" in agent_names

    # --- 9. POST /gate/run crea un run ---
    r = client.post(
        "/api/v1/gate/run",
        json={"topic": "fintech para PYMEs Ecuador E2E test"},
    )
    assert r.status_code == 201, r.text
    run_id = r.json()["run_id"]
    assert run_id

    # --- 10. /runs lista incluye el nuevo ---
    r = client.get("/api/v1/runs?limit=20", headers=auth)
    assert r.status_code == 200
    run_ids = [item["run_id"] for item in r.json()["items"]]
    assert run_id in run_ids

    # --- 11. Digest data + preview funcionan sin error ---
    r = client.get("/api/v1/digest/data", headers=auth)
    assert r.status_code == 200
    digest = r.json()
    assert digest["stats"]["signals_total"] >= 2
    assert digest["stats"]["runs_total"] >= 1

    r = client.get("/api/v1/digest/preview", headers=auth)
    assert r.status_code == 200
    assert "<!DOCTYPE html>" in r.text

    # --- 12. consensus.analyze sintetiza 2 perspectives ---
    r = client.post(
        "/api/v1/consensus/analyze", headers=auth,
        json={
            "decision_question": "¿Promovemos la idea de fintech PYMEs Ecuador?",
            "perspectives": [
                {"source": "trend_gap_analyzer",
                 "text": "Atacar Ecuador primero, USA y Brasil ya validados."},
                {"source": "founder",
                 "text": "Timing parece bueno pero budget ajustado."},
            ],
        },
    )
    assert r.status_code == 200
    consensus = r.json()
    assert 0.0 <= consensus["agreement_score"] <= 1.0
    assert consensus["final_recommendation"]


def test_e2e_health_check_endpoints_all_respond(client):
    """Smoke test minimo de los endpoints públicos críticos."""
    r = client.get("/api/v1/health")
    assert r.status_code == 200

    r = client.get("/api/v1/diagnostic")
    assert r.status_code == 200
    diag = r.json()
    assert "mode" in diag
    assert "features" in diag


def test_e2e_admin_endpoints_require_auth(client):
    """Sin auth, los endpoints sensibles devuelven 401."""
    sensitive = [
        "/api/v1/stats",
        "/api/v1/admin/status",
        "/api/v1/sources",
        "/api/v1/signals",
        "/api/v1/runs",
        "/api/v1/digest/data",
        "/api/v1/digest/preview",
        "/api/v1/trend-gaps",
        "/api/v1/niche-opportunities",
        "/api/v1/signals/stats-by-type",
    ]
    for path in sensitive:
        r = client.get(path)
        assert r.status_code == 401, f"{path} no requiere auth: {r.status_code}"
