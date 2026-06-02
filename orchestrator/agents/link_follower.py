"""
M10.0 — LinkFollowerAgent.

Mines the evidence_urls of approved/promoted signals to surface NEW source
candidates the founder can add to the cazador. Three discovery patterns:

  1. <link rel="alternate" type="application/rss+xml" href="..."> on the
     destination HTML — finds blog RSS feeds.
  2. github.com/<user>/<repo>/... → propose RSS at /releases.atom
     (so we track new releases of repos we've already deemed interesting).
  3. reddit.com/r/<sub>/... → propose a `reddit` source with target=sub.

The agent is intentionally non-LLM (deterministic + free) so it can run in
a cron loop without budget concerns. It returns a list of ProposedSource
dicts that the dashboard surfaces in /cazar/fuentes for approve/reject.

Design choice — no DB writes here: the agent ONLY proposes. The endpoint
layer (api.py) decides whether to persist proposals or just return them.
This keeps the agent pure and the side effects auditable.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# Regex for github repo path: /<owner>/<repo> with optional trailing path
_GITHUB_REPO_RE = re.compile(r"^/([^/]+)/([^/]+)(/.*)?$")
# Regex for reddit subreddit path: /r/<sub>/...
_REDDIT_SUB_RE = re.compile(r"^/r/([^/]+)(/.*)?$", re.IGNORECASE)
# Regex for the <link rel="alternate" ... type="application/rss+xml" href="...">
# We use a generic alternate-link matcher because the order of attrs varies.
_LINK_TAG_RE = re.compile(
    r"<link\b[^>]*?>",
    re.IGNORECASE,
)
_ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"', re.IGNORECASE)


@dataclass
class ProposedSource:
    """A single source proposal — what to add and why."""
    kind: str               # 'rss' | 'github_trending' | 'reddit' | ...
    target: str             # URL or subreddit name
    name: str               # Human-readable display label
    reason: str             # Why we proposed this (audit trail)
    origin_url: str = ""    # Which evidence_url we discovered it from
    score: float = 0.5      # Confidence 0.0-1.0; higher = more likely useful


@dataclass
class FollowResult:
    """Aggregate of all proposals discovered for one signal."""
    signal_id: int
    proposals: List[ProposedSource] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure pattern detectors (no I/O — fully testable)
# ---------------------------------------------------------------------------

def detect_github_releases(url: str) -> Optional[ProposedSource]:
    """If URL is github.com/<owner>/<repo>, propose releases.atom."""
    try:
        p = urlparse(url)
    except Exception:  # noqa: BLE001
        return None
    if "github.com" not in (p.netloc or "").lower():
        return None
    m = _GITHUB_REPO_RE.match(p.path or "")
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    # Avoid github.com/<user> profile pages (no repo)
    if not repo or repo in {"settings", "marketplace", "explore", "topics"}:
        return None
    releases_url = f"https://github.com/{owner}/{repo}/releases.atom"
    return ProposedSource(
        kind="rss",
        target=releases_url,
        name=f"GitHub releases — {owner}/{repo}",
        reason=f"Approved signal links to {owner}/{repo}; tracking new releases",
        origin_url=url,
        score=0.75,
    )


def detect_reddit_subreddit(url: str) -> Optional[ProposedSource]:
    """If URL is reddit.com/r/<sub>/..., propose adding the subreddit."""
    try:
        p = urlparse(url)
    except Exception:  # noqa: BLE001
        return None
    host = (p.netloc or "").lower()
    if not (host == "reddit.com" or host.endswith(".reddit.com")):
        return None
    m = _REDDIT_SUB_RE.match(p.path or "")
    if not m:
        return None
    sub = m.group(1)
    # Skip reserved / meta paths that aren't actual subreddits
    if sub.lower() in {"all", "popular", "random"}:
        return None
    return ProposedSource(
        kind="reddit",
        target=sub,
        name=f"Reddit r/{sub}",
        reason=f"Approved signal links to a comment/post in r/{sub}",
        origin_url=url,
        score=0.65,
    )


def extract_rss_links_from_html(html: str, base_url: str) -> List[ProposedSource]:
    """Find <link rel='alternate' type='application/rss+xml' href='...'> tags.

    Returns one proposal per discovered feed. The score is high (0.85)
    because alternate-RSS-link is an explicit publisher signal — "yes, we
    have a feed at this URL".
    """
    results: List[ProposedSource] = []
    if not html or "<link" not in html.lower():
        return results
    for tag in _LINK_TAG_RE.findall(html):
        attrs = {k.lower(): v for k, v in _ATTR_RE.findall(tag)}
        if attrs.get("rel", "").lower() != "alternate":
            continue
        ctype = attrs.get("type", "").lower()
        if "rss" not in ctype and "atom" not in ctype:
            continue
        href = attrs.get("href")
        if not href:
            continue
        # Resolve relative href to absolute
        resolved = _resolve_href(base_url, href)
        if not resolved:
            continue
        title = attrs.get("title") or _domain_of(base_url) or "Discovered feed"
        results.append(ProposedSource(
            kind="rss",
            target=resolved,
            name=f"Feed — {title}",
            reason=f"<link rel='alternate' type='{ctype}'> tag at {base_url}",
            origin_url=base_url,
            score=0.85,
        ))
    return results


# ---------------------------------------------------------------------------
# Orchestrator — the agent's public surface
# ---------------------------------------------------------------------------


class LinkFollowerAgent:
    """Stateless agent. Pass evidence_urls in, get proposals out.

    HTML fetching is optional and best-effort. If httpx is unavailable or
    the request fails, we still return the pattern-based proposals
    (github / reddit) — fail-soft by design so the cron loop keeps moving.
    """

    def __init__(self, fetch_html: Optional[callable] = None) -> None:
        # Allow tests to inject a stub fetcher without monkeypatching httpx
        self._fetch_html = fetch_html or _default_fetch_html

    def follow(self, signal_id: int, evidence_urls: Iterable[str]) -> FollowResult:
        result = FollowResult(signal_id=signal_id)
        seen_targets: set = set()
        for url in (evidence_urls or []):
            if not url:
                continue
            # Pattern proposals (no I/O — always run first)
            for fn in (detect_github_releases, detect_reddit_subreddit):
                p = fn(url)
                if p and p.target not in seen_targets:
                    seen_targets.add(p.target)
                    result.proposals.append(p)
            # HTML-derived proposals (network call; best-effort)
            try:
                html = self._fetch_html(url)
            except Exception as e:  # noqa: BLE001
                result.errors.append(f"fetch failed for {url}: {e}")
                continue
            if not html:
                continue
            for p in extract_rss_links_from_html(html, url):
                if p.target not in seen_targets:
                    seen_targets.add(p.target)
                    result.proposals.append(p)
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_href(base: str, href: str) -> Optional[str]:
    """Resolve a relative href against a base URL. Returns absolute URL or
    None if base is unparseable."""
    if not href:
        return None
    if href.startswith("http://") or href.startswith("https://"):
        return href
    try:
        from urllib.parse import urljoin
        return urljoin(base, href)
    except Exception:  # noqa: BLE001
        return None


def _domain_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().replace("www.", "")
    except Exception:  # noqa: BLE001
        return ""


def _default_fetch_html(url: str) -> str:
    """Default httpx-based fetcher. ~2s timeout, 64KB max body to avoid
    pulling multi-MB pages we'll mostly ignore."""
    try:
        import httpx
    except ImportError:
        return ""
    try:
        with httpx.Client(
            timeout=2.5, follow_redirects=True,
            headers={"User-Agent": "CircleLLC-LinkFollower/1.0"},
        ) as c:
            r = c.get(url)
            if r.status_code >= 400:
                return ""
            # Read at most ~64KB. Most pages have <link rel=alternate> in <head>
            # well within that budget.
            return r.text[:65_536]
    except Exception as e:  # noqa: BLE001
        logger.debug("link_follower: fetch %s failed: %s", url, e)
        return ""


__all__ = [
    "ProposedSource",
    "FollowResult",
    "LinkFollowerAgent",
    "detect_github_releases",
    "detect_reddit_subreddit",
    "extract_rss_links_from_html",
]
