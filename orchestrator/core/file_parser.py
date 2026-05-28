"""
Extract URLs from uploaded text/WhatsApp/Word files (R30 / ADR-013).

Stdlib-only for txt and WhatsApp chats. python-docx is optional — DOCX
parsing degrades gracefully if it's not installed.

Supported input types:
  - .txt              : any plain text
  - .csv              : extracted as plain text
  - WhatsApp exports  : same as .txt (the export is plain UTF-8 with
                        lines like '[dd/mm/yy hh:mm] Name: message')
  - .docx             : Word documents — requires python-docx
"""
from __future__ import annotations

import logging
import re
from typing import List

logger = logging.getLogger(__name__)


# Conservative URL regex — captures http/https URLs commonly found in chats
# and articles. Trailing punctuation (.,;:)?! is trimmed in post-processing.
_URL_RE = re.compile(
    r'https?://[^\s<>"\'\)\]\}]+',
    re.IGNORECASE,
)

# Trailing punctuation to strip
_TRAILING = ".,;:!?)]}>'\""


def extract_urls(text: str) -> List[str]:
    """Extract de-duplicated URLs from plain text, preserving order."""
    if not text:
        return []
    found = _URL_RE.findall(text)
    seen: set[str] = set()
    out: List[str] = []
    for raw in found:
        # Trim trailing punctuation that's not part of the URL
        url = raw
        while url and url[-1] in _TRAILING:
            url = url[:-1]
        if len(url) < 10 or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


# ---------------------------------------------------------------------------
# M3.15 — URL quality filter (heuristic, sin LLM)
#
# Cuando el founder sube un chat de WhatsApp, no todas las URLs son ideas.
# Hay status de X (Twitter), reels de Instagram, posts personales que NO son
# ideas de negocio. Las heurísticas de abajo separan:
#   keep  → contenido tipo artículo, repo, post de blog (probable idea)
#   discard → status personal, reel, foto personal (ruido)
# ---------------------------------------------------------------------------

# Dominios cuyos URLs siempre son ruido para hunting B2B
_NOISE_DOMAINS = {
    # Social media personal — los posts individuales rara vez son ideas
    "facebook.com", "www.facebook.com", "m.facebook.com",
    "instagram.com", "www.instagram.com",
    "twitter.com", "x.com", "www.x.com",
    "t.co",  # shortener de twitter
    "tiktok.com", "www.tiktok.com", "vm.tiktok.com",
    # Servicios de mensajería personal
    "wa.me", "api.whatsapp.com", "chat.whatsapp.com",
    "t.me",  # telegram
    # Multimedia personal
    "youtube.com/shorts",  # special-cased — shorts son personales
    "youtu.be",  # shortener — suele ser para compartir, no análisis
}

# Dominios de "salida" o utility que tampoco son ideas
_UTILITY_DOMAINS = {
    "google.com", "www.google.com", "maps.google.com",
    "drive.google.com", "docs.google.com",
    "zoom.us", "us02web.zoom.us", "us04web.zoom.us",
    "calendly.com", "calendar.google.com",
    "github.com/login",  # path login específico
}

# Patrones de path que indican contenido personal/efímero (no idea de negocio)
_NOISE_PATH_PATTERNS = (
    "/status/",    # Twitter/X status
    "/p/",         # Instagram post individual
    "/reel/",      # Instagram/FB reels
    "/stories/",   # IG/FB stories
    "/photo/",     # Foto individual
    "/photos/",
    "/share/",     # Share-link genérico
)


def classify_url(url: str) -> tuple[bool, str]:
    """Classify a URL as (keep, reason).

    - keep=True  → vale la pena guardarla en links_log para análisis
    - keep=False → ruido (mensajería personal, status, foto). reason explica.

    Heurísticas conservadoras: en duda, mantener (la calidad final la decide
    `link_analyzer` con LLM cuando el founder ejecute análisis batch).
    """
    if not url or len(url) < 10:
        return False, "URL demasiado corta"
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        host = (p.hostname or "").lower()
        path = (p.path or "").lower()
    except Exception:  # noqa: BLE001
        return False, "URL malformada"

    if not host:
        return False, "Sin dominio"

    # Schemes no-http son sospechosos
    if p.scheme not in ("http", "https"):
        return False, f"Esquema {p.scheme!r} no soportado"

    # Dominios de ruido conocido
    if host in _NOISE_DOMAINS:
        return False, f"Red social personal ({host}) — los posts individuales no son ideas"
    if host in _UTILITY_DOMAINS:
        return False, f"Dominio de utilidad ({host})"

    # Patrones de path que indican contenido efímero
    for pat in _NOISE_PATH_PATTERNS:
        if pat in path:
            return False, f"Contenido personal/efímero (path contiene '{pat.strip('/')}')"

    # YouTube: aceptar /watch (videos largos), descartar /shorts
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        if "/shorts/" in path:
            return False, "YouTube Shorts (formato efímero personal)"
        # /watch?v= y /channel/ y /c/ pueden ser ideas
        # cae al keep por default

    # LinkedIn: posts personales (/posts/, /pulse/) sí cuentan, perfiles no
    if host in ("linkedin.com", "www.linkedin.com"):
        if "/in/" in path and "/posts/" not in path and "/recent-activity/" not in path:
            return False, "Perfil de LinkedIn (no es contenido)"

    return True, "OK"


def filter_urls_by_quality(urls: List[str]) -> tuple[List[str], List[dict]]:
    """Apply classify_url to each URL, returning (kept, discarded_with_reasons).

    discarded list is a list of {"url": str, "reason": str} so the dashboard
    can show the founder what was filtered and why.
    """
    kept: List[str] = []
    discarded: List[dict] = []
    for u in urls:
        ok, reason = classify_url(u)
        if ok:
            kept.append(u)
        else:
            discarded.append({"url": u, "reason": reason})
    return kept, discarded


def parse_text_file(content: bytes) -> str:
    """Decode bytes as text (UTF-8 with fallback)."""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1", errors="replace")


def parse_docx_file(content: bytes) -> str:
    """Extract text from a .docx file. Returns empty string if python-docx
    is not installed."""
    try:
        from io import BytesIO
        from docx import Document  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("parse_docx_file: python-docx not installed; install with `pip install python-docx`")
        return ""
    try:
        doc = Document(BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text)
    except Exception as e:  # noqa: BLE001
        logger.warning("parse_docx_file: failed to parse: %s", e)
        return ""


def parse_file(filename: str, content: bytes) -> str:
    """Dispatch by extension. Returns the extracted text."""
    name = (filename or "").lower()
    if name.endswith(".docx"):
        return parse_docx_file(content)
    # .txt, .csv, WhatsApp chats, and unknown -> try plain text
    return parse_text_file(content)


__all__ = ["extract_urls", "parse_text_file", "parse_docx_file", "parse_file"]
