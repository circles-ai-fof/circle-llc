"""
M13.0 — SecurityValidator (heuristic static).

Per the security-validator spec, this module validates the safety of URLs
that enter the cazador (manual /api/v1/sources POST, SourceDiscoveryAgent
proposals, LinkFollowerAgent discoveries). Without it the autonomous
discovery agents M9.4 + M10.0 are a bypass of human curation: a malicious
URL recommended by Gemini lands directly in the source list.

This is the ZERO-COST tier — pure regex / Unicode / dictionary heuristics.
External-API tiers (VirusTotal, urlscan.io, OSV) come in M13.2+. The
module never makes network calls so it's safe to invoke synchronously
during ingestion.

Verdicts (per spec — verbatim):
  SAFE        no suspicious signals at all
  SUSPICIOUS  one or more weak red flags
  DANGEROUS   strong red flag (typosquat of well-known brand, .exe download)
  UNKNOWN     can't decide — default to caution, not SAFE

Principle of safe bias: when in doubt, escalate to SUSPICIOUS or UNKNOWN,
never SAFE. A false SAFE is the worst possible error.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# Well-known domains the cazador trusts. Typosquatting check measures
# Levenshtein distance against these. Distance 1-2 = highly suspicious
# (almost certainly impersonation).
_TRUSTED_DOMAINS = {
    # AI / dev tools
    "openai.com", "anthropic.com", "github.com", "huggingface.co",
    "gemini.google.com", "claude.ai", "x.ai", "deepmind.google",
    # Big tech
    "google.com", "microsoft.com", "apple.com", "amazon.com", "meta.com",
    # Dev publishing
    "vercel.com", "netlify.com", "cloudflare.com", "stackoverflow.com",
    "developer.mozilla.org", "ycombinator.com",
    # Social / forums
    "reddit.com", "news.ycombinator.com", "producthunt.com",
    "twitter.com", "x.com", "bluesky.social", "linkedin.com",
    # Newsletters / content
    "substack.com", "medium.com", "indiehackers.com", "techcrunch.com",
    # Storage / marketplaces
    "apps.apple.com", "play.google.com", "chrome.google.com",
    # Payment / financial
    "stripe.com", "paypal.com", "sec.gov",
}

# Free / commonly-abused TLDs. Not auto-DANGEROUS but a strong contributor
# to SUSPICIOUS when combined with other signals.
_ABUSED_TLDS = {".tk", ".ml", ".ga", ".cf", ".gq", ".top", ".xyz", ".zip", ".review"}

# URL shorteners — they HIDE the real destination. Cazador should never
# accept a source whose target is a shortener (won't know what's behind it).
_SHORTENERS = {
    "bit.ly", "tinyurl.com", "goo.gl", "t.co", "ow.ly", "is.gd",
    "buff.ly", "soo.gd", "rebrand.ly", "cutt.ly", "shorturl.at",
    "rb.gy", "bl.ink",
}

# File extensions that should NEVER be a source target (binaries to install).
_DANGEROUS_EXTENSIONS = {
    ".exe", ".msi", ".scr", ".bat", ".cmd", ".com", ".pif",
    ".jar", ".vbs", ".js", ".jse", ".wsf", ".wsh",
    ".dmg", ".pkg", ".app",
    ".apk", ".ipa", ".xap",
    ".deb", ".rpm",
    ".ps1", ".psm1",
}

# Unicode-confusable groups: Cyrillic and Greek letters that LOOK like
# Latin letters. If a domain mixes scripts it's almost always an
# impersonation attempt (homoglyph attack).
_LATIN_LOOKALIKES = {
    # Cyrillic that looks Latin
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C", "У": "Y", "Х": "X",
    "В": "B", "К": "K", "М": "M", "Н": "H", "Т": "T",
    # Greek that looks Latin
    "ο": "o", "ν": "v", "ρ": "p", "τ": "t",
}


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------

@dataclass
class SecuritySignal:
    """One specific finding raised against the URL."""
    severity: str   # "weak" | "strong"
    code: str       # machine-readable, e.g. "homoglyph_in_host"
    message: str    # human-readable explanation
    evidence: str = ""  # the exact substring that triggered the check


@dataclass
class SecurityVerdict:
    """Result of a URL validation."""
    verdict: str          # "SAFE" | "SUSPICIOUS" | "DANGEROUS" | "UNKNOWN"
    confidence: str       # "alta" | "media" | "baja"
    signals: List[SecuritySignal] = field(default_factory=list)
    recommendation: str = ""
    url: str = ""

    @property
    def strong_signals(self) -> List[SecuritySignal]:
        return [s for s in self.signals if s.severity == "strong"]

    @property
    def weak_signals(self) -> List[SecuritySignal]:
        return [s for s in self.signals if s.severity == "weak"]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def validate_url(url: str, link_text: Optional[str] = None) -> SecurityVerdict:
    """Run all heuristic checks on a URL and emit a verdict.

    Args:
        url:        the URL to validate
        link_text:  the visible text of the link, if any (used to detect
                    label-vs-href mismatch — a classic phishing pattern)

    Returns SecurityVerdict. NEVER raises. Empty/malformed URL → UNKNOWN.
    """
    verdict = SecurityVerdict(verdict="UNKNOWN", confidence="baja", url=url or "")
    if not url or not isinstance(url, str):
        verdict.signals.append(SecuritySignal(
            severity="weak",
            code="empty_url",
            message="URL vacía o no es string",
        ))
        verdict.recommendation = "no abrir — URL inválida"
        return verdict

    try:
        parsed = urlparse(url.strip())
    except Exception:  # noqa: BLE001
        verdict.signals.append(SecuritySignal(
            severity="strong",
            code="malformed_url",
            message="No se pudo parsear la URL",
        ))
        verdict.verdict = "DANGEROUS"
        verdict.confidence = "alta"
        verdict.recommendation = "no abrir — URL malformada"
        return verdict

    scheme = (parsed.scheme or "").lower()
    host = (parsed.netloc or "").lower().split(":", 1)[0]
    path = parsed.path or ""

    # 1. Scheme check
    if scheme not in {"https", "http"}:
        verdict.signals.append(SecuritySignal(
            severity="strong",
            code="non_http_scheme",
            message=f"Esquema no HTTP(S): {scheme!r}",
            evidence=scheme,
        ))
    if scheme == "http":
        verdict.signals.append(SecuritySignal(
            severity="weak",
            code="plain_http",
            message="URL sin TLS (http://) — propensa a MITM",
        ))

    # 2. No host = unparseable
    if not host:
        verdict.signals.append(SecuritySignal(
            severity="strong",
            code="no_host",
            message="URL sin host",
        ))
        verdict.verdict = "DANGEROUS"
        verdict.confidence = "alta"
        verdict.recommendation = "no abrir"
        return verdict

    # 3. URL shortener — hides destination. Cazador shouldn't accept these.
    if host in _SHORTENERS:
        verdict.signals.append(SecuritySignal(
            severity="strong",
            code="url_shortener",
            message=f"URL shortener detectado ({host}) — oculta el destino real",
            evidence=host,
        ))

    # 4. Abused TLD
    tld = "." + host.rsplit(".", 1)[-1] if "." in host else ""
    if tld in _ABUSED_TLDS:
        verdict.signals.append(SecuritySignal(
            severity="weak",
            code="abused_tld",
            message=f"TLD frecuentemente abusado para phishing ({tld})",
            evidence=tld,
        ))

    # 5. Homoglyph / mixed-script detection
    homo_hits = detect_homoglyphs(host)
    for ch in homo_hits:
        verdict.signals.append(SecuritySignal(
            severity="strong",
            code="homoglyph_in_host",
            message=f"Carácter homoglifo {ch!r} en el host (impersonation)",
            evidence=ch,
        ))

    # 6. Punycode (IDN) usage — not auto-bad but worth flagging
    if "xn--" in host:
        verdict.signals.append(SecuritySignal(
            severity="weak",
            code="punycode_host",
            message="Host usa punycode (IDN) — verificar manualmente",
            evidence=host,
        ))

    # 7. Typosquatting against the trusted allowlist
    squat = detect_typosquat(host)
    if squat:
        target, distance = squat
        verdict.signals.append(SecuritySignal(
            severity="strong",
            code="typosquat",
            message=(
                f"Posible typosquat de {target!r} "
                f"(distancia Levenshtein={distance})"
            ),
            evidence=f"{host} ~ {target}",
        ))

    # 8. Dangerous file extension in path
    path_lower = path.lower()
    for ext in _DANGEROUS_EXTENSIONS:
        if path_lower.endswith(ext):
            verdict.signals.append(SecuritySignal(
                severity="strong",
                code="executable_download",
                message=f"URL apunta directamente a un binario ({ext})",
                evidence=ext,
            ))
            break

    # 9. Label/href mismatch — classic phishing
    if link_text:
        mismatch = detect_label_href_mismatch(link_text, host)
        if mismatch:
            verdict.signals.append(SecuritySignal(
                severity="strong",
                code="label_href_mismatch",
                message=(
                    f"El texto del link dice {link_text!r} pero el host real "
                    f"es {host!r}"
                ),
                evidence=f"{link_text!r} vs {host}",
            ))

    # 10. Suspicious subdomain depth (more than 4 levels often = phishing)
    label_count = host.count(".") + 1
    if label_count >= 5:
        verdict.signals.append(SecuritySignal(
            severity="weak",
            code="deep_subdomain",
            message=f"Subdominio inusualmente profundo ({label_count} labels)",
            evidence=host,
        ))

    # 11. IP-address-as-host
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
        verdict.signals.append(SecuritySignal(
            severity="strong",
            code="ip_host",
            message="Host es una IP literal (no un dominio nombrado)",
            evidence=host,
        ))

    # 12. @ in URL (classic spoofing trick: http://google.com@evil.com)
    if "@" in (parsed.netloc or ""):
        verdict.signals.append(SecuritySignal(
            severity="strong",
            code="userinfo_in_url",
            message="URL contiene userinfo (@) — clásico truco de spoofing",
            evidence=parsed.netloc,
        ))

    # 13. Excessive hyphens in host (heuristic — phishing domains often
    # chain "secure-login-microsoft-update")
    if host.count("-") >= 4:
        verdict.signals.append(SecuritySignal(
            severity="weak",
            code="excessive_hyphens",
            message=f"Host con muchos guiones ({host.count('-')}) — patrón phishing",
            evidence=host,
        ))

    # Combine: tally severity → final verdict
    return _finalize_verdict(verdict)


# ---------------------------------------------------------------------------
# Sub-detectors (also exported so callers can run individual checks)
# ---------------------------------------------------------------------------

def detect_homoglyphs(host: str) -> List[str]:
    """Return the homoglyph characters found in the host. Empty list when
    the host is pure ASCII (Latin-only)."""
    found: List[str] = []
    for ch in host:
        if ch in _LATIN_LOOKALIKES:
            found.append(ch)
            continue
        # General Unicode category check: non-Latin letter inside what
        # looks like a Latin word is a strong signal.
        if ch.isalpha() and ord(ch) > 127:
            # Skip emoji range etc. — only LETTERS count
            cat = unicodedata.category(ch)
            if cat.startswith("L"):
                # Mixed Latin + non-Latin letters in same host = suspicious
                if any(c.isascii() and c.isalpha() for c in host):
                    found.append(ch)
    return found


def detect_typosquat(host: str) -> Optional[Tuple[str, int]]:
    """If `host` is within Levenshtein distance 1-2 of a trusted domain
    (but not exactly equal), return (trusted_match, distance). Else None.
    """
    host = host.lower().removeprefix("www.")
    if not host or "." not in host:
        return None
    # Don't flag exact matches or known-good subdomains
    for trusted in _TRUSTED_DOMAINS:
        if host == trusted or host.endswith("." + trusted):
            return None
    # Otherwise check distance against each trusted apex
    best: Optional[Tuple[str, int]] = None
    for trusted in _TRUSTED_DOMAINS:
        d = _levenshtein(host, trusted)
        if 0 < d <= 2:
            if best is None or d < best[1]:
                best = (trusted, d)
    return best


def detect_label_href_mismatch(link_text: str, host: str) -> bool:
    """If the visible text claims one domain but href points elsewhere,
    it's a classic phishing pattern."""
    if not link_text or not host:
        return False
    text_lower = link_text.lower()
    # Look for a domain-like token in the visible text
    m = re.search(r"\b([a-z0-9-]+\.[a-z]{2,})\b", text_lower)
    if not m:
        return False
    claimed = m.group(1)
    actual = host.removeprefix("www.")
    if claimed == actual:
        return False
    # Mismatch only if the claim looks like a trusted brand
    if claimed in _TRUSTED_DOMAINS:
        return True
    return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _levenshtein(a: str, b: str) -> int:
    """Iterative Levenshtein distance. Small inputs only (hostnames)."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(
                cur[j - 1] + 1,        # insertion
                prev[j] + 1,           # deletion
                prev[j - 1] + cost,    # substitution
            )
        prev = cur
    return prev[-1]


def _finalize_verdict(v: SecurityVerdict) -> SecurityVerdict:
    """Combine the accumulated signals into the final verdict per spec.

    Rules (safe-biased):
      - Any strong signal -> DANGEROUS, confianza alta
      - Two or more weak signals -> SUSPICIOUS, confianza media
      - One weak signal -> SUSPICIOUS, confianza baja
      - No signals -> SAFE, confianza alta
    """
    strong = v.strong_signals
    weak = v.weak_signals
    if strong:
        v.verdict = "DANGEROUS"
        v.confidence = "alta"
        codes = ", ".join({s.code for s in strong})
        v.recommendation = f"no abrir — señales fuertes: {codes}"
    elif len(weak) >= 2:
        v.verdict = "SUSPICIOUS"
        v.confidence = "media"
        v.recommendation = "abrir solo en entorno aislado o descartar"
    elif len(weak) == 1:
        v.verdict = "SUSPICIOUS"
        v.confidence = "baja"
        v.recommendation = "verificar manualmente antes de adoptar"
    else:
        v.verdict = "SAFE"
        v.confidence = "alta"
        v.recommendation = "abrir / adoptar (heurístico — no es garantía absoluta)"
    return v


__all__ = [
    "SecurityVerdict",
    "SecuritySignal",
    "validate_url",
    "detect_homoglyphs",
    "detect_typosquat",
    "detect_label_href_mismatch",
]
