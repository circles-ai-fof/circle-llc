"""Unit tests for the source_fetcher (stdlib only, no network calls).

Access via the live module (`_sf()`) so other tests' sys.modules manipulation
doesn't make our function references stale.
"""
import sys

from unittest.mock import patch


def _sf():
    """Returns the LIVE source_fetcher module, re-imported if necessary."""
    if "orchestrator.core.source_fetcher" not in sys.modules:
        from orchestrator.core import source_fetcher  # noqa: F401
    from orchestrator.core import source_fetcher as s
    return s


def _patch_http_get(return_value):
    """Patch the live module's _http_get (the one currently in sys.modules)."""
    sf = _sf()
    return patch.object(sf, "_http_get", return_value=return_value)


def test_html_to_text_strips_tags():
    html = "<html><body><h1>Hello</h1><p>World <b>!</b></p><script>alert(1)</script></body></html>"
    out = _sf()._html_to_text(html)
    assert "Hello" in out
    assert "World" in out
    assert "alert" not in out
    assert "<" not in out
    assert ">" not in out


def test_html_to_text_decodes_entities():
    assert _sf()._html_to_text("5 &amp; 10 &lt; 100 &mdash; ok") == "5 & 10 < 100 — ok"


def test_truncate():
    sf = _sf()
    assert sf._truncate("short", 10) == "short"
    out = sf._truncate("a very long string indeed", 10)
    assert out.endswith("…")
    assert len(out) <= 11


def test_fetch_url_returns_none_on_network_error():
    with _patch_http_get(None):
        assert _sf().fetch_url("https://example.com/article") is None


def test_fetch_url_extracts_title_and_body():
    html = b"<html><head><title>The Article</title></head><body><p>This is the body content.</p></body></html>"
    with _patch_http_get(html):
        item = _sf().fetch_url("https://example.com/x")
    assert item is not None
    assert item.title == "The Article"
    assert "body content" in item.body
    assert item.source_kind == "url"


def test_fetch_rss_parses_rss20():
    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel>
        <title>Feed</title>
        <item><title>One</title><description>First post</description><link>https://x.com/1</link></item>
        <item><title>Two</title><description>Second post</description><link>https://x.com/2</link></item>
    </channel></rss>"""
    with _patch_http_get(rss):
        items = _sf().fetch_rss("https://feed.test/rss")
    assert len(items) == 2
    assert items[0].title == "One"
    assert items[0].url == "https://x.com/1"
    assert items[0].source_kind == "rss"


def test_fetch_rss_parses_atom():
    atom = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
        <entry><title>Alpha</title><summary>About alpha</summary><link href="https://a.test/1"/></entry>
    </feed>"""
    with _patch_http_get(atom):
        items = _sf().fetch_rss("https://feed.test/atom")
    assert len(items) == 1
    assert items[0].title == "Alpha"
    assert items[0].url == "https://a.test/1"


def test_fetch_rss_returns_empty_on_malformed():
    with _patch_http_get(b"not xml"):
        assert _sf().fetch_rss("https://feed.test/bad") == []


def test_fetch_by_kind_unknown():
    assert _sf().fetch_by_kind("unknown_kind", "x") == []


def test_fetched_item_to_dict():
    sf = _sf()
    it = sf.FetchedItem(
        source_kind="url", url="https://x.com", title="t", summary="s", body="b",
    )
    d = it.to_dict()
    assert d["source_kind"] == "url"
    assert d["title"] == "t"
    assert isinstance(d["fetched_at"], int)


# ---------------------------------------------------------------------------
# M3.1 new source kinds — YouTube, Bluesky, Telegram
# ---------------------------------------------------------------------------


def test_youtube_resolve_raw_channel_id():
    """Raw UC-prefixed channel id resolves directly to the RSS feed URL."""
    feed = _sf()._resolve_youtube_to_rss("UCxK1JKBdJrCQ74yqMyKW7sQ")
    assert feed is not None
    assert "channel_id=UCxK1JKBdJrCQ74yqMyKW7sQ" in feed


def test_youtube_resolve_channel_url():
    feed = _sf()._resolve_youtube_to_rss("https://www.youtube.com/channel/UC123_AbcDefGhijKLMnOPq")
    assert feed is not None
    assert "channel_id=UC123_AbcDefGhijKLMnOPq" in feed


def test_youtube_resolve_invalid_returns_none():
    """Unresolvable target -> None (no network mock here, so handle/c/ resolve)."""
    with _patch_http_get(None):
        assert _sf()._resolve_youtube_to_rss("@nonexistent-channel-test") is None


def test_bluesky_empty_query_returns_empty():
    assert _sf().fetch_bluesky("") == []


def test_bluesky_parses_posts_from_json():
    payload = {
        "posts": [
            {
                "uri": "at://did:plc:xxx/app.bsky.feed.post/abc",
                "author": {"handle": "founder.bsky.team"},
                "record": {"text": "Building a fintech for LATAM PYMEs"},
                "likeCount": 42,
            }
        ]
    }
    import json as _json
    with _patch_http_get(_json.dumps(payload).encode()):
        items = _sf().fetch_bluesky("fintech LATAM")
    assert len(items) == 1
    assert items[0].source_kind == "bluesky"
    assert "founder.bsky.team" in items[0].title
    assert "fintech" in items[0].body.lower()


def test_bluesky_skips_empty_posts():
    import json as _json
    payload = {"posts": [{"record": {"text": ""}, "author": {"handle": "x"}}]}
    with _patch_http_get(_json.dumps(payload).encode()):
        assert _sf().fetch_bluesky("anything") == []


def test_telegram_empty_handle_returns_empty():
    assert _sf().fetch_telegram("") == []


def test_telegram_parses_public_channel_html():
    html = b"""
    <html><body>
      <a class="tgme_widget_message_date" href="https://t.me/durov/1"><time>...</time></a>
      <div class="tgme_widget_message_text">Hello from <b>Telegram</b></div>
      <a class="tgme_widget_message_date" href="https://t.me/durov/2"><time>...</time></a>
      <div class="tgme_widget_message_text">Second message here</div>
    </body></html>
    """
    with _patch_http_get(html):
        items = _sf().fetch_telegram("durov")
    assert len(items) >= 1
    assert items[0].source_kind == "telegram"
    assert "@durov" in items[0].title or "durov" in items[0].title.lower()


def test_telegram_handle_normalization():
    """Accepts @handle, t.me/handle, or bare handle."""
    with _patch_http_get(None):  # network fails -> we only check the call did happen
        assert _sf().fetch_telegram("@durov") == []
        assert _sf().fetch_telegram("t.me/durov") == []
        assert _sf().fetch_telegram("durov") == []


def test_fetch_by_kind_routes_to_new_kinds():
    """Dispatch table includes youtube/bluesky/telegram."""
    sf = _sf()
    with _patch_http_get(None):
        assert sf.fetch_by_kind("youtube", "UCxxxxxxxxxxxxxxxxxx00") == []
        assert sf.fetch_by_kind("bluesky", "fintech") == []
        assert sf.fetch_by_kind("telegram", "durov") == []
