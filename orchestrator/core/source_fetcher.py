"""
Source fetcher (R28 / ADR-011).

Pulls content from external sources for the idea_hunter to ground its
generation in real-world signals. Stdlib only — no readability-lxml,
beautifulsoup4 or feedparser dependencies. We sacrifice extraction
quality for image size + supply-chain simplicity.

Supported sources:
  - URL          : raw article HTML, stripped to plaintext
  - RSS / Atom   : feed of items (title + summary + link)
  - Hacker News  : top stories from the official Firebase API
  - Reddit       : top posts of a subreddit (last 24h)
  - GitHub Trend : trending repos (scraped — GH has no official endpoint)
  - Product Hunt : daily feed (RSS)

Hard limits to bound cost + abuse:
  - per-request timeout: 8s
  - per-source max characters: 4000 (then truncated)
  - max items per feed:  10
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = "circle-llc/0.2 (+https://circles-ai.ai)"
REQUEST_TIMEOUT = 8
MAX_CHARS_PER_SOURCE = 4000
MAX_ITEMS_PER_FEED = 10

_HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
_HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class FetchedItem:
    """One piece of content fetched from a source."""
    source_kind: str       # "url" | "rss" | "hn" | "reddit" | "github_trending" | "product_hunt"
    url: str
    title: str
    summary: str           # short snippet (<=400 chars)
    body: str              # longer content (<=MAX_CHARS_PER_SOURCE)
    fetched_at: int = field(default_factory=lambda: int(time.time()))

    def to_dict(self) -> dict:
        return {
            "source_kind": self.source_kind,
            "url": self.url,
            "title": self.title,
            "summary": self.summary,
            "body": self.body,
            "fetched_at": self.fetched_at,
        }


# ---------------------------------------------------------------------------
# Low-level HTTP helper
# ---------------------------------------------------------------------------


def _http_get(url: str, timeout: int = REQUEST_TIMEOUT) -> Optional[bytes]:
    """GET with timeout + UA + content-size cap. Returns None on error."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # Read at most 5 MB (sanity)
            data = resp.read(5 * 1024 * 1024)
        return data
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        logger.warning("fetch_url failed for %s: %s", url, e)
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_url unexpected error for %s: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# HTML → text
# ---------------------------------------------------------------------------

_RE_SCRIPT = re.compile(r"<script[\s\S]*?</script>", re.IGNORECASE)
_RE_STYLE = re.compile(r"<style[\s\S]*?</style>", re.IGNORECASE)
_RE_NAV = re.compile(r"<(?:nav|header|footer|aside|form)[\s\S]*?</(?:nav|header|footer|aside|form)>", re.IGNORECASE)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_WS = re.compile(r"\s+")
_RE_ENT = re.compile(r"&(amp|lt|gt|quot|#39|nbsp|hellip|mdash|ndash);")


def _html_to_text(html: str) -> str:
    """Best-effort plaintext extraction from HTML. Stdlib only."""
    if not html:
        return ""
    s = _RE_SCRIPT.sub(" ", html)
    s = _RE_STYLE.sub(" ", s)
    s = _RE_NAV.sub(" ", s)
    s = _RE_TAG.sub(" ", s)
    # Decode common entities
    entities = {
        "amp": "&", "lt": "<", "gt": ">", "quot": '"',
        "#39": "'", "nbsp": " ", "hellip": "…", "mdash": "—", "ndash": "–",
    }
    s = _RE_ENT.sub(lambda m: entities.get(m.group(1), ""), s)
    s = _RE_WS.sub(" ", s).strip()
    return s


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n].rstrip() + "…"


# ---------------------------------------------------------------------------
# URL (single article)
# ---------------------------------------------------------------------------


def fetch_url(url: str) -> Optional[FetchedItem]:
    """Fetch one URL and extract plaintext. Returns None on error."""
    raw = _http_get(url)
    if raw is None:
        return None
    try:
        html = raw.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None
    text = _html_to_text(html)
    if not text:
        return None
    # Pick the longest <title> for a name (very crude — good enough)
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = _html_to_text(title_match.group(1)) if title_match else _truncate(text, 80)
    body = _truncate(text, MAX_CHARS_PER_SOURCE)
    summary = _truncate(text, 400)
    return FetchedItem(
        source_kind="url",
        url=url,
        title=title or url,
        summary=summary,
        body=body,
    )


# ---------------------------------------------------------------------------
# RSS / Atom feed
# ---------------------------------------------------------------------------


def fetch_rss(feed_url: str, max_items: int = MAX_ITEMS_PER_FEED) -> List[FetchedItem]:
    """Parse RSS/Atom and return up to `max_items` FetchedItem."""
    raw = _http_get(feed_url)
    if raw is None:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        logger.warning("fetch_rss parse failed for %s: %s", feed_url, e)
        return []

    # RSS 2.0:  <rss><channel><item><title|description|link>
    # Atom:     <feed><entry><title|summary|link>
    items: List[FetchedItem] = []
    # RSS path
    for item in root.findall(".//item")[:max_items]:
        title = (item.findtext("title") or "").strip()
        desc = _html_to_text((item.findtext("description") or "").strip())
        link = (item.findtext("link") or "").strip()
        if not title and not desc:
            continue
        items.append(
            FetchedItem(
                source_kind="rss",
                url=link or feed_url,
                title=_truncate(title, 200),
                summary=_truncate(desc, 400),
                body=_truncate(desc, MAX_CHARS_PER_SOURCE),
            )
        )
    if items:
        return items
    # Atom path
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//a:entry", ns)[:max_items]:
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        summary = _html_to_text(entry.findtext("a:summary", default="", namespaces=ns) or "")
        # link element has href attribute
        link_el = entry.find("a:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        if not title and not summary:
            continue
        items.append(
            FetchedItem(
                source_kind="rss",
                url=link or feed_url,
                title=_truncate(title, 200),
                summary=_truncate(summary, 400),
                body=_truncate(summary, MAX_CHARS_PER_SOURCE),
            )
        )
    return items


# ---------------------------------------------------------------------------
# Hacker News (Firebase API)
# ---------------------------------------------------------------------------


def fetch_hn_top(max_items: int = MAX_ITEMS_PER_FEED) -> List[FetchedItem]:
    """Top stories from Hacker News (JSON API, no auth)."""
    raw = _http_get(_HN_TOP_URL)
    if raw is None:
        return []
    try:
        ids = json.loads(raw)[:max_items]
    except json.JSONDecodeError:
        return []
    items: List[FetchedItem] = []
    for hid in ids:
        item_raw = _http_get(_HN_ITEM_URL.format(id=hid))
        if not item_raw:
            continue
        try:
            d = json.loads(item_raw)
        except json.JSONDecodeError:
            continue
        title = d.get("title", "")
        url = d.get("url", f"https://news.ycombinator.com/item?id={hid}")
        text = _html_to_text(d.get("text") or "")
        score = d.get("score", 0)
        summary = f"[{score} points] {title}"
        body = _truncate(f"{title}\n\n{text}\n\nDiscussion: https://news.ycombinator.com/item?id={hid}", MAX_CHARS_PER_SOURCE)
        items.append(
            FetchedItem(
                source_kind="hn",
                url=url,
                title=_truncate(title, 200),
                summary=_truncate(summary, 400),
                body=body,
            )
        )
    return items


# ---------------------------------------------------------------------------
# Reddit (public JSON)
# ---------------------------------------------------------------------------


def fetch_reddit(subreddit: str, max_items: int = MAX_ITEMS_PER_FEED) -> List[FetchedItem]:
    """
    Top posts of last 24h from a subreddit.
    Example subreddit: 'startups', 'SaaS', 'entrepreneur'.
    Returns empty list on rate-limit (Reddit can 429 unauthenticated requests).
    """
    subreddit = subreddit.strip().lstrip("/r/").lstrip("r/")
    url = f"https://www.reddit.com/r/{subreddit}/top.json?t=day&limit={max_items}"
    raw = _http_get(url)
    if raw is None:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    posts = data.get("data", {}).get("children", [])[:max_items]
    items: List[FetchedItem] = []
    for p in posts:
        d = p.get("data", {})
        title = d.get("title", "")
        selftext = _html_to_text(d.get("selftext", "") or "")
        score = d.get("score", 0)
        permalink = "https://reddit.com" + d.get("permalink", "")
        external_url = d.get("url", permalink)
        if not title:
            continue
        items.append(
            FetchedItem(
                source_kind="reddit",
                url=external_url,
                title=_truncate(title, 200),
                summary=_truncate(f"r/{subreddit} [{score} upvotes] — {title}", 400),
                body=_truncate(f"{title}\n\n{selftext}\n\nDiscussion: {permalink}", MAX_CHARS_PER_SOURCE),
            )
        )
    return items


# ---------------------------------------------------------------------------
# Product Hunt (RSS)
# ---------------------------------------------------------------------------


def fetch_product_hunt(max_items: int = MAX_ITEMS_PER_FEED) -> List[FetchedItem]:
    items = fetch_rss("https://www.producthunt.com/feed", max_items)
    for it in items:
        it.source_kind = "product_hunt"
    return items


# ---------------------------------------------------------------------------
# GitHub Trending (scrape — no official API)
# ---------------------------------------------------------------------------


def fetch_github_trending(max_items: int = MAX_ITEMS_PER_FEED) -> List[FetchedItem]:
    """Scrapes github.com/trending. Brittle but free."""
    raw = _http_get("https://github.com/trending")
    if raw is None:
        return []
    try:
        html = raw.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return []
    # Extract repo entries — each <article class="Box-row">
    repo_blocks = re.findall(r'<article[^>]*class="Box-row"[^>]*>(.*?)</article>', html, re.DOTALL)
    items: List[FetchedItem] = []
    for block in repo_blocks[:max_items]:
        # Repo name: <a href="/owner/name">
        href_m = re.search(r'<a\s+href="(/[^"/]+/[^"/]+)"[^>]*data-view-component', block)
        if not href_m:
            href_m = re.search(r'<a\s+href="(/[^"/]+/[^"/]+)"', block)
        if not href_m:
            continue
        path = href_m.group(1)
        url = f"https://github.com{path}"
        title = path.lstrip("/")
        # Description: <p class="col-9 ...">desc</p>
        desc_m = re.search(r'<p[^>]*col-9[^>]*>(.*?)</p>', block, re.DOTALL)
        desc = _html_to_text(desc_m.group(1)) if desc_m else ""
        items.append(
            FetchedItem(
                source_kind="github_trending",
                url=url,
                title=title,
                summary=_truncate(f"GitHub trending — {title}: {desc}", 400),
                body=_truncate(f"{title}\n\n{desc}\n\nRepo: {url}", MAX_CHARS_PER_SOURCE),
            )
        )
    return items


# ---------------------------------------------------------------------------
# Dispatch by source kind
# ---------------------------------------------------------------------------


def fetch_by_kind(kind: str, target: str = "", max_items: int = MAX_ITEMS_PER_FEED) -> List[FetchedItem]:
    """
    Generic dispatch. Returns a list (single-item for url, many for feeds).

      kind="url",        target="https://example.com/article"
      kind="rss",        target="https://feed.url/rss"
      kind="hn",         target="" (ignored)
      kind="reddit",     target="startups"
      kind="github_trending", target="" (ignored)
      kind="product_hunt", target="" (ignored)
    """
    if kind == "url":
        item = fetch_url(target)
        return [item] if item else []
    if kind == "rss":
        return fetch_rss(target, max_items)
    if kind == "hn":
        return fetch_hn_top(max_items)
    if kind == "reddit":
        return fetch_reddit(target, max_items)
    if kind == "github_trending":
        return fetch_github_trending(max_items)
    if kind == "product_hunt":
        return fetch_product_hunt(max_items)
    logger.warning("fetch_by_kind: unknown kind %r", kind)
    return []


__all__ = [
    "FetchedItem",
    "USER_AGENT",
    "REQUEST_TIMEOUT",
    "MAX_CHARS_PER_SOURCE",
    "MAX_ITEMS_PER_FEED",
    "fetch_url",
    "fetch_rss",
    "fetch_hn_top",
    "fetch_reddit",
    "fetch_product_hunt",
    "fetch_github_trending",
    "fetch_by_kind",
]
