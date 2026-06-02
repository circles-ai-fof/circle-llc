"""
Tests for M9.1 — scrape-time translator + SignalsStore hook.

Critical safety properties (these are the regressions we must never ship):
  1. Translation is OPT-IN — disabled when auto_translate_to == ''
  2. Translation is SKIPPED when detected_lang already matches target
  3. Translation FAILURES are SWALLOWED — signal still saves with theme/excerpt
  4. The hook must work in mock mode (no API key) without burning tokens
"""
from unittest.mock import patch


# ---------------------------------------------------------------------------
# translate_text — pure function tests
# ---------------------------------------------------------------------------

def test_translate_text_mock_mode_returns_placeholder(monkeypatch):
    """In mock mode (no ANTHROPIC_API_KEY), translator returns deterministic
    placeholders so tests can assert without burning tokens."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from orchestrator.core import translator
    theme_t, excerpt_t = translator.translate_text(
        "OpenAI launches o5", "Announced at DevDay 2026", "es",
    )
    assert theme_t is not None
    assert excerpt_t is not None
    assert "Traducción demo" in theme_t


def test_translate_text_empty_inputs_returns_none():
    from orchestrator.core import translator
    a, b = translator.translate_text("", "", "es")
    assert a is None and b is None


def test_translate_text_empty_target_lang_returns_none():
    from orchestrator.core import translator
    a, b = translator.translate_text("hello", "world", "")
    assert a is None and b is None


def test_translate_text_handles_api_failure():
    """If the Anthropic client raises, translator must return (None, None)
    instead of propagating — the caller treats translation as best-effort."""
    import os
    os.environ["ANTHROPIC_API_KEY"] = "fake-key-for-test"
    try:
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_anthropic.side_effect = RuntimeError("API down")
            from orchestrator.core import translator
            a, b = translator.translate_text("title", "body", "es")
        assert a is None and b is None
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)


def test_translate_text_parses_json_with_markdown_fences():
    """Models often wrap JSON in ```json ... ```. Parser must handle that."""
    import os
    os.environ["ANTHROPIC_API_KEY"] = "fake-key-for-test"
    try:
        class _Resp:
            class _Content:
                text = '```json\n{"theme": "Hola", "excerpt": "Mundo"}\n```'
            content = [_Content()]

        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_anthropic.return_value.messages.create.return_value = _Resp()
            from orchestrator.core import translator
            a, b = translator.translate_text("hi", "world", "es")
        assert a == "Hola"
        assert b == "Mundo"
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)


def test_translate_text_parses_loose_json_with_preamble():
    """Some models add a preamble before the JSON object."""
    import os
    os.environ["ANTHROPIC_API_KEY"] = "fake-key-for-test"
    try:
        class _Resp:
            class _Content:
                text = 'Here is the translation:\n{"theme": "Adiós", "excerpt": "Cruel mundo"}\nLet me know if you need adjustments.'
            content = [_Content()]

        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_anthropic.return_value.messages.create.return_value = _Resp()
            from orchestrator.core import translator
            a, b = translator.translate_text("bye", "cruel world", "es")
        assert a == "Adiós"
        assert b == "Cruel mundo"
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)


def test_translate_text_returns_none_on_malformed_json():
    """If the model returns garbage that doesn't contain a JSON dict, the
    translator must NOT raise — it returns (None, None)."""
    import os
    os.environ["ANTHROPIC_API_KEY"] = "fake-key-for-test"
    try:
        class _Resp:
            class _Content:
                text = "I cannot translate this. The text seems toxic."
            content = [_Content()]

        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_anthropic.return_value.messages.create.return_value = _Resp()
            from orchestrator.core import translator
            a, b = translator.translate_text("hi", "world", "es")
        assert a is None and b is None
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)


# ---------------------------------------------------------------------------
# SignalsStore.add() hook — the integration that actually matters in prod
# ---------------------------------------------------------------------------

def test_signal_add_skips_translation_when_setting_empty():
    """auto_translate_to='' must completely disable scrape-time translation
    even if the signal is in English."""
    from orchestrator.core.storage import (
        signals_store, user_settings_store,
    )
    signals_store.clear()
    user_settings_store.clear()
    user_settings_store.update({"auto_translate_to": ""})

    sid = signals_store.add(
        source_id=1, source_kind="rss",
        theme="OpenAI announces new tool",
        score=0.7, excerpt="The new tool will replace MoreOldThing.",
        evidence_urls=["https://openai.com/x"],
        suggested_topic="ai",
    )
    s = signals_store.get(sid)
    assert s["translated_theme"] is None
    assert s["translated_excerpt"] is None


def test_signal_add_skips_translation_when_already_in_target():
    """If detected_lang matches target, don't waste an LLM call."""
    from orchestrator.core.storage import (
        signals_store, user_settings_store,
    )
    signals_store.clear()
    user_settings_store.clear()
    user_settings_store.update({"auto_translate_to": "es"})

    # Spanish-sounding content → detect_language should return "es"
    sid = signals_store.add(
        source_id=1, source_kind="rss",
        theme="Startup fintech ecuatoriana lanza nuevo producto",
        score=0.7,
        excerpt="La empresa anunció hoy que abrirá una nueva sede para "
                "atender la creciente demanda de servicios.",
        evidence_urls=["https://contxto.com/x"],
        suggested_topic="fintech",
    )
    s = signals_store.get(sid)
    # Already in es → no translation persisted
    assert s["translated_theme"] is None


def test_signal_add_translates_in_mock_mode_when_lang_differs():
    """English signal + auto_translate_to=es + mock mode → placeholder gets
    stored on the row so downstream code can rely on translated_theme being
    present whenever the setting requests it."""
    import os
    from orchestrator.core.storage import (
        signals_store, user_settings_store,
    )
    # Force mock mode
    os.environ.pop("ANTHROPIC_API_KEY", None)
    signals_store.clear()
    user_settings_store.clear()
    user_settings_store.update({"auto_translate_to": "es"})

    sid = signals_store.add(
        source_id=1, source_kind="hn",
        theme="OpenAI announces a powerful tool for developers and engineers",
        score=0.7,
        excerpt="The announcement was made at DevDay. The new tool will "
                "replace older workflows with simpler abstractions for users.",
        evidence_urls=["https://openai.com/x"],
        suggested_topic="ai",
    )
    s = signals_store.get(sid)
    # In mock mode the translator returns a deterministic placeholder
    assert s["translated_theme"] is not None
    assert "Traducción demo" in s["translated_theme"]


def test_signal_add_save_succeeds_even_when_translator_raises():
    """Critical safety property: a translator crash MUST NOT prevent the
    signal from being saved. If translation fails, theme/excerpt are still
    persisted (just without translated_*)."""
    from orchestrator.core.storage import (
        signals_store, user_settings_store,
    )
    signals_store.clear()
    user_settings_store.clear()
    user_settings_store.update({"auto_translate_to": "es"})

    with patch(
        "orchestrator.core.translator.translate_text",
        side_effect=RuntimeError("translator boom"),
    ):
        sid = signals_store.add(
            source_id=1, source_kind="rss",
            theme="A signal in English that triggers translation",
            score=0.7,
            excerpt="Long English excerpt to ensure non-es detection.",
            evidence_urls=["https://x.com"],
            suggested_topic="t",
        )
    s = signals_store.get(sid)
    assert s is not None, "signal must be saved despite translator failure"
    assert s["theme"] == "A signal in English that triggers translation"
    assert s["translated_theme"] is None
