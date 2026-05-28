"""
M4.0 / ADR-018 — platform detection + credential introspection.
"""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def pf():
    """Live module reference (defends against sys.modules deletion)."""
    return importlib.import_module("orchestrator.core.platforms")


# ---------------------------------------------------------------------------
# detect_platform
# ---------------------------------------------------------------------------


def test_detect_youtube_watch(pf):
    assert pf.detect_platform("https://www.youtube.com/watch?v=abc123") == "youtube"


def test_detect_youtube_short_url(pf):
    assert pf.detect_platform("https://youtu.be/abc123") == "youtube"


def test_detect_x_com(pf):
    assert pf.detect_platform("https://x.com/foo/status/123") == "x"
    assert pf.detect_platform("https://twitter.com/foo/status/123") == "x"


def test_detect_linkedin(pf):
    assert pf.detect_platform("https://www.linkedin.com/in/cristian") == "linkedin"
    assert pf.detect_platform("https://linkedin.com/posts/foo") == "linkedin"


def test_detect_instagram(pf):
    assert pf.detect_platform("https://www.instagram.com/p/abc") == "instagram"


def test_detect_facebook(pf):
    assert pf.detect_platform("https://www.facebook.com/page/123") == "facebook"


def test_detect_tiktok(pf):
    assert pf.detect_platform("https://www.tiktok.com/@user/video/123") == "tiktok"


def test_detect_bluesky(pf):
    assert pf.detect_platform("https://bsky.app/profile/x.bsky.social") == "bluesky"


def test_detect_telegram(pf):
    assert pf.detect_platform("https://t.me/somechannel") == "telegram"


def test_detect_hn(pf):
    assert pf.detect_platform("https://news.ycombinator.com/item?id=1") == "hn"


def test_detect_reddit(pf):
    assert pf.detect_platform("https://www.reddit.com/r/SaaS/comments/abc") == "reddit"


def test_detect_product_hunt(pf):
    assert pf.detect_platform("https://www.producthunt.com/posts/abc") == "product_hunt"


def test_detect_github_trending(pf):
    assert pf.detect_platform("https://github.com/trending") == "github_trending"


def test_detect_rss_feed_by_path(pf):
    assert pf.detect_platform("https://blog.example.com/feed/") == "rss"
    assert pf.detect_platform("https://blog.example.com/feed.xml") == "rss"
    assert pf.detect_platform("https://example.com/atom") == "rss"


def test_detect_returns_none_for_generic_url(pf):
    assert pf.detect_platform("https://example.com/article/123") is None


def test_detect_handles_malformed(pf):
    assert pf.detect_platform("") is None
    assert pf.detect_platform("not a url") is None


# ---------------------------------------------------------------------------
# check_credentials
# ---------------------------------------------------------------------------


def test_credentials_ready_for_bluesky(pf):
    c = pf.check_credentials("bluesky")
    assert c["status"] == "ready"
    assert not c["needs_credentials"]
    assert c["missing_keys"] == []
    assert c["recommended_kind"] == "bluesky"


def test_credentials_deferred_for_x(pf):
    c = pf.check_credentials("x")
    assert c["status"] == "deferred"
    assert c["needs_credentials"]
    assert c["oauth_required"]
    assert "ADR-011" in c["message"] or "diferid" in c["message"].lower()


def test_credentials_optional_for_youtube_without_key(pf, monkeypatch):
    """Without YOUTUBE_API_KEY, status is optional_credentials (works via RSS)."""
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    c = pf.check_credentials("youtube")
    assert c["status"] == "optional_credentials"
    assert not c["needs_credentials"]  # functions without
    assert "YOUTUBE_API_KEY" in c["missing_keys"]


def test_credentials_configured_for_youtube_with_key(pf, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "AIza_test_key")
    c = pf.check_credentials("youtube")
    assert c["status"] == "configured"
    assert not c["needs_credentials"]
    assert c["missing_keys"] == []
    assert "YOUTUBE_API_KEY" in c["configured_keys"]


def test_credentials_unknown_platform_treats_as_generic(pf):
    c = pf.check_credentials("nonexistent")
    assert c["status"] == "ready"
    assert c["recommended_kind"] == "url"


def test_list_all_platforms_returns_full_catalog(pf):
    items = pf.list_all_platforms_status()
    platforms = {i["platform"] for i in items}
    # Must include the deferred ones explicitly (founder needs to see WHY)
    assert "x" in platforms
    assert "linkedin" in platforms
    assert "instagram" in platforms
    # And the ready ones
    assert "bluesky" in platforms
    assert "telegram" in platforms
    assert "youtube" in platforms
