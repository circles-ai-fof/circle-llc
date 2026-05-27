"""
Seed default LATAM-tech-friendly sources into the hunter catalog.

Curated for circles-ai.ai's use case: capturing pain points from where LATAM
founders, indie hackers, and tech leaders actually post. All sources are FREE
and require no API keys.

Run once after `DATABASE_PATH` is configured:
    python scripts/seed_default_sources.py

Idempotent: skips sources whose (kind, target) is already present.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env if present so DATABASE_PATH points at the right SQLite file
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if "#" in v:
            v = v.split("#", 1)[0]
        os.environ.setdefault(k.strip(), v.strip())

from orchestrator.core.storage import sources_store  # noqa: E402


# Curated seed list — kept small (10 sources) to stay within free-tier budgets
# and produce clear signal:noise on first scan.
SEED_SOURCES: list[tuple[str, str, str]] = [
    # kind, target, name
    ("hn", "", "Hacker News — Top stories"),
    ("github_trending", "", "GitHub Trending (global)"),
    ("product_hunt", "", "Product Hunt — Daily"),

    # Reddit communities with LATAM + startup overlap
    ("reddit", "startups", "r/startups"),
    ("reddit", "SaaS", "r/SaaS"),
    ("reddit", "Entrepreneur", "r/Entrepreneur"),

    # Bluesky search queries (free public XRPC)
    ("bluesky", "fintech LATAM", "Bluesky — fintech LATAM"),
    ("bluesky", "founders ecuador", "Bluesky — founders Ecuador"),

    # RSS feeds — LATAM tech media
    ("rss", "https://hipertextual.com/feed", "Hipertextual (RSS)"),
    ("rss", "https://startupeable.com/feed/", "Startupeable LATAM (RSS)"),
]


def main() -> int:
    existing = {(s["kind"], s["target"]) for s in sources_store.list()}
    added = 0
    skipped = 0
    for kind, target, name in SEED_SOURCES:
        key = (kind, target)
        if key in existing:
            print(f"  [skip] {kind:18s} {name}")
            skipped += 1
            continue
        sid = sources_store.add(kind=kind, target=target, name=name)
        print(f"  [+id={sid}] {kind:18s} {name}")
        added += 1
    print(f"\nDone. Added: {added}, skipped: {skipped}, total catalog: {len(sources_store.list())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
