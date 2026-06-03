"""
M12.1 — Solution-type heuristic classifier.

Per the OpportunityScout spec, every signal should also be tagged by the
TYPE OF SOLUTION the opportunity points to. Letting the founder filter the
dashboard by "show me only ideas that would become a webapp/SaaS" is more
useful than the general content_type (noticia/blog/producto/video) we
already store from M4.3.

Taxonomy (verbatim from the spec):

  app_movil               — native mobile (iOS / Android / cross-platform)
  webapp_saas             — web SaaS dashboards / web apps
  sitio_web               — static / marketing / portfolio sites
  automatizacion_agente   — workflow automation / AI agents / scripts
  extension               — browser / IDE / Slack extensions
  marketplace             — multi-sided platforms (buyers + sellers)
  infoproducto_contenido  — courses, books, newsletters, ebooks
  servicio                — agency / consulting / done-for-you

This is a HEURISTIC classifier — no LLM cost. Each candidate type has a
keyword set; the type with the highest weighted hit count wins. If nothing
matches at all we return "unknown" instead of guessing.

The classifier looks at: theme + excerpt + first evidence URL host.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# Canonical taxonomy values — caller-stable.
SOLUTION_TYPES = (
    "app_movil",
    "webapp_saas",
    "sitio_web",
    "automatizacion_agente",
    "extension",
    "marketplace",
    "infoproducto_contenido",
    "servicio",
    "unknown",
)


@dataclass
class SolutionClassification:
    kind: str             # one of SOLUTION_TYPES
    confidence: float     # 0.0-1.0 (weighted-hit ratio)
    matched_keywords: List[str]


# Each tuple is (regex, weight). Higher weight = stronger signal of that type.
# Word boundaries used so "ios" doesn't fire on "iosevka" font.
_RULES: Dict[str, List[Tuple[re.Pattern, float]]] = {
    "app_movil": [
        (re.compile(r"\b(ios|iphone|ipad)\b", re.I), 2.0),
        (re.compile(r"\b(android|play\s*store)\b", re.I), 2.0),
        (re.compile(r"\b(react\s*native|flutter|swift\s?ui|kotlin)\b", re.I), 2.0),
        (re.compile(r"\b(app\s+store|tienda\s+de\s+apps)\b", re.I), 1.5),
        (re.compile(r"\b(app\s+m[óo]vil|aplicaci[óo]n\s+m[óo]vil)\b", re.I), 2.0),
        (re.compile(r"\b(mobile\s+app)\b", re.I), 1.5),
    ],
    "webapp_saas": [
        (re.compile(r"\b(saas|software[\-\s]as[\-\s]a[\-\s]service)\b", re.I), 2.5),
        (re.compile(r"\b(dashboard|admin\s+panel|cms)\b", re.I), 1.0),
        (re.compile(r"\b(next\.?js|nuxt|svelte|remix|astro)\b", re.I), 1.5),
        (re.compile(r"\b(web\s*app|webapp)\b", re.I), 2.0),
        (re.compile(r"\b(login|signup|onboarding)\b", re.I), 0.5),
        (re.compile(r"\b(subscription|monthly\s+plan|mensual)\b", re.I), 0.8),
        (re.compile(r"\.(io|app|dev)\b", re.I), 0.4),
    ],
    "sitio_web": [
        (re.compile(r"\b(landing\s+page|landing|sitio\s+web|website)\b", re.I), 1.5),
        (re.compile(r"\b(portfolio|portafolio|p[áa]gina\s+personal)\b", re.I), 2.0),
        (re.compile(r"\b(blog|wordpress|ghost|webflow)\b", re.I), 1.0),
        (re.compile(r"\b(seo\s+optimized|marketing\s+site)\b", re.I), 1.0),
    ],
    "automatizacion_agente": [
        (re.compile(r"\b(automat[ei]|automation|automatiza)\b", re.I), 1.5),
        (re.compile(r"\b(ai\s+agent|agente\s+(de\s+)?ia|llm\s+agent)\b", re.I), 2.5),
        (re.compile(r"\b(workflow|n8n|zapier|make\.com)\b", re.I), 2.0),
        (re.compile(r"\b(script|bash|python\s+script|cron)\b", re.I), 0.8),
        (re.compile(r"\b(rpa|bot\b|chatbot)\b", re.I), 1.5),
        (re.compile(r"\b(autonomous|auton[óo]mo)\b", re.I), 1.0),
    ],
    "extension": [
        (re.compile(r"\b(chrome\s+extension|firefox\s+addon|edge\s+extension)\b", re.I), 3.0),
        (re.compile(r"\b(browser\s+extension|extensi[óo]n\s+(de|para)\s+navegador)\b", re.I), 2.5),
        (re.compile(r"\b(vscode\s+extension|vs\s+code\s+extension|jetbrains\s+plugin)\b", re.I), 2.5),
        (re.compile(r"\b(slack\s+app|slack\s+integration|figma\s+plugin)\b", re.I), 2.0),
        (re.compile(r"\b(manifest\s*v?[23])\b", re.I), 1.5),
    ],
    "marketplace": [
        (re.compile(r"\bmarketplace\b", re.I), 2.5),
        (re.compile(r"\b(two[\-\s]sided|multi[\-\s]sided)\s+platform\b", re.I), 2.5),
        (re.compile(r"\b(buyers\s+and\s+sellers|compradores\s+y\s+vendedores)\b", re.I), 2.0),
        (re.compile(r"\b(p2p|peer[\-\s]to[\-\s]peer)\b", re.I), 1.0),
        (re.compile(r"\b(commission\s+based|comisi[óo]n\s+por\s+transacci[óo]n)\b", re.I), 1.5),
    ],
    "infoproducto_contenido": [
        (re.compile(r"\b(course|curso|bootcamp|workshop)\b", re.I), 1.5),
        (re.compile(r"\b(ebook|book|libro\s+digital|pdf\s+guide)\b", re.I), 1.5),
        (re.compile(r"\b(newsletter|substack|paid\s+newsletter)\b", re.I), 2.0),
        (re.compile(r"\b(youtube\s+channel|podcast|patreon)\b", re.I), 1.0),
        (re.compile(r"\b(membership\s+site|comunidad\s+(de\s+)?pago)\b", re.I), 1.5),
        (re.compile(r"\b(infoproducto|info[\-\s]producto)\b", re.I), 3.0),
    ],
    "servicio": [
        (re.compile(r"\b(consultoria|consulting|consultor[íi]a)\b", re.I), 2.0),
        (re.compile(r"\b(agency|agencia)\b", re.I), 2.0),
        (re.compile(r"\b(done[\-\s]for[\-\s]you|hecho\s+para\s+(ti|usted))\b", re.I), 1.5),
        (re.compile(r"\b(servicio\s+profesional|professional\s+service)\b", re.I), 1.0),
        (re.compile(r"\b(freelance|freelancer)\b", re.I), 1.0),
        (re.compile(r"\b(implementation\s+service|outsourcing)\b", re.I), 1.0),
    ],
}

# URL-host hints — concrete domain patterns that are a strong signal even
# when the surrounding text is vague.
_HOST_HINTS: Dict[str, str] = {
    "play.google.com": "app_movil",
    "apps.apple.com": "app_movil",
    "chrome.google.com": "extension",
    "addons.mozilla.org": "extension",
    "marketplace.visualstudio.com": "extension",
    "github.com/marketplace": "extension",
    "store.figma.com": "extension",
    "slack.com/apps": "extension",
    "amazon.com": "marketplace",
    "etsy.com": "marketplace",
    "udemy.com": "infoproducto_contenido",
    "gumroad.com": "infoproducto_contenido",
    "substack.com": "infoproducto_contenido",
    "n8n.io": "automatizacion_agente",
    "zapier.com": "automatizacion_agente",
    "make.com": "automatizacion_agente",
    "fiverr.com": "servicio",
    "upwork.com": "servicio",
    "webflow.com": "sitio_web",
}


def classify_solution(
    theme: str,
    excerpt: str = "",
    url: Optional[str] = None,
) -> SolutionClassification:
    """Classify an opportunity into the 8-way solution taxonomy.

    Inputs:
      theme:    short title of the signal
      excerpt:  longer summary text
      url:      first evidence URL (host inspected for hints)

    Returns SolutionClassification with kind="unknown" + confidence=0.0
    when nothing matches.
    """
    text = f"{theme or ''} {excerpt or ''}"
    if not text.strip() and not url:
        return SolutionClassification(
            kind="unknown", confidence=0.0, matched_keywords=[],
        )

    scores: Dict[str, float] = {}
    matched: Dict[str, List[str]] = {}

    # 1. Keyword matches on text
    for kind, rules in _RULES.items():
        total = 0.0
        kw: List[str] = []
        for pattern, weight in rules:
            m = pattern.search(text)
            if m:
                total += weight
                kw.append(m.group(0))
        if total > 0:
            scores[kind] = total
            matched[kind] = kw

    # 2. URL host hint (additive)
    if url:
        try:
            host = (urlparse(url).netloc or "").lower().lstrip("www.")
            for needle, hinted_kind in _HOST_HINTS.items():
                if needle in host or host.startswith(needle):
                    scores[hinted_kind] = scores.get(hinted_kind, 0.0) + 2.5
                    matched.setdefault(hinted_kind, []).append(f"host:{needle}")
                    break
        except Exception:  # noqa: BLE001
            pass

    if not scores:
        return SolutionClassification(
            kind="unknown", confidence=0.0, matched_keywords=[],
        )

    # Winner = highest score. Confidence = winner / (winner + sum_others).
    winner = max(scores, key=scores.get)
    total_signal = sum(scores.values())
    confidence = scores[winner] / total_signal if total_signal else 0.0

    return SolutionClassification(
        kind=winner,
        confidence=round(confidence, 3),
        matched_keywords=matched.get(winner, [])[:5],
    )


__all__ = [
    "SolutionClassification",
    "SOLUTION_TYPES",
    "classify_solution",
]
