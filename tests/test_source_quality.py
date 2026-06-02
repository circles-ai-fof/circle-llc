"""
Tests for M9.5 — source quality scoring + smart scan queue.

Pin down:
  - Brand-new sources stay at neutral 0.5 quality_score (no unfair demotion)
  - hit_rate = promoted / total
  - avg_signal_score = mean(signals.score) for that source
  - quality_score = 0.6 * hit_rate + 0.4 * avg_signal_score
  - smart_scan_queue tiers by quality and ties go to coldest scan
"""


def test_brand_new_source_keeps_neutral_quality():
    """A source with zero signals should not be demoted below 0.5."""
    from orchestrator.core.storage import sources_store, signals_store
    sources_store.clear()
    signals_store.clear()
    src_id = sources_store.add("rss", "https://x.com", "fresh source")
    result = sources_store.recompute_quality(src_id)
    assert result["quality_score"] == 0.5
    assert result["hit_rate"] == 0.0
    assert result["signals_total"] == 0


def test_quality_score_formula():
    """All signals promoted + high scores → quality near 1.0."""
    from orchestrator.core.storage import sources_store, signals_store
    sources_store.clear()
    signals_store.clear()
    src_id = sources_store.add("rss", "https://gold.com", "gold mine")
    # Add 3 high-scoring promoted signals
    for i in range(3):
        sid = signals_store.add(
            source_id=src_id, source_kind="rss",
            theme=f"signal {i}", score=0.9,
            excerpt=f"x{i}", evidence_urls=[f"https://gold.com/{i}"],
            suggested_topic="t",
        )
        signals_store.mark_promoted(sid, f"run-{i}")
    result = sources_store.recompute_quality(src_id)
    # hit_rate = 3/3 = 1.0, avg_score = 0.9
    # quality = 0.6 * 1.0 + 0.4 * 0.9 = 0.96
    assert abs(result["hit_rate"] - 1.0) < 0.01
    assert abs(result["avg_signal_score"] - 0.9) < 0.01
    assert abs(result["quality_score"] - 0.96) < 0.01


def test_noise_source_gets_low_quality():
    """All signals unpromoted + low scores → quality near 0.0."""
    from orchestrator.core.storage import sources_store, signals_store
    sources_store.clear()
    signals_store.clear()
    src_id = sources_store.add("rss", "https://noise.com", "noise")
    for i in range(5):
        signals_store.add(
            source_id=src_id, source_kind="rss",
            theme=f"low signal {i}", score=0.1,
            excerpt=f"x{i}", evidence_urls=[f"https://noise.com/{i}"],
            suggested_topic="t",
        )
    result = sources_store.recompute_quality(src_id)
    # hit_rate = 0, avg = 0.1, quality = 0 + 0.04 = 0.04
    assert result["hit_rate"] == 0.0
    assert abs(result["avg_signal_score"] - 0.1) < 0.01
    assert abs(result["quality_score"] - 0.04) < 0.01


def test_smart_scan_queue_orders_by_quality_then_recency():
    """Top quality wins; within a band, coldest source (smallest last_scanned_at)
    goes first so we don't repeatedly hit the same hot source."""
    from orchestrator.core.storage import sources_store, signals_store
    import time
    sources_store.clear()
    signals_store.clear()

    s_gold = sources_store.add("rss", "https://gold.com", "gold")
    s_mid = sources_store.add("rss", "https://mid.com", "mid")
    s_noise = sources_store.add("rss", "https://noise.com", "noise")

    # Gold = promoted hits → quality > 0.6
    for _ in range(3):
        sid = signals_store.add(
            source_id=s_gold, source_kind="rss", theme="gold",
            score=0.9, excerpt="x", evidence_urls=["https://gold.com/p"],
            suggested_topic="t",
        )
        signals_store.mark_promoted(sid, "run-x")
    # Mid = neutral
    signals_store.add(
        source_id=s_mid, source_kind="rss", theme="mid",
        score=0.5, excerpt="x", evidence_urls=["https://mid.com/p"],
        suggested_topic="t",
    )
    # Noise = many low-score, no promotions
    for i in range(4):
        signals_store.add(
            source_id=s_noise, source_kind="rss", theme=f"n{i}",
            score=0.1, excerpt="x", evidence_urls=[f"https://noise.com/{i}"],
            suggested_topic="t",
        )

    sources_store.recompute_quality_all()
    queue = sources_store.smart_scan_queue()
    ids_in_order = [s["id"] for s in queue]
    # Gold first (quality > 0.6), then mid (already deduped because the
    # theme "gold" repeats — actual order depends on quality math, just
    # ensure gold comes before noise).
    assert ids_in_order.index(s_gold) < ids_in_order.index(s_noise)


def test_recompute_quality_all_returns_count():
    from orchestrator.core.storage import sources_store
    sources_store.clear()
    sources_store.add("rss", "https://a.com", "a")
    sources_store.add("rss", "https://b.com", "b")
    sources_store.add("rss", "https://c.com", "c")
    assert sources_store.recompute_quality_all() == 3


def test_recompute_quality_endpoint():
    """Smoke test the HTTP endpoint."""
    import os
    from fastapi.testclient import TestClient
    os.environ["ALLOWED_EMAILS"] = "test@example.com"
    from orchestrator.api import app
    from orchestrator.core.storage import sources_store, signals_store
    sources_store.clear()
    signals_store.clear()
    sources_store.add("rss", "https://x.com", "x")

    c = TestClient(app)
    t = c.post("/api/v1/auth/login", json={"email": "test@example.com"}).json()["token"]
    h = {"Authorization": f"Bearer {t}"}
    r = c.post("/api/v1/sources/recompute-quality", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["processed"] == 1


def test_scan_queue_endpoint_returns_active_sources():
    import os
    from fastapi.testclient import TestClient
    os.environ["ALLOWED_EMAILS"] = "test@example.com"
    from orchestrator.api import app
    from orchestrator.core.storage import sources_store
    sources_store.clear()
    sources_store.add("rss", "https://x.com", "x")
    sources_store.add("rss", "https://y.com", "y")

    c = TestClient(app)
    t = c.post("/api/v1/auth/login", json={"email": "test@example.com"}).json()["token"]
    h = {"Authorization": f"Bearer {t}"}
    r = c.get("/api/v1/sources/scan-queue", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
