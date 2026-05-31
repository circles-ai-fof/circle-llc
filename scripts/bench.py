#!/usr/bin/env python
"""
M7.10 — Performance benchmark del backend.

Seedea N señales en un DB temporal y mide latencia de los hot-path queries:
- signals_store.list() con filtros varios
- signals_store.cross_country_gaps()
- signals_store.niche_opportunities()
- signals_store.stats_by_content_type()

Útil para validar que CREATE INDEX dieron el speed-up esperado.

Uso:
  python scripts/bench.py                 # N=1000 default
  python scripts/bench.py --signals 5000
  python scripts/bench.py --signals 10000 --runs 5

Output: tabla con N, P50, P95 por operación.
"""
from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path

# Asegurarse de que el repo root está en sys.path para poder importar
# orchestrator desde cualquier cwd
sys.path.insert(0, str(Path(__file__).parent.parent))


def seed_signals(n: int) -> None:
    """Inserta N signals diversos para que los queries hagan trabajo real."""
    from orchestrator.core.storage import signals_store

    KINDS = ["rss", "hn", "reddit", "github_trending", "events",
             "sec_edgar", "google_trends", "url", "youtube", "bluesky"]
    TOPICS = ["fintech pymes ecuador", "edtech profesores latam",
              "logistics last-mile", "marketplace freelancers", "agtech cosecha",
              "healthtech telemedicina", "saas rh", "proptech alquileres",
              "cleantech residuos", "fintech corporativo"]
    THEMES_PREFIX = ["Idea sobre", "Article about", "Discussion of",
                     "Trending: ", "Founder asks about", "New launch:"]
    URLS_HOSTS = ["https://example.com/", "https://news.example.org/",
                  "https://blog.example.io/", "https://bbc.com/news/",
                  "https://github.com/foo/", "https://example.net/post-"]

    print(f"  Seeding {n} signals…", end=" ", flush=True)
    t0 = time.monotonic()
    for i in range(n):
        kind = random.choice(KINDS)
        topic = random.choice(TOPICS)
        theme = f"{random.choice(THEMES_PREFIX)} {topic} #{i}"
        url = f"{random.choice(URLS_HOSTS)}signal-{i}"
        signals_store.add(
            source_id=None,
            source_kind=kind,
            theme=theme,
            score=random.uniform(0.3, 0.95),
            excerpt=f"Excerpt for signal {i} on {topic}",
            evidence_urls=[url],
            suggested_topic=topic,
            item_titles=[theme[:80]],
        )
    print(f"OK ({time.monotonic() - t0:.2f}s)")


def time_op(fn, runs: int) -> tuple[float, float, float]:
    """Ejecuta fn() N veces y devuelve (p50, p95, mean) en ms."""
    durations: list[float] = []
    for _ in range(runs):
        t0 = time.monotonic()
        fn()
        durations.append((time.monotonic() - t0) * 1000)
    durations.sort()
    p50 = statistics.median(durations)
    p95 = durations[int(len(durations) * 0.95)] if len(durations) > 1 else durations[0]
    mean = statistics.mean(durations)
    return p50, p95, mean


def main() -> int:
    parser = argparse.ArgumentParser(description="Backend perf benchmark")
    parser.add_argument("--signals", type=int, default=1000,
                        help="Cantidad de señales a seedear (default 1000)")
    parser.add_argument("--runs", type=int, default=5,
                        help="Repeticiones por operación (default 5)")
    args = parser.parse_args()

    # Crear DB temp y forzar init
    tmp_db = tempfile.mktemp(suffix=".db")
    os.environ["DATABASE_PATH"] = tmp_db
    print(f"=== Bench backend ===")
    print(f"DB:      {tmp_db}")
    print(f"Signals: {args.signals}")
    print(f"Runs:    {args.runs} por operación")
    print()

    # Importar después de setear env
    from orchestrator.core.storage import signals_store

    # Seed
    seed_signals(args.signals)
    print()

    # Operaciones a medir
    operations = [
        ("list() todas",
            lambda: signals_store.list(limit=10000, min_score=0.0)),
        ("list() min_score=0.5",
            lambda: signals_store.list(limit=10000, min_score=0.5)),
        ("list() search 'fintech'",
            lambda: signals_store.list(limit=100, min_score=0.0, search="fintech")),
        ("list() limit=20",
            lambda: signals_store.list(limit=20, min_score=0.0)),
        ("cross_country_gaps()",
            lambda: signals_store.cross_country_gaps()),
        ("niche_opportunities()",
            lambda: signals_store.niche_opportunities()),
        ("stats_by_content_type()",
            lambda: signals_store.stats_by_content_type()),
    ]

    # Bench
    print(f"{'Operación':<35} {'P50 (ms)':>10} {'P95 (ms)':>10} {'mean (ms)':>10}")
    print("-" * 70)
    for name, fn in operations:
        try:
            p50, p95, mean = time_op(fn, args.runs)
            print(f"{name:<35} {p50:>10.2f} {p95:>10.2f} {mean:>10.2f}")
        except Exception as exc:  # noqa: BLE001
            print(f"{name:<35} ERROR: {exc}")

    print()
    print(f"DB size: {os.path.getsize(tmp_db) / 1024:.1f} KB")
    try:
        os.unlink(tmp_db)
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
