#!/usr/bin/env python
"""
seed-example-sources.py — M7.1 — bootstrap del cazador con fuentes curadas.

Cuando clonás el repo y levantás el backend, el dashboard se ve vacío. Este
script añade 10-12 fuentes de ejemplo cubriendo los 12 source kinds para
que el founder vea actividad desde minuto 1.

Uso:
  # Local
  BEARER_TOKEN=xxx python scripts/seed-example-sources.py

  # Contra producción
  API_URL=https://api.circles-ai.ai BEARER_TOKEN=xxx \\
    python scripts/seed-example-sources.py

  # Modo dry-run (NO inserta, solo muestra qué haría)
  python scripts/seed-example-sources.py --dry-run

Cómo obtener el BEARER_TOKEN:
  curl -X POST $API_URL/api/v1/auth/login \\
    -H "Content-Type: application/json" \\
    -d '{"email":"YOUR@EMAIL.COM"}' | jq -r .token

El script es idempotente: si una fuente con el mismo nombre ya existe, la
salta sin error (vía heurística por name match).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# Fuentes curadas que cubren los 12 source kinds.
# Cada tupla: (kind, target, name)
EXAMPLE_SOURCES: List[Tuple[str, str, str]] = [
    # ----- 1. RSS feeds curados (LATAM tech + business) -----
    ("rss", "https://techcrunch.com/feed/", "TechCrunch"),
    ("rss", "https://contxto.com/en/feed/", "Contxto (LATAM tech)"),

    # ----- 2. Hacker News -----
    ("hn", "", "Hacker News (top stories)"),

    # ----- 3. Reddit subreddits relevantes -----
    ("reddit", "startups", "Reddit r/startups"),
    ("reddit", "SaaS", "Reddit r/SaaS"),

    # ----- 4. GitHub Trending -----
    ("github_trending", "", "GitHub Trending (daily)"),

    # ----- 5. Product Hunt -----
    ("product_hunt", "", "Product Hunt (daily)"),

    # ----- 6. YouTube canal (Y Combinator) -----
    ("youtube", "@ycombinator", "Y Combinator YouTube"),

    # ----- 7. Bluesky search -----
    ("bluesky", "fintech LATAM", "Bluesky: fintech LATAM"),

    # ----- 8. Telegram canal público -----
    ("telegram", "indiehackers", "Telegram: Indie Hackers"),

    # ----- 9. Events: Lu.ma feed de eventos tech -----
    ("events", "https://lu.ma/feed.xml", "Lu.ma eventos tech"),

    # ----- 10. SEC EDGAR — Apple (ejemplo de filings públicos US) -----
    ("sec_edgar", "320193", "SEC EDGAR: Apple (CIK 320193)"),
    ("sec_edgar", "789019", "SEC EDGAR: Microsoft (CIK 789019)"),

    # ----- 11. Google Trends por país (cubre 4 mercados clave) -----
    ("google_trends", "US", "Google Trends — Estados Unidos"),
    ("google_trends", "EC", "Google Trends — Ecuador"),
    ("google_trends", "MX", "Google Trends — México"),
    ("google_trends", "CO", "Google Trends — Colombia"),
]


def http_request(
    method: str, url: str, headers: dict, body: dict | None = None,
    timeout: int = 15,
) -> Tuple[int, dict]:
    """HTTP request usando stdlib urllib (sin requests dependency)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            try:
                body_json = json.loads(resp.read().decode("utf-8"))
            except (json.JSONDecodeError, ValueError):
                body_json = {}
            return resp.status, body_json
    except HTTPError as e:
        try:
            body_json = json.loads(e.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            body_json = {"error": str(e)}
        return e.code, body_json
    except URLError as e:
        print(f"  FAIL Network error: {e.reason}", file=sys.stderr)
        return 0, {"error": str(e.reason)}


def get_existing_source_names(api_url: str, token: str) -> set:
    """Lista fuentes ya existentes (para idempotencia)."""
    status, body = http_request(
        "GET", f"{api_url}/api/v1/sources",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        print(f"  WARN No pude listar fuentes existentes (HTTP {status}). Asumiendo cero.", file=sys.stderr)
        return set()
    items = body.get("items", []) if isinstance(body, dict) else []
    return {s.get("name") for s in items if s.get("name")}


def add_source(api_url: str, token: str, kind: str, target: str, name: str) -> bool:
    """Añade una fuente. Retorna True si fue creada exitosamente."""
    status, body = http_request(
        "POST", f"{api_url}/api/v1/sources",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        body={"kind": kind, "target": target, "name": name},
    )
    if status in (200, 201):
        return True
    print(f"  FAIL HTTP {status}: {body.get('detail', body) if isinstance(body, dict) else body}", file=sys.stderr)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed example sources into the Cazador")
    parser.add_argument("--api-url", default=os.getenv("API_URL", "http://localhost:8002"),
                        help="API URL del backend (default: localhost:8002 o env API_URL)")
    parser.add_argument("--token", default=os.getenv("BEARER_TOKEN"),
                        help="Bearer token (default: env BEARER_TOKEN)")
    parser.add_argument("--dry-run", action="store_true",
                        help="No insertar nada, solo mostrar qué fuentes se añadirían")
    args = parser.parse_args()

    api_url = args.api_url.rstrip("/")
    token = args.token

    print(f"=== Seed example sources ===")
    print(f"API: {api_url}")
    print(f"Auth: {'(provided)' if token else '(NONE — needed for non-dry-run)'}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"Total candidatos: {len(EXAMPLE_SOURCES)}")
    print()

    if not args.dry_run and not token:
        print("FAIL BEARER_TOKEN requerido cuando no es --dry-run.", file=sys.stderr)
        print("  Genera uno con:", file=sys.stderr)
        print("    curl -X POST $API_URL/api/v1/auth/login \\", file=sys.stderr)
        print("      -H 'Content-Type: application/json' \\", file=sys.stderr)
        print("      -d '{\"email\":\"YOUR@EMAIL\"}' | jq -r .token", file=sys.stderr)
        return 2

    if args.dry_run:
        for kind, target, name in EXAMPLE_SOURCES:
            print(f"  Would add: [{kind:18}] {name} -> {target or '(no target)'}")
        return 0

    # Idempotencia: leer fuentes existentes
    print("Listando fuentes existentes…")
    existing = get_existing_source_names(api_url, token)
    print(f"  -> {len(existing)} fuentes ya configuradas.")
    print()

    created, skipped, failed = 0, 0, 0
    for kind, target, name in EXAMPLE_SOURCES:
        if name in existing:
            print(f"  SKIP Skip (ya existe): {name}")
            skipped += 1
            continue
        print(f"  + Adding: [{kind:18}] {name}", end=" ")
        if add_source(api_url, token, kind, target, name):
            print("OK")
            created += 1
        else:
            failed += 1

    print()
    print(f"=== Resumen ===")
    print(f"  OK Creadas:     {created}")
    print(f"  SKIP Skip (dupe): {skipped}")
    print(f"  FAIL Fallidas:    {failed}")
    print()

    if created > 0:
        print(f"Tip: corre 'POST /api/v1/sources/scan' para que el cazador")
        print(f"   escanee las fuentes nuevas y produzca las primeras señales.")
        print(f"   O usá el botón '▶ Escanear ahora' en /cazar/fuentes.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
