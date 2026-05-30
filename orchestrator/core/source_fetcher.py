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
    published_at: Optional[int] = None  # unix ts of ORIGINAL publication (from feed pubDate, HN time, reddit created_utc...)

    def to_dict(self) -> dict:
        return {
            "source_kind": self.source_kind,
            "url": self.url,
            "title": self.title,
            "summary": self.summary,
            "body": self.body,
            "fetched_at": self.fetched_at,
            "published_at": self.published_at,
        }


def _parse_rfc822_or_iso(s: str) -> Optional[int]:
    """Parse RFC 822 (RSS pubDate) or ISO 8601 (Atom updated) -> unix ts. None on failure."""
    if not s:
        return None
    from email.utils import parsedate_to_datetime
    from datetime import datetime
    s = s.strip()
    try:
        return int(parsedate_to_datetime(s).timestamp())
    except (TypeError, ValueError):
        pass
    # ISO 8601: 2026-05-27T14:30:00Z or with offset
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except (TypeError, ValueError):
        return None


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


def _meta_content(html: str, *names: str) -> Optional[str]:
    """Extract <meta name|property="X" content="Y"> for any of the given names.

    Order matters: prefer og: / twitter: tags (curated by the publisher).
    """
    for name in names:
        # property="og:title" or name="description" — both shapes
        pattern = (
            rf'<meta\s+(?:[^>]*?\s)?(?:property|name)\s*=\s*["\']{re.escape(name)}["\']'
            rf'[^>]*?\scontent\s*=\s*["\']([^"\']+)["\']'
        )
        m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if m:
            return _html_to_text(m.group(1))
        # Reversed order: content first, then property
        pattern2 = (
            rf'<meta\s+(?:[^>]*?\s)?content\s*=\s*["\']([^"\']+)["\']'
            rf'[^>]*?\s(?:property|name)\s*=\s*["\']{re.escape(name)}["\']'
        )
        m2 = re.search(pattern2, html, re.IGNORECASE | re.DOTALL)
        if m2:
            return _html_to_text(m2.group(1))
    return None


# M3.18 — detección de fallbacks de SPAs que requieren JS para renderizar
# (x.com, instagram, facebook, tiktok, etc.). Cuando hacemos GET con urllib
# sin ejecutar JS, recibimos un placeholder tipo "JavaScript is not available"
# en vez del contenido real. Detectamos esto y devolvemos None.
_SPA_FALLBACK_PATTERNS = (
    "javascript is not available",
    "we've detected that javascript is disabled",
    "we have detected that javascript is disabled",
    "please enable javascript",
    "you need to enable javascript",
    "you'll need to turn on javascript",
    "este navegador no soporta javascript",
    "javascript no está disponible",
    "javascript no esta disponible",
    "habilite javascript",
    "switch to a supported browser to continue",
    # Login walls genéricos
    "log in to instagram",
    "log into facebook",
    "iniciar sesión en instagram",
    "iniciar sesion en instagram",
)


def _is_spa_fallback(title: str, summary: str) -> bool:
    """True si el contenido extraído es un fallback de SPA, no contenido real."""
    blob = f"{title} {summary}".lower()
    return any(pat in blob for pat in _SPA_FALLBACK_PATTERNS)


# M4.2 — detección de descripciones corporativas (NO son ideas de negocio).
# Una "idea" describe un PROBLEMA y una posible SOLUCIÓN. Una "descripción
# corporativa" describe lo que ya hace una empresa establecida. El founder
# reportó: "Asiservy — Alimentos del Mar con Propósito" pasó como idea pero
# es la home de la empresa con texto tipo "Empresa líder en procesamiento de
# atún. 30 años, 31+ países, trazabilidad blockchain, certificaciones".
_CORPORATE_DESCRIPTION_PATTERNS = (
    "empresa líder en",
    "empresa lider en",
    "compañía líder",
    "compania lider",
    "leading company in",
    "líder en el sector",
    "lider en el sector",
    "fundada en",
    "founded in",
    "desde hace",
    "since 19",
    "since 20",
    "años de experiencia",
    "years of experience",
    "+ países",
    "+ paises",
    "+ countries",
    "trazabilidad blockchain",
    "certificaciones globales",
    "certificaciones internacionales",
    "global certifications",
    "iso 9001",
    "iso 14001",
    "iso 22000",
    "haccp",
    "brc certified",
    "msc certified",
    "fda approved",
    "our mission is",
    "nuestra misión",
    "nuestra mision",
    "nuestra visión",
    "nuestra vision",
    "nuestros valores",
    "our values",
    "quiénes somos",
    "quienes somos",
    "about us",
    "sobre nosotros",
    "acerca de nosotros",
    "contact us",
    "contáctanos",
    "contactanos",
)


def _is_corporate_description(title: str, summary: str) -> bool:
    """True si el texto parece descripción corporativa / home de empresa,
    NO una idea de negocio."""
    blob = f"{title} {summary}".lower()
    # Necesita 2+ patterns para reducir falsos positivos
    hits = sum(1 for pat in _CORPORATE_DESCRIPTION_PATTERNS if pat in blob)
    return hits >= 2


def fetch_url(url: str) -> Optional[FetchedItem]:
    """Fetch one URL and extract plaintext + structured metadata.

    M3.17: prefers OpenGraph / Twitter card meta tags for title and summary
    (publishers curate these for sharing — more informative than parsing the
    body). Falls back to <title> + body text if meta tags are missing.

    M3.18: returns None when the page is a SPA fallback ("JavaScript is not
    available…") because that text is not the actual content of the URL.
    Caller should treat it like a fetch failure.
    """
    raw = _http_get(url)
    if raw is None:
        return None
    try:
        html = raw.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None

    # Title: prefer og:title → twitter:title → <title>
    og_title = _meta_content(html, "og:title", "twitter:title")
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title_tag = _html_to_text(title_match.group(1)) if title_match else None
    title = og_title or title_tag or url

    # Summary: prefer og:description → twitter:description → meta description → body
    og_desc = _meta_content(
        html, "og:description", "twitter:description", "description"
    )
    text = _html_to_text(html)
    body = _truncate(text, MAX_CHARS_PER_SOURCE)
    summary = og_desc or _truncate(text, 400)
    if not summary:
        return None

    # M3.18: si lo que extrajimos es el fallback de no-JS, NO es contenido válido
    if _is_spa_fallback(title, summary):
        logger.info("fetch_url: skipping SPA fallback content for %s", url)
        return None

    # M4.2: si es descripción corporativa, no es una idea — descartar
    if _is_corporate_description(title, summary):
        logger.info("fetch_url: skipping corporate description content for %s", url)
        return None

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
        published_at = _parse_rfc822_or_iso(item.findtext("pubDate") or "")
        if not title and not desc:
            continue
        items.append(
            FetchedItem(
                source_kind="rss",
                url=link or feed_url,
                title=_truncate(title, 200),
                summary=_truncate(desc, 400),
                body=_truncate(desc, MAX_CHARS_PER_SOURCE),
                published_at=published_at,
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
        published_at = _parse_rfc822_or_iso(
            entry.findtext("a:published", default="", namespaces=ns)
            or entry.findtext("a:updated", default="", namespaces=ns)
            or ""
        )
        if not title and not summary:
            continue
        items.append(
            FetchedItem(
                source_kind="rss",
                url=link or feed_url,
                title=_truncate(title, 200),
                summary=_truncate(summary, 400),
                body=_truncate(summary, MAX_CHARS_PER_SOURCE),
                published_at=published_at,
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
        published_at = d.get("time")  # HN time is unix ts already
        summary = f"[{score} points] {title}"
        body = _truncate(f"{title}\n\n{text}\n\nDiscussion: https://news.ycombinator.com/item?id={hid}", MAX_CHARS_PER_SOURCE)
        items.append(
            FetchedItem(
                source_kind="hn",
                url=url,
                title=_truncate(title, 200),
                summary=_truncate(summary, 400),
                body=body,
                published_at=int(published_at) if published_at else None,
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
        created_utc = d.get("created_utc")  # float unix ts
        if not title:
            continue
        items.append(
            FetchedItem(
                source_kind="reddit",
                url=external_url,
                title=_truncate(title, 200),
                summary=_truncate(f"r/{subreddit} [{score} upvotes] — {title}", 400),
                body=_truncate(f"{title}\n\n{selftext}\n\nDiscussion: {permalink}", MAX_CHARS_PER_SOURCE),
                published_at=int(created_utc) if created_utc else None,
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
# YouTube — uses the FREE per-channel/playlist RSS feed (no API key required)
# ---------------------------------------------------------------------------

_YT_CHANNEL_ID_RE = re.compile(r'"channelId":"(UC[\w-]+)"')


def _resolve_youtube_to_rss(target: str) -> Optional[str]:
    """
    Turn a YouTube URL or handle into an RSS feed URL.
    Accepts: @handle, /channel/UCxxx, /c/Name, raw UCxxxxx, or a full URL.
    """
    target = (target or "").strip()
    if not target:
        return None
    if target.startswith("UC") and len(target) >= 20 and "/" not in target:
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={target}"
    m = re.search(r"/channel/(UC[\w-]+)", target)
    if m:
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={m.group(1)}"
    if target.startswith("@"):
        url = f"https://www.youtube.com/{target}"
    elif "/c/" in target or "/@" in target or target.startswith("http"):
        url = target
    else:
        url = f"https://www.youtube.com/@{target}"
    raw = _http_get(url)
    if raw is None:
        return None
    try:
        html = raw.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None
    m = _YT_CHANNEL_ID_RE.search(html)
    if not m:
        return None
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={m.group(1)}"


def fetch_youtube_channel(target: str, max_items: int = MAX_ITEMS_PER_FEED) -> List[FetchedItem]:
    """Latest videos of a YouTube channel via its RSS feed (no API key)."""
    feed_url = _resolve_youtube_to_rss(target)
    if not feed_url:
        logger.warning("fetch_youtube_channel: could not resolve %r", target)
        return []
    items = fetch_rss(feed_url, max_items)
    for it in items:
        it.source_kind = "youtube"
    return items


# ---------------------------------------------------------------------------
# Bluesky — public AT Protocol XRPC endpoint (no auth)
# ---------------------------------------------------------------------------

_BSKY_SEARCH_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"


def fetch_bluesky(query: str, max_items: int = MAX_ITEMS_PER_FEED) -> List[FetchedItem]:
    """Search Bluesky public posts for a query string."""
    if not query.strip():
        return []
    qs = urllib.parse.urlencode({"q": query, "limit": min(max_items, 25)})
    raw = _http_get(f"{_BSKY_SEARCH_URL}?{qs}")
    if raw is None:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    posts = data.get("posts", [])[:max_items]
    items: List[FetchedItem] = []
    for p in posts:
        record = p.get("record", {})
        text = (record.get("text") or "").strip()
        if not text:
            continue
        author = p.get("author", {})
        handle = author.get("handle", "")
        uri = p.get("uri", "")
        post_id = uri.rsplit("/", 1)[-1] if uri else ""
        web_url = f"https://bsky.app/profile/{handle}/post/{post_id}" if handle and post_id else uri
        like_count = p.get("likeCount", 0)
        items.append(
            FetchedItem(
                source_kind="bluesky",
                url=web_url,
                title=_truncate(f"@{handle}: {text.splitlines()[0]}", 200),
                summary=_truncate(f"@{handle} [{like_count} likes] — {text}", 400),
                body=_truncate(f"@{handle}\n{text}\n\n{web_url}", MAX_CHARS_PER_SOURCE),
            )
        )
    return items


# ---------------------------------------------------------------------------
# Telegram — public channels via t.me/s/<channel> (no auth, HTML scrape)
# ---------------------------------------------------------------------------


def fetch_telegram(channel: str, max_items: int = MAX_ITEMS_PER_FEED) -> List[FetchedItem]:
    """Read recent messages from a PUBLIC Telegram channel (web preview).
    `channel` is the handle without @ or t.me/. Private channels return []."""
    handle = channel.strip().lstrip("@").replace("t.me/", "").replace("s/", "").rstrip("/")
    if not handle:
        return []
    raw = _http_get(f"https://t.me/s/{handle}")
    if raw is None:
        return []
    try:
        html = raw.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return []
    msg_blocks = re.findall(
        r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
        html, re.DOTALL,
    )
    link_re = re.compile(r'<a class="tgme_widget_message_date"[^>]*href="(https://t\.me/[^"]+)"')
    links = link_re.findall(html)
    items: List[FetchedItem] = []
    for i, msg_html in enumerate(msg_blocks[-max_items:][::-1]):
        text = _html_to_text(msg_html)
        if not text:
            continue
        link = links[-(i + 1)] if i < len(links) else f"https://t.me/{handle}"
        items.append(
            FetchedItem(
                source_kind="telegram",
                url=link,
                title=_truncate(f"@{handle}: {text.splitlines()[0][:160]}", 200),
                summary=_truncate(text, 400),
                body=_truncate(f"@{handle}\n{text}\n\n{link}", MAX_CHARS_PER_SOURCE),
            )
        )
    return items[:max_items]


# ---------------------------------------------------------------------------
# SEC EDGAR — M4.12 sleeper companies radar (Phase 1: fetcher)
# ---------------------------------------------------------------------------


def fetch_sec_edgar(target: str, max_items: int = MAX_ITEMS_PER_FEED) -> List[FetchedItem]:
    """M4.12 — Lee las últimas filings de una empresa pública US desde SEC EDGAR.

    Founder del audio: "identificar cuáles son los líderes del mercado y cuál
    es el segundo de a bordo que en base a información pública financiera ya
    se vea que está atrás y que tiene potencial de poder crecer".

    Phase 1: source kind fetcher. Cada filing nueva se convierte en una
    signal. La detección "líder vs second-best" como agente queda para
    M5.x (requiere SIC code grouping + financial parsing — fuera de scope
    de M4).

    target: el CIK (Central Index Key) de la empresa. Acepta variantes:
      - "320193" (Apple)
      - "0000320193"
      - "CIK0000320193"
      - "AAPL" → no soportado en Phase 1 (haría falta ticker→CIK lookup)

    Cumple con SEC EDGAR fair access policy:
      - User-Agent identificable
      - Endpoint /submissions/ rate limit 10 req/s (single req aquí, OK)
    """
    raw_target = target.strip().upper().replace("CIK", "").lstrip("0")
    if not raw_target.isdigit():
        logger.warning("fetch_sec_edgar: target %r no es un CIK numérico", target)
        return []
    cik = raw_target.zfill(10)  # SEC requiere 10 dígitos con ceros izq

    # User-Agent obligatorio per SEC EDGAR fair-access policy
    sec_headers = {
        "User-Agent": "circles-ai-fof factory-of-factories (circles.fof.ai@gmail.com)",
        "Accept": "application/json",
    }
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        # Reusar el HTTP helper pero con headers extra. _http_get no acepta
        # headers extra, así que hacemos urllib aquí directamente para no
        # romper el contrato del resto del módulo.
        import urllib.request
        req = urllib.request.Request(url, headers=sec_headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_sec_edgar: HTTP error for CIK %s: %s", cik, exc)
        return []

    try:
        import json as _json
        body = _json.loads(data.decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_sec_edgar: JSON parse error for CIK %s: %s", cik, exc)
        return []

    company_name = body.get("name") or f"CIK {cik}"
    recent = body.get("filings", {}).get("recent", {})
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    accessions = recent.get("accessionNumber") or []
    primary_docs = recent.get("primaryDocument") or []

    items: List[FetchedItem] = []
    for i in range(min(len(forms), max_items)):
        form = forms[i]
        date = dates[i] if i < len(dates) else "?"
        accession = accessions[i] if i < len(accessions) else ""
        acc_nodash = accession.replace("-", "")
        primary = primary_docs[i] if i < len(primary_docs) else ""
        if acc_nodash and primary:
            filing_url = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{acc_nodash}/{primary}"
            )
        else:
            filing_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
        title = f"{company_name} — {form} filed {date}"
        summary = (
            f"Filing pública de {company_name} ({form}) registrada el {date}. "
            f"Accession {accession}."
        )
        items.append(
            FetchedItem(
                source_kind="sec_edgar",
                url=filing_url,
                title=_truncate(title, 200),
                summary=_truncate(summary, 400),
                body=_truncate(
                    f"{company_name}\n\nForm: {form}\nFiled: {date}\n"
                    f"Accession: {accession}\nURL: {filing_url}",
                    MAX_CHARS_PER_SOURCE,
                ),
            )
        )
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
    if kind == "youtube":
        return fetch_youtube_channel(target, max_items)
    if kind == "bluesky":
        return fetch_bluesky(target, max_items)
    if kind == "telegram":
        return fetch_telegram(target, max_items)
    if kind == "sec_edgar":
        # M4.12 — SEC EDGAR Phase 1: company filings fetcher
        return fetch_sec_edgar(target, max_items)
    if kind == "events":
        # M4.13 — Eventos/Ferias radar (inspirado en audio del founder:
        # "en qué ferias, en qué congresos hay que estar"). Por ahora delegamos
        # en fetch_rss porque la mayoría de sitios de eventos (Eventbrite,
        # Lu.ma, conferencias verticales) exponen RSS estándar. La distinción
        # es semántica: el founder añade un feed RSS de eventos y nuestro
        # clasificador de content_type detecta "course_tutorial"/"video_podcast"
        # según el contenido. En M4.14+ podemos especializar con Eventbrite API.
        return fetch_rss(target, max_items)
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
    "fetch_youtube_channel",
    "fetch_bluesky",
    "fetch_telegram",
    "fetch_by_kind",
]
