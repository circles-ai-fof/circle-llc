"""
Platform detection and credential introspection.

M4.0 / ADR-018 — when the founder pastes a URL into /cazar/fuentes the
backend should:
  1. Detect which platform the URL belongs to (youtube? bluesky? x.com?)
  2. Decide which `kind` of source would monitor it (rss / youtube / hn /
     bluesky / telegram / url / ...)
  3. Report whether that platform needs credentials and, if so, whether
     the required env vars are present
  4. Optionally surface a "deferred" status for platforms we explicitly
     decided NOT to integrate (X, LinkedIn, Instagram, Facebook, TikTok —
     see ADR-011)

NO credentials are stored here. Required env var NAMES are listed so the
dashboard can tell the founder "add YOUTUBE_API_KEY to .env".
"""
from __future__ import annotations

import os
from typing import Optional
from urllib.parse import urlparse


# Catalog of supported platforms.
#
# `recommended_kind` — qué tipo de source crear si el founder añade esa URL
# `requires_credentials` — True si requiere API keys
# `env_keys` — tuple de env vars que el operador debe configurar
# `oauth_required` — True si necesita un flujo OAuth (no solo una API key)
# `notes` — para mostrar en el UI
# `status` — 'ready' (sin creds requeridas), 'optional_credentials' (mejora con
#            creds pero funciona sin), 'requires_credentials' (no funciona sin),
#            'deferred' (ADR-011 lo descartó)
PLATFORM_CATALOG = {
    # ---------- READY: vías legales, sin creds ----------
    "rss": {
        "recommended_kind": "rss",
        "requires_credentials": False,
        "env_keys": (),
        "oauth_required": False,
        "status": "ready",
        "notes": "RSS/Atom feed público. No requiere configuración.",
    },
    "url": {
        "recommended_kind": "url",
        "requires_credentials": False,
        "env_keys": (),
        "oauth_required": False,
        "status": "ready",
        "notes": "URL única para monitoreo manual. Sin auth.",
    },
    "hn": {
        "recommended_kind": "hn",
        "requires_credentials": False,
        "env_keys": (),
        "oauth_required": False,
        "status": "ready",
        "notes": "Hacker News usa la Firebase API pública. Sin auth.",
    },
    "reddit": {
        "recommended_kind": "reddit",
        "requires_credentials": False,
        "env_keys": (),
        "oauth_required": False,
        "status": "ready",
        "notes": "Reddit JSON endpoints públicos (sin OAuth). Rate limit moderado.",
    },
    "github_trending": {
        "recommended_kind": "github_trending",
        "requires_credentials": False,
        "env_keys": (),
        "oauth_required": False,
        "status": "ready",
        "notes": "GitHub Trending scraped (público, sin auth).",
    },
    "product_hunt": {
        "recommended_kind": "product_hunt",
        "requires_credentials": False,
        "env_keys": (),
        "oauth_required": False,
        "status": "ready",
        "notes": "RSS feed público de Product Hunt.",
    },
    "bluesky": {
        "recommended_kind": "bluesky",
        "requires_credentials": False,
        "env_keys": (),
        "oauth_required": False,
        "status": "ready",
        "notes": "Bluesky XRPC API pública. Sin auth para búsquedas.",
    },
    "telegram": {
        "recommended_kind": "telegram",
        "requires_credentials": False,
        "env_keys": (),
        "oauth_required": False,
        "status": "ready",
        "notes": "Canales públicos de Telegram vía t.me/s/<channel>.",
    },

    # ---------- OPTIONAL CREDENTIALS: funciona sin pero mejora con ----------
    "youtube": {
        "recommended_kind": "youtube",
        "requires_credentials": False,  # falla back a RSS por canal sin key
        "env_keys": ("YOUTUBE_API_KEY",),
        "oauth_required": False,
        "status": "optional_credentials",
        "notes": (
            "Sin YOUTUBE_API_KEY usamos el RSS por canal (limitado a últimos "
            "15 videos por canal). Con la key activamos YouTube Data API v3 "
            "(búsquedas, más videos, metadata rica). Free tier: 10k req/día."
        ),
    },

    # ---------- DEFERRED por ADR-011: ToS o costo ----------
    "x": {
        "recommended_kind": None,
        "requires_credentials": True,
        "env_keys": ("X_BEARER_TOKEN", "X_API_KEY", "X_API_SECRET"),
        "oauth_required": True,
        "status": "deferred",
        "notes": (
            "X/Twitter API básica cuesta $100/mes. ADR-011 lo difiere. "
            "Por ahora descartamos URLs de x.com/status/ como ruido al "
            "importar archivos."
        ),
    },
    "linkedin": {
        "recommended_kind": None,
        "requires_credentials": True,
        "env_keys": ("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "LINKEDIN_ACCESS_TOKEN"),
        "oauth_required": True,
        "status": "deferred",
        "notes": (
            "LinkedIn API solo se otorga a partners (no es open self-serve). "
            "ADR-011 lo difiere. TODO: implementar OAuth si conseguimos "
            "partner access."
        ),
    },
    "instagram": {
        "recommended_kind": None,
        "requires_credentials": True,
        "env_keys": ("INSTAGRAM_GRAPH_TOKEN",),
        "oauth_required": True,
        "status": "deferred",
        "notes": (
            "Instagram Graph API solo expone TUS posts (con OAuth a TU cuenta). "
            "Para hunting B2B no aporta. ADR-011 lo difiere."
        ),
    },
    "facebook": {
        "recommended_kind": None,
        "requires_credentials": True,
        "env_keys": ("FACEBOOK_GRAPH_TOKEN",),
        "oauth_required": True,
        "status": "deferred",
        "notes": "Idem Instagram — Graph API solo TUS pages. Deferido.",
    },
    "tiktok": {
        "recommended_kind": None,
        "requires_credentials": True,
        "env_keys": ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"),
        "oauth_required": True,
        "status": "deferred",
        "notes": "TikTok API requires partner agreement. Deferido.",
    },
}


def detect_platform(url: str) -> Optional[str]:
    """Detect which platform a URL belongs to.

    Returns the platform key (e.g. "youtube", "x", "bluesky") or None
    if no specific platform matches (caller should fall back to "url" or "rss").
    """
    if not url:
        return None
    try:
        host = (urlparse(url).hostname or "").lower()
        path = (urlparse(url).path or "").lower()
    except Exception:  # noqa: BLE001
        return None
    if not host:
        return None

    # Strip www. and m. prefixes for matching
    h = host.removeprefix("www.").removeprefix("m.")

    if h in ("youtube.com", "youtu.be"):
        return "youtube"
    if h in ("x.com", "twitter.com", "t.co"):
        return "x"
    if h in ("linkedin.com",) or h.endswith(".linkedin.com"):
        return "linkedin"
    if h in ("instagram.com",):
        return "instagram"
    if h in ("facebook.com", "fb.com"):
        return "facebook"
    if h in ("tiktok.com",) or h.endswith(".tiktok.com"):
        return "tiktok"
    if h in ("bsky.app", "bsky.social") or h.endswith(".bsky.social"):
        return "bluesky"
    if h in ("t.me",):
        return "telegram"
    if h in ("news.ycombinator.com",):
        return "hn"
    if h == "reddit.com" or h.endswith(".reddit.com"):
        return "reddit"
    if h == "producthunt.com" or h.endswith(".producthunt.com"):
        return "product_hunt"
    if h == "github.com" and "/trending" in path:
        return "github_trending"
    # If the URL ends in /feed, /rss, /atom — it's an RSS source
    if path.endswith(("/feed", "/feed/", "/rss", "/rss/", "/atom", "/atom.xml", "/feed.xml")):
        return "rss"
    return None  # caller will treat as "url"-kind source


def check_credentials(platform: str) -> dict:
    """Return the credential status for a platform.

    Output:
      {
        "platform": "youtube",
        "status": "ready" | "optional_credentials" | "requires_credentials" | "deferred",
        "needs_credentials": bool,
        "missing_keys": [str, ...],
        "configured_keys": [str, ...],
        "oauth_required": bool,
        "message": str (user-facing, in Spanish),
        "recommended_kind": str | None,  // qué kind crear para esta plataforma
        "notes": str,
      }
    """
    cat = PLATFORM_CATALOG.get(platform)
    if cat is None:
        return {
            "platform": platform,
            "status": "ready",
            "needs_credentials": False,
            "missing_keys": [],
            "configured_keys": [],
            "oauth_required": False,
            "message": f"Plataforma '{platform}' tratada como URL genérica (sin requisitos).",
            "recommended_kind": "url",
            "notes": "",
        }
    env_keys = cat["env_keys"]
    configured = [k for k in env_keys if (os.getenv(k) or "").strip()]
    missing = [k for k in env_keys if not (os.getenv(k) or "").strip()]
    status = cat["status"]

    # Para optional_credentials, downgrade a 'ready' si todas las keys están
    if status == "optional_credentials" and not missing:
        status = "configured"

    if status == "deferred":
        message = (
            f"⛔ Plataforma '{platform}' está diferida (ADR-011): {cat['notes']}"
        )
        needs = True
    elif status == "ready":
        message = f"✅ Plataforma '{platform}' lista. {cat['notes']}"
        needs = False
    elif status == "optional_credentials":
        message = (
            f"⚠️ Plataforma '{platform}' funciona pero mejora con credenciales. "
            f"Faltan: {', '.join(missing)}. {cat['notes']}"
        )
        needs = False  # funciona sin
    elif status == "configured":
        message = f"✅ Plataforma '{platform}' configurada y lista."
        needs = False
    elif status == "requires_credentials":
        message = (
            f"⚠️ Plataforma '{platform}' requiere credenciales. "
            f"Faltan: {', '.join(missing)}. {cat['notes']}"
        )
        needs = True
    else:
        message = cat["notes"]
        needs = status != "ready"

    return {
        "platform": platform,
        "status": status,
        "needs_credentials": needs,
        "missing_keys": missing,
        "configured_keys": configured,
        "oauth_required": bool(cat.get("oauth_required")),
        "message": message,
        "recommended_kind": cat.get("recommended_kind"),
        "notes": cat["notes"],
    }


def list_all_platforms_status() -> list[dict]:
    """For the /configuracion/cuentas page — status of every known platform."""
    return [check_credentials(p) for p in PLATFORM_CATALOG.keys()]
