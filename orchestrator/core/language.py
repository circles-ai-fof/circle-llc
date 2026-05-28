"""
M4.4 — Detección heurística de idioma + interfaz de traducción.

Founder feedback: "dependiendo del idioma que esté en señales debe ser
traducido al español o que exista la opción traducir".

Heurística sin LLM (gratis, instantánea):
  - Cuenta palabras comunes de español vs inglés en el texto
  - Devuelve 'es' / 'en' / 'unknown'
  - Si no hay suficientes palabras (<3), devuelve 'unknown'

La traducción real se hace on-demand vía LLM (Haiku) cuando el founder
clickea "🌐 Traducir" — el detector solo decide si MOSTRAR el botón.
"""
from __future__ import annotations

import re
from typing import Tuple


# Stopwords y palabras frecuentes — diferenciadores fuertes entre ES y EN
_SPANISH_MARKERS = {
    # Articles + pronouns
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "lo", "le", "les", "se", "su", "sus", "mi", "tu", "tus",
    # Prepositions + conjunctions
    "de", "del", "al", "en", "con", "sin", "por", "para",
    "que", "y", "o", "pero", "como", "más", "menos",
    # Verbs estar/ser/haber/tener common forms
    "es", "son", "está", "están", "esta", "estan",
    "fue", "fueron", "será", "sera", "ha", "han", "haber",
    "tener", "tiene", "tenia", "tenía",
    # Specific Spanish words
    "para", "porque", "porqué", "porque",
    "según", "segun", "también", "tambien", "siempre",
    "muy", "donde", "dónde",
    # Spanish accented vowels in any word (counted separately)
    "año", "años", "día", "días", "país", "países", "información",
    "tecnología", "tecnologia", "empresa", "empresas",
    # Common verbs in infinitive
    "hacer", "hacer", "decir", "ver", "poder", "querer",
}

_ENGLISH_MARKERS = {
    # Articles + pronouns
    "the", "a", "an", "this", "that", "these", "those",
    "he", "she", "it", "they", "we", "you", "i",
    "his", "her", "its", "their", "our", "your", "my",
    # Prepositions + conjunctions
    "of", "in", "on", "at", "to", "from", "for", "with",
    "and", "or", "but", "as", "by", "if", "than",
    # Verbs be/have/do/will common forms
    "is", "are", "was", "were", "be", "been", "being",
    "has", "have", "had", "having",
    "do", "does", "did", "doing", "done",
    "will", "would", "could", "should", "shall", "may", "might",
    "can", "must", "ought",
    # Common English-specific words
    "about", "after", "before", "between", "during",
    "through", "while", "where", "what", "when", "why", "how",
    "all", "any", "some", "no", "not", "only",
    # Common topic words
    "news", "report", "study", "company", "business",
}


_WORD_PATTERN = re.compile(r"[a-záéíóúñü]+", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return _WORD_PATTERN.findall(text.lower())


def detect_language(text: str) -> Tuple[str, float]:
    """Returns (language_code, confidence).

    language_code: 'es' | 'en' | 'unknown'
    confidence: 0.0 to 1.0
    """
    words = _tokenize(text)
    if len(words) < 3:
        return ("unknown", 0.0)

    es_hits = sum(1 for w in words if w in _SPANISH_MARKERS)
    en_hits = sum(1 for w in words if w in _ENGLISH_MARKERS)

    # Strong signals: Spanish-specific characters (ñ, accented vowels)
    has_spanish_chars = bool(re.search(r"[ñáéíóú¿¡]", text.lower()))
    if has_spanish_chars:
        es_hits += 3

    total_hits = es_hits + en_hits
    if total_hits == 0:
        return ("unknown", 0.0)

    if es_hits > en_hits:
        return ("es", min(1.0, es_hits / max(1, total_hits)))
    if en_hits > es_hits:
        return ("en", min(1.0, en_hits / max(1, total_hits)))
    return ("unknown", 0.5)


def is_spanish(text: str) -> bool:
    """Convenience wrapper."""
    lang, conf = detect_language(text)
    return lang == "es" and conf >= 0.5


def needs_translation(text: str) -> bool:
    """True si el texto NO está en español con confianza razonable.

    Default = False (no traducir si no estamos seguros) — minimiza llamadas
    LLM innecesarias.
    """
    lang, conf = detect_language(text)
    if lang == "unknown":
        return False
    return lang != "es"
