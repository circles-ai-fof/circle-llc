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
