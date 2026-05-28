"""M4.4 — tests del detector de idioma."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def lang_mod():
    return importlib.import_module("orchestrator.core.language")


def test_detect_english(lang_mod):
    lang, conf = lang_mod.detect_language(
        "Facebook and Google extend working from home to end of year"
    )
    assert lang == "en"
    assert conf > 0.5


def test_detect_spanish(lang_mod):
    lang, conf = lang_mod.detect_language(
        "Plataforma fintech para PYMEs Ecuador con reconciliación bancaria"
    )
    assert lang == "es"
    assert conf > 0.5


def test_spanish_chars_boost_detection(lang_mod):
    """A single Spanish char (ñ, á, é) is a strong signal."""
    lang, _ = lang_mod.detect_language("El año pasado fue mejor")
    assert lang == "es"


def test_too_short_returns_unknown(lang_mod):
    assert lang_mod.detect_language("AI ML")[0] == "unknown"
    assert lang_mod.detect_language("")[0] == "unknown"


def test_needs_translation_for_english(lang_mod):
    assert lang_mod.needs_translation("This is an English text about AI")


def test_does_not_need_translation_for_spanish(lang_mod):
    assert not lang_mod.needs_translation("Este texto está en español neutro")


def test_does_not_need_translation_for_unknown(lang_mod):
    """When uncertain, default to NOT translating (avoid spurious LLM calls)."""
    assert not lang_mod.needs_translation("12345 ABC")


def test_is_spanish_helper(lang_mod):
    assert lang_mod.is_spanish("Hola amigos, ¿cómo están?")
    assert not lang_mod.is_spanish("Hello friends, how are you")
