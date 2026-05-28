"""Tests for file_parser (URL extraction + text/docx parsing)."""
import sys


def _fp():
    if "orchestrator.core.file_parser" not in sys.modules:
        from orchestrator.core import file_parser  # noqa: F401
    from orchestrator.core import file_parser as m
    return m


def test_extract_urls_empty():
    assert _fp().extract_urls("") == []
    assert _fp().extract_urls("no urls here") == []


def test_extract_urls_single():
    assert _fp().extract_urls("look at https://example.com today") == ["https://example.com"]


def test_extract_urls_multiple():
    text = "Check https://a.com and https://b.com/path and http://c.org"
    urls = _fp().extract_urls(text)
    assert urls == ["https://a.com", "https://b.com/path", "http://c.org"]


def test_extract_urls_dedup():
    text = "https://x.com once, https://x.com again, and https://y.com"
    urls = _fp().extract_urls(text)
    assert urls == ["https://x.com", "https://y.com"]


def test_extract_urls_trim_trailing_punctuation():
    text = "Source: https://x.com/page. Also https://y.com/?q=test, end."
    urls = _fp().extract_urls(text)
    assert "https://x.com/page" in urls
    assert "https://y.com/?q=test" in urls


def test_extract_urls_whatsapp_style():
    chat = """[12/05/26 09:32] Cristian: mira esto https://techcrunch.com/article/xyz
[12/05/26 09:33] JF: y este también — https://www.elcomercio.com/noticia/abc
[12/05/26 09:35] Cristian: 🤔 (no link aquí)
[12/05/26 09:36] JF: y este último: https://medium.com/@autor/post-largo-con-titulo-12345"""
    urls = _fp().extract_urls(chat)
    assert len(urls) == 3
    assert any("techcrunch" in u for u in urls)
    assert any("elcomercio" in u for u in urls)
    assert any("medium.com" in u for u in urls)


def test_parse_text_file_utf8():
    content = "Hola — esta es una prueba con acentos áéíóú 🚀".encode("utf-8")
    assert "áéíóú" in _fp().parse_text_file(content)


def test_parse_text_file_latin1_fallback():
    # Latin-1 encoded text should NOT crash; falls back gracefully
    content = "Cafe con leche".encode("latin-1")
    assert "Cafe" in _fp().parse_text_file(content)


def test_parse_file_dispatches_by_extension():
    sf = _fp()
    txt = sf.parse_file("chat.txt", b"hello https://x.com world")
    assert "hello" in txt
    # Unknown extension -> treated as text
    other = sf.parse_file("data.csv", b"name,url\nfoo,https://y.com")
    assert "https://y.com" in other


def test_parse_docx_returns_empty_when_lib_missing(monkeypatch):
    """If python-docx isn't importable, parse_docx_file logs warning and returns ''."""
    sf = _fp()
    # We can't easily uninstall python-docx for the test, so we mock the import
    real_modules = dict(sys.modules)
    sys.modules["docx"] = None  # type: ignore
    try:
        result = sf.parse_docx_file(b"fake bytes")
        assert result == ""
    finally:
        sys.modules.clear()
        sys.modules.update(real_modules)


# ---------------------------------------------------------------------------
# M3.15 — URL quality filter
# ---------------------------------------------------------------------------


def test_classify_url_keeps_company_sites():
    """Real company websites should be kept."""
    sf = _fp()
    keep, _ = sf.classify_url("https://runachay.com/")
    assert keep
    keep2, _ = sf.classify_url("https://www.eventifica.com/")
    assert keep2


def test_classify_url_discards_x_status():
    """X/Twitter status URLs are personal posts, not ideas."""
    sf = _fp()
    keep, reason = sf.classify_url("https://x.com/bancoguayaquil/status/1996993796756984235")
    assert not keep
    assert "personal" in reason.lower() or "x.com" in reason.lower()


def test_classify_url_discards_instagram_reel():
    sf = _fp()
    keep, reason = sf.classify_url("https://www.instagram.com/reel/DVheXDnjjwM/")
    assert not keep
    assert "instagram" in reason.lower() or "personal" in reason.lower()


def test_classify_url_discards_youtube_shorts_keeps_watch():
    sf = _fp()
    keep_short, _ = sf.classify_url("https://www.youtube.com/shorts/abcd")
    assert not keep_short
    keep_watch, _ = sf.classify_url("https://www.youtube.com/watch?v=abcd")
    assert keep_watch


def test_classify_url_keeps_github_repos():
    sf = _fp()
    keep, _ = sf.classify_url("https://github.com/microsoft/vscode")
    assert keep


def test_classify_url_discards_wa_me_telegram():
    sf = _fp()
    assert not sf.classify_url("https://wa.me/521234567890")[0]
    assert not sf.classify_url("https://t.me/somechannel")[0]


def test_filter_urls_by_quality_returns_kept_and_discarded():
    """End-to-end: a mixed list of WhatsApp-style URLs is correctly split."""
    sf = _fp()
    urls = [
        "https://x.com/foo/status/123",
        "https://www.instagram.com/reel/abc",
        "https://runachay.com/",
        "https://github.com/foo/bar",
        "https://wa.me/521234",
        "https://t.co/abc",
    ]
    kept, discarded = sf.filter_urls_by_quality(urls)
    assert len(kept) == 2
    assert "https://runachay.com/" in kept
    assert "https://github.com/foo/bar" in kept
    assert len(discarded) == 4
    # Each discarded item has url + reason
    for d in discarded:
        assert "url" in d and "reason" in d
        assert d["reason"]  # non-empty
