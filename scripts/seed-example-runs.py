#!/usr/bin/env python
"""
seed-example-runs.py — M7.2 — bootstrap del dashboard con runs ejecutados.

Tras correr seed-example-sources.py (M7.1), todavía /fabricas y la home (/)
se ven vacíos porque no hay runs. Este script ejecuta 3 corridas del
EvidenceGateWorkflow contra ideas curadas para poblar la tabla de runs.

Uso:
  # Genera token primero
  TOKEN=$(curl -s -X POST $API_URL/api/v1/auth/login \\
    -H 'Content-Type: application/json' \\
    -d '{"email":"YOUR@EMAIL"}' | jq -r .token)

  # Ejecutar 3 runs (default)
  BEARER_TOKEN=$TOKEN python scripts/seed-example-runs.py

  # Cambiar cantidad
  BEARER_TOKEN=$TOKEN python scripts/seed-example-runs.py --count 5

  # Dry-run (no ejecuta, solo lista)
  python scripts/seed-example-runs.py --dry-run

ADVERTENCIA: Cada run cuesta ~$0.06 en LLM (Anthropic + OpenAI + Google).
3 runs = $0.18 USD aproximado. Si backend en mock_mode (sin
ANTHROPIC_API_KEY), el costo es $0 pero los outputs son placeholders.

El script es idempotente por idea_title: si ya hay un run con el mismo
título, lo salta (verifica via GET /api/v1/runs antes).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# Ideas curadas que reflejan el modelo FoF — diversidad de mercados y
# verticals para que el dashboard muestre variedad de verdicts.
EXAMPLE_TOPICS: List[str] = [
    "fintech para PYMEs Ecuador con reconciliación bancaria automática",
    "edtech para profesores rurales LATAM — onboarding con WhatsApp",
    "platform de logística last-mile para e-commerce regional",
    "marketplace de servicios profesionales con escrow B2B",
    "tooling para community managers en español — programación + analytics",
    "compliance SaaS para empresas medianas en Colombia (LOPD + GDPR)",
    "agtech para optimización de cosecha en pequeños productores",
    "healthtech telemedicina pre-pago para zonas remotas del Perú",
]


def http_request(
    method: str, url: str, headers: dict, body: Optional[dict] = None,
    timeout: int = 300,
) -> tuple[int, dict]:
    """HTTP request via stdlib urllib (sin requests dep). Timeout largo (5 min)
    porque /gate/run con LLM real + ensemble vote + fact-check puede tomar
    60-180s. En mock_mode tarda <2s."""
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


def get_existing_run_titles(api_url: str, token: Optional[str]) -> set:
    """Lista títulos de runs ya ejecutados. Si no podemos listar, asumimos cero."""
    if not token:
        return set()
    status, body = http_request(
        "GET", f"{api_url}/api/v1/runs?limit=100",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        return set()
    items = body.get("items", []) if isinstance(body, dict) else []
    return {r.get("idea_title", "").strip() for r in items if r.get("idea_title")}


def run_workflow(api_url: str, topic: str) -> tuple[bool, dict]:
    """Ejecuta POST /api/v1/gate/run. Note: este endpoint NO requiere auth
    (es público para integraciones externas; el costo lo paga el operador
    del backend via API keys configuradas en env)."""
    status, body = http_request(
        "POST", f"{api_url}/api/v1/gate/run",
        headers={"Content-Type": "application/json"},
        body={"topic": topic},
    )
    if status == 201:
        return True, body
    return False, body


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed example runs into the dashboard")
    parser.add_argument("--api-url", default=os.getenv("API_URL", "http://localhost:8002"),
                        help="API URL del backend (default: localhost:8002 o env API_URL)")
    parser.add_argument("--token", default=os.getenv("BEARER_TOKEN"),
                        help="Bearer token (default: env BEARER_TOKEN). Opcional — solo "
                             "necesario para idempotency check (listar runs existentes).")
    parser.add_argument("--count", type=int, default=3,
                        help="Cantidad de runs a ejecutar (default 3, max 8)")
    parser.add_argument("--dry-run", action="store_true",
                        help="No ejecutar nada, solo mostrar qué topics se usarían")
    args = parser.parse_args()

    api_url = args.api_url.rstrip("/")
    token = args.token
    count = max(1, min(args.count, len(EXAMPLE_TOPICS)))

    print(f"=== Seed example runs ===")
    print(f"API: {api_url}")
    print(f"Auth: {'(provided)' if token else '(none — idempotency check disabled)'}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"Runs a ejecutar: {count} de {len(EXAMPLE_TOPICS)} candidatos")
    print(f"Costo estimado: ~${count * 0.06:.2f} USD si backend en live mode")
    print()

    topics_to_run = EXAMPLE_TOPICS[:count]

    if args.dry_run:
        for i, topic in enumerate(topics_to_run, 1):
            print(f"  Would run [{i}/{count}]: {topic[:80]}")
        return 0

    # Idempotencia: leer runs existentes (si tenemos auth para listar)
    if token:
        print("Verificando runs existentes…")
        existing_titles = get_existing_run_titles(api_url, token)
        print(f"  -> {len(existing_titles)} runs ya en la base.")
        print()
    else:
        existing_titles = set()
        print("WARN no provisto BEARER_TOKEN — no podemos chequear duplicados.")
        print()

    created, skipped, failed = 0, 0, 0
    total_cost = 0.0
    verdicts = {"pass": 0, "kill": 0, "iterate": 0, "unknown": 0}

    for i, topic in enumerate(topics_to_run, 1):
        # Idempotency check (best effort)
        if existing_titles:
            # Heurística: si algún título existente contiene las primeras
            # 5 palabras del topic, lo consideramos duplicado
            first_words = " ".join(topic.lower().split()[:5])
            if any(first_words in t.lower() for t in existing_titles):
                print(f"  SKIP [{i}/{count}] Ya existe similar: {topic[:60]}")
                skipped += 1
                continue

        print(f"  + [{i}/{count}] Ejecutando: {topic[:70]}…", flush=True)
        t0 = time.monotonic()
        ok, body = run_workflow(api_url, topic)
        elapsed = time.monotonic() - t0

        if ok:
            verdict = body.get("verdict", "unknown")
            confidence = float(body.get("confidence", 0) or 0)
            cost = float(body.get("cost_usd_estimated", 0) or 0)
            verdicts[verdict] = verdicts.get(verdict, 0) + 1
            total_cost += cost
            print(f"    OK  verdict={verdict} conf={confidence:.2f} "
                  f"cost=${cost:.4f} ({elapsed:.1f}s)")
            created += 1
        else:
            err = body.get("detail", body) if isinstance(body, dict) else body
            print(f"    FAIL {err}")
            failed += 1

    print()
    print(f"=== Resumen ===")
    print(f"  OK   Creadas:     {created}")
    print(f"  SKIP Duplicadas:  {skipped}")
    print(f"  FAIL Fallidas:    {failed}")
    if created > 0:
        print(f"  $    Costo total: ${total_cost:.4f}")
        print(f"  Verdicts: {verdicts}")
    print()

    if created > 0:
        print(f"Tip: abrí {api_url.replace('8002', '3001')}/fabricas para ver los runs nuevos.")
        print(f"     O la home del dashboard tiene la tabla 'Runs recientes' poblada.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
