"""
M4.3 — Clasificación automática del tipo de contenido de una señal.

Founder feedback: "Esto es una noticia. ¿Puedes identificar cuando son
noticias, o son otro tipo de contenido, con un icono y descripción?"

Heurístico sin LLM ($0). Combina:
  1. Dominio conocido (bbc.com → news, github.com → tool_product, etc.)
  2. Path patterns (/news/, /article/, /paper/, /tutorial/, /docs/)
  3. Keywords en theme/excerpt

Categorías:
  news               📰 Noticia (BBC, CNN, Reuters, NYT, ...)
  blog               📝 Blog / opinión (Medium, Substack, blogs personales)
  research_paper     🔬 Paper / estudio (arxiv, papers, research reports)
  tool_product       🛠️ Tool / producto (GitHub repos, Product Hunt)
  course_tutorial    🎓 Curso / tutorial (Coursera, Udemy, paths)
  video_podcast      🎙️ Video / podcast (YouTube watch, Spotify, etc.)
  corporate          🏢 Home corporativa (descartada por filtro M4.2)
  community          💬 Foro / discusión (Reddit, HN, forums)
  unknown            ❓ Sin clasificar
"""
from __future__ import annotations

from typing import Tuple
from urllib.parse import urlparse


# Dominios → tipo de contenido (heurísticas curated)
_NEWS_DOMAINS = {
    "bbc.com", "bbc.co.uk", "cnn.com", "reuters.com", "ap.org",
    "nytimes.com", "wsj.com", "ft.com", "economist.com",
    "elcomercio.com", "eluniverso.com", "primicias.ec", "eltiempo.com",
    "lanacion.com.ar", "infobae.com", "milenio.com", "expansion.mx",
    "elpais.com", "elmundo.es", "abc.es", "20minutos.es",
    "bloomberg.com", "techcrunch.com", "theverge.com", "wired.com",
    "engadget.com", "venturebeat.com", "axios.com",
    "businessinsider.com", "forbes.com", "fortune.com",
    "guardian.com", "theguardian.com", "independent.co.uk",
    "npr.org", "pbs.org", "cbsnews.com", "nbcnews.com", "abcnews.go.com",
    "elcomercio.pe", "larepublica.pe",
}

_RESEARCH_DOMAINS = {
    "arxiv.org", "papers.ssrn.com", "ssrn.com",
    "scholar.google.com", "semanticscholar.org",
    "researchgate.net", "academia.edu",
    "nature.com", "science.org", "cell.com",
    "papers.nips.cc", "openreview.net",
    "huggingface.co/papers",
    "mckinsey.com", "bcg.com", "bain.com",  # consulting research
    "pewresearch.org", "statista.com",
}

_TOOL_PRODUCT_DOMAINS = {
    "github.com", "gitlab.com", "bitbucket.org",
    "producthunt.com", "betalist.com", "indiehackers.com",
    "huggingface.co",  # model hub
    "npmjs.com", "pypi.org", "crates.io", "rubygems.org",
    "vercel.com", "netlify.com", "supabase.com",
    "stripe.com", "twilio.com",
}

_COURSE_DOMAINS = {
    "coursera.org", "udemy.com", "edx.org",
    "linkedin.com/learning", "pluralsight.com",
    "skillshare.com", "domestika.org",
    "platzi.com", "crehana.com",
    "khanacademy.org", "freecodecamp.org",
    "deeplearning.ai", "fast.ai",
    "anthropic.com/courses", "openai.com/courses",
}

_VIDEO_PODCAST_DOMAINS = {
    "youtube.com", "youtu.be", "vimeo.com",
    "spotify.com", "podcasts.apple.com", "anchor.fm",
    "soundcloud.com", "twitch.tv",
}

_BLOG_DOMAINS = {
    "medium.com", "substack.com", "ghost.io",
    "dev.to", "hashnode.com",
    "blog.google", "blog.openai.com", "anthropic.com/news",
    "stratechery.com", "ben-evans.com",
    "paulgraham.com", "lesswrong.com",
}

_COMMUNITY_DOMAINS = {
    "reddit.com", "news.ycombinator.com",
    "stackoverflow.com", "stackexchange.com",
    "discourse.org", "lobste.rs",
}


# Path patterns
_NEWS_PATHS = ("/news/", "/article/", "/articles/", "/story/", "/stories/")
_BLOG_PATHS = ("/blog/", "/post/", "/posts/", "/p/")
_RESEARCH_PATHS = ("/paper", "/papers", "/research", "/pdf", "/abs/")  # arxiv: /abs/2401.xxx
_TUTORIAL_PATHS = ("/tutorial", "/tutorials", "/learn/", "/course/", "/lesson")
_TOOL_PATHS = ("/docs/", "/api/", "/sdk/", "/cli/")


# Keywords en theme/excerpt (lowercase)
_NEWS_KEYWORDS = (
    "extends ", "extend ", "anuncia ", "anuncian ", "lanza ",
    "launches ", "announces ", "reports ", "report says",
    "according to", "según ", "segun ",
    "this week", "esta semana",
    "breaking:", "última hora", "ultima hora",
)
_BLOG_KEYWORDS = (
    "i built", "i created", "how we ", "lessons learned",
    "my journey", "mi experiencia",
    "thoughts on", "opinión sobre", "opinion sobre",
)
_TOOL_KEYWORDS = (
    "open-source", "open source",
    "github.com/", "release notes",
    "version ", "v1.", "v2.", "v3.",
    "install", "instalar",
)
_RESEARCH_KEYWORDS = (
    "abstract:", "we propose", "we show",
    "experimental results", "ablation study",
    "study finds", "research finds",
    "statistical significance",
    "p < 0.05", "p<0.05",
)
_COURSE_KEYWORDS = (
    "course", "curso", "tutorial", "guide",
    "learn ", "aprende ", "aprender ",
    "step by step", "paso a paso",
    "syllabus", "syllabi",
)


def _hostname(url: str) -> str:
    try:
        h = (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""
    return h.removeprefix("www.").removeprefix("m.")


def _path(url: str) -> str:
    try:
        return (urlparse(url).path or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def classify_content_type(
    url: str = "",
    theme: str = "",
    excerpt: str = "",
) -> Tuple[str, str, str]:
    """Classify content type using heuristics.

    Returns (category, icon, label_es):
      news            📰  Noticia
      blog            📝  Blog
      research_paper  🔬  Estudio
      tool_product    🛠️  Producto
      course_tutorial 🎓  Curso
      video_podcast   🎙️  Video/Podcast
      community       💬  Foro
      corporate       🏢  Corporativo
      unknown         ❓  Otro
    """
    host = _hostname(url)
    path = _path(url)
    blob = f"{theme} {excerpt}".lower()

    # ----- 1) Domain-based detection (más confiable) -----
    if host in _NEWS_DOMAINS or any(h in host for h in _NEWS_DOMAINS):
        return ("news", "📰", "Noticia")
    if host in _RESEARCH_DOMAINS or any(h in host for h in _RESEARCH_DOMAINS):
        return ("research_paper", "🔬", "Estudio")
    if host in _TOOL_PRODUCT_DOMAINS:
        return ("tool_product", "🛠️", "Producto")
    if host in _COURSE_DOMAINS or any(c in host for c in _COURSE_DOMAINS):
        return ("course_tutorial", "🎓", "Curso")
    if host in _VIDEO_PODCAST_DOMAINS:
        # YouTube /shorts ya está filtrado por classify_url; aquí asumimos /watch
        return ("video_podcast", "🎙️", "Video")
    if host in _BLOG_DOMAINS or any(b in host for b in _BLOG_DOMAINS):
        return ("blog", "📝", "Blog")
    if host in _COMMUNITY_DOMAINS:
        return ("community", "💬", "Foro")

    # ----- 2) Path-based detection -----
    if any(p in path for p in _RESEARCH_PATHS):
        return ("research_paper", "🔬", "Estudio")
    if any(p in path for p in _TUTORIAL_PATHS):
        return ("course_tutorial", "🎓", "Curso")
    if any(p in path for p in _NEWS_PATHS):
        return ("news", "📰", "Noticia")
    if any(p in path for p in _BLOG_PATHS):
        return ("blog", "📝", "Blog")
    if any(p in path for p in _TOOL_PATHS):
        return ("tool_product", "🛠️", "Producto")

    # ----- 3) Keyword-based detection -----
    if sum(1 for k in _NEWS_KEYWORDS if k in blob) >= 1:
        return ("news", "📰", "Noticia")
    if sum(1 for k in _RESEARCH_KEYWORDS if k in blob) >= 1:
        return ("research_paper", "🔬", "Estudio")
    if sum(1 for k in _TOOL_KEYWORDS if k in blob) >= 2:
        return ("tool_product", "🛠️", "Producto")
    if sum(1 for k in _COURSE_KEYWORDS if k in blob) >= 1:
        return ("course_tutorial", "🎓", "Curso")
    if sum(1 for k in _BLOG_KEYWORDS if k in blob) >= 1:
        return ("blog", "📝", "Blog")

    return ("unknown", "❓", "Otro")


# Para usar en api.py sin tener que importar la tupla siempre
def classify_content_dict(url: str = "", theme: str = "", excerpt: str = "") -> dict:
    cat, icon, label = classify_content_type(url, theme, excerpt)
    return {"category": cat, "icon": icon, "label": label}
