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
