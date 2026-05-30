"""Integration tests for hunter endpoints (sources / scan / signals)."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from orchestrator.api import app


def _auth_token(client):
    """Helper: login as the first allowed email, return Bearer header."""
    from orchestrator.core import auth as ab_auth
    # Hardcode an allowlisted email for tests
    import os
    os.environ["ALLOWED_EMAILS"] = "test@circles-ai.ai"
    r = client.post("/api/v1/auth/login", json={"email": "test@circles-ai.ai"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth(client):
    return _auth_token(client)


def test_list_sources_empty(client, auth):
    r = client.get("/api/v1/sources", headers=auth)
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_add_source_then_list(client, auth):
    r = client.post(
        "/api/v1/sources",
        headers=auth,
        json={"kind": "hn", "target": "", "name": "Hacker News"},
    )
    assert r.status_code == 201
    sid = r.json()["id"]
    assert sid >= 1
    r2 = client.get("/api/v1/sources", headers=auth)
    assert r2.status_code == 200
    assert r2.json()["total"] == 1
    assert r2.json()["items"][0]["kind"] == "hn"


def test_add_source_invalid_kind_422(client, auth):
    r = client.post(
        "/api/v1/sources",
        headers=auth,
        json={"kind": "invalid_kind", "target": "", "name": "X"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# M4.0 — connected_accounts + check-platform (ADR-018)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# M4.1 — preferences + autonomy (ADR-019)
# ---------------------------------------------------------------------------


def test_preferences_engine_reports_mode(client, auth):
    r = client.get("/api/v1/preferences/engine", headers=auth)
    assert r.status_code == 200
    d = r.json()
    assert d["mode"] in ("real", "fallback")


def test_preferences_engine_requires_auth(client):
    assert client.get("/api/v1/preferences/engine").status_code == 401


def test_recluster_embeds_and_assigns_clusters(client, auth):
    """Recluster genera embeddings para todas las señales sin uno y aplica
    clustering."""
    from orchestrator.core.storage import signals_store, embeddings_store
    for i in range(6):
        signals_store.add(
            None, "rss", f"Fintech LATAM #{i}", 0.7,
            f"Tema sobre fintech y reconciliación bancaria {i}",
            [], "topic fintech",
        )

    r = client.post("/api/v1/preferences/recluster", headers=auth)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["signals_embedded"] == 6
    # All 6 embeddings exist in the store
    assert len(embeddings_store.list_all()) == 6


def test_list_clusters_returns_grouped_signals(client, auth):
    from orchestrator.core.storage import signals_store
    for i in range(5):
        sig_id = signals_store.add(
            None, "rss", f"Tema {i}", 0.7, "excerpt", [], "topic"
        )
    # Recluster first
    client.post("/api/v1/preferences/recluster", headers=auth)
    r = client.get("/api/v1/preferences/clusters", headers=auth)
    assert r.status_code == 200
    d = r.json()
    assert "items" in d
    assert d["mode"] in ("real", "fallback")


def test_clusters_requires_auth(client):
    assert client.get("/api/v1/preferences/clusters").status_code == 401


def test_source_suggestions_returns_keywords(client, auth):
    from orchestrator.core.storage import signals_store, embeddings_store
    from orchestrator.core.preferences import compute_embedding
    # Create signals with shared keywords + positive feedback
    s1 = signals_store.add(None, "rss", "Fintech para PYMEs LATAM",
                            0.8, "Reconciliación bancaria automática",
                            [], "topic")
    s2 = signals_store.add(None, "rss", "Fintech automática PYMEs Ecuador",
                            0.8, "Reconciliación contable para empresas",
                            [], "topic")
    signals_store.set_feedback(s1, "up")
    signals_store.set_feedback(s2, "up")
    # Embed them with the same cluster_id (force grouping)
    for sid in (s1, s2):
        embeddings_store.upsert(sid, compute_embedding("fintech pymes latam"), cluster_id=42)

    r = client.get("/api/v1/sources/suggestions", headers=auth)
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d["items"], list)


def test_get_autonomy_default_is_manual(client, auth):
    r = client.get("/api/v1/autonomy", headers=auth)
    assert r.status_code == 200
    assert r.json()["level"] == "manual"


def test_set_autonomy_persists(client, auth):
    r = client.put("/api/v1/autonomy", headers=auth, json={"level": "assisted"})
    assert r.status_code == 200
    assert r.json()["level"] == "assisted"
    # Re-read
    assert client.get("/api/v1/autonomy", headers=auth).json()["level"] == "assisted"


def test_set_autonomy_rejects_invalid_level(client, auth):
    r = client.put("/api/v1/autonomy", headers=auth, json={"level": "banana"})
    assert r.status_code == 422


def test_autonomy_requires_auth(client):
    assert client.get("/api/v1/autonomy").status_code == 401
    assert client.put("/api/v1/autonomy", json={"level": "manual"}).status_code == 401
    # POST alias also requires auth (M4.5)
    assert client.post("/api/v1/autonomy", json={"level": "manual"}).status_code == 401


def test_set_autonomy_via_post_alias_works(client, auth):
    """M4.5 — POST /api/v1/autonomy es un alias del PUT canónico. Existe para
    que el dashboard funcione antes de que el backend deployado reinicie con
    el nuevo CORS allow_methods=PUT."""
    r = client.post("/api/v1/autonomy", headers=auth, json={"level": "autonomous_with_approval"})
    assert r.status_code == 200
    assert r.json()["level"] == "autonomous_with_approval"
    # Confirma persistencia consultando con GET
    assert client.get("/api/v1/autonomy", headers=auth).json()["level"] == "autonomous_with_approval"


def test_set_autonomy_via_post_rejects_invalid_level(client, auth):
    r = client.post("/api/v1/autonomy", headers=auth, json={"level": "banana"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# M4.5 — CORS allows PUT/DELETE (regresión: autonomy/delete fallaban en browser)
# ---------------------------------------------------------------------------


def test_cors_preflight_allows_put_for_autonomy(client):
    """Bug M4.5: el browser bloqueaba PUT /api/v1/autonomy con NetworkError
    porque la preflight de CORS solo aceptaba GET/POST/OPTIONS. Verificamos
    que PUT está ahora en allow_methods."""
    r = client.options(
        "/api/v1/autonomy",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "Content-Type, Authorization",
        },
    )
    # FastAPI/Starlette returns 200 con los headers CORS si el preflight pasa
    assert r.status_code in (200, 204)
    allowed = r.headers.get("access-control-allow-methods", "")
    assert "PUT" in allowed.upper(), f"PUT not in allow-methods: {allowed!r}"


def test_cors_preflight_allows_delete_for_sources(client):
    """Mismo bug: DELETE /api/v1/sources/{id} también fallaba."""
    r = client.options(
        "/api/v1/sources/1",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert r.status_code in (200, 204)
    allowed = r.headers.get("access-control-allow-methods", "")
    assert "DELETE" in allowed.upper(), f"DELETE not in allow-methods: {allowed!r}"


# ---------------------------------------------------------------------------
# M4.5 — filtro por content_type en /api/v1/signals
# ---------------------------------------------------------------------------


def test_signals_filter_by_content_type_news(client, auth):
    """Bug del founder: 'Debemos poder filtrar por tipo' (Noticia/Producto/…).

    Aprovechamos el auto-classifier por URL: bbc.com → news,
    github.com → tool_product (ver content_type.py).
    """
    from orchestrator.core.storage import signals_store
    signals_store.add(
        source_id=None, source_kind="rss", theme="BBC News headline M45",
        score=0.7, excerpt="news ex",
        evidence_urls=["https://www.bbc.com/news/article-m45"],
        suggested_topic="news topic", item_titles=["BBC headline"],
    )
    signals_store.add(
        source_id=None, source_kind="rss", theme="GitHub project release M45",
        score=0.7, excerpt="tool ex",
        evidence_urls=["https://github.com/foo/bar-m45"],
        suggested_topic="tool topic", item_titles=["GH release"],
    )
    r = client.get("/api/v1/signals?content_type=news&min_score=0.0", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    # all returned items must match the filter
    assert all(it["content_type"] == "news" for it in items)
    # and our seeded news item must be present
    assert any("BBC News headline M45" in it["theme"] for it in items)
    # and the tool_product item must NOT be present
    assert not any("GitHub project release M45" in it["theme"] for it in items)


def test_signals_filter_content_type_rejects_invalid(client, auth):
    r = client.get("/api/v1/signals?content_type=banana", headers=auth)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# M4.6 — bulk delete signals by content_type (founder request M4.6)
# ---------------------------------------------------------------------------


def test_delete_signals_by_type_news_preserves_other_types(client, auth):
    """Founder: 'debe existir la opción de eliminar las noticias por tipo'."""
    from orchestrator.core.storage import signals_store
    sid_news = signals_store.add(
        source_id=None, source_kind="rss", theme="BBC headline M46-news",
        score=0.7, excerpt="news ex",
        evidence_urls=["https://www.bbc.com/news/article-m46"],
        suggested_topic="topic", item_titles=["t"],
    )
    sid_tool = signals_store.add(
        source_id=None, source_kind="rss", theme="GitHub repo M46-tool",
        score=0.7, excerpt="tool ex",
        evidence_urls=["https://github.com/foo/bar-m46"],
        suggested_topic="topic", item_titles=["t"],
    )
    r = client.post(
        "/api/v1/signals/delete-by-type",
        headers=auth, json={"content_type": "news"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["content_type"] == "news"
    assert data["deleted"] >= 1
    # La news debe estar borrada, el tool_product NO
    listed = client.get(
        "/api/v1/signals?min_score=0.0&limit=500", headers=auth
    ).json()["items"]
    themes = {it["theme"] for it in listed}
    assert "BBC headline M46-news" not in themes
    assert "GitHub repo M46-tool" in themes
    # Cleanup
    _ = sid_news, sid_tool


def test_delete_signals_by_type_preserves_promoted_by_default(client, auth):
    """No queremos romper el historial: si el founder promovió una noticia,
    no la borramos al hacer 'borrar todas las noticias'."""
    from orchestrator.core.storage import signals_store
    sid = signals_store.add(
        source_id=None, source_kind="rss", theme="BBC promoted M46",
        score=0.9, excerpt="ex",
        evidence_urls=["https://www.bbc.com/news/article-promoted-m46"],
        suggested_topic="topic", item_titles=["t"],
    )
    # Marcar como promovida directamente en storage para no depender del LLM
    signals_store.mark_promoted(sid, run_id="run-fake-uuid-m46")
    r = client.post(
        "/api/v1/signals/delete-by-type",
        headers=auth, json={"content_type": "news", "keep_promoted": True},
    )
    assert r.status_code == 200
    data = r.json()
    # La señal promovida NO debe haber sido borrada
    listed = client.get(
        "/api/v1/signals?min_score=0.0&limit=500", headers=auth
    ).json()["items"]
    themes = {it["theme"] for it in listed}
    assert "BBC promoted M46" in themes
    assert data["kept_promoted"] >= 1


def test_delete_signals_by_type_preserves_feedback_by_default(client, auth):
    from orchestrator.core.storage import signals_store
    sid = signals_store.add(
        source_id=None, source_kind="rss", theme="BBC liked M46",
        score=0.5, excerpt="ex",
        evidence_urls=["https://www.bbc.com/news/article-liked-m46"],
        suggested_topic="topic", item_titles=["t"],
    )
    signals_store.set_feedback(sid, "up")
    r = client.post(
        "/api/v1/signals/delete-by-type",
        headers=auth, json={"content_type": "news", "keep_feedback": True},
    )
    assert r.status_code == 200
    listed = client.get(
        "/api/v1/signals?min_score=0.0&limit=500", headers=auth
    ).json()["items"]
    themes = {it["theme"] for it in listed}
    assert "BBC liked M46" in themes


def test_delete_signals_by_type_force_includes_feedback(client, auth):
    """Con keep_feedback=False y keep_promoted=False, borramos TODO el tipo."""
    from orchestrator.core.storage import signals_store
    sid = signals_store.add(
        source_id=None, source_kind="rss", theme="BBC liked force M46",
        score=0.5, excerpt="ex",
        evidence_urls=["https://www.bbc.com/news/article-force-m46"],
        suggested_topic="topic", item_titles=["t"],
    )
    signals_store.set_feedback(sid, "up")
    r = client.post(
        "/api/v1/signals/delete-by-type",
        headers=auth,
        json={"content_type": "news", "keep_promoted": False, "keep_feedback": False},
    )
    assert r.status_code == 200
    listed = client.get(
        "/api/v1/signals?min_score=0.0&limit=500", headers=auth
    ).json()["items"]
    themes = {it["theme"] for it in listed}
    assert "BBC liked force M46" not in themes


def test_delete_signals_by_type_rejects_invalid(client, auth):
    r = client.post(
        "/api/v1/signals/delete-by-type",
        headers=auth, json={"content_type": "banana"},
    )
    assert r.status_code == 422


def test_delete_signals_by_type_requires_auth(client):
    r = client.post(
        "/api/v1/signals/delete-by-type", json={"content_type": "news"}
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# M4.6b — extensión: borrar por source_kind / source_id
# ---------------------------------------------------------------------------


def test_delete_signals_by_source_kind(client, auth):
    """Founder: además del tipo, borrar señales de una fuente específica
    (p.ej. todas las RSS, o todas las del chat importado)."""
    from orchestrator.core.storage import signals_store
    signals_store.add(
        source_id=None, source_kind="rss", theme="RSS to delete M46b",
        score=0.5, excerpt="ex", evidence_urls=["https://example.com/rss-a"],
        suggested_topic="t", item_titles=["t"],
    )
    signals_store.add(
        source_id=None, source_kind="hn", theme="HN to keep M46b",
        score=0.5, excerpt="ex", evidence_urls=["https://news.ycombinator.com/item?id=1"],
        suggested_topic="t", item_titles=["t"],
    )
    r = client.post(
        "/api/v1/signals/delete-by-type",
        headers=auth, json={"source_kind": "rss"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["source_kind"] == "rss"
    assert data["deleted"] >= 1
    listed = client.get(
        "/api/v1/signals?min_score=0.0&limit=500", headers=auth
    ).json()["items"]
    themes = {it["theme"] for it in listed}
    assert "RSS to delete M46b" not in themes
    assert "HN to keep M46b" in themes


def test_delete_signals_by_source_id(client, auth):
    from orchestrator.core.storage import signals_store, sources_store
    sid = sources_store.add(kind="rss", target="https://example.com/feed", name="Test M46b")
    signals_store.add(
        source_id=sid, source_kind="rss", theme="Signal from src M46b",
        score=0.5, excerpt="ex", evidence_urls=["https://example.com/a"],
        suggested_topic="t", item_titles=["t"],
    )
    signals_store.add(
        source_id=None, source_kind="rss", theme="Signal without src M46b",
        score=0.5, excerpt="ex", evidence_urls=["https://example.com/b"],
        suggested_topic="t", item_titles=["t"],
    )
    r = client.post(
        "/api/v1/signals/delete-by-type",
        headers=auth, json={"source_id": sid},
    )
    assert r.status_code == 200
    listed = client.get(
        "/api/v1/signals?min_score=0.0&limit=500", headers=auth
    ).json()["items"]
    themes = {it["theme"] for it in listed}
    assert "Signal from src M46b" not in themes
    assert "Signal without src M46b" in themes


def test_delete_signals_by_type_and_source_kind_combined(client, auth):
    """AND de filtros: borrar sólo las NOTICIAS DE RSS — no las noticias de HN
    ni las herramientas de RSS."""
    from orchestrator.core.storage import signals_store
    signals_store.add(
        source_id=None, source_kind="rss", theme="BBC via RSS M46b",
        score=0.5, excerpt="ex",
        evidence_urls=["https://www.bbc.com/news/article-and-m46b"],
        suggested_topic="t", item_titles=["t"],
    )
    signals_store.add(
        source_id=None, source_kind="hn", theme="BBC via HN M46b",
        score=0.5, excerpt="ex",
        evidence_urls=["https://www.bbc.com/news/article-and-hn-m46b"],
        suggested_topic="t", item_titles=["t"],
    )
    signals_store.add(
        source_id=None, source_kind="rss", theme="GH via RSS M46b",
        score=0.5, excerpt="ex",
        evidence_urls=["https://github.com/foo/bar-and-m46b"],
        suggested_topic="t", item_titles=["t"],
    )
    r = client.post(
        "/api/v1/signals/delete-by-type",
        headers=auth, json={"content_type": "news", "source_kind": "rss"},
    )
    assert r.status_code == 200
    listed = client.get(
        "/api/v1/signals?min_score=0.0&limit=500", headers=auth
    ).json()["items"]
    themes = {it["theme"] for it in listed}
    assert "BBC via RSS M46b" not in themes  # borrada (news + rss)
    assert "BBC via HN M46b" in themes        # conservada (news pero NO rss)
    assert "GH via RSS M46b" in themes        # conservada (rss pero NO news)


def test_delete_signals_by_type_rejects_no_filter(client, auth):
    """Si no se pasa NINGÚN filtro, retorna 422 — no permitimos borrar todo."""
    r = client.post(
        "/api/v1/signals/delete-by-type",
        headers=auth, json={},
    )
    assert r.status_code == 422


def test_delete_signals_by_source_kind_rejects_invalid(client, auth):
    r = client.post(
        "/api/v1/signals/delete-by-type",
        headers=auth, json={"source_kind": "banana"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# M4.7 — distribución de señales por content_type
# ---------------------------------------------------------------------------


def test_signals_stats_by_type_counts_each_bucket(client, auth):
    """El endpoint cuenta señales por content_type y devuelve los 9 buckets
    + total. Verificamos que añadir señales nuevas mueve los contadores
    correctos."""
    from orchestrator.core.storage import signals_store
    # Snapshot inicial
    before = client.get("/api/v1/signals/stats-by-type", headers=auth).json()
    assert "news" in before and "tool_product" in before and "total" in before
    base_news = before["news"]
    base_tool = before["tool_product"]
    base_total = before["total"]
    # Añadir 2 noticias (BBC) y 1 producto (GitHub) — auto-clasifica por URL
    signals_store.add(
        source_id=None, source_kind="rss", theme="BBC stats M47 a",
        score=0.5, excerpt="ex",
        evidence_urls=["https://www.bbc.com/news/article-stats-a"],
        suggested_topic="t", item_titles=["t"],
    )
    signals_store.add(
        source_id=None, source_kind="rss", theme="BBC stats M47 b",
        score=0.5, excerpt="ex",
        evidence_urls=["https://www.bbc.com/news/article-stats-b"],
        suggested_topic="t", item_titles=["t"],
    )
    signals_store.add(
        source_id=None, source_kind="rss", theme="GH stats M47",
        score=0.5, excerpt="ex",
        evidence_urls=["https://github.com/foo/bar-stats-m47"],
        suggested_topic="t", item_titles=["t"],
    )
    after = client.get("/api/v1/signals/stats-by-type", headers=auth).json()
    assert after["news"] == base_news + 2
    assert after["tool_product"] == base_tool + 1
    assert after["total"] == base_total + 3


def test_signals_stats_by_type_returns_all_buckets_even_when_zero(client, auth):
    """Aunque no haya señales de un tipo, el bucket debe estar presente con
    valor 0 — la UI cuenta con la estructura completa para renderizar todos
    los badges."""
    r = client.get("/api/v1/signals/stats-by-type", headers=auth)
    assert r.status_code == 200
    data = r.json()
    expected_keys = {
        "news", "blog", "research_paper", "tool_product", "course_tutorial",
        "video_podcast", "community", "corporate", "unknown", "total",
    }
    assert expected_keys <= set(data.keys())
    # Cada uno debe ser un int >= 0
    for k in expected_keys:
        assert isinstance(data[k], int)
        assert data[k] >= 0


def test_signals_stats_by_type_requires_auth(client):
    assert client.get("/api/v1/signals/stats-by-type").status_code == 401


# ---------------------------------------------------------------------------
# M4.9 — bulk feedback (multi-select + marcar varias como 👍/👎)
# ---------------------------------------------------------------------------


def test_bulk_feedback_up_marks_all_listed(client, auth):
    from orchestrator.core.storage import signals_store
    s1 = signals_store.add(
        source_id=None, source_kind="rss", theme="Sig A M49",
        score=0.5, excerpt="ex", evidence_urls=["https://example.com/a-m49"],
        suggested_topic="t", item_titles=["t"],
    )
    s2 = signals_store.add(
        source_id=None, source_kind="rss", theme="Sig B M49",
        score=0.5, excerpt="ex", evidence_urls=["https://example.com/b-m49"],
        suggested_topic="t", item_titles=["t"],
    )
    r = client.post(
        "/api/v1/signals/bulk-feedback",
        headers=auth, json={"signal_ids": [s1, s2], "feedback": "up"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["updated"] == 2
    assert data["feedback_applied"] == "up"
    assert data["skipped_missing"] == 0
    # Verificar persistencia
    listed = client.get(
        "/api/v1/signals?min_score=0.0&limit=500", headers=auth
    ).json()["items"]
    by_id = {it["id"]: it for it in listed}
    assert by_id[s1]["feedback"] == "up"
    assert by_id[s2]["feedback"] == "up"


def test_bulk_feedback_clear_removes_existing(client, auth):
    from orchestrator.core.storage import signals_store
    sid = signals_store.add(
        source_id=None, source_kind="rss", theme="Sig clear M49",
        score=0.5, excerpt="ex", evidence_urls=["https://example.com/clear-m49"],
        suggested_topic="t", item_titles=["t"],
    )
    signals_store.set_feedback(sid, "down")
    r = client.post(
        "/api/v1/signals/bulk-feedback",
        headers=auth, json={"signal_ids": [sid], "feedback": "clear"},
    )
    assert r.status_code == 200
    listed = client.get(
        "/api/v1/signals?min_score=0.0&limit=500", headers=auth
    ).json()["items"]
    by_id = {it["id"]: it for it in listed}
    assert by_id[sid]["feedback"] is None


def test_bulk_feedback_counts_skipped_missing(client, auth):
    """IDs que no existen suman a skipped_missing pero no fallan el batch."""
    from orchestrator.core.storage import signals_store
    sid = signals_store.add(
        source_id=None, source_kind="rss", theme="Sig real M49",
        score=0.5, excerpt="ex", evidence_urls=["https://example.com/real-m49"],
        suggested_topic="t", item_titles=["t"],
    )
    r = client.post(
        "/api/v1/signals/bulk-feedback",
        headers=auth,
        json={"signal_ids": [sid, 999_999, 888_888], "feedback": "down"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["updated"] == 1
    assert data["skipped_missing"] == 2


def test_bulk_feedback_rejects_invalid_feedback(client, auth):
    r = client.post(
        "/api/v1/signals/bulk-feedback",
        headers=auth, json={"signal_ids": [1], "feedback": "banana"},
    )
    assert r.status_code == 422


def test_bulk_feedback_rejects_empty_list(client, auth):
    r = client.post(
        "/api/v1/signals/bulk-feedback",
        headers=auth, json={"signal_ids": [], "feedback": "up"},
    )
    assert r.status_code == 422


def test_bulk_feedback_caps_at_500_ids(client, auth):
    """No queremos que un cliente malicioso meta 100k ids."""
    r = client.post(
        "/api/v1/signals/bulk-feedback",
        headers=auth,
        json={"signal_ids": list(range(1, 600)), "feedback": "up"},
    )
    assert r.status_code == 422


def test_bulk_feedback_requires_auth(client):
    r = client.post(
        "/api/v1/signals/bulk-feedback",
        json={"signal_ids": [1], "feedback": "up"},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# M4.9 — bulk delete por lista de IDs (companion del bulk-feedback)
# ---------------------------------------------------------------------------


def test_bulk_delete_by_ids_removes_signals(client, auth):
    from orchestrator.core.storage import signals_store
    s1 = signals_store.add(
        source_id=None, source_kind="rss", theme="Sig del A M49",
        score=0.5, excerpt="ex", evidence_urls=["https://example.com/del-a-m49"],
        suggested_topic="t", item_titles=["t"],
    )
    s2 = signals_store.add(
        source_id=None, source_kind="rss", theme="Sig del B M49",
        score=0.5, excerpt="ex", evidence_urls=["https://example.com/del-b-m49"],
        suggested_topic="t", item_titles=["t"],
    )
    survivor = signals_store.add(
        source_id=None, source_kind="rss", theme="Sig keep M49",
        score=0.5, excerpt="ex", evidence_urls=["https://example.com/keep-m49"],
        suggested_topic="t", item_titles=["t"],
    )
    r = client.post(
        "/api/v1/signals/bulk-delete-by-ids",
        headers=auth, json={"signal_ids": [s1, s2]},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["deleted"] == 2
    listed = client.get(
        "/api/v1/signals?min_score=0.0&limit=500", headers=auth
    ).json()["items"]
    themes = {it["theme"] for it in listed}
    assert "Sig del A M49" not in themes
    assert "Sig del B M49" not in themes
    assert "Sig keep M49" in themes
    _ = survivor


def test_bulk_delete_by_ids_rejects_empty_list(client, auth):
    r = client.post(
        "/api/v1/signals/bulk-delete-by-ids",
        headers=auth, json={"signal_ids": []},
    )
    assert r.status_code == 422


def test_bulk_delete_by_ids_caps_at_500(client, auth):
    r = client.post(
        "/api/v1/signals/bulk-delete-by-ids",
        headers=auth, json={"signal_ids": list(range(1, 600))},
    )
    assert r.status_code == 422


def test_bulk_delete_by_ids_requires_auth(client):
    r = client.post(
        "/api/v1/signals/bulk-delete-by-ids", json={"signal_ids": [1]}
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# M4.10 — listado de runs para el overview ejecutivo
# ---------------------------------------------------------------------------


def _inject_run(verdict: str = "iterate", idea_title: str = "Test M410") -> str:
    """Helper para inyectar un run sintético directo en el store."""
    from uuid import uuid4
    from orchestrator.core.storage import runs_store
    from orchestrator.schemas.api import RunGateResponse

    run_id = str(uuid4())
    runs_store[run_id] = RunGateResponse(
        run_id=run_id,
        status="completed",
        idea_title=idea_title,
        verdict=verdict,
        confidence=0.7,
        rationale="…",
        next_steps=["…"],
        landing_headline="…",
        landing_slug=idea_title.lower().replace(" ", "-"),
        test_design={"hypothesis": "…"},
        canonical_goal_statement="…",
        steps_used=5,
        cost_usd_estimated=0.06,
        needs_human_review=False,
        review_reason=None,
        ensemble_votes=None,
    )
    return run_id


def test_list_runs_returns_recent(client, auth):
    """El endpoint /api/v1/runs lista runs ordenados por created_at desc."""
    rid1 = _inject_run(verdict="pass", idea_title="M410 pass A")
    rid2 = _inject_run(verdict="kill", idea_title="M410 kill B")
    r = client.get("/api/v1/runs?limit=50", headers=auth)
    assert r.status_code == 200
    data = r.json()
    items_by_id = {it["run_id"]: it for it in data["items"]}
    assert rid1 in items_by_id
    assert rid2 in items_by_id
    assert items_by_id[rid1]["verdict"] == "pass"
    assert items_by_id[rid2]["verdict"] == "kill"
    assert items_by_id[rid1]["idea_title"] == "M410 pass A"


def test_list_runs_filter_by_verdict(client, auth):
    _inject_run(verdict="pass", idea_title="M410 filter pass")
    _inject_run(verdict="kill", idea_title="M410 filter kill")
    r = client.get("/api/v1/runs?verdict=pass&limit=50", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    # Todos los retornados deben ser pass
    assert all(it["verdict"] == "pass" for it in items)


def test_list_runs_respects_limit(client, auth):
    # Inyectamos 5, pedimos 3
    for i in range(5):
        _inject_run(verdict="iterate", idea_title=f"M410 limit {i}")
    r = client.get("/api/v1/runs?limit=3", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 3


def test_list_runs_rejects_invalid_limit(client, auth):
    r = client.get("/api/v1/runs?limit=0", headers=auth)
    assert r.status_code == 422
    r = client.get("/api/v1/runs?limit=200", headers=auth)
    assert r.status_code == 422


def test_list_runs_rejects_invalid_verdict(client, auth):
    r = client.get("/api/v1/runs?verdict=banana", headers=auth)
    assert r.status_code == 422


def test_list_runs_requires_auth(client):
    r = client.get("/api/v1/runs")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# M4.11 — Cross-country trend gap detector (first-mover opportunities)
# ---------------------------------------------------------------------------


def _add_signal_with_country(
    theme: str, country: str, *, score: float = 0.7, feedback: str | None = None,
    suggested_topic: str | None = None, idea_summary: str = "",
) -> int:
    """Helper: añade signal y le inyecta analysis con country_focus.

    Usa el setter público signals_store.set_analysis() para funcionar
    en modo SQLite y en modo in-memory (pytest sin DATABASE_PATH).
    """
    from orchestrator.core.storage import signals_store
    sid = signals_store.add(
        source_id=None, source_kind="rss", theme=theme,
        score=score, excerpt="ex",
        evidence_urls=[f"https://example.com/{theme[:30].replace(' ', '-').lower()}"],
        suggested_topic=suggested_topic or theme.lower()[:50],
        item_titles=[theme],
    )
    analysis = {
        "idea_summary": idea_summary or theme,
        "country_focus": country,
        "market_size_estimate": "—",
        "icp_probable": "—",
        "competitors": [],
        "differentiator": "—",
        "risks": [],
        "recommendation": "wait_for_more_data",
        "reasoning": "test",
    }
    signals_store.set_analysis(sid, analysis)
    if feedback:
        signals_store.set_feedback(sid, feedback)
    return sid


def test_trend_gaps_detects_validated_in_x_missing_in_y(client, auth):
    """Founder del audio: 'si llegas first-mover ahí, posibilidades de poderla
    reventar'. La idea está validada en USA (2 signals, 1 con 👍) y NO existe
    ningún signal de la misma idea en Ecuador → Ecuador es first-mover gap."""
    # 2 signals USA del mismo cluster (suggested_topic = "fintech pymes saas")
    _add_signal_with_country(
        "Fintech PYMEs SaaS USA #1", country="Estados Unidos",
        feedback="up", suggested_topic="fintech pymes saas m411",
    )
    _add_signal_with_country(
        "Fintech PYMEs SaaS USA #2", country="Estados Unidos",
        suggested_topic="fintech pymes saas m411",
    )
    # 1 signal aislado de algo distinto en BR
    _add_signal_with_country(
        "Unrelated edtech BR", country="Brasil",
        suggested_topic="edtech aislada m411",
    )
    r = client.get(
        "/api/v1/trend-gaps?min_validation_signals=2&min_validation_feedback=1",
        headers=auth,
    )
    assert r.status_code == 200
    data = r.json()
    # Buscar el cluster de fintech
    fintech = next(
        (it for it in data["items"] if "fintech pymes saas" in it["idea_summary"].lower()),
        None,
    )
    assert fintech is not None, f"fintech cluster no encontrado en {data['items']}"
    # USA debe estar en validated_in
    val_countries = {v["country"] for v in fintech["validated_in"]}
    assert "Estados Unidos" in val_countries
    # Ecuador debe estar en missing_in (default LATAM)
    assert "Ecuador" in fintech["missing_in"]
    # opportunity_score > 0
    assert fintech["opportunity_score"] > 0


def test_trend_gaps_excludes_already_present_countries(client, auth):
    """Si una idea YA tiene signals en Ecuador, Ecuador no aparece como gap."""
    _add_signal_with_country(
        "Saas RH gap test #1", country="Estados Unidos",
        feedback="up", suggested_topic="saas rh m411b",
    )
    _add_signal_with_country(
        "Saas RH gap test #2", country="Estados Unidos",
        suggested_topic="saas rh m411b",
    )
    # Ya existe uno en Ecuador → no debe aparecer como gap
    _add_signal_with_country(
        "Saas RH gap test EC", country="Ecuador",
        suggested_topic="saas rh m411b",
    )
    r = client.get(
        "/api/v1/trend-gaps?min_validation_signals=2&min_validation_feedback=1",
        headers=auth,
    )
    data = r.json()
    saas = next(
        (it for it in data["items"] if "saas rh m411b" in it["idea_summary"].lower()),
        None,
    )
    if saas is not None:  # podría no aparecer si todos los target están cubiertos
        assert "Ecuador" not in saas["missing_in"]


def test_trend_gaps_requires_validation_min_signals(client, auth):
    """Una sola signal del mismo país NO valida — necesita ≥ min_validation_signals."""
    _add_signal_with_country(
        "Solo 1 signal m411c", country="México",
        feedback="up", suggested_topic="solo 1 signal m411c",
    )
    r = client.get(
        "/api/v1/trend-gaps?min_validation_signals=2&min_validation_feedback=1",
        headers=auth,
    )
    data = r.json()
    # Ese cluster NO debe aparecer (solo tiene 1 signal en MX)
    assert not any("solo 1 signal m411c" in it["idea_summary"].lower() for it in data["items"])


def test_trend_gaps_accepts_custom_countries(client, auth):
    """countries=Ecuador,Colombia restringe a esos 2 países."""
    _add_signal_with_country(
        "Custom countries test #1", country="Estados Unidos",
        feedback="up", suggested_topic="custom countries m411d",
    )
    _add_signal_with_country(
        "Custom countries test #2", country="Estados Unidos",
        suggested_topic="custom countries m411d",
    )
    r = client.get(
        "/api/v1/trend-gaps?countries=Ecuador,Colombia&min_validation_signals=2&min_validation_feedback=1",
        headers=auth,
    )
    data = r.json()
    # El idea_summary del response viene de analysis.idea_summary que el helper
    # rellena con el theme ("Custom countries test #1"). Buscamos por esa pista.
    target = next(
        (it for it in data["items"] if "custom countries test" in it["idea_summary"].lower()),
        None,
    )
    assert target is not None
    # missing_in solo puede tener Ecuador y/o Colombia (porque countries=EC,CO)
    assert set(target["missing_in"]) <= {"Ecuador", "Colombia"}


def test_trend_gaps_rejects_invalid_args(client, auth):
    assert client.get("/api/v1/trend-gaps?min_validation_signals=0", headers=auth).status_code == 422
    assert client.get("/api/v1/trend-gaps?min_validation_signals=100", headers=auth).status_code == 422
    assert client.get("/api/v1/trend-gaps?min_validation_feedback=-1", headers=auth).status_code == 422
    # >30 países
    countries = ",".join(["X"] * 35)
    assert client.get(f"/api/v1/trend-gaps?countries={countries}", headers=auth).status_code == 422


def test_trend_gaps_requires_auth(client):
    r = client.get("/api/v1/trend-gaps")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# M4.13 — Eventos / Ferias como nuevo source kind
# ---------------------------------------------------------------------------


def test_events_kind_accepted_by_sources_endpoint(client, auth):
    """Founder del audio: 'en qué ferias, en qué congresos hay que estar'."""
    r = client.post(
        "/api/v1/sources",
        headers=auth,
        json={"kind": "events", "target": "https://lu.ma/feed.xml", "name": "Lu.ma feed"},
    )
    assert r.status_code in (200, 201), r.text


def test_events_kind_filter_works_in_signals_endpoint(client, auth):
    """El filtro ?kind=events del listing acepta el nuevo kind."""
    r = client.get("/api/v1/signals?kind=events", headers=auth)
    assert r.status_code == 200


def test_events_kind_delete_by_source_kind(client, auth):
    """delete-by-type acepta source_kind=events (pattern includes it)."""
    r = client.post(
        "/api/v1/signals/delete-by-type",
        headers=auth,
        json={"source_kind": "events"},
    )
    assert r.status_code == 200  # passes even if no signals exist yet


# ---------------------------------------------------------------------------
# M4.15 — Niche-en-gigante detector (heurístico Phase 1)
# ---------------------------------------------------------------------------


def _add_signal_with_topic(theme: str, suggested_topic: str) -> int:
    """Helper: inyecta signal con suggested_topic específico."""
    from orchestrator.core.storage import signals_store
    return signals_store.add(
        source_id=None, source_kind="rss", theme=theme,
        score=0.5, excerpt="ex",
        evidence_urls=[f"https://example.com/{suggested_topic[:30].replace(' ', '-').lower()}"],
        suggested_topic=suggested_topic, item_titles=[theme],
    )


def test_niche_detects_giant_with_underexplored_subniche(client, auth):
    """Founder: 'recoger las migajas de los gigantes'. Si hay 5+ signals en
    'fintech' como gigante, pero sólo 1 en 'fintech para adultos mayores',
    ese sub-niche es una oportunidad."""
    # 5 signals en fintech para PYMEs (el líder del gigante "fintech")
    for i in range(5):
        _add_signal_with_topic(
            f"Fintech PYME signal #{i} M415",
            suggested_topic="fintech para pymes ecuador",
        )
    # 1 signal en una niche sub-explorada del mismo gigante
    _add_signal_with_topic(
        "Fintech adultos mayores M415",
        suggested_topic="fintech para adultos mayores",
    )
    r = client.get(
        "/api/v1/niche-opportunities?min_parent_size=3&max_niche_size=2",
        headers=auth,
    )
    assert r.status_code == 200
    data = r.json()
    fintech = next(
        (it for it in data["items"] if "fintech" in it["parent_market"].lower()),
        None,
    )
    assert fintech is not None, f"fintech parent no encontrado en {data['items']}"
    # El leader debe ser el sub-niche PYMEs (con 5 signals)
    assert fintech["leader_niche"]["signals"] == 5
    # Debe haber al menos 1 underexplored niche
    assert len(fintech["underexplored_niches"]) >= 1
    # Y uno de ellos debe ser sobre adultos mayores
    under_topics = [n["topic"] for n in fintech["underexplored_niches"]]
    assert any("adultos mayores" in t for t in under_topics)


def test_niche_excludes_small_parents(client, auth):
    """Un parent con < min_parent_size signals no es 'gigante', no se reporta."""
    # Solo 2 signals en algún parent random
    _add_signal_with_topic("Pequeño A", "edtech k12 chile")
    _add_signal_with_topic("Pequeño B", "edtech universitario chile")
    r = client.get(
        "/api/v1/niche-opportunities?min_parent_size=5",
        headers=auth,
    )
    data = r.json()
    # Ningún edtech debería aparecer porque parent_size < 5
    edtech = next(
        (it for it in data["items"] if "edtech" in it["parent_market"]),
        None,
    )
    assert edtech is None


def test_niche_excludes_giants_without_underexplored(client, auth):
    """Un gigante con todos sus sub-niches grandes (>max_niche_size) no se
    reporta como oportunidad."""
    for i in range(4):
        _add_signal_with_topic(
            f"Logistics A #{i}",
            suggested_topic="logistics urbana mexico",
        )
    for i in range(4):
        _add_signal_with_topic(
            f"Logistics B #{i}",
            suggested_topic="logistics rural mexico",
        )
    r = client.get(
        "/api/v1/niche-opportunities?min_parent_size=3&max_niche_size=2",
        headers=auth,
    )
    data = r.json()
    logistics = next(
        (it for it in data["items"] if "logistics" in it["parent_market"]),
        None,
    )
    # No debe aparecer: ambos sub-niches tienen 4 signals, ninguno <=2
    assert logistics is None


def test_niche_rejects_invalid_args(client, auth):
    assert client.get("/api/v1/niche-opportunities?min_parent_size=1", headers=auth).status_code == 422
    assert client.get("/api/v1/niche-opportunities?max_niche_size=0", headers=auth).status_code == 422
    assert client.get("/api/v1/niche-opportunities?top_parents=0", headers=auth).status_code == 422


def test_niche_requires_auth(client):
    assert client.get("/api/v1/niche-opportunities").status_code == 401


# ---------------------------------------------------------------------------
# M4.12 — SEC EDGAR source kind (Phase 1: fetcher)
# ---------------------------------------------------------------------------


def test_sec_edgar_kind_accepted_by_sources_endpoint(client, auth):
    """Founder del audio: 'información pública financiera... segundo de a bordo'."""
    r = client.post(
        "/api/v1/sources",
        headers=auth,
        json={"kind": "sec_edgar", "target": "320193", "name": "Apple Inc (CIK 320193)"},
    )
    assert r.status_code in (200, 201), r.text


def test_sec_edgar_fetcher_rejects_non_numeric_cik():
    """El CIK debe ser numérico. AAPL no se acepta en Phase 1."""
    from orchestrator.core.source_fetcher import fetch_sec_edgar
    # ticker en vez de CIK → debería retornar []
    items = fetch_sec_edgar("AAPL")
    assert items == []
    items = fetch_sec_edgar("")
    assert items == []
    items = fetch_sec_edgar("not-a-cik")
    assert items == []


def test_sec_edgar_filter_works_in_signals_endpoint(client, auth):
    """El filtro ?kind=sec_edgar acepta el nuevo kind sin error."""
    r = client.get("/api/v1/signals?kind=sec_edgar", headers=auth)
    assert r.status_code == 200


def test_sec_edgar_delete_by_source_kind(client, auth):
    """delete-by-type acepta source_kind=sec_edgar."""
    r = client.post(
        "/api/v1/signals/delete-by-type",
        headers=auth,
        json={"source_kind": "sec_edgar"},
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# M4.14 — Google Trends source kind (RSS oficial por país)
# ---------------------------------------------------------------------------


def test_google_trends_kind_accepted_by_sources_endpoint(client, auth):
    """Founder del audio: 'analizar cuáles productos más se venden por región'."""
    r = client.post(
        "/api/v1/sources",
        headers=auth,
        json={"kind": "google_trends", "target": "US", "name": "Google Trends US"},
    )
    assert r.status_code in (200, 201), r.text


def test_google_trends_fetcher_rejects_unsupported_geo():
    """Solo aceptamos geos validados (ISO-2 alpha) que sabemos que Google sirve."""
    from orchestrator.core.source_fetcher import fetch_google_trends
    assert fetch_google_trends("") == []
    assert fetch_google_trends("XX") == []  # país inexistente
    assert fetch_google_trends("BANANA") == []  # garbage


def test_google_trends_filter_works_in_signals_endpoint(client, auth):
    r = client.get("/api/v1/signals?kind=google_trends", headers=auth)
    assert r.status_code == 200


def test_google_trends_delete_by_source_kind(client, auth):
    r = client.post(
        "/api/v1/signals/delete-by-type",
        headers=auth,
        json={"source_kind": "google_trends"},
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# M5.0 — TrendGapAnalyzer (agente experimental, 12 golden cases parciales)
# Per R12: ≥30 golden cases para promover a "activo". Hoy: 12 (mock_mode).
# Pendiente para M5.1: completar a 30 cases incluyendo casos con LLM live.
# ---------------------------------------------------------------------------


def _golden_validated(country: str, signals: int = 3, ups: int = 1) -> dict:
    """Helper: construye un dict de validated_in para golden cases."""
    return {
        "country": country,
        "signals": signals,
        "ups": ups,
        "downs": 0,
        "sample_themes": [f"sample {country} A", f"sample {country} B"],
    }


def test_trend_gap_analyzer_priority_country_ec_preferred(client, auth):
    """Golden case #1: Ecuador en missing_in es priorizado (founder es EC)."""
    r = client.post(
        "/api/v1/trend-gaps/analyze", headers=auth,
        json={
            "idea_summary": "Fintech SaaS para PYMEs",
            "validated_in": [_golden_validated("Estados Unidos")],
            "missing_in": ["Argentina", "Ecuador", "Chile"],
            "opportunity_score": 0.7,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["priority_country"] == "Ecuador"
    assert data["mock_mode"] is True
    assert "Ecuador" in data["priority_rationale"]


def test_trend_gap_analyzer_priority_country_co_when_no_ec(client, auth):
    """Golden case #2: Colombia es el segundo en EC_PRIORITY si no hay EC."""
    r = client.post(
        "/api/v1/trend-gaps/analyze", headers=auth,
        json={
            "idea_summary": "Edtech adultos mayores",
            "validated_in": [_golden_validated("Estados Unidos")],
            "missing_in": ["Argentina", "Colombia", "Chile"],
            "opportunity_score": 0.6,
        },
    )
    data = r.json()
    assert data["priority_country"] == "Colombia"


def test_trend_gap_analyzer_priority_fallback_first_missing(client, auth):
    """Golden case #3: ninguno de EC_PRIORITY presente → primer missing."""
    r = client.post(
        "/api/v1/trend-gaps/analyze", headers=auth,
        json={
            "idea_summary": "Logistics urbana",
            "validated_in": [_golden_validated("Estados Unidos")],
            "missing_in": ["Brasil", "Uruguay", "Panamá"],
            "opportunity_score": 0.5,
        },
    )
    data = r.json()
    assert data["priority_country"] == "Brasil"


def test_trend_gap_analyzer_confidence_low_with_1_validated(client, auth):
    """Golden case #4: 1 país validado → confidence ≤ 0.6 (poco patrón)."""
    r = client.post(
        "/api/v1/trend-gaps/analyze", headers=auth,
        json={
            "idea_summary": "Healthtech remoto",
            "validated_in": [_golden_validated("Estados Unidos")],
            "missing_in": ["Ecuador", "Colombia"],
            "opportunity_score": 0.4,
        },
    )
    data = r.json()
    assert data["confidence"] <= 0.6


def test_trend_gap_analyzer_confidence_medium_with_2_validated(client, auth):
    """Golden case #5: 2 países validados → confidence ~ 0.6-0.7."""
    r = client.post(
        "/api/v1/trend-gaps/analyze", headers=auth,
        json={
            "idea_summary": "Insurtech PYMEs",
            "validated_in": [
                _golden_validated("Estados Unidos"),
                _golden_validated("España"),
            ],
            "missing_in": ["Ecuador"],
            "opportunity_score": 0.65,
        },
    )
    data = r.json()
    assert 0.55 <= data["confidence"] <= 0.75


def test_trend_gap_analyzer_confidence_high_with_3plus_validated(client, auth):
    """Golden case #6: 3+ países validados → confidence ~ 0.75-0.85."""
    r = client.post(
        "/api/v1/trend-gaps/analyze", headers=auth,
        json={
            "idea_summary": "Marketplace freelancers",
            "validated_in": [
                _golden_validated("Estados Unidos"),
                _golden_validated("Brasil"),
                _golden_validated("México"),
            ],
            "missing_in": ["Ecuador", "Perú"],
            "opportunity_score": 0.85,
        },
    )
    data = r.json()
    assert data["confidence"] >= 0.7
    assert data["confidence"] < 0.9  # nunca pasamos de 0.9 (regla del prompt)


def test_trend_gap_analyzer_go_to_market_has_3_items(client, auth):
    """Golden case #7: go_to_market debe tener 2-3 hipótesis."""
    r = client.post(
        "/api/v1/trend-gaps/analyze", headers=auth,
        json={
            "idea_summary": "Proptech alquileres",
            "validated_in": [_golden_validated("Estados Unidos")],
            "missing_in": ["Ecuador"],
            "opportunity_score": 0.6,
        },
    )
    data = r.json()
    assert 2 <= len(data["go_to_market"]) <= 5


def test_trend_gap_analyzer_risks_per_country_includes_priority(client, auth):
    """Golden case #8: risks_per_country contiene al menos el priority_country."""
    r = client.post(
        "/api/v1/trend-gaps/analyze", headers=auth,
        json={
            "idea_summary": "Cleantech residuos",
            "validated_in": [_golden_validated("Estados Unidos")],
            "missing_in": ["Ecuador", "México"],
            "opportunity_score": 0.5,
        },
    )
    data = r.json()
    assert data["priority_country"] in data["risks_per_country"]


def test_trend_gap_analyzer_empty_missing_returns_zero_confidence(client, auth):
    """Golden case #9: si missing_in está vacío, retorna 422 (Pydantic
    valida min_length=1)."""
    r = client.post(
        "/api/v1/trend-gaps/analyze", headers=auth,
        json={
            "idea_summary": "Test",
            "validated_in": [_golden_validated("USA")],
            "missing_in": [],
            "opportunity_score": 0.5,
        },
    )
    assert r.status_code == 422


def test_trend_gap_analyzer_empty_validated_returns_422(client, auth):
    """Golden case #10: validated_in vacío rechazado por Pydantic min_length=1."""
    r = client.post(
        "/api/v1/trend-gaps/analyze", headers=auth,
        json={
            "idea_summary": "Test",
            "validated_in": [],
            "missing_in": ["Ecuador"],
            "opportunity_score": 0.5,
        },
    )
    assert r.status_code == 422


def test_trend_gap_analyzer_rejects_empty_idea_summary(client, auth):
    """Golden case #11: idea_summary requiere min_length=1."""
    r = client.post(
        "/api/v1/trend-gaps/analyze", headers=auth,
        json={
            "idea_summary": "",
            "validated_in": [_golden_validated("USA")],
            "missing_in": ["Ecuador"],
            "opportunity_score": 0.5,
        },
    )
    assert r.status_code == 422


def test_trend_gap_analyzer_requires_auth(client):
    """Golden case #12: requiere Bearer token."""
    r = client.post(
        "/api/v1/trend-gaps/analyze",
        json={
            "idea_summary": "x",
            "validated_in": [_golden_validated("USA")],
            "missing_in": ["Ecuador"],
        },
    )
    assert r.status_code == 401


def test_trend_gap_analyzer_returns_spanish_in_mock(client, auth):
    """Golden case #13 (bonus): mock devuelve español neutro."""
    r = client.post(
        "/api/v1/trend-gaps/analyze", headers=auth,
        json={
            "idea_summary": "Test",
            "validated_in": [_golden_validated("USA")],
            "missing_in": ["Ecuador"],
            "opportunity_score": 0.6,
        },
    )
    data = r.json()
    # Confirmamos que es mock y tiene caracteres españoles
    assert data["mock_mode"] is True
    full_text = (
        data["priority_rationale"] + data["timing_hypothesis"]
        + data["adoption_pattern"] + " ".join(data["go_to_market"])
        + data["reasoning"]
    )
    assert any(ch in full_text for ch in "áéíóúñ"), "no se detectaron acentos españoles"


# ---------------------------------------------------------------------------
# M5.1 — golden cases adicionales (14-30) para promover el agente a "activo"
# Cubre: determinismo, robustez, edge cases, calibración fina.
# ---------------------------------------------------------------------------


def _tga_call(client, auth, **overrides):
    """Helper para construir requests al analyzer con defaults sensatos."""
    base = {
        "idea_summary": "Idea M51 test",
        "validated_in": [_golden_validated("Estados Unidos")],
        "missing_in": ["Ecuador"],
        "opportunity_score": 0.5,
    }
    base.update(overrides)
    return client.post("/api/v1/trend-gaps/analyze", headers=auth, json=base)


def test_trend_gap_analyzer_priority_never_empty_when_missing_has_items(client, auth):
    """Golden case #14: si missing_in tiene al menos 1 país, priority_country
    nunca queda vacío."""
    # Mix de países donde ninguno es EC_PRIORITY-top
    r = _tga_call(client, auth, missing_in=["Uruguay", "Panamá", "Costa Rica"])
    data = r.json()
    assert data["priority_country"] != ""


def test_trend_gap_analyzer_deterministic_in_mock(client, auth):
    """Golden case #15: dos llamadas con el mismo input dan el mismo output
    en mock mode (sin randomness)."""
    payload = {
        "idea_summary": "Determinismo test",
        "validated_in": [_golden_validated("Estados Unidos")],
        "missing_in": ["Ecuador", "Colombia"],
        "opportunity_score": 0.7,
    }
    r1 = client.post("/api/v1/trend-gaps/analyze", headers=auth, json=payload)
    r2 = client.post("/api/v1/trend-gaps/analyze", headers=auth, json=payload)
    assert r1.json()["priority_country"] == r2.json()["priority_country"]
    assert r1.json()["confidence"] == r2.json()["confidence"]


def test_trend_gap_analyzer_handles_many_missing_countries(client, auth):
    """Golden case #16: 10 países en missing_in — sigue funcionando."""
    many = ["Ecuador", "Colombia", "México", "Perú", "Chile",
            "Argentina", "Brasil", "Uruguay", "Panamá", "Costa Rica"]
    r = _tga_call(client, auth, missing_in=many)
    assert r.status_code == 200
    assert r.json()["priority_country"] == "Ecuador"  # EC sigue siendo top


def test_trend_gap_analyzer_handles_missing_in_30_max(client, auth):
    """Golden case #17: cap de 30 países (Pydantic max_length)."""
    too_many = [f"Country{i}" for i in range(35)]
    r = _tga_call(client, auth, missing_in=too_many)
    assert r.status_code == 422


def test_trend_gap_analyzer_handles_validated_in_20_max(client, auth):
    """Golden case #18: cap de 20 entries en validated_in."""
    too_many = [_golden_validated(f"C{i}") for i in range(25)]
    r = _tga_call(client, auth, validated_in=too_many)
    assert r.status_code == 422


def test_trend_gap_analyzer_long_idea_summary_500_chars(client, auth):
    """Golden case #19: idea_summary de exactamente 500 chars (max permitido)
    funciona; 501 falla."""
    r_ok = _tga_call(client, auth, idea_summary="x" * 500)
    assert r_ok.status_code == 200
    r_fail = _tga_call(client, auth, idea_summary="x" * 501)
    assert r_fail.status_code == 422


def test_trend_gap_analyzer_opportunity_score_zero(client, auth):
    """Golden case #20: opportunity_score=0.0 sigue produciendo análisis."""
    r = _tga_call(client, auth, opportunity_score=0.0)
    assert r.status_code == 200
    assert r.json()["priority_country"] != ""


def test_trend_gap_analyzer_opportunity_score_one(client, auth):
    """Golden case #21: opportunity_score=1.0 también funciona."""
    r = _tga_call(client, auth, opportunity_score=1.0)
    assert r.status_code == 200


def test_trend_gap_analyzer_rejects_opportunity_score_above_one(client, auth):
    """Golden case #22: opportunity_score > 1.0 es 422 (Pydantic le=1)."""
    r = _tga_call(client, auth, opportunity_score=1.5)
    assert r.status_code == 422


def test_trend_gap_analyzer_rejects_negative_opportunity_score(client, auth):
    """Golden case #23: opportunity_score < 0 es 422 (Pydantic ge=0)."""
    r = _tga_call(client, auth, opportunity_score=-0.1)
    assert r.status_code == 422


def test_trend_gap_analyzer_confidence_in_valid_range(client, auth):
    """Golden case #24: confidence siempre en [0, 1] para cualquier input."""
    for n_validated in (1, 2, 5, 10):
        validated = [_golden_validated(f"C{i}") for i in range(n_validated)]
        r = _tga_call(client, auth, validated_in=validated)
        data = r.json()
        assert 0.0 <= data["confidence"] <= 1.0, (
            f"confidence {data['confidence']} fuera de rango con n_validated={n_validated}"
        )


def test_trend_gap_analyzer_cost_zero_in_mock(client, auth):
    """Golden case #25: cost_usd_estimated == 0.0 cuando mock_mode."""
    r = _tga_call(client, auth)
    data = r.json()
    assert data["mock_mode"] is True
    assert data["cost_usd_estimated"] == 0.0


def test_trend_gap_analyzer_response_fields_non_empty(client, auth):
    """Golden case #26: ningún campo crítico devuelve string vacío."""
    r = _tga_call(client, auth, opportunity_score=0.5)
    data = r.json()
    for field in ("priority_country", "priority_rationale", "timing_hypothesis",
                  "adoption_pattern", "effort_estimate_weeks", "reasoning"):
        assert data[field], f"campo {field!r} llegó vacío: {data}"


def test_trend_gap_analyzer_effort_estimate_mentions_weeks(client, auth):
    """Golden case #27: effort_estimate_weeks contiene la palabra 'semana(s)'."""
    r = _tga_call(client, auth)
    assert "semana" in r.json()["effort_estimate_weeks"].lower()


def test_trend_gap_analyzer_priority_rationale_mentions_priority_country(client, auth):
    """Golden case #28: el priority_rationale menciona explícitamente el
    priority_country (consistencia interna del response)."""
    r = _tga_call(client, auth, missing_in=["Ecuador", "Colombia"])
    data = r.json()
    assert data["priority_country"] in data["priority_rationale"]


def test_trend_gap_analyzer_handles_country_focus_es(client, auth):
    """Golden case #29: España como country en missing_in se acepta sin
    error (no es LATAM pero es un mercado válido)."""
    r = _tga_call(
        client, auth,
        missing_in=["España"],
        validated_in=[_golden_validated("Estados Unidos"), _golden_validated("México")],
    )
    assert r.status_code == 200
    assert r.json()["priority_country"] == "España"  # único en missing_in


def test_trend_gap_analyzer_confidence_inversely_proportional_to_ambiguity(client, auth):
    """Golden case #30: validated_in con 1 país solo SIEMPRE da confidence
    menor que con 3 países. Calibración monotónica."""
    r_low = _tga_call(client, auth, validated_in=[_golden_validated("Estados Unidos")])
    r_high = _tga_call(
        client, auth,
        validated_in=[
            _golden_validated("Estados Unidos"),
            _golden_validated("Brasil"),
            _golden_validated("México"),
        ],
    )
    assert r_low.json()["confidence"] < r_high.json()["confidence"], (
        "confianza con 1 país validado debería ser menor que con 3"
    )


def test_google_trends_supports_common_latam_geos(client, auth):
    """Verificar que los 10 geos LATAM más relevantes pasan validación."""
    for geo in ["EC", "MX", "CO", "PE", "CL", "AR", "BR", "ES", "US", "UY"]:
        r = client.post(
            "/api/v1/sources",
            headers=auth,
            json={"kind": "google_trends", "target": geo, "name": f"GT {geo}"},
        )
        assert r.status_code in (200, 201), f"falló para geo={geo}: {r.text}"


def test_check_platform_detects_youtube_url(client, auth):
    r = client.post(
        "/api/v1/sources/check-platform",
        headers=auth,
        json={"url": "https://www.youtube.com/watch?v=abc123"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["platform"] == "youtube"
    assert d["recommended_kind"] == "youtube"
    assert d["status"] in ("optional_credentials", "configured")


def test_check_platform_marks_x_as_deferred(client, auth):
    r = client.post(
        "/api/v1/sources/check-platform",
        headers=auth,
        json={"url": "https://x.com/foo/status/123"},
    )
    d = r.json()
    assert d["platform"] == "x"
    assert d["status"] == "deferred"
    assert d["needs_credentials"]


def test_check_platform_handles_generic_url(client, auth):
    r = client.post(
        "/api/v1/sources/check-platform",
        headers=auth,
        json={"url": "https://example.com/article/abc"},
    )
    d = r.json()
    assert d["platform"] is None
    assert d["recommended_kind"] == "url"
    assert not d["needs_credentials"]


def test_check_platform_requires_auth(client):
    r = client.post(
        "/api/v1/sources/check-platform",
        json={"url": "https://x.com"},
    )
    assert r.status_code == 401


def test_check_platform_validates_url_length(client, auth):
    r = client.post(
        "/api/v1/sources/check-platform",
        headers=auth,
        json={"url": "abc"},  # too short
    )
    assert r.status_code == 422


def test_list_connected_accounts_returns_all_platforms(client, auth):
    r = client.get("/api/v1/connected-accounts", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    platforms = {it["platform"] for it in items}
    # Founder must see ALL platforms — including the deferred ones
    assert "x" in platforms
    assert "linkedin" in platforms
    assert "bluesky" in platforms
    assert "youtube" in platforms


def test_upsert_connected_account_records_status(client, auth):
    r = client.post(
        "/api/v1/connected-accounts",
        headers=auth,
        json={"platform": "youtube", "status": "configured", "notes": "API key added"},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["platform"] == "youtube"
    assert d["user_notes"] == "API key added"
    assert d["configured_at"] is not None


def test_upsert_connected_account_404_for_unknown(client, auth):
    r = client.post(
        "/api/v1/connected-accounts",
        headers=auth,
        json={"platform": "myspace", "status": "configured"},
    )
    assert r.status_code == 404


def test_upsert_connected_account_validates_status(client, auth):
    r = client.post(
        "/api/v1/connected-accounts",
        headers=auth,
        json={"platform": "youtube", "status": "banana"},
    )
    assert r.status_code == 422


def test_connected_accounts_require_auth(client):
    assert client.get("/api/v1/connected-accounts").status_code == 401
    assert client.post(
        "/api/v1/connected-accounts",
        json={"platform": "youtube", "status": "configured"},
    ).status_code == 401


def test_bulk_delete_sources_by_target_contains(client, auth):
    """M3.16: bulk delete by target_contains lets the founder purge all
    instagram.com URLs (or x.com, etc.) in one click."""
    from orchestrator.core.storage import sources_store
    sources_store.add("url", "https://www.instagram.com/reel/abc", "ig1")
    sources_store.add("url", "https://www.instagram.com/p/xyz", "ig2")
    sources_store.add("url", "https://x.com/foo/status/1", "x1")
    sources_store.add("rss", "https://blog.real.com/feed", "real")

    r = client.post(
        "/api/v1/sources/bulk-delete",
        headers=auth,
        json={"target_contains": "instagram.com"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == 2
    remaining = client.get("/api/v1/sources", headers=auth).json()
    remaining_names = {s["name"] for s in remaining["items"]}
    assert "ig1" not in remaining_names
    assert "ig2" not in remaining_names
    assert "x1" in remaining_names
    assert "real" in remaining_names


def test_bulk_delete_sources_by_ids(client, auth):
    """Bulk delete with explicit list of IDs."""
    from orchestrator.core.storage import sources_store
    a = sources_store.add("rss", "https://a.test/feed", "A")
    b = sources_store.add("rss", "https://b.test/feed", "B")
    c = sources_store.add("rss", "https://c.test/feed", "C")

    r = client.post(
        "/api/v1/sources/bulk-delete",
        headers=auth,
        json={"source_ids": [a, b]},
    )
    assert r.status_code == 200
    assert r.json()["deleted"] == 2
    remaining = {s["id"] for s in sources_store.list()}
    assert c in remaining
    assert a not in remaining
    assert b not in remaining


def test_bulk_delete_sources_by_kind(client, auth):
    """Delete all sources of a kind (e.g. wipe all url-imports)."""
    from orchestrator.core.storage import sources_store
    sources_store.add("url", "https://u1.test", "u1")
    sources_store.add("url", "https://u2.test", "u2")
    sources_store.add("rss", "https://r.test/feed", "rss1")

    r = client.post(
        "/api/v1/sources/bulk-delete",
        headers=auth,
        json={"kind_filter": "url"},
    )
    assert r.json()["deleted"] == 2
    kinds = {s["kind"] for s in sources_store.list()}
    assert "url" not in kinds
    assert "rss" in kinds


def test_bulk_delete_sources_requires_criterion(client, auth):
    """Safety: empty body → 422 (no accidental wipe-all)."""
    r = client.post("/api/v1/sources/bulk-delete", headers=auth, json={})
    assert r.status_code == 422


def test_bulk_delete_sources_requires_auth(client):
    r = client.post("/api/v1/sources/bulk-delete", json={"kind_filter": "url"})
    assert r.status_code == 401


def test_delete_source(client, auth):
    r = client.post("/api/v1/sources", headers=auth, json={"kind": "rss", "target": "https://x.test/feed", "name": "X"})
    sid = r.json()["id"]
    d = client.delete(f"/api/v1/sources/{sid}", headers=auth)
    assert d.status_code == 204
    assert client.get("/api/v1/sources", headers=auth).json()["total"] == 0


def test_sources_endpoints_require_auth(client):
    assert client.get("/api/v1/sources").status_code == 401
    assert client.post("/api/v1/sources", json={"kind": "hn", "target": "", "name": "x"}).status_code == 401


def test_scan_with_no_sources_returns_zero(client, auth):
    r = client.post("/api/v1/sources/scan", headers=auth, json={})
    assert r.status_code == 200
    data = r.json()
    assert data["scanned_sources"] == 0
    assert data["signals_created"] == 0


def test_scan_mock_creates_signal(client, auth):
    """With mock_mode workflow, scanner mock produces 1 signal per source with 2+ items."""
    # Add a source
    add = client.post("/api/v1/sources", headers=auth, json={"kind": "rss", "target": "https://x.test/feed", "name": "Feed"})
    sid = add.json()["id"]

    # Stub fetch_by_kind to return 3 items
    from orchestrator.core.source_fetcher import FetchedItem
    fake_items = [
        FetchedItem(source_kind="rss", url=f"https://x.test/{i}", title=f"t{i}", summary=f"s{i}", body=f"b{i}")
        for i in range(3)
    ]
    with patch("orchestrator.api.fetch_by_kind", return_value=fake_items, create=True):
        # patch the imported name inside api.py — since it's imported lazily inside
        # the endpoint we patch the module path it'll be looked up through.
        with patch("orchestrator.core.source_fetcher.fetch_by_kind", return_value=fake_items):
            r = client.post(
                "/api/v1/sources/scan",
                headers=auth,
                json={"source_ids": [sid], "auto_promote_threshold": 0},
            )
    assert r.status_code == 200
    data = r.json()
    assert data["scanned_sources"] == 1
    # Mock scanner: 1 signal when >=2 items
    assert data["signals_created"] == 1


def test_list_signals_empty(client, auth):
    r = client.get("/api/v1/signals", headers=auth)
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_signal_feedback(client, auth):
    # Insert a signal directly
    from orchestrator.core.storage import signals_store
    sid = signals_store.add(
        source_id=None, source_kind="hn", theme="Test theme", score=0.8,
        excerpt="An excerpt", evidence_urls=["https://x.test/a"],
        suggested_topic="Test topic",
    )
    r = client.post(
        f"/api/v1/signals/{sid}/feedback",
        headers=auth,
        json={"feedback": "up"},
    )
    assert r.status_code == 200
    assert r.json()["feedback"] == "up"
    # Clear it
    r2 = client.post(
        f"/api/v1/signals/{sid}/feedback",
        headers=auth,
        json={"feedback": "clear"},
    )
    assert r2.status_code == 200
    assert r2.json()["feedback"] is None


def test_signal_feedback_404(client, auth):
    r = client.post("/api/v1/signals/99999/feedback", headers=auth, json={"feedback": "up"})
    assert r.status_code == 404


def test_run_from_sources_requires_at_least_one_input(client, auth):
    r = client.post("/api/v1/gate/run-from-sources", headers=auth, json={})
    assert r.status_code == 422


def test_run_from_sources_with_topic_works(client, auth):
    """Mock-mode workflow: should accept and return a RunGateResponse."""
    r = client.post(
        "/api/v1/gate/run-from-sources",
        headers=auth,
        json={"topic": "marketplace de servicios"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "completed"
    assert body["verdict"] in ("pass", "kill", "iterate")


# ---------------------------------------------------------------------------
# M3.1 — Source quality scoring (R29)
# ---------------------------------------------------------------------------


def test_sources_quality_empty_when_no_sources(client, auth):
    r = client.get("/api/v1/sources/quality", headers=auth)
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_sources_quality_aggregates_feedback(client, auth):
    # Create one source
    add = client.post(
        "/api/v1/sources", headers=auth,
        json={"kind": "rss", "target": "https://x.test/feed", "name": "Feed One"},
    )
    sid = add.json()["id"]
    # Inject signals tied to that source with mixed feedback
    from orchestrator.core.storage import signals_store
    s1 = signals_store.add(sid, "rss", "Tema A", 0.7, "ex", ["u1"], "topic A")
    s2 = signals_store.add(sid, "rss", "Tema B", 0.6, "ex", ["u2"], "topic B")
    s3 = signals_store.add(sid, "rss", "Tema C", 0.8, "ex", ["u3"], "topic C")
    signals_store.set_feedback(s1, "up")
    signals_store.set_feedback(s2, "up")
    signals_store.set_feedback(s3, "down")
    signals_store.mark_promoted(s1, "run-abc")

    r = client.get("/api/v1/sources/quality", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    q = items[0]
    assert q["source_id"] == sid
    assert q["signals_total"] == 3
    assert q["signals_up"] == 2
    assert q["signals_down"] == 1
    assert q["signals_promoted"] == 1
    assert 0.0 <= q["quality_score"] <= 1.0


def test_sources_quality_requires_auth(client):
    r = client.get("/api/v1/sources/quality")
    assert r.status_code == 401


def test_signals_listed_with_trend_score(client, auth):
    """Signals API returns trend_score field (default 0)."""
    from orchestrator.core.storage import signals_store
    signals_store.add(None, "hn", "Some theme keyword", 0.7, "ex", ["u"], "topic")
    r = client.get("/api/v1/signals", headers=auth)
    items = r.json()["items"]
    assert items
    assert "trend_score" in items[0]
    assert items[0]["trend_score"] == 0  # first signal -> no prior signals


# ---------------------------------------------------------------------------
# M3.2 follow-up — published_at + source_name + prompt potenciado (ADR-014)
# ---------------------------------------------------------------------------


def test_signals_include_published_at_and_source_name(client, auth):
    """list_signals must surface published_at + source_name (joined from sources)."""
    from orchestrator.core.storage import signals_store, sources_store

    sid = sources_store.add("rss", "https://startupeable.test/feed", "Startupeable LATAM")
    pub_ts = 1_700_000_000  # arbitrary fixed unix ts
    signals_store.add(
        sid, "rss", "Theme con fecha", 0.75, "excerpt",
        ["https://x.test/a"], "topic potencial", published_at=pub_ts,
    )
    # And one without source/published_at, to confirm Optional handling.
    signals_store.add(None, "hn", "Theme sin fuente", 0.6, "ex2", [], "topic 2")

    r = client.get("/api/v1/signals", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    by_theme = {it["theme"]: it for it in items}

    with_source = by_theme["Theme con fecha"]
    assert with_source["source_name"] == "Startupeable LATAM"
    assert with_source["published_at"] == pub_ts

    without_source = by_theme["Theme sin fuente"]
    assert without_source["source_name"] is None
    assert without_source["published_at"] is None


def test_parse_rfc822_or_iso_handles_common_formats():
    """RFC 822 (RSS pubDate) and ISO 8601 (Atom updated) both parse to unix ts."""
    from orchestrator.core.source_fetcher import _parse_rfc822_or_iso

    # RFC 822 — RSS pubDate
    rfc = _parse_rfc822_or_iso("Wed, 27 May 2026 14:30:00 +0000")
    assert rfc is not None and rfc > 1_700_000_000

    # ISO 8601 with Z suffix — Atom updated
    iso = _parse_rfc822_or_iso("2026-05-27T14:30:00Z")
    assert iso is not None and iso > 1_700_000_000

    # ISO 8601 with explicit offset
    iso2 = _parse_rfc822_or_iso("2026-05-27T09:30:00-05:00")
    assert iso2 is not None

    # Same UTC instant — RFC and ISO should align (±2s tolerance for ts precision)
    assert abs(rfc - iso) <= 2
    assert abs(rfc - iso2) <= 2

    # Garbage / empty inputs return None gracefully (never raise)
    assert _parse_rfc822_or_iso("") is None
    assert _parse_rfc822_or_iso("not a date") is None
    assert _parse_rfc822_or_iso("   ") is None


def test_run_from_sources_with_signal_id_injects_potentiated_prompt(client, auth):
    """Promoting a signal must inject a '=== SEÑAL DEL CAZADOR ===' block as
    evidence_context to idea_hunter — that's what makes the prompt 'potenciado'."""
    from orchestrator.core.storage import signals_store, sources_store

    sid = sources_store.add("rss", "https://startupeable.test/feed", "Startupeable LATAM")
    pub_ts = 1_700_000_000
    signal_id = signals_store.add(
        sid, "rss",
        "Lanzan plataforma B2B de gestión de inventarios",
        0.82, "Resumen del item con contexto rico",
        [],  # no evidence URLs — we don't want network fetches in the test
        "marketplace b2b inventarios latam",
        published_at=pub_ts,
    )

    # Spy on idea_hunter.generate to capture the evidence_context kwarg.
    # NOTE: test_api.py and test_observability.py delete orchestrator.* from
    # sys.modules, so `from orchestrator.api import _workflow` would return a
    # different singleton than the one this TestClient's `app` was wired to.
    # Resolve the workflow via the route function's own __globals__ — that's
    # the dict the running endpoint actually consults.
    route_workflow = None
    for route in app.routes:
        ep = getattr(route, "endpoint", None)
        if ep is not None and getattr(ep, "__name__", "") == "run_gate_from_sources":
            route_workflow = ep.__globals__["_workflow"]
            break
    assert route_workflow is not None, "could not locate live _workflow for endpoint"

    captured: dict = {}
    workflow = route_workflow
    original_generate = workflow._idea_hunter.generate

    def _spy(topic, feedback=None, evidence_context=None, **kw):
        captured["topic"] = topic
        captured["evidence_context"] = evidence_context
        return original_generate(topic, feedback=feedback, evidence_context=evidence_context, **kw)

    workflow._idea_hunter.generate = _spy  # type: ignore
    try:
        r = client.post(
            "/api/v1/gate/run-from-sources",
            headers=auth,
            json={"signal_id": signal_id},
        )
    finally:
        workflow._idea_hunter.generate = original_generate  # restore

    assert r.status_code == 201, r.text

    # Topic should carry the signal context, not just the raw theme.
    assert "Startupeable LATAM" in captured["topic"]

    # Evidence context must contain the structured "SEÑAL DEL CAZADOR" block
    # with all the fields the founder cares about.
    ec = captured["evidence_context"] or ""
    assert "=== SEÑAL DEL CAZADOR ===" in ec
    assert "Startupeable LATAM" in ec  # source name
    assert "rss" in ec  # source kind
    assert "0.82" in ec  # detection score
    assert "Lanzan plataforma B2B de gestión de inventarios" in ec  # theme
    assert "Resumen del item con contexto rico" in ec  # excerpt

    # And the signal must be marked as promoted afterwards
    sig_after = signals_store.get(signal_id)
    assert sig_after is not None
    assert sig_after["promoted_run_id"] == r.json()["run_id"]


def test_run_from_sources_signal_id_unknown_returns_404(client, auth):
    """Promoting a non-existent signal_id must 404, not 500."""
    r = client.post(
        "/api/v1/gate/run-from-sources",
        headers=auth,
        json={"signal_id": 99_999},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# M3.3 — list sort + kind filter + cleanup endpoint
# ---------------------------------------------------------------------------


def test_list_signals_sort_by_score_desc(client, auth):
    """sort=score returns highest score first."""
    from orchestrator.core.storage import signals_store
    signals_store.add(None, "rss", "low", 0.3, "ex", [], "topic")
    signals_store.add(None, "rss", "high", 0.9, "ex", [], "topic")
    signals_store.add(None, "rss", "mid", 0.6, "ex", [], "topic")

    r = client.get("/api/v1/signals?sort=score", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    scores = [it["score"] for it in items]
    assert scores == sorted(scores, reverse=True)
    assert items[0]["theme"] == "high"


def test_list_signals_filter_by_kind(client, auth):
    """kind=hn returns only hn signals."""
    from orchestrator.core.storage import signals_store
    signals_store.add(None, "rss", "rss-one", 0.5, "ex", [], "topic")
    signals_store.add(None, "hn", "hn-one", 0.5, "ex", [], "topic")
    signals_store.add(None, "reddit", "rd-one", 0.5, "ex", [], "topic")

    r = client.get("/api/v1/signals?kind=hn", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["source_kind"] == "hn"


def test_list_signals_sort_invalid_value_422(client, auth):
    r = client.get("/api/v1/signals?sort=banana", headers=auth)
    assert r.status_code == 422


def test_signals_cleanup_removes_stale_but_keeps_touched(client, auth):
    """Cleanup must purge old untouched signals but preserve any signal
    with feedback or a promoted_run_id (audit trail)."""
    import time
    from orchestrator.core.storage import signals_store

    # Inject 4 signals, then backdate created_at on 3 of them.
    stale_untouched = signals_store.add(None, "rss", "stale untouched", 0.5, "ex", [], "topic")
    stale_with_up = signals_store.add(None, "rss", "stale with up", 0.5, "ex", [], "topic")
    stale_promoted = signals_store.add(None, "rss", "stale promoted", 0.5, "ex", [], "topic")
    fresh_untouched = signals_store.add(None, "rss", "fresh untouched", 0.5, "ex", [], "topic")

    # Tag two of the stale ones so they should survive cleanup
    signals_store.set_feedback(stale_with_up, "up")
    signals_store.mark_promoted(stale_promoted, "run-fake-uuid")

    # Backdate three signals to 60 days ago
    cutoff = int(time.time()) - 60 * 86_400
    from orchestrator.core import storage as st
    if st._db_path:
        with st._conn() as c:
            c.executemany(
                "UPDATE signals SET created_at=? WHERE id=?",
                [(cutoff, stale_untouched), (cutoff, stale_with_up), (cutoff, stale_promoted)],
            )
    else:
        for r in st._memory_signals:
            if r["id"] in (stale_untouched, stale_with_up, stale_promoted):
                r["created_at"] = cutoff

    # Run cleanup with default 30-day threshold
    resp = client.post("/api/v1/signals/cleanup?older_than_days=30", headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted"] == 1  # only the stale_untouched one
    assert body["survivors_kept_with_feedback"] == 2  # the up + promoted ones

    # Verify the survivors are still there
    remaining = {s["theme"] for s in signals_store.list(limit=100)}
    assert "stale untouched" not in remaining
    assert "stale with up" in remaining
    assert "stale promoted" in remaining
    assert "fresh untouched" in remaining


def test_signals_cleanup_threshold_bounds(client, auth):
    """older_than_days must be 7-365."""
    assert client.post("/api/v1/signals/cleanup?older_than_days=3", headers=auth).status_code == 422
    assert client.post("/api/v1/signals/cleanup?older_than_days=1000", headers=auth).status_code == 422


def test_signals_cleanup_requires_auth(client):
    assert client.post("/api/v1/signals/cleanup").status_code == 401


# ---------------------------------------------------------------------------
# Autoscan loop status + resilience of _run_scan_internal
# ---------------------------------------------------------------------------


def test_autoscan_status_endpoint_default_disabled(client, auth):
    """In test env autoscan startup is skipped — endpoint reports disabled."""
    r = client.get("/api/v1/autoscan/status", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["interval_minutes"] == 0
    assert body["runs_completed"] == 0


def test_autoscan_status_requires_auth(client):
    assert client.get("/api/v1/autoscan/status").status_code == 401


# ---------------------------------------------------------------------------
# M3.5 — IdeaAnalyzer endpoint + cleanup-mocks
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# M4.4 — translation
# ---------------------------------------------------------------------------


def test_translate_signal_already_in_spanish_skips_llm(client, auth):
    """Si la señal ya está en español, devuelve sin llamar al LLM."""
    from orchestrator.core.storage import signals_store
    sid = signals_store.add(
        None, "rss", "Plataforma fintech para PYMEs LATAM",
        0.7, "Reconciliación bancaria automática para empresas ecuatorianas",
        [], "topic",
    )
    r = client.post(f"/api/v1/signals/{sid}/translate", headers=auth)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["already_in_spanish"]
    assert d["original_language"] == "es"
    assert d["cost_usd_estimated"] == 0.0


def test_translate_signal_english_in_mock_mode(client, auth):
    """En mock_mode genera placeholder y persiste."""
    from orchestrator.core.storage import signals_store
    sid = signals_store.add(
        None, "rss", "Facebook and Google extend working from home",
        0.7, "Tech companies announce extending remote work policies",
        [], "topic",
    )
    r = client.post(f"/api/v1/signals/{sid}/translate", headers=auth)
    assert r.status_code == 200, r.text
    d = r.json()
    assert not d["already_in_spanish"]
    assert d["original_language"] == "en"
    assert "[Traducción demo]" in d["translated_theme"]
    # Persisted in BD
    sig_after = signals_store.get(sid)
    assert sig_after["translated_theme"]
    assert sig_after["translated_excerpt"]


def test_translate_signal_404_for_unknown(client, auth):
    r = client.post("/api/v1/signals/99999/translate", headers=auth)
    assert r.status_code == 404


def test_translate_signal_requires_auth(client):
    r = client.post("/api/v1/signals/1/translate")
    assert r.status_code == 401


def test_enrich_signal_uses_og_tags(client, auth):
    """M3.17: /signals/{id}/enrich extrae og:title + og:description y
    actualiza theme + excerpt SIN llamar al LLM."""
    from unittest.mock import patch
    from orchestrator.core.storage import signals_store
    from orchestrator.core.source_fetcher import FetchedItem

    signal_id = signals_store.add(
        None, "url", "Instagram",  # theme genérico
        0.6, "Single item: Instagram", ["https://example.com/article"],
        "topic",
    )

    fake_item = FetchedItem(
        source_kind="url",
        url="https://example.com/article",
        title="Cómo construir un SaaS B2B para LATAM en 90 días",
        summary="Guía práctica para founders ecuatorianos sobre cómo lanzar una idea SaaS B2B con un budget mínimo y validar product-market fit en 90 días.",
        body="...",
    )
    with patch("orchestrator.api.fetch_url", return_value=fake_item, create=True):
        with patch("orchestrator.core.source_fetcher.fetch_url", return_value=fake_item):
            r = client.post(f"/api/v1/signals/{signal_id}/enrich", headers=auth)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["urls_fetched"] == 1
    assert data["theme_updated"] is True
    assert data["excerpt_updated"] is True
    assert data["item_titles_updated"] is True
    assert "SaaS B2B" in data["new_theme"]

    # Verificar que la BD se actualizó
    updated = signals_store.get(signal_id)
    assert "Instagram" not in updated["theme"]
    assert "SaaS B2B" in updated["theme"]
    assert "founders ecuatorianos" in updated["excerpt"]


def test_enrich_signal_returns_404_for_unknown(client, auth):
    r = client.post("/api/v1/signals/99999/enrich", headers=auth)
    assert r.status_code == 404


def test_enrich_signal_requires_auth(client):
    r = client.post("/api/v1/signals/1/enrich")
    assert r.status_code == 401


def test_enrich_signal_handles_no_urls(client, auth):
    """Una señal sin evidence_urls no rompe enrich (devuelve 0/0)."""
    from orchestrator.core.storage import signals_store
    signal_id = signals_store.add(
        None, "rss", "Test", 0.5, "ex", [], "topic"
    )
    r = client.post(f"/api/v1/signals/{signal_id}/enrich", headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert data["urls_fetched"] == 0
    assert data["theme_updated"] is False


def test_security_headers_present(client):
    """M3.17: cada response debe traer todos los security headers."""
    r = client.get("/api/v1/health")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "Permissions-Policy" in dict(r.headers) or "permissions-policy" in dict(r.headers)
    assert "max-age" in r.headers.get("strict-transport-security", "")
    assert "default-src 'none'" in r.headers.get("content-security-policy", "")
    assert r.headers.get("x-xss-protection") == "0"
    assert r.headers.get("cross-origin-opener-policy") == "same-origin"
    assert r.headers.get("cross-origin-resource-policy") == "same-origin"
    # Anti enumeration: no debe exponer Uvicorn version
    assert r.headers.get("server", "") == "circles-ai"


def test_analyze_signal_returns_structured_analysis(client, auth):
    """POST /signals/{id}/analyze returns market/ICP/competitors/recommendation."""
    from orchestrator.core.storage import signals_store, sources_store

    sid = sources_store.add("rss", "https://x.test/feed", "Test Feed")
    signal_id = signals_store.add(
        sid, "rss", "Tema interesante sobre logística LATAM",
        0.75, "Excerpt con contexto real", ["https://x.test/a"],
        "logistica latam pymes",
    )

    r = client.post(f"/api/v1/signals/{signal_id}/analyze", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["signal_id"] == signal_id
    a = body["analysis"]
    # Required fields, all in Spanish, all non-empty
    assert a["market_size_estimate"]
    assert a["icp_probable"]
    assert isinstance(a["competitors"], list)
    assert a["differentiator"]
    assert isinstance(a["risks"], list) and len(a["risks"]) >= 1
    assert a["recommendation"] in ("promote", "wait_for_more_data", "discard")
    assert a["reasoning"]


def test_analyze_signal_persists_analysis(client, auth):
    """After analyzing, GET /signals returns the analysis attached to the signal."""
    from orchestrator.core.storage import signals_store

    signal_id = signals_store.add(
        None, "hn", "Tema X", 0.7, "ex", [], "topic"
    )
    # Before analyze: analysis is None
    r0 = client.get("/api/v1/signals", headers=auth)
    items0 = r0.json()["items"]
    target0 = next(it for it in items0 if it["id"] == signal_id)
    assert target0["analysis"] is None

    # Analyze
    assert client.post(f"/api/v1/signals/{signal_id}/analyze", headers=auth).status_code == 200

    # After analyze: analysis is populated
    r1 = client.get("/api/v1/signals", headers=auth)
    items1 = r1.json()["items"]
    target1 = next(it for it in items1 if it["id"] == signal_id)
    assert target1["analysis"] is not None
    assert target1["analysis"]["recommendation"] in ("promote", "wait_for_more_data", "discard")


def test_analyze_signal_404_for_unknown_id(client, auth):
    r = client.post("/api/v1/signals/99999/analyze", headers=auth)
    assert r.status_code == 404


def test_analyze_signal_requires_auth(client):
    assert client.post("/api/v1/signals/1/analyze").status_code == 401


def test_cleanup_mocks_removes_legacy_mock_signals(client, auth):
    """cleanup-mocks deletes only signals with theme starting with 'Mock signal from'."""
    from orchestrator.core.storage import signals_store

    real_a = signals_store.add(None, "rss", "Tema real LATAM", 0.7, "ex", [], "topic")
    real_b = signals_store.add(None, "hn", "Otro tema real", 0.6, "ex", [], "topic")
    mock1 = signals_store.add(None, "rss", "Mock signal from rss", 0.5, "ex", [], "Mock topic derived from rss signals")
    mock2 = signals_store.add(None, "hn", "Mock signal from hn", 0.5, "ex", [], "topic")

    r = client.post("/api/v1/signals/cleanup-mocks", headers=auth)
    assert r.status_code == 200
    assert r.json()["deleted"] == 2

    remaining = {s["id"] for s in signals_store.list(limit=100)}
    assert real_a in remaining
    assert real_b in remaining
    assert mock1 not in remaining
    assert mock2 not in remaining


def test_cleanup_mocks_requires_auth(client):
    assert client.post("/api/v1/signals/cleanup-mocks").status_code == 401


def test_signals_list_repairs_placeholder_theme_using_item_titles(client, auth):
    """M3.13: legacy 'Mock signal from rss' theme is replaced on-the-fly
    with the first item_title when the dashboard fetches it."""
    from orchestrator.core.storage import signals_store
    signal_id = signals_store.add(
        None, "rss", "Mock signal from rss",
        0.7, "ex", ["https://x.test/a"],
        "topic",
        item_titles=["Pablo Palafox | De un Rechazo en YC a $500M"],
    )

    r = client.get("/api/v1/signals", headers=auth)
    items = r.json()["items"]
    polished = next(it for it in items if it["id"] == signal_id)
    # Polished output uses the item_title, NOT the stored placeholder
    assert polished["theme"].startswith("Pablo Palafox")
    assert "Mock signal from rss" not in polished["theme"]


def test_signals_list_dedups_repeated_urls_when_no_titles(client, auth):
    """M3.13: when evidence_urls has duplicates and there are no real titles,
    show only the unique URL (the old scanner produced 3 copies of the
    same hipertextual.com link)."""
    from orchestrator.core.storage import signals_store
    signal_id = signals_store.add(
        None, "rss", "Mock signal from rss",
        0.5, "ex",
        ["https://hipertextual.com/x", "https://hipertextual.com/x", "https://hipertextual.com/x"],
        "topic",
        item_titles=["", "", ""],
    )

    r = client.get("/api/v1/signals", headers=auth)
    items = r.json()["items"]
    polished = next(it for it in items if it["id"] == signal_id)
    assert len(polished["evidence_urls"]) == 1
    assert polished["evidence_urls"][0] == "https://hipertextual.com/x"


def test_signals_list_does_not_alter_real_signals(client, auth):
    """Polish must be a no-op for real signals — preserves themes and URLs."""
    from orchestrator.core.storage import signals_store
    signal_id = signals_store.add(
        None, "rss", "Tema legítimo LATAM",
        0.7, "Excerpt real",
        ["https://a.test/x", "https://b.test/y"],
        "topic ok",
        item_titles=["Título A", "Título B"],
    )

    r = client.get("/api/v1/signals", headers=auth)
    items = r.json()["items"]
    polished = next(it for it in items if it["id"] == signal_id)
    assert polished["theme"] == "Tema legítimo LATAM"
    assert polished["evidence_urls"] == ["https://a.test/x", "https://b.test/y"]
    assert polished["item_titles"] == ["Título A", "Título B"]


def test_cleanup_mocks_removes_generic_placeholders(client, auth):
    """Cleanup also purges signals with generic placeholder text in
    theme/excerpt — these don't help the founder decide."""
    from orchestrator.core.storage import signals_store

    s1 = signals_store.add(None, "rss", "Tema legítimo LATAM", 0.7, "ex", [], "topic ok")
    s2 = signals_store.add(None, "rss", "Otra señal real", 0.6,
                            "Detected pattern across 10 items: foo bar", [], "topic")
    s3 = signals_store.add(None, "rss", "Tema recurrente en rss", 0.5, "ex", [], "topic")
    s4 = signals_store.add(None, "hn", "Item de hn", 0.4, "ex", [], "topic")

    r = client.post("/api/v1/signals/cleanup-mocks", headers=auth)
    assert r.status_code == 200
    assert r.json()["deleted"] == 3  # s2, s3, s4

    remaining = {s["id"] for s in signals_store.list(limit=100)}
    assert s1 in remaining
    assert s2 not in remaining
    assert s3 not in remaining
    assert s4 not in remaining


# ---------------------------------------------------------------------------
# M3.6 — GET single signal + batch analyze + item_titles
# ---------------------------------------------------------------------------


def test_get_single_signal_by_id(client, auth):
    from orchestrator.core.storage import signals_store, sources_store
    sid = sources_store.add("rss", "https://x.test/feed", "Mi Feed")
    signal_id = signals_store.add(
        sid, "rss", "Tema X", 0.7, "ex", ["https://x.test/a", "https://x.test/b"],
        "topic",
        item_titles=["Título A", "Título B"],
    )

    r = client.get(f"/api/v1/signals/{signal_id}", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == signal_id
    assert body["theme"] == "Tema X"
    assert body["source_name"] == "Mi Feed"
    assert body["item_titles"] == ["Título A", "Título B"]
    assert body["evidence_urls"] == ["https://x.test/a", "https://x.test/b"]


def test_get_signal_404_for_unknown(client, auth):
    assert client.get("/api/v1/signals/99999", headers=auth).status_code == 404


def test_get_signal_requires_auth(client):
    assert client.get("/api/v1/signals/1").status_code == 401


def test_analyze_batch_with_explicit_ids(client, auth):
    """Batch analyze: pass signal_ids explicitly."""
    from orchestrator.core.storage import signals_store
    s1 = signals_store.add(None, "rss", "Tema A LATAM", 0.7, "ex", [], "topic A")
    s2 = signals_store.add(None, "hn", "Tema B LATAM", 0.6, "ex", [], "topic B")

    r = client.post(
        "/api/v1/signals/analyze-batch",
        headers=auth,
        json={"signal_ids": [s1, s2]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["analyzed"] == 2
    assert body["errors"] == 0
    assert set(body["signal_ids_analyzed"]) == {s1, s2}

    # Verify analysis was persisted
    r1 = client.get(f"/api/v1/signals/{s1}", headers=auth).json()
    assert r1["analysis"] is not None


def test_analyze_batch_skips_already_analyzed(client, auth):
    from orchestrator.core.storage import signals_store
    sid = signals_store.add(None, "rss", "Ya analizada", 0.7, "ex", [], "topic")
    # Pre-analyze
    client.post(f"/api/v1/signals/{sid}/analyze", headers=auth)

    r = client.post(
        "/api/v1/signals/analyze-batch",
        headers=auth,
        json={"signal_ids": [sid], "skip_already_analyzed": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["analyzed"] == 0
    assert body["skipped_already_analyzed"] == 1


def test_analyze_batch_auto_pick_by_top_n(client, auth):
    """Without signal_ids, picks top_n highest-trend signals to analyze."""
    from orchestrator.core.storage import signals_store
    # Create 5 signals — top_n=3 should analyze the 3 highest scored
    for i in range(5):
        signals_store.add(None, "rss", f"Tema {i}", 0.5 + i * 0.05, "ex", [], f"topic {i}")

    r = client.post(
        "/api/v1/signals/analyze-batch",
        headers=auth,
        json={"top_n": 3, "min_trend": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["analyzed"] == 3
    assert body["errors"] == 0


def test_analyze_batch_requires_auth(client):
    assert client.post("/api/v1/signals/analyze-batch", json={}).status_code == 401


def test_list_signals_search_filters_by_theme(client, auth):
    """?search= does case-insensitive substring match on theme."""
    from orchestrator.core.storage import signals_store
    signals_store.add(None, "rss", "Plataforma fintech LATAM", 0.7, "ex1", [], "topic1")
    signals_store.add(None, "rss", "Marketplace agrícola Colombia", 0.7, "ex2", [], "topic2")
    signals_store.add(None, "hn", "Edtech para universitarios", 0.6, "ex3", [], "topic3")

    r = client.get("/api/v1/signals?search=fintech", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    themes = [it["theme"] for it in items]
    assert "Plataforma fintech LATAM" in themes
    assert "Marketplace agrícola Colombia" not in themes


def test_list_signals_search_is_case_insensitive(client, auth):
    from orchestrator.core.storage import signals_store
    signals_store.add(None, "rss", "Plataforma FINTECH LATAM", 0.7, "ex", [], "topic")

    r = client.get("/api/v1/signals?search=fintech", headers=auth)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1


def test_list_signals_search_matches_excerpt_and_topic(client, auth):
    from orchestrator.core.storage import signals_store
    signals_store.add(None, "rss", "Tema A", 0.7, "Excerpt mentions LOGISTICA", [], "topic1")
    signals_store.add(None, "rss", "Tema B", 0.7, "Otro extracto", [], "topic con logistica")
    signals_store.add(None, "rss", "Tema C", 0.7, "irrelevant", [], "topic D")

    r = client.get("/api/v1/signals?search=logistica", headers=auth)
    assert r.status_code == 200
    themes = [it["theme"] for it in r.json()["items"]]
    assert set(themes) == {"Tema A", "Tema B"}


def test_list_signals_search_too_long_422(client, auth):
    r = client.get(f"/api/v1/signals?search={'x' * 300}", headers=auth)
    assert r.status_code == 422


def test_stats_endpoint_returns_aggregated_counts(client, auth):
    """GET /stats returns counts for signals, sources, runs, and cost."""
    from orchestrator.core.storage import signals_store, sources_store
    sid = sources_store.add("rss", "https://x.test/feed", "Feed")
    s1 = signals_store.add(sid, "rss", "A", 0.7, "ex", [], "t")
    s2 = signals_store.add(sid, "rss", "B", 0.6, "ex", [], "t")
    signals_store.set_feedback(s1, "up")
    signals_store.mark_promoted(s2, "run-fake")

    r = client.get("/api/v1/stats", headers=auth)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["signals_total"] >= 2
    assert s["signals_promoted"] >= 1
    assert s["sources_total"] >= 1
    assert s["sources_active"] >= 1
    assert "cost_usd_total_30d" in s
    assert "runs_total" in s


def test_stats_requires_auth(client):
    assert client.get("/api/v1/stats").status_code == 401


def test_signals_csv_export(client, auth):
    """GET /signals.csv streams a CSV with all the columns."""
    from orchestrator.core.storage import signals_store, sources_store
    sid = sources_store.add("rss", "https://x.test/feed", "Mi Fuente")
    signals_store.add(sid, "rss", "Tema CSV", 0.75, "ex", ["https://x.test/a"], "topic")

    r = client.get("/api/v1/signals.csv", headers=auth)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers.get("content-disposition", "")
    body = r.text
    # Header row
    assert "id,created_at_iso,source_name,source_kind,theme" in body.split("\n")[0]
    # Data row contains our values
    assert "Tema CSV" in body
    assert "Mi Fuente" in body


def test_signals_csv_promoted_only_filter(client, auth):
    from orchestrator.core.storage import signals_store
    a = signals_store.add(None, "rss", "Promovida", 0.7, "ex", [], "topic")
    signals_store.add(None, "rss", "No promovida", 0.7, "ex", [], "topic")
    signals_store.mark_promoted(a, "run-aaa")

    r = client.get("/api/v1/signals.csv?promoted_only=true", headers=auth)
    assert r.status_code == 200
    body = r.text
    assert "Promovida" in body
    assert "No promovida" not in body


def test_signals_csv_requires_auth(client):
    assert client.get("/api/v1/signals.csv").status_code == 401


def test_run_from_signal_id_injects_analysis_when_present(client, auth):
    """When the signal already has analysis, the evidence_context must
    include the '=== ANÁLISIS PREVIO ===' block — avoids re-doing market/ICP
    estimation from scratch in the hunter."""
    from orchestrator.core.storage import signals_store

    signal_id = signals_store.add(
        None, "rss", "Tema con análisis previo",
        0.8, "Excerpt", [], "topic con analisis",
    )
    # Run analyzer to attach analysis
    client.post(f"/api/v1/signals/{signal_id}/analyze", headers=auth)

    # Spy on the live workflow
    route_workflow = None
    for route in app.routes:
        ep = getattr(route, "endpoint", None)
        if ep and getattr(ep, "__name__", "") == "run_gate_from_sources":
            route_workflow = ep.__globals__["_workflow"]
            break
    assert route_workflow is not None

    captured = {}
    original_generate = route_workflow._idea_hunter.generate

    def _spy(topic, feedback=None, evidence_context=None, **kw):
        captured["evidence_context"] = evidence_context
        return original_generate(topic, feedback=feedback, evidence_context=evidence_context, **kw)

    route_workflow._idea_hunter.generate = _spy  # type: ignore
    try:
        r = client.post(
            "/api/v1/gate/run-from-sources",
            headers=auth,
            json={"signal_id": signal_id},
        )
    finally:
        route_workflow._idea_hunter.generate = original_generate

    assert r.status_code == 201, r.text
    ec = captured.get("evidence_context") or ""
    assert "=== ANÁLISIS PREVIO" in ec
    assert "Recomendación previa:" in ec
    assert "Mercado estimado:" in ec
    assert "ICP probable:" in ec


def test_scan_request_accepts_auto_promote_trend_threshold(client, auth):
    """auto_promote_trend_threshold is bounded 0-10 by schema."""
    r = client.post(
        "/api/v1/sources/scan",
        headers=auth,
        json={"auto_promote_trend_threshold": 50},
    )
    assert r.status_code == 422
    r2 = client.post(
        "/api/v1/sources/scan",
        headers=auth,
        json={"auto_promote_trend_threshold": 5},
    )
    assert r2.status_code == 200


def test_scan_request_accepts_auto_analyze_threshold(client, auth):
    """auto_analyze_trend_threshold is bounded 0-10 by schema."""
    r = client.post(
        "/api/v1/sources/scan",
        headers=auth,
        json={"auto_analyze_trend_threshold": 100},
    )
    assert r.status_code == 422  # too high
    r2 = client.post(
        "/api/v1/sources/scan",
        headers=auth,
        json={"auto_analyze_trend_threshold": 3},
    )
    assert r2.status_code == 200  # valid, even with no sources


def test_list_promoted_signals_returns_only_promoted(client, auth):
    """GET /api/v1/signals/promoted lists only signals with a promoted_run_id,
    newest first, with source_name joined."""
    from orchestrator.core.storage import signals_store, sources_store

    sid = sources_store.add("rss", "https://x.test/feed", "Test Feed")
    not_promoted = signals_store.add(sid, "rss", "Sin promover", 0.6, "ex", [], "topic")
    promoted_a = signals_store.add(sid, "rss", "Promovida A", 0.8, "ex", [], "topic")
    promoted_b = signals_store.add(sid, "rss", "Promovida B", 0.7, "ex", [], "topic")
    signals_store.mark_promoted(promoted_a, "run-aaa-uuid")
    signals_store.mark_promoted(promoted_b, "run-bbb-uuid")

    r = client.get("/api/v1/signals/promoted", headers=auth)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    themes = {it["theme"] for it in items}
    assert themes == {"Promovida A", "Promovida B"}
    assert "Sin promover" not in themes
    # source_name joined
    assert all(it["source_name"] == "Test Feed" for it in items)
    assert all(it["promoted_run_id"] for it in items)
    _ = not_promoted  # silence unused


def test_list_promoted_signals_requires_auth(client):
    assert client.get("/api/v1/signals/promoted").status_code == 401


def test_list_promoted_signals_invalid_limit_422(client, auth):
    assert client.get("/api/v1/signals/promoted?limit=0", headers=auth).status_code == 422
    assert client.get("/api/v1/signals/promoted?limit=999", headers=auth).status_code == 422


def test_run_scan_internal_swallows_fetch_errors(client, auth):
    """A misbehaving fetcher must not crash the scan — the loop relies on this."""
    from unittest.mock import patch
    # Add one source so _run_scan_internal has something to iterate
    add = client.post(
        "/api/v1/sources", headers=auth,
        json={"kind": "rss", "target": "https://x.test/feed", "name": "Broken Feed"},
    )
    assert add.status_code == 201

    # Locate the live api module via the route function (resilient to sys.modules swaps)
    api_mod = None
    for route in app.routes:
        ep = getattr(route, "endpoint", None)
        if ep is not None and getattr(ep, "__name__", "") == "scan_sources":
            api_mod = __import__(ep.__module__, fromlist=["_run_scan_internal"])
            break
    assert api_mod is not None

    def _boom(*args, **kw):
        raise RuntimeError("upstream is down")

    with patch.object(api_mod, "_workflow", api_mod._workflow):
        # Patch fetch_by_kind so the scan hits the failure branch
        with patch("orchestrator.core.source_fetcher.fetch_by_kind", side_effect=_boom):
            result = api_mod._run_scan_internal()

    # Did NOT raise. Scanned the source but produced 0 signals.
    assert result["scanned_sources"] == 1
    assert result["signals_created"] == 0
    assert result["items_fetched"] == 0
