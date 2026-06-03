"""
Tests for M12.1 — solution_type heuristic classifier.

Verify each of the 8 taxonomy buckets fires on canonical examples + that
the classifier returns "unknown" when there's no signal. Plus the
SignalsStore integration end-to-end.
"""


# ---------------------------------------------------------------------------
# Per-bucket detection
# ---------------------------------------------------------------------------

def test_classify_mobile_app():
    from orchestrator.core.solution_type import classify_solution
    r = classify_solution(
        theme="New iOS app for habit tracking",
        excerpt="Built with SwiftUI, available on the App Store today.",
        url="https://apps.apple.com/us/app/habitkit/id1635060198",
    )
    assert r.kind == "app_movil"
    assert r.confidence > 0


def test_classify_webapp_saas():
    from orchestrator.core.solution_type import classify_solution
    r = classify_solution(
        theme="Linear: the SaaS project tracker startups love",
        excerpt="Cloud dashboard. Monthly subscription, login required.",
        url="https://linear.app",
    )
    assert r.kind == "webapp_saas"


def test_classify_sitio_web():
    from orchestrator.core.solution_type import classify_solution
    r = classify_solution(
        theme="Built a portfolio website over the weekend",
        excerpt="Landing page in webflow, no backend.",
    )
    assert r.kind == "sitio_web"


def test_classify_automation_agent():
    from orchestrator.core.solution_type import classify_solution
    r = classify_solution(
        theme="AI agent that automates Notion-to-Slack syncing",
        excerpt="Built on n8n workflows + LLM agent loop. Autonomous.",
        url="https://n8n.io/workflows/123",
    )
    assert r.kind == "automatizacion_agente"


def test_classify_extension():
    from orchestrator.core.solution_type import classify_solution
    r = classify_solution(
        theme="Chrome extension that summarizes Reddit threads",
        excerpt="Manifest v3, sidebar popup.",
        url="https://chrome.google.com/webstore/detail/abc/xyz",
    )
    assert r.kind == "extension"


def test_classify_marketplace():
    from orchestrator.core.solution_type import classify_solution
    r = classify_solution(
        theme="Marketplace for indie game asset packs",
        excerpt="Two-sided platform connecting buyers and sellers; commission based.",
    )
    assert r.kind == "marketplace"


def test_classify_infoproducto():
    from orchestrator.core.solution_type import classify_solution
    r = classify_solution(
        theme="Paid newsletter on LATAM startup funding",
        excerpt="Substack, monthly membership site.",
        url="https://example.substack.com",
    )
    assert r.kind == "infoproducto_contenido"


def test_classify_servicio():
    from orchestrator.core.solution_type import classify_solution
    r = classify_solution(
        theme="Consultoría de implementación SAP B1 para retail",
        excerpt="Agency that offers done-for-you setup, professional service.",
    )
    assert r.kind == "servicio"


# ---------------------------------------------------------------------------
# Unknown / empty
# ---------------------------------------------------------------------------

def test_classify_empty_returns_unknown():
    from orchestrator.core.solution_type import classify_solution
    r = classify_solution(theme="", excerpt="")
    assert r.kind == "unknown"
    assert r.confidence == 0.0


def test_classify_neutral_text_returns_unknown():
    from orchestrator.core.solution_type import classify_solution
    r = classify_solution(
        theme="Spring is in the air this week",
        excerpt="A short observation about the weather.",
    )
    assert r.kind == "unknown"


# ---------------------------------------------------------------------------
# URL host hints override weak text signal
# ---------------------------------------------------------------------------

def test_url_host_hint_overrides_weak_text():
    """When the text is ambiguous but the URL is play.google.com, we trust
    the URL hint."""
    from orchestrator.core.solution_type import classify_solution
    r = classify_solution(
        theme="Free download today only",
        excerpt="Get it for free for a limited time.",
        url="https://play.google.com/store/apps/details?id=com.x.y",
    )
    assert r.kind == "app_movil"


def test_chrome_webstore_url_classifies_as_extension():
    from orchestrator.core.solution_type import classify_solution
    r = classify_solution(
        theme="A handy thing",
        excerpt="Some description.",
        url="https://chrome.google.com/webstore/detail/xyz",
    )
    assert r.kind == "extension"


# ---------------------------------------------------------------------------
# Confidence is bounded
# ---------------------------------------------------------------------------

def test_confidence_in_unit_interval():
    from orchestrator.core.solution_type import classify_solution
    r = classify_solution(
        theme="iOS app SaaS dashboard marketplace newsletter consulting",
        excerpt="Chrome extension android dashboard",
    )
    # Many kinds match — confidence should still be in [0, 1]
    assert 0.0 <= r.confidence <= 1.0


# ---------------------------------------------------------------------------
# SignalsStore integration
# ---------------------------------------------------------------------------

def test_signals_store_populates_solution_type():
    """End-to-end: a saved signal carries the classifier's verdict."""
    from orchestrator.core.storage import signals_store
    signals_store.clear()
    sid = signals_store.add(
        source_id=1, source_kind="reddit",
        theme="Chrome extension that summarizes long Reddit threads",
        score=0.6,
        excerpt="Manifest v3 extension, sidebar popup.",
        evidence_urls=["https://chrome.google.com/webstore/detail/abc"],
        suggested_topic="dev-tools",
    )
    saved = signals_store.get(sid)
    assert saved["solution_type"] == "extension"


def test_signals_store_solution_type_unknown_when_neutral():
    from orchestrator.core.storage import signals_store
    signals_store.clear()
    sid = signals_store.add(
        source_id=1, source_kind="rss",
        theme="Weather report for Tuesday",
        score=0.4,
        excerpt="Light rain expected in the morning.",
        evidence_urls=["https://example.com/weather"],
        suggested_topic="weather",
    )
    saved = signals_store.get(sid)
    assert saved["solution_type"] == "unknown"
