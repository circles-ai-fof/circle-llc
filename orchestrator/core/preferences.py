"""
M4.1 / ADR-019 — Cazador Fase 3: aprendizaje de preferencias.

Este módulo:
  1. Genera embeddings de cada señal (texto → vector 384-dim)
  2. Agrupa señales similares con clustering
  3. Score de relevancia: similar a señales que el founder marcó 👍 sube,
     similar a señales que marcó 👎 baja
  4. Sugiere nuevas fuentes basado en keywords de clusters aprobados

Dos modos de operación:

  REAL (cuando sentence-transformers + hdbscan + sklearn están instalados):
    - Embeddings semánticos con modelo multilingual ES-friendly
    - HDBSCAN para clustering jerárquico (detecta # de clusters solo)
    - TF-IDF + cosine similarity para sugerencias

  FALLBACK (sin deps instaladas — siempre disponible):
    - Embeddings determinísticos hash-based (no semánticos pero deterministas)
    - Clustering por prefix de hash
    - Sugerencias por keywords con frecuencia simple

El módulo SIEMPRE funciona; el modo se reporta en
`get_engine_info()["mode"]`. Tests cubren ambos modos.
"""
from __future__ import annotations

import hashlib
import logging
import re
import struct
from collections import Counter
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384  # Same as MiniLM family — keeps schema stable across modes

# ---------------------------------------------------------------------------
# Engine detection
# ---------------------------------------------------------------------------

_st_model = None  # sentence_transformers model singleton (lazy)
_engine_cache: Optional[dict] = None


def get_engine_info() -> dict:
    """Returns which engine is active. Cached after first call."""
    global _engine_cache
    if _engine_cache is not None:
        return _engine_cache
    info = {
        "mode": "fallback",
        "embedding_lib": None,
        "clustering_lib": None,
        "embedding_model": None,
        "notes": "Fallback determinista (sin deps externas). Embeddings hash-based.",
    }
    try:
        import sentence_transformers  # noqa: F401

        info["embedding_lib"] = "sentence-transformers"
        info["embedding_model"] = "paraphrase-multilingual-MiniLM-L12-v2"
        info["mode"] = "real"
        info["notes"] = "Embeddings semánticos multilingüe (ES-friendly)."
    except Exception:  # noqa: BLE001
        pass
    try:
        import hdbscan  # noqa: F401

        info["clustering_lib"] = "hdbscan"
    except Exception:  # noqa: BLE001
        info["clustering_lib"] = "hash-buckets-fallback"
    _engine_cache = info
    return info


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


def _normalize_text(text: str) -> str:
    """Lower + collapse whitespace; OK for hash-based or semantic embeddings."""
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def _fallback_embedding(text: str) -> List[float]:
    """Determinístico, sin deps. Hash → seed → vector 384-dim normalizado.

    NO es semántico: textos similares pero distintos darán vectores muy distintos.
    PERO es estable: el mismo texto siempre da el mismo vector. Útil para tests
    y para que la pipeline funcione sin descargar 500MB.

    Para señales con palabras compartidas, mezclamos los hashes de cada palabra
    para que señales con vocabulario común tengan vectores con alguna similitud.
    """
    norm = _normalize_text(text)
    if not norm:
        return [0.0] * EMBEDDING_DIM

    # Mix per-word hashes — palabras compartidas → cierta similitud
    words = [w for w in re.split(r"\W+", norm) if len(w) > 2][:50]
    if not words:
        words = [norm[:50]]

    acc = [0.0] * EMBEDDING_DIM
    for word in words:
        h = hashlib.sha256(word.encode("utf-8")).digest()
        # Repeat hash + counter to fill EMBEDDING_DIM floats.
        # Use uint32 → map to [-1, 1] to avoid NaN/inf from interpreting
        # random bits as IEEE-754 floats directly.
        chunks: List[float] = []
        i = 0
        while len(chunks) < EMBEDDING_DIM:
            hh = hashlib.sha256(h + str(i).encode()).digest()
            # 32 bytes = 8 uint32. Each → (x / 2**31) - 1 ∈ [-1, 1)
            uints = struct.unpack(">8I", hh[:32])
            chunks.extend((u / 2147483648.0) - 1.0 for u in uints)
            i += 1
        for j in range(EMBEDDING_DIM):
            acc[j] += chunks[j] / max(1, len(words))

    # L2 normalize so cosine similarity == dot product
    norm_factor = sum(x * x for x in acc) ** 0.5
    if norm_factor < 1e-9:
        return acc
    return [x / norm_factor for x in acc]


def _real_embedding(text: str) -> List[float]:
    """Real semantic embedding via sentence-transformers."""
    global _st_model
    from sentence_transformers import SentenceTransformer  # type: ignore

    if _st_model is None:
        _st_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    vec = _st_model.encode(text, normalize_embeddings=True)
    return [float(x) for x in vec]


def compute_embedding(text: str) -> List[float]:
    """Public API: returns 384-dim L2-normalized embedding for a text."""
    info = get_engine_info()
    if info["mode"] == "real":
        try:
            return _real_embedding(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("preferences: real embedding failed (%s) — falling back", exc)
    return _fallback_embedding(text)


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------


def cosine_sim(a: List[float], b: List[float]) -> float:
    """Cosine similarity entre 2 vectores L2-normalized → equivalente a dot product."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


# ---------------------------------------------------------------------------
# Scoring de relevancia (aprende del feedback)
# ---------------------------------------------------------------------------


def score_against_feedback(
    candidate_embedding: List[float],
    positive_embeddings: Iterable[List[float]],
    negative_embeddings: Iterable[List[float]],
) -> float:
    """Score ∈ [0, 1] de qué tan relevante es candidate dado el historial.

    Heurística simple, sin entrenamiento:
      base = mean cos_sim con positivos
      penalty = mean cos_sim con negativos
      score = sigmoide(base - penalty)
    """
    pos = list(positive_embeddings)
    neg = list(negative_embeddings)
    if not pos and not neg:
        return 0.5  # neutral cuando no hay historial
    pos_score = (
        sum(cosine_sim(candidate_embedding, p) for p in pos) / len(pos)
        if pos
        else 0.0
    )
    neg_score = (
        sum(cosine_sim(candidate_embedding, n) for n in neg) / len(neg)
        if neg
        else 0.0
    )
    raw = pos_score - neg_score
    # Squash a [0, 1] con sigmoide
    import math

    return 1.0 / (1.0 + math.exp(-4 * raw))


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------


def _fallback_clustering(embeddings: List[List[float]]) -> List[int]:
    """Sin HDBSCAN: cluster por hash del top-3 dims → buckets.

    No es bueno semánticamente pero permite tests deterministas y pipeline
    completa sin deps.
    """
    out: List[int] = []
    for vec in embeddings:
        if not vec:
            out.append(-1)
            continue
        # Top 3 dims con mayor magnitud → forman el "bucket"
        idx_top = sorted(range(len(vec)), key=lambda i: abs(vec[i]), reverse=True)[:3]
        signature = "".join(f"{i}{'+' if vec[i] > 0 else '-'}" for i in sorted(idx_top))
        bucket = int(hashlib.sha256(signature.encode()).hexdigest()[:6], 16) % 1000
        out.append(bucket)
    return out


def _real_clustering(embeddings: List[List[float]]) -> List[int]:
    """HDBSCAN real cuando está instalado."""
    import hdbscan  # type: ignore
    import numpy as np  # comes with hdbscan

    if len(embeddings) < 5:
        # Too few to cluster meaningfully
        return [-1] * len(embeddings)
    arr = np.array(embeddings, dtype="float32")
    clusterer = hdbscan.HDBSCAN(min_cluster_size=3, metric="euclidean")
    labels = clusterer.fit_predict(arr)
    return [int(l) for l in labels]


def cluster_embeddings(embeddings: List[List[float]]) -> List[int]:
    """Returns a cluster label per embedding. -1 == noise / unclassified."""
    info = get_engine_info()
    if info["clustering_lib"] == "hdbscan":
        try:
            return _real_clustering(embeddings)
        except Exception as exc:  # noqa: BLE001
            logger.warning("preferences: HDBSCAN failed (%s) — fallback", exc)
    return _fallback_clustering(embeddings)


# ---------------------------------------------------------------------------
# Suggestions: top keywords by cluster
# ---------------------------------------------------------------------------

_STOPWORDS = {
    # Spanish stopwords mínimas (no necesitamos NLTK para esto)
    "el", "la", "los", "las", "un", "una", "y", "o", "de", "del", "que",
    "en", "a", "por", "para", "con", "sin", "es", "se", "su", "sus",
    "más", "menos", "como", "esto", "esta", "este", "estos", "estas",
    "lo", "le", "les", "al", "no", "si", "sí", "ya", "muy", "pero", "mi",
    # English bleed-through
    "the", "a", "an", "of", "for", "to", "in", "on", "at", "is", "are",
    "and", "or", "with", "by", "from", "this", "that", "these", "those",
    "be", "been", "being", "have", "has", "had", "as", "it",
}


def extract_keywords(texts: List[str], top_n: int = 5) -> List[str]:
    """TF-style keyword extraction. Para clusters con LLM real usaríamos
    TF-IDF; para el fallback es solo frequency-based filtrando stopwords."""
    counter: Counter = Counter()
    for t in texts:
        words = re.findall(r"[a-záéíóúñü]{4,}", _normalize_text(t))
        counter.update(w for w in words if w not in _STOPWORDS)
    return [w for w, _ in counter.most_common(top_n)]


def suggest_sources_from_clusters(
    cluster_texts: dict[int, List[str]],
    max_suggestions: int = 5,
) -> List[dict]:
    """Genera sugerencias de búsqueda/feed a partir de clusters aprobados.

    Input: {cluster_id: [texto1, texto2, ...]}
    Output: lista de {keywords, suggested_query, rationale}
    """
    suggestions: List[dict] = []
    for cluster_id, texts in cluster_texts.items():
        if cluster_id < 0 or len(texts) < 2:
            continue
        keywords = extract_keywords(texts, top_n=5)
        if not keywords:
            continue
        suggestions.append({
            "cluster_id": cluster_id,
            "keywords": keywords,
            "suggested_query": " ".join(keywords[:3]),
            "rationale": (
                f"Cluster #{cluster_id} con {len(texts)} señales aprobadas que "
                f"comparten: {', '.join(keywords[:3])}. Considera añadir una "
                f"búsqueda en Bluesky / Reddit / GitHub trending con estos términos."
            ),
        })
    suggestions.sort(key=lambda s: -len(cluster_texts[s["cluster_id"]]))
    return suggestions[:max_suggestions]
