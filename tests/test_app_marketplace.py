"""
Tests for M9.2 — app_marketplace source_kind.

Aggregator sites (lovableapp.org, claudecreations.com, adorableapp.org) all
share the same shape: a category-paginated list of apps, each rendered as a
card with a title, a short description, and a link. The fetcher uses
permissive regex patterns to extract those three fields without needing a
heavyweight HTML parser.

These tests stub urlopen so they run offline. They cover:
  - Card-based HTML (the common case)
  - Fallback to <h2><a>...</a></h2> when no card class is present
  - max_items honored
  - Empty page handled gracefully
  - fetch_by_kind dispatches "app_marketplace" correctly
  - HTML entities decoded
"""
from unittest.mock import patch


# A minimal HTML response shaped like Lovable / Adorable category page
_HTML_CARDS = """
<html><body>
<main class="apps">
  <article class="app-card">
    <h3>Vibe Coding Studio</h3>
    <p class="description">Build full-stack apps by describing them in chat.</p>
    <a href="/apps/vibe-studio">Open</a>
  </article>

  <article class="app-card">
    <h3>Realtime Whiteboard</h3>
    <p class="description">Collaborative drawing for remote teams.</p>
    <a href="https://realtimewb.app">Visit</a>
  </article>

  <article class="app-card">
    <h3>Tax Calculator EC</h3>
    <p class="description">Calcula impuestos del SRI en segundos.</p>
    <a href="/apps/tax-ec">Open</a>
  </article>
</main>
</body></html>
"""

# Fallback shape: just headers with anchors, no card class
_HTML_HEADER_LIST = """
<html><body>
<h2><a href="/apps/photo-ai">PhotoAI Generator</a></h2>
<h2><a href="https://otherapp.com">Other App</a></h2>
<h3><a href="/apps/text-summarizer">Text Summarizer</a></h3>
</body></html>
"""


def _stub_urlopen(html: str):
    """Returns a context-manager that mimics urlopen's read() interface."""
    from io import BytesIO

    class _Resp:
        def __init__(self, body):
            self._body = body.encode("utf-8")
            self._reader = BytesIO(self._body)

        def read(self, n=-1):
            return self._reader.read(n)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _open(req, timeout=None):
        return _Resp(html)

    return _open


# ---------------------------------------------------------------------------
# Card-based parsing
# ---------------------------------------------------------------------------

def test_fetch_app_marketplace_extracts_three_cards():
    from orchestrator.core import source_fetcher
    with patch("urllib.request.urlopen", _stub_urlopen(_HTML_CARDS)):
        items = source_fetcher.fetch_app_marketplace(
            "https://lovableapp.org/category/productivity",
        )
    assert len(items) == 3
    titles = [i.title for i in items]
    assert "Vibe Coding Studio" in titles
    assert "Realtime Whiteboard" in titles
    assert "Tax Calculator EC" in titles


def test_fetch_app_marketplace_resolves_relative_urls():
    """Relative hrefs must be absolutized against the listing page URL."""
    from orchestrator.core import source_fetcher
    with patch("urllib.request.urlopen", _stub_urlopen(_HTML_CARDS)):
        items = source_fetcher.fetch_app_marketplace(
            "https://lovableapp.org/category/productivity",
        )
    vibe = next(i for i in items if i.title == "Vibe Coding Studio")
    assert vibe.url.startswith("https://lovableapp.org/")
    realtime = next(i for i in items if i.title == "Realtime Whiteboard")
    assert realtime.url == "https://realtimewb.app"  # absolute already


def test_fetch_app_marketplace_each_item_has_source_kind():
    from orchestrator.core import source_fetcher
    with patch("urllib.request.urlopen", _stub_urlopen(_HTML_CARDS)):
        items = source_fetcher.fetch_app_marketplace(
            "https://lovableapp.org/",
        )
    assert all(i.source_kind == "app_marketplace" for i in items)


def test_fetch_app_marketplace_max_items_honored():
    from orchestrator.core import source_fetcher
    with patch("urllib.request.urlopen", _stub_urlopen(_HTML_CARDS)):
        items = source_fetcher.fetch_app_marketplace(
            "https://lovableapp.org/", max_items=2,
        )
    assert len(items) == 2


# ---------------------------------------------------------------------------
# Header-list fallback
# ---------------------------------------------------------------------------

def test_fetch_app_marketplace_falls_back_to_header_anchors():
    """If no .card / .app-item DOM is found, scan <h2><a>...</a></h2> instead.
    Catches simpler/minimalist marketplace layouts."""
    from orchestrator.core import source_fetcher
    with patch("urllib.request.urlopen", _stub_urlopen(_HTML_HEADER_LIST)):
        items = source_fetcher.fetch_app_marketplace(
            "https://minimalmarketplace.com/",
        )
    assert len(items) >= 2
    titles = [i.title for i in items]
    assert "PhotoAI Generator" in titles
    assert "Other App" in titles


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_fetch_app_marketplace_empty_target_returns_empty():
    from orchestrator.core import source_fetcher
    assert source_fetcher.fetch_app_marketplace("") == []


def test_fetch_app_marketplace_handles_empty_page():
    from orchestrator.core import source_fetcher
    with patch("urllib.request.urlopen", _stub_urlopen("<html></html>")):
        items = source_fetcher.fetch_app_marketplace("https://x.com")
    assert items == []


def test_fetch_app_marketplace_handles_network_failure():
    """A URLError during fetch must NOT raise — return empty list instead."""
    import urllib.error
    from orchestrator.core import source_fetcher

    def _boom(req, timeout=None):
        raise urllib.error.URLError("name resolution failed")

    with patch("urllib.request.urlopen", side_effect=_boom):
        items = source_fetcher.fetch_app_marketplace("https://offline.com")
    assert items == []


def test_strip_html_decodes_common_entities():
    from orchestrator.core import source_fetcher
    raw = "<p>Hello&nbsp;world &amp; goodbye</p>"
    assert source_fetcher._strip_html(raw) == "Hello world & goodbye"


# ---------------------------------------------------------------------------
# Dispatcher integration
# ---------------------------------------------------------------------------

def test_fetch_by_kind_dispatches_app_marketplace():
    """The single source of truth for source_kind routing must include
    app_marketplace — otherwise SourcesStore.add(kind='app_marketplace')
    would land but never produce any items."""
    from orchestrator.core import source_fetcher
    with patch("urllib.request.urlopen", _stub_urlopen(_HTML_CARDS)):
        items = source_fetcher.fetch_by_kind(
            kind="app_marketplace",
            target="https://lovableapp.org/category/productivity",
            max_items=5,
        )
    assert len(items) == 3
    assert all(i.source_kind == "app_marketplace" for i in items)
