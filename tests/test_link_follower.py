"""
Tests for M10.0 — LinkFollowerAgent.

Three discovery patterns are pinned down by tests:

  1. github.com/<owner>/<repo>/... → propose releases.atom RSS
  2. reddit.com/r/<sub>/...        → propose `reddit` source kind
  3. <link rel="alternate" type="application/rss+xml">  → propose RSS

Plus integration:
  - Agent dedups across multiple evidence URLs (same target proposed only once)
  - Agent doesn't crash if HTML fetch fails — pattern proposals still surface
  - HTTP endpoint runs end-to-end on a signal in the store
"""
from orchestrator.agents.link_follower import (
    LinkFollowerAgent,
    ProposedSource,
    detect_github_releases,
    detect_reddit_subreddit,
    extract_rss_links_from_html,
)


# ---------------------------------------------------------------------------
# github_releases detector
# ---------------------------------------------------------------------------

def test_github_repo_url_proposes_releases_atom():
    p = detect_github_releases("https://github.com/anthropics/claude-code")
    assert p is not None
    assert p.kind == "rss"
    assert p.target == "https://github.com/anthropics/claude-code/releases.atom"
    assert "anthropics/claude-code" in p.name
    assert p.score >= 0.7


def test_github_repo_with_extra_path_still_proposes_root():
    """A link to /releases/tag/v1 still proposes the repo's root releases.atom."""
    p = detect_github_releases(
        "https://github.com/openai/openai-python/releases/tag/v2.0.0"
    )
    assert p is not None
    assert p.target.endswith("/openai/openai-python/releases.atom")


def test_github_profile_url_is_ignored():
    """github.com/<user> alone (no repo) should NOT propose anything."""
    p = detect_github_releases("https://github.com/anthropics")
    # The regex doesn't match a single-segment path
    assert p is None


def test_github_meta_paths_ignored():
    """Reserved paths like /settings or /marketplace are not real repos."""
    for path in ("settings", "marketplace", "explore", "topics"):
        p = detect_github_releases(f"https://github.com/foo/{path}")
        assert p is None, f"expected None for /foo/{path}"


def test_non_github_url_returns_none():
    assert detect_github_releases("https://example.com/repo") is None


def test_github_detector_handles_malformed_url():
    assert detect_github_releases("not a url at all") is None
    assert detect_github_releases("") is None


# ---------------------------------------------------------------------------
# reddit subreddit detector
# ---------------------------------------------------------------------------

def test_reddit_post_url_proposes_subreddit():
    p = detect_reddit_subreddit(
        "https://reddit.com/r/SaaS/comments/abc123/my_launch/"
    )
    assert p is not None
    assert p.kind == "reddit"
    assert p.target == "SaaS"
    assert "r/SaaS" in p.name


def test_reddit_with_www_subdomain():
    p = detect_reddit_subreddit("https://www.reddit.com/r/startups/")
    assert p is not None
    assert p.target == "startups"


def test_reddit_meta_paths_ignored():
    """/r/all, /r/popular, /r/random are not real subreddits."""
    for sub in ("all", "popular", "random"):
        p = detect_reddit_subreddit(f"https://reddit.com/r/{sub}/hot")
        assert p is None


def test_non_reddit_url_returns_none():
    assert detect_reddit_subreddit("https://twitter.com/r/SaaS") is None


# ---------------------------------------------------------------------------
# RSS alternate link extractor
# ---------------------------------------------------------------------------

def test_rss_link_extracted_from_html_head():
    html = """
    <html><head>
      <link rel="alternate" type="application/rss+xml"
            href="/feed.xml" title="OpenAI Blog">
    </head></html>
    """
    feeds = extract_rss_links_from_html(html, "https://openai.com/blog/post")
    assert len(feeds) == 1
    f = feeds[0]
    assert f.kind == "rss"
    # Relative href should be resolved against the base URL
    assert f.target == "https://openai.com/feed.xml"
    assert "OpenAI Blog" in f.name


def test_rss_link_absolute_href_preserved():
    html = '<link rel="alternate" type="application/atom+xml" href="https://anthropic.com/rss.xml">'
    feeds = extract_rss_links_from_html(html, "https://anthropic.com/news/x")
    assert len(feeds) == 1
    assert feeds[0].target == "https://anthropic.com/rss.xml"


def test_rss_link_atom_type_also_detected():
    """application/atom+xml is a valid alternate too."""
    html = '<link rel="alternate" type="application/atom+xml" href="/atom.xml">'
    feeds = extract_rss_links_from_html(html, "https://example.com")
    assert len(feeds) == 1


def test_non_alternate_link_ignored():
    """rel='stylesheet' etc must NOT be misclassified as a feed."""
    html = '<link rel="stylesheet" type="text/css" href="/style.css">'
    assert extract_rss_links_from_html(html, "https://example.com") == []


def test_link_without_href_ignored():
    html = '<link rel="alternate" type="application/rss+xml">'
    assert extract_rss_links_from_html(html, "https://example.com") == []


def test_multiple_feeds_extracted():
    html = """
    <link rel="alternate" type="application/rss+xml" href="/rss.xml" title="Main">
    <link rel="alternate" type="application/atom+xml" href="/atom.xml" title="Atom">
    """
    feeds = extract_rss_links_from_html(html, "https://example.com")
    assert len(feeds) == 2


# ---------------------------------------------------------------------------
# Agent integration
# ---------------------------------------------------------------------------

def test_agent_dedups_targets_across_evidence_urls():
    """If two evidence URLs both point to the same repo, the agent must
    propose releases.atom only ONCE."""
    agent = LinkFollowerAgent(fetch_html=lambda u: "")
    res = agent.follow(
        signal_id=42,
        evidence_urls=[
            "https://github.com/anthropics/claude-code",
            "https://github.com/anthropics/claude-code/issues/123",
        ],
    )
    targets = [p.target for p in res.proposals]
    assert targets.count(
        "https://github.com/anthropics/claude-code/releases.atom"
    ) == 1


def test_agent_does_not_crash_on_fetch_failure():
    """If the HTML fetcher throws, pattern proposals must still surface
    and errors are collected for inspection (not raised)."""
    def _boom(url):
        raise RuntimeError("network down")

    agent = LinkFollowerAgent(fetch_html=_boom)
    res = agent.follow(
        signal_id=1,
        evidence_urls=["https://github.com/foo/bar"],
    )
    # Pattern proposal (github releases) still discovered
    assert any(p.kind == "rss" and "foo/bar" in p.target for p in res.proposals)
    # Errors recorded
    assert len(res.errors) == 1
    assert "network down" in res.errors[0]


def test_agent_returns_empty_for_no_urls():
    agent = LinkFollowerAgent(fetch_html=lambda u: "")
    res = agent.follow(signal_id=1, evidence_urls=[])
    assert res.proposals == []
    assert res.errors == []


def test_agent_combines_pattern_and_html_proposals():
    """Same URL produces both pattern-based (none for openai.com) and
    HTML-based (feed link) proposals."""
    def _fetcher(url):
        return '<link rel="alternate" type="application/rss+xml" href="/blog.xml">'

    agent = LinkFollowerAgent(fetch_html=_fetcher)
    res = agent.follow(
        signal_id=1,
        evidence_urls=["https://openai.com/blog/devday"],
    )
    rss_targets = [p.target for p in res.proposals if p.kind == "rss"]
    assert "https://openai.com/blog.xml" in rss_targets


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------

def test_discover_feeds_endpoint_e2e():
    import os
    from fastapi.testclient import TestClient
    os.environ["ALLOWED_EMAILS"] = "test@example.com"
    from orchestrator.api import app
    from orchestrator.core.storage import signals_store
    signals_store.clear()
    sid = signals_store.add(
        source_id=1, source_kind="rss",
        theme="Anthropic releases Claude v5",
        score=0.9, excerpt="major launch",
        evidence_urls=[
            "https://github.com/anthropics/anthropic-sdk-python",
            "https://www.reddit.com/r/ClaudeAI/comments/xyz/discussion/",
        ],
        suggested_topic="ai",
    )

    c = TestClient(app)
    t = c.post("/api/v1/auth/login", json={"email": "test@example.com"}).json()["token"]
    h = {"Authorization": f"Bearer {t}"}
    r = c.post(f"/api/v1/signals/{sid}/discover-feeds", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["signal_id"] == sid
    assert body["evidence_count"] == 2
    kinds = {p["kind"] for p in body["proposals"]}
    # At minimum we should have the GitHub releases proposal + reddit
    assert "rss" in kinds  # github releases is rss kind
    assert "reddit" in kinds


def test_discover_feeds_endpoint_404_for_missing_signal():
    import os
    from fastapi.testclient import TestClient
    os.environ["ALLOWED_EMAILS"] = "test@example.com"
    from orchestrator.api import app

    c = TestClient(app)
    t = c.post("/api/v1/auth/login", json={"email": "test@example.com"}).json()["token"]
    h = {"Authorization": f"Bearer {t}"}
    r = c.post("/api/v1/signals/999999/discover-feeds", headers=h)
    assert r.status_code == 404
