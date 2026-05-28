"""
M4.1 / ADR-019 — tests del módulo de preferences.

Cubrimos el modo FALLBACK (sin sentence-transformers ni hdbscan). En CI no
queremos descargar 500MB de deps; los tests se enfocan en la correctness de
la pipeline, no en la calidad semántica del embedding.
"""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def pref():
    return importlib.import_module("orchestrator.core.preferences")


# ---------------------------------------------------------------------------
# Engine detection
# ---------------------------------------------------------------------------


def test_engine_info_reports_mode(pref):
    info = pref.get_engine_info()
    assert info["mode"] in ("real", "fallback")
    assert "notes" in info


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


def test_embedding_has_correct_dim(pref):
    v = pref.compute_embedding("fintech LATAM")
    assert len(v) == pref.EMBEDDING_DIM


def test_embedding_is_deterministic(pref):
    v1 = pref.compute_embedding("idea de negocio en Ecuador")
    v2 = pref.compute_embedding("idea de negocio en Ecuador")
    assert v1 == v2


def test_embedding_empty_text_returns_zero_vector(pref):
    v = pref.compute_embedding("")
    assert all(x == 0.0 for x in v)


def test_embedding_no_nan_or_inf(pref):
    import math
    v = pref.compute_embedding("fintech para PYMEs Ecuador con muchas palabras y acentos")
    assert all(math.isfinite(x) for x in v)
    # L2-normalized
    norm = sum(x * x for x in v) ** 0.5
    assert 0.99 < norm < 1.01


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------


def test_cosine_sim_self_is_high(pref):
    v = pref.compute_embedding("marketplace agrícola Colombia")
    assert pref.cosine_sim(v, v) > 0.99


def test_cosine_sim_shared_words_correlates(pref):
    """Frases con palabras compartidas tienen mayor sim que sin compartir.
    En fallback determinista no es semántico pero la palabra común aporta."""
    a = pref.compute_embedding("fintech para PYMEs Ecuador")
    b = pref.compute_embedding("fintech para PYMEs Colombia")
    c = pref.compute_embedding("receta de ceviche peruano")
    sim_ab = pref.cosine_sim(a, b)
    sim_ac = pref.cosine_sim(a, c)
    assert sim_ab > sim_ac  # shared "fintech para PYMEs" makes a/b closer


def test_cosine_sim_empty_returns_zero(pref):
    assert pref.cosine_sim([], [1.0, 2.0]) == 0.0
    assert pref.cosine_sim([1.0, 2.0], [1.0]) == 0.0  # mismatched dims


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def test_score_neutral_without_history(pref):
    v = pref.compute_embedding("idea X")
    assert pref.score_against_feedback(v, [], []) == 0.5


def test_score_higher_when_similar_to_positives(pref):
    cand = pref.compute_embedding("fintech PYMEs LATAM")
    pos = [pref.compute_embedding("fintech para empresas LATAM")]
    neg = [pref.compute_embedding("recetas de cocina")]
    score = pref.score_against_feedback(cand, pos, neg)
    assert score > 0.5


def test_score_in_zero_one_range(pref):
    v = pref.compute_embedding("test")
    s = pref.score_against_feedback(v, [v, v], [pref.compute_embedding("nada")])
    assert 0.0 <= s <= 1.0


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------


def test_clustering_returns_label_per_input(pref):
    vecs = [pref.compute_embedding(f"texto {i}") for i in range(5)]
    labels = pref.cluster_embeddings(vecs)
    assert len(labels) == 5


def test_clustering_handles_empty(pref):
    assert pref.cluster_embeddings([]) == []


def test_clustering_deterministic_in_fallback(pref):
    vecs = [pref.compute_embedding(f"texto {i}") for i in range(5)]
    labels1 = pref.cluster_embeddings(vecs)
    labels2 = pref.cluster_embeddings(vecs)
    assert labels1 == labels2


# ---------------------------------------------------------------------------
# Keyword extraction
# ---------------------------------------------------------------------------


def test_keywords_filters_stopwords(pref):
    texts = ["el fintech para las PYMEs ecuatorianas con un producto B2B"]
    kw = pref.extract_keywords(texts, top_n=5)
    assert "fintech" in kw or "pymes" in kw or "producto" in kw
    # Spanish stopwords filtered
    assert "el" not in kw
    assert "para" not in kw
    assert "las" not in kw


def test_keywords_empty_returns_empty(pref):
    assert pref.extract_keywords([]) == []


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------


def test_suggestions_use_keywords_from_clusters(pref):
    cluster_texts = {
        5: [
            "fintech para PYMEs Ecuador reconciliación bancaria",
            "fintech automática para empresas LATAM",
            "reconciliación contable PYMEs Colombia",
        ],
        7: ["receta de pastel de chocolate", "cómo hacer flan"],  # too small + off-topic
        -1: ["ruido sin cluster"],
    }
    suggestions = pref.suggest_sources_from_clusters(cluster_texts, max_suggestions=3)
    # Cluster 5 makes the cut (≥2 elements)
    cluster_ids = [s["cluster_id"] for s in suggestions]
    assert 5 in cluster_ids
    assert -1 not in cluster_ids  # noise cluster ignored
    s5 = next(s for s in suggestions if s["cluster_id"] == 5)
    assert "fintech" in s5["keywords"] or "pymes" in s5["keywords"]
    assert s5["suggested_query"]
    assert s5["rationale"]


def test_suggestions_skip_singleton_clusters(pref):
    # A cluster with 1 text doesn't generate suggestions
    cluster_texts = {1: ["single text"]}
    assert pref.suggest_sources_from_clusters(cluster_texts) == []


def test_suggestions_respect_max_count(pref):
    cluster_texts = {
        i: [f"text a {i}", f"text b {i}", f"text c {i}"]
        for i in range(10)
    }
    suggestions = pref.suggest_sources_from_clusters(cluster_texts, max_suggestions=3)
    assert len(suggestions) == 3
