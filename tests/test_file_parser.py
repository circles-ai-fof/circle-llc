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
