"""
Tests for M12.0 — Pain-phrase booster.

Pin down:
  - English patterns match common pain phrases
  - Spanish patterns match common pain phrases
  - No pain phrases → score unchanged
  - Boost capped (max +0.30 of original)
  - Duplicate label not double-counted (avoids "I wish I wish I wish" gaming)
  - Score never exceeds 1.0 even with high base + many matches
  - SignalsStore.add applies the boost end-to-end
  - Audit trail (snippet) included in matches
"""


# ---------------------------------------------------------------------------
# English patterns
# ---------------------------------------------------------------------------

def test_detects_wish_there_was():
    from orchestrator.core.pain_phrases import detect_pain_phrases
    m = detect_pain_phrases("I wish there was a tool that could do this for me")
    assert len(m) >= 1
    assert any("wish-there-was" == x.label for x in m)


def test_detects_why_is_there_no():
    from orchestrator.core.pain_phrases import detect_pain_phrases
    m = detect_pain_phrases("Why is there no decent tool for syncing my notes?")
    assert any("why-is-there-no" == x.label for x in m)


def test_detects_anyone_know_a_tool():
    from orchestrator.core.pain_phrases import detect_pain_phrases
    m = detect_pain_phrases("Anyone know of a tool for batch resizing images?")
    labels = {x.label for x in m}
    assert "anyone-know-a-tool" in labels


def test_detects_i_hate_that():
    from orchestrator.core.pain_phrases import detect_pain_phrases
    m = detect_pain_phrases("I hate that there's no shortcut for this")
    assert any("i-hate-that" == x.label for x in m)


def test_detects_would_pay():
    from orchestrator.core.pain_phrases import detect_pain_phrases
    m = detect_pain_phrases("I would pay for an app that does this automatically")
    assert any("would-pay-for" == x.label for x in m)


def test_detects_manual_pain():
    from orchestrator.core.pain_phrases import detect_pain_phrases
    m = detect_pain_phrases("Right now I'm manually copying entries between sheets")
    assert any("manual-pain" == x.label for x in m)


# ---------------------------------------------------------------------------
# Spanish patterns
# ---------------------------------------------------------------------------

def test_detects_ojala_existiera():
    from orchestrator.core.pain_phrases import detect_pain_phrases
    m = detect_pain_phrases("Ojalá existiera una app que me organizara las facturas")
    assert any(x.label == "ojala-existiera" for x in m)
    assert all(x.language == "es" for x in m if x.label == "ojala-existiera")


def test_detects_por_que_no_existe():
    from orchestrator.core.pain_phrases import detect_pain_phrases
    m = detect_pain_phrases("¿Por qué no existe una herramienta para esto en LATAM?")
    assert any("por-que-no-existe" == x.label for x in m)


def test_detects_alguien_conoce():
    from orchestrator.core.pain_phrases import detect_pain_phrases
    m = detect_pain_phrases("Alguien conoce una herramienta para hacer reconciliación bancaria?")
    assert any("alguien-conoce-tool" == x.label for x in m)


def test_detects_odio_que():
    from orchestrator.core.pain_phrases import detect_pain_phrases
    m = detect_pain_phrases("Odio que tenga que abrir 5 apps para esto")
    assert any("odio-que" == x.label for x in m)


def test_detects_pagaria_por():
    from orchestrator.core.pain_phrases import detect_pain_phrases
    m = detect_pain_phrases("Pagaría por algo que me resuelva esto en un click")
    assert any("pagaria-por" == x.label for x in m)


# ---------------------------------------------------------------------------
# Boost math
# ---------------------------------------------------------------------------

def test_no_match_returns_score_unchanged():
    from orchestrator.core.pain_phrases import apply_boost
    new, matches = apply_boost(0.7, "A neutral announcement about a product launch")
    assert new == 0.7
    assert matches == []


def test_single_match_boosts_by_10pct():
    from orchestrator.core.pain_phrases import apply_boost, PAIN_BOOST_PER_MATCH
    new, matches = apply_boost(0.5, "I wish there was a fix for this")
    expected = 0.5 * (1.0 + PAIN_BOOST_PER_MATCH)
    assert abs(new - expected) < 0.001
    assert len(matches) >= 1


def test_multiple_unique_labels_stack():
    from orchestrator.core.pain_phrases import apply_boost
    # 3 distinct labels → 3 × 0.10 = +30% (which equals the cap)
    text = (
        "I wish there was a tool for X. "
        "Why is there no decent solution? "
        "I would pay for it tomorrow."
    )
    new, matches = apply_boost(0.5, text)
    labels = {m.label for m in matches}
    assert len(labels) >= 3
    assert new > 0.5 * 1.20  # boosted noticeably


def test_boost_capped_at_max():
    from orchestrator.core.pain_phrases import apply_boost, MAX_BOOST
    # Force many distinct labels — boost should NOT exceed MAX_BOOST.
    text = (
        "I wish there was. Why is there no. Anyone know a tool. "
        "I hate that. Would pay for. Biggest pain. Struggling with. "
        "Wasting time. Manually doing."
    )
    new, _matches = apply_boost(0.5, text)
    assert new <= 0.5 * (1.0 + MAX_BOOST) + 0.001  # epsilon for fp


def test_boost_does_not_exceed_one():
    from orchestrator.core.pain_phrases import apply_boost
    new, _ = apply_boost(0.95, "I wish there was. Why is there no. Would pay for.")
    assert new <= 1.0


def test_same_label_repeated_counts_once():
    """Defense against gaming: 5x 'i wish there was' doesn't 5x the boost."""
    from orchestrator.core.pain_phrases import apply_boost, PAIN_BOOST_PER_MATCH
    text = " ".join(["I wish there was a fix."] * 5)
    new, _ = apply_boost(0.5, text)
    expected = 0.5 * (1.0 + PAIN_BOOST_PER_MATCH)  # 1 unique label
    assert abs(new - expected) < 0.01


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

def test_match_includes_snippet_for_audit_trail():
    """Founders should be able to see WHY a signal was boosted, not just
    '+20%' with no context."""
    from orchestrator.core.pain_phrases import detect_pain_phrases
    text = "Just earlier today I wish there was a way to skip this step automatically"
    matches = detect_pain_phrases(text)
    assert any("wish" in m.snippet.lower() for m in matches)
    # Snippet should be bounded so it doesn't blow up logs
    for m in matches:
        assert len(m.snippet) <= 160


# ---------------------------------------------------------------------------
# Integration with SignalsStore.add
# ---------------------------------------------------------------------------

def test_signals_store_applies_pain_boost():
    """End-to-end: a signal with pain text gets a higher stored score than
    its base score. Without pain phrases, score stored as-is."""
    from orchestrator.core.storage import signals_store
    signals_store.clear()

    # Without pain phrases
    sid_neutral = signals_store.add(
        source_id=1, source_kind="rss",
        theme="Company launches new product version",
        score=0.5,
        excerpt="Press release about the latest update.",
        evidence_urls=["https://example.com/a"],
        suggested_topic="ai",
    )
    neutral = signals_store.get(sid_neutral)
    assert abs(neutral["score"] - 0.5) < 0.001

    # With explicit pain phrases
    sid_pain = signals_store.add(
        source_id=1, source_kind="reddit",
        theme="Why is there no good tool for this?",
        score=0.5,
        excerpt="I wish there was an app I could use for batch resizing. "
                "I would pay for it. Anyone know of a tool?",
        evidence_urls=["https://reddit.com/r/x/2"],
        suggested_topic="dev-tools",
    )
    pained = signals_store.get(sid_pain)
    assert pained["score"] > neutral["score"]
    # And capped at 1.0
    assert pained["score"] <= 1.0
