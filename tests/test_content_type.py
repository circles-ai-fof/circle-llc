"""
M4.3 — tests del clasificador de tipo de contenido.
"""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def ct():
    return importlib.import_module("orchestrator.core.content_type")


# ---------------------------------------------------------------------------
# Domain detection
# ---------------------------------------------------------------------------


def test_bbc_is_news(ct):
    cat, _, label = ct.classify_content_type("https://www.bbc.com/news/business-1234")
    assert cat == "news"
    assert label == "Noticia"


def test_techcrunch_is_news(ct):
    cat, _, _ = ct.classify_content_type("https://techcrunch.com/article/foo")
    assert cat == "news"


def test_arxiv_is_research(ct):
    cat, _, _ = ct.classify_content_type("https://arxiv.org/abs/2401.12345")
    assert cat == "research_paper"


def test_github_is_tool_product(ct):
    cat, _, _ = ct.classify_content_type("https://github.com/microsoft/vscode")
    assert cat == "tool_product"


def test_medium_is_blog(ct):
    cat, _, _ = ct.classify_content_type("https://medium.com/@author/post")
    assert cat == "blog"


def test_coursera_is_course(ct):
    cat, _, _ = ct.classify_content_type("https://www.coursera.org/learn/ml")
    assert cat == "course_tutorial"


def test_youtube_watch_is_video(ct):
    cat, _, _ = ct.classify_content_type("https://www.youtube.com/watch?v=abc")
    assert cat == "video_podcast"


def test_hn_is_community(ct):
    cat, _, _ = ct.classify_content_type("https://news.ycombinator.com/item?id=1")
    assert cat == "community"


def test_reddit_is_community(ct):
    cat, _, _ = ct.classify_content_type("https://www.reddit.com/r/SaaS")
    assert cat == "community"


# ---------------------------------------------------------------------------
# Path-based detection (when domain is unknown)
# ---------------------------------------------------------------------------


def test_unknown_domain_with_news_path(ct):
    cat, _, _ = ct.classify_content_type("https://example.com/news/breaking")
    assert cat == "news"


def test_unknown_domain_with_blog_path(ct):
    cat, _, _ = ct.classify_content_type("https://example.com/blog/my-post")
    assert cat == "blog"


def test_unknown_domain_with_research_path(ct):
    cat, _, _ = ct.classify_content_type("https://example.com/papers/foo")
    assert cat == "research_paper"


# ---------------------------------------------------------------------------
# Keyword-based (when no domain/path hint)
# ---------------------------------------------------------------------------


def test_keyword_announces_is_news(ct):
    cat, _, _ = ct.classify_content_type(
        "https://example.com/x",
        "Company announces new product line",
        "Today, the company announces...",
    )
    assert cat == "news"


def test_keyword_research_is_paper(ct):
    cat, _, _ = ct.classify_content_type(
        "https://example.com/x",
        "Optimization study",
        "Abstract: We propose a novel algorithm. Experimental results show p < 0.05.",
    )
    assert cat == "research_paper"


# ---------------------------------------------------------------------------
# Founder case: BBC News example
# ---------------------------------------------------------------------------


def test_founder_real_case_bbc_news(ct):
    """Founder reportó: Facebook and Google extend WFH desde www.bbc.com."""
    cat, icon, label = ct.classify_content_type(
        "https://www.bbc.com/news/business-12345",
        "Facebook and Google extend working from home to end of year",
        "Tech giants are extending remote work policies",
    )
    assert cat == "news"
    assert icon == "📰"
    assert label == "Noticia"


# ---------------------------------------------------------------------------
# Fallback: unknown
# ---------------------------------------------------------------------------


def test_unknown_when_no_signals(ct):
    cat, _, _ = ct.classify_content_type("https://example.com/random")
    assert cat == "unknown"


def test_empty_inputs_returns_unknown(ct):
    cat, _, _ = ct.classify_content_type()
    assert cat == "unknown"


# ---------------------------------------------------------------------------
# classify_content_dict helper
# ---------------------------------------------------------------------------


def test_dict_helper_returns_all_fields(ct):
    d = ct.classify_content_dict("https://www.bbc.com/news/x", "Title", "")
    assert d["category"] == "news"
    assert d["icon"] == "📰"
    assert d["label"] == "Noticia"
