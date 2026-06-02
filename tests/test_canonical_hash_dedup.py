"""
Tests for M9.3 — canonical_hash dedup across sources.

When the same idea appears in Lovable AND ProductHunt AND HN we used to insert
3 separate signals (cosmetic dupes). M9.3 collapses them to ONE signal and
increments `times_seen` so the founder sees "this appeared in 3 sources" as a
hype indicator instead of 3 rows of identical content cluttering the view.

We pin down:
  - URL canonicalization (utm strip, www strip, trailing slash, port, fragment)
  - Hash stability across cosmetic variants
  - The dedup path actually skips the insert and bumps times_seen
  - Different ideas don't collide on the truncation boundary
"""
from orchestrator.core.storage import _canonical_hash, _canonicalize_url


# ---------------------------------------------------------------------------
# URL canonicalization
# ---------------------------------------------------------------------------

def test_canonicalize_url_strips_utm_params():
    base = "https://example.com/article"
    tagged = "https://example.com/article?utm_source=hn&utm_medium=feed"
    assert _canonicalize_url(base) == _canonicalize_url(tagged)


def test_canonicalize_url_strips_www():
    a = _canonicalize_url("https://www.openai.com/blog/dev-day")
    b = _canonicalize_url("https://openai.com/blog/dev-day")
    assert a == b


def test_canonicalize_url_strips_trailing_slash():
    a = _canonicalize_url("https://anthropic.com/news/")
    b = _canonicalize_url("https://anthropic.com/news")
    assert a == b


def test_canonicalize_url_strips_fragment_and_port():
    a = _canonicalize_url("https://example.com:443/article#top")
    b = _canonicalize_url("https://example.com/article")
    assert a == b


def test_canonicalize_url_lowercases_host_but_keeps_distinct_paths():
    """Distinct paths must stay distinct even after lowercasing host."""
    a = _canonicalize_url("https://GitHub.com/anthropics/claude")
    b = _canonicalize_url("https://github.com/anthropics/agents")
    assert a != b


def test_canonicalize_url_handles_empty_and_malformed():
    assert _canonicalize_url("") == ""
    assert _canonicalize_url("not a url") == "not a url"


def test_canonicalize_url_strips_gclid_and_fbclid():
    """gclid / fbclid are tracking params and must be stripped so the same
    article doesn't show up twice based on click attribution alone."""
    base = "https://shop.example.com/product"
    bare = _canonicalize_url(base)
    a = _canonicalize_url(f"{base}?gclid=ABC123")
    b = _canonicalize_url(f"{base}?fbclid=XYZ789")
    assert a == bare == b
    # And no leftover gclid/fbclid in the canonical form
    assert "gclid" not in a
    assert "fbclid" not in b


def test_canonicalize_url_keeps_meaningful_query_params():
    """Non-tracking params (id, q, page) must survive canonicalization."""
    canonical = _canonicalize_url("https://example.com/search?q=fintech&page=2")
    assert "q=fintech" in canonical
    assert "page=2" in canonical


# ---------------------------------------------------------------------------
# canonical_hash stability
# ---------------------------------------------------------------------------

def test_hash_stable_for_cosmetic_url_variants():
    """The same article with different tracking should produce the same hash."""
    h1 = _canonical_hash(
        "Anthropic launches Claude Sonnet 4.7",
        ["https://www.anthropic.com/news/sonnet-47?utm_source=hn"],
    )
    h2 = _canonical_hash(
        "Anthropic launches Claude Sonnet 4.7",
        ["https://anthropic.com/news/sonnet-47/"],
    )
    assert h1 == h2


def test_hash_stable_for_case_differences_in_title():
    h1 = _canonical_hash("Vibe Coding Apps Trending", ["https://lovable.app/x"])
    h2 = _canonical_hash("VIBE CODING APPS TRENDING", ["https://lovable.app/x"])
    assert h1 == h2


def test_hash_distinct_for_different_ideas_same_url_host():
    """Same host, different paths/titles → different hashes."""
    h1 = _canonical_hash("Idea A", ["https://github.com/foo/a"])
    h2 = _canonical_hash("Idea B", ["https://github.com/foo/b"])
    assert h1 != h2


def test_hash_distinct_for_different_titles_no_url():
    """Without an evidence URL, the title alone differentiates ideas."""
    h1 = _canonical_hash("AI agent for finance", [])
    h2 = _canonical_hash("AI agent for healthcare", [])
    assert h1 != h2


def test_hash_collapses_long_titles_at_120_chars():
    """Titles past 120 chars are truncated — two articles that diverge only
    after char 120 should collide. This is intentional: long-tail tracking
    text shouldn't fragment dedup."""
    prefix = "Anthropic releases major model upgrade with new tools and improved reasoning capabilities across all task domains"
    assert len(prefix) > 110
    h1 = _canonical_hash(prefix + "  — Source A", ["https://x.com/a"])
    h2 = _canonical_hash(prefix + "  — Source B (different suffix)", ["https://x.com/a"])
    # Same prefix + same URL = same hash even with different suffixes
    assert h1 == h2


def test_hash_is_16_chars_hex():
    """Document the hash format so downstream code can rely on it."""
    h = _canonical_hash("test", ["https://example.com"])
    assert len(h) == 16
    int(h, 16)  # raises if not hex


# ---------------------------------------------------------------------------
# Dedup path on SignalsStore.add
# ---------------------------------------------------------------------------

def test_signals_store_dedup_returns_same_id():
    """When the same idea is added twice, the second add returns the FIRST id
    instead of creating a new row. times_seen on the existing row is bumped."""
    from orchestrator.core.storage import SignalsStore, signals_store

    signals_store.clear()
    store = signals_store

    id1 = store.add(
        source_id=1,
        source_kind="rss",
        theme="Claude Sonnet 4.7 launches",
        score=0.85,
        excerpt="Anthropic unveiled the next-gen Claude.",
        evidence_urls=["https://anthropic.com/news/sonnet-47"],
        suggested_topic="AI launches",
    )
    # Same idea, different source_kind (would be 2 dupes pre-M9.3)
    id2 = store.add(
        source_id=2,
        source_kind="hn",
        theme="Claude Sonnet 4.7 launches",
        score=0.90,
        excerpt="Anthropic just dropped Sonnet 4.7.",
        evidence_urls=["https://www.anthropic.com/news/sonnet-47/?utm_source=hn"],
        suggested_topic="AI launches",
    )
    assert id1 == id2, "expected the second add to return the existing id"


def test_signals_store_dedup_bumps_times_seen():
    """Each repeat increments times_seen so we can rank by 'hype' score."""
    from orchestrator.core.storage import signals_store

    signals_store.clear()
    id_ = signals_store.add(
        source_id=1, source_kind="rss",
        theme="Niche app trending",
        score=0.7, excerpt="x",
        evidence_urls=["https://example.com/niche"],
        suggested_topic="t",
    )
    for _ in range(4):
        signals_store.add(
            source_id=99, source_kind="reddit",
            theme="Niche app trending",
            score=0.7, excerpt="y",
            evidence_urls=["https://example.com/niche?utm_source=reddit"],
            suggested_topic="t",
        )
    s = signals_store.get(id_)
    assert s is not None
    # Started at 1, then 4 dedup bumps → 5
    assert int(s.get("times_seen", 0)) == 5


def test_signals_store_distinct_ideas_do_not_dedup():
    """Sanity: two genuinely different ideas remain 2 rows."""
    from orchestrator.core.storage import signals_store

    signals_store.clear()
    id1 = signals_store.add(
        source_id=1, source_kind="rss", theme="Fintech LATAM",
        score=0.8, excerpt="x", evidence_urls=["https://a.com/1"], suggested_topic="t",
    )
    id2 = signals_store.add(
        source_id=2, source_kind="rss", theme="Agtech LATAM",
        score=0.8, excerpt="y", evidence_urls=["https://b.com/2"], suggested_topic="t",
    )
    assert id1 != id2
