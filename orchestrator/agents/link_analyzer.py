"""
LinkAnalyzer — classifies a fetched URL into idea / not-idea + extracts
structured metadata (sector, area) for the bitácora.

ADR-013 reactivates this agent from _deferred/. Use case:
- User uploads a WhatsApp chat or Word doc with dozens of URLs
- file_parser extracts the URLs
- For each URL, source_fetcher.fetch_url() pulls the content
- link_analyzer decides: is this an idea/pain-point/opportunity signal?
  - YES -> summarize + sector + area_of_application
  - NO  -> reject with reason (e.g. "promo article", "404", "off-topic")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from ..core.base_agent import BaseAgent
from ..core.source_fetcher import FetchedItem

logger = logging.getLogger(__name__)


_SYSTEM = """You are LinkAnalyzer — a triage agent for the Factory of Factories.

YOUR SCOPE (do exactly this, nothing else):
- Read the content of ONE web page (already fetched as plain text)
- Decide if it contains a startup idea, market pain point, or business opportunity
- If YES: extract a concise summary + sector + area of application
- If NO: reject with a short reason

ACCEPT (status = "analyzed") if the page:
- Describes a real problem people experience (pain points, frustrations)
- Discusses a product/service with clear value proposition
- Reports market data, trends, or sector dynamics
- Is a founder's blog post / startup announcement / case study

REJECT (status = "rejected") if the page:
- Is a 404 or has no useful content
- Is a generic article about productivity/AI hype with no concrete pain
- Is promotional spam, recipe, news headline without depth
- Is in a language we can't analyze well
- Is a homepage / category page with no specific topic

OUTPUT FORMAT (strict JSON, no markdown fences):
{
  "status": "analyzed" | "rejected",
  "idea_summary": "1-2 sentences max — the core insight from this page",   // null if rejected
  "sector": "fintech | healthtech | edtech | ecommerce | saas | marketplace | community | media | logistics | proptech | other",  // null if rejected
  "area": "Short specific area (e.g. 'pagos B2B Ecuador', 'recetas digitales rurales')",  // null if rejected
  "rejection_reason": "Short reason"  // null if analyzed
}"""


@dataclass
class LinkAnalysis:
    status: str   # "analyzed" | "rejected"
    idea_summary: Optional[str]
    sector: Optional[str]
    area: Optional[str]
    rejection_reason: Optional[str]


class LinkAnalyzerAgent(BaseAgent):
    """Single LLM call per URL. Cheap (~$0.005-0.01). Mock-friendly."""

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def analyze(self, item: FetchedItem) -> LinkAnalysis:
        if self._mock_mode:
            return self._mock_analyze(item)
        body = (item.body or item.summary or item.title or "").strip()
        if not body:
            return LinkAnalysis(
                status="rejected",
                idea_summary=None, sector=None, area=None,
                rejection_reason="empty content (page returned no extractable text)",
            )
        prompt = (
            f"URL: {item.url}\n"
            f"Title: {item.title}\n\n"
            f"Content (truncated):\n{body[:3500]}\n\n"
            f"Respond with JSON only."
        )
        try:
            raw = self._call(prompt, max_tokens=600)
            data = self._extract_json(raw)
        except Exception as e:  # noqa: BLE001
            logger.warning("link_analyzer: LLM call failed: %s", e)
            return LinkAnalysis(
                status="error",
                idea_summary=None, sector=None, area=None,
                rejection_reason=f"analyzer error: {e}",
            )
        status = str(data.get("status", "rejected")).lower()
        if status not in ("analyzed", "rejected"):
            status = "rejected"
        return LinkAnalysis(
            status=status,
            idea_summary=data.get("idea_summary") if status == "analyzed" else None,
            sector=data.get("sector") if status == "analyzed" else None,
            area=data.get("area") if status == "analyzed" else None,
            rejection_reason=data.get("rejection_reason") if status == "rejected" else None,
        )

    def _mock_analyze(self, item: FetchedItem) -> LinkAnalysis:
        """
        Deterministic mock:
        - empty content   -> rejected
        - title mentions promo/news/recipe -> rejected
        - otherwise       -> analyzed with placeholder fields
        """
        body = (item.body or item.summary or item.title or "").strip().lower()
        if not body:
            return LinkAnalysis(
                status="rejected",
                idea_summary=None, sector=None, area=None,
                rejection_reason="empty content",
            )
        if any(k in body for k in ("receta", "lottery", "promo", "horoscope")):
            return LinkAnalysis(
                status="rejected",
                idea_summary=None, sector=None, area=None,
                rejection_reason="off-topic content",
            )
        return LinkAnalysis(
            status="analyzed",
            idea_summary=f"Mock summary of {item.title[:80] or item.url}",
            sector="saas",
            area="LATAM pain point",
            rejection_reason=None,
        )


__all__ = ["LinkAnalyzerAgent", "LinkAnalysis"]
