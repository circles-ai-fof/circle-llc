"""
Generate a pool of real EvidenceGateWorkflow runs for the public landing demo.

Why: the demo at circles-ai.ai/#how-it-works needs to show *real* outputs of
the 3-LLM ensemble without exposing the live $0.06-per-call endpoint to bots.
Pre-computing a pool of ~15 outputs covers most user queries by keyword match
and costs ~$1 total.

Output: landing/lib/demo-runs.json (consumed by landing/lib/demo-pool.ts)

Run from the repo root:
    python scripts/generate_demo_pool.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env BEFORE importing the workflow (so anthropic.Anthropic() picks up the key)
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        # Strip inline comments (`KEY=val   # comment`)
        if "#" in v:
            v = v.split("#", 1)[0]
        os.environ[k.strip()] = v.strip()

from orchestrator.workflows.evidence_gate import EvidenceGateWorkflow  # noqa: E402


# 15 topics covering main verticals. Keywords are used for matching at runtime.
TOPICS = [
    # SaaS
    {
        "id": "saas-facturacion",
        "category": "saas",
        "keywords": ["facturacion", "contabilidad", "sri", "factura", "electronica", "saas", "pyme", "contable"],
        "topic": "SaaS de facturacion electronica para PYMEs Ecuador con integracion SRI",
    },
    {
        "id": "saas-crm",
        "category": "saas",
        "keywords": ["crm", "clientes", "ventas", "leads", "pipeline", "ventas"],
        "topic": "CRM ligero para vendedores B2B en LATAM con WhatsApp integrado",
    },
    {
        "id": "saas-hr",
        "category": "saas",
        "keywords": ["rrhh", "nomina", "empleados", "iess", "recursos humanos", "payroll"],
        "topic": "Plataforma de nomina y gestion IESS automatica para PYMEs Ecuador",
    },
    # Marketplace
    {
        "id": "marketplace-freelancers",
        "category": "marketplace",
        "keywords": ["freelancers", "freelance", "trabajo", "remoto", "developers", "diseñadores", "talento"],
        "topic": "Marketplace de freelancers tech LATAM para startups en early stage",
    },
    {
        "id": "marketplace-servicios",
        "category": "marketplace",
        "keywords": ["servicios", "profesionales", "abogados", "contadores", "consultores", "marketplace"],
        "topic": "Marketplace de servicios legales online para PYMEs Colombia y Ecuador",
    },
    # Fintech
    {
        "id": "fintech-credito",
        "category": "fintech",
        "keywords": ["credito", "prestamo", "capital", "trabajo", "factoring", "fintech", "liquidez"],
        "topic": "Fintech de capital de trabajo en 24 horas para PYMEs LATAM sin hipoteca",
    },
    {
        "id": "fintech-pagos",
        "category": "fintech",
        "keywords": ["pagos", "qr", "yappy", "bre-b", "deuna", "billetera", "wallet"],
        "topic": "Billetera digital con pagos QR interoperables para comercios pequeños LATAM",
    },
    # Healthtech
    {
        "id": "healthtech-telemedicina",
        "category": "healthtech",
        "keywords": ["telemedicina", "salud", "doctor", "consulta", "medico", "rural", "remoto"],
        "topic": "Telemedicina para zonas rurales Ecuador con triage IA y especialistas urbanos",
    },
    {
        "id": "healthtech-mental",
        "category": "healthtech",
        "keywords": ["salud", "mental", "psicologia", "terapia", "ansiedad", "depresion", "bienestar"],
        "topic": "Plataforma de salud mental B2B para empresas medianas LATAM con terapeutas certificados",
    },
    # Edtech
    {
        "id": "edtech-ingles",
        "category": "edtech",
        "keywords": ["ingles", "english", "idiomas", "niños", "kids", "aprendizaje", "edtech"],
        "topic": "Plataforma de ingles para niños LATAM con tutores IA y feedback de pronunciacion",
    },
    {
        "id": "edtech-programacion",
        "category": "edtech",
        "keywords": ["programacion", "codigo", "coding", "developers", "bootcamp", "tech", "carrera"],
        "topic": "Bootcamp de programacion full-stack online para adultos LATAM con garantia de empleo",
    },
    # Ecommerce
    {
        "id": "ecommerce-mascotas",
        "category": "ecommerce",
        "keywords": ["mascotas", "perros", "gatos", "pet", "comida", "alimento", "tienda"],
        "topic": "Subscription box mensual de alimentos premium para perros y gatos en Ecuador",
    },
    # Community / Media
    {
        "id": "media-tech",
        "category": "media",
        "keywords": ["noticias", "tech", "medios", "periodismo", "contenido", "media", "techpulse"],
        "topic": "Plataforma de noticias tech con IA y revision humana para medios LATAM",
    },
    # Logistics
    {
        "id": "logistics-delivery",
        "category": "logistics",
        "keywords": ["delivery", "envios", "logistica", "ultima milla", "courier", "transporte"],
        "topic": "Delivery de ultima milla on-demand para tiendas locales en ciudades secundarias LATAM",
    },
    # Real estate / proptech
    {
        "id": "proptech-renta",
        "category": "proptech",
        "keywords": ["alquiler", "renta", "inmueble", "departamento", "apartamento", "vivienda"],
        "topic": "Plataforma de alquiler residencial con verificacion de inquilinos y pagos automaticos Ecuador",
    },
]


def serialize_run(run, meta: dict) -> dict:
    """Convert an EvidenceGateRun to a JSON-friendly dict."""
    return {
        "id": meta["id"],
        "category": meta["category"],
        "keywords": meta["keywords"],
        "topic_input": meta["topic"],
        "idea": {
            "title": run.idea.title,
            "description": run.idea.description,
            "target_market": run.idea.target_market,
            "problem_statement": run.idea.problem_statement,
            "proposed_solution": run.idea.proposed_solution,
            "vertical_category": run.idea.vertical_category.value,
        },
        "icp": run.mature_idea.icp.model_dump(mode="json") if hasattr(run.mature_idea, "icp") else None,
        "value_proposition": run.mature_idea.value_proposition,
        "test_design": {
            "hypothesis": run.test_design.hypothesis,
            "ad_budget_usd": run.test_design.ad_budget_usd,
            "test_duration_days": run.test_design.test_duration_days,
            "target_ctr": run.test_design.target_ctr,
            "target_conversion_rate": run.test_design.target_conversion_rate,
        },
        "landing": {
            "headline": run.landing.headline,
            "subheadline": run.landing.subheadline,
            "value_props": run.landing.value_props,
            "cta_text": run.landing.cta_text,
            "social_proof": run.landing.social_proof,
            "domain_slug": run.landing.domain_slug,
        },
        "decision": {
            "verdict": run.decision.verdict.value,
            "confidence": run.decision.confidence,
            "rationale": run.decision.rationale,
            "next_steps": run.decision.next_steps,
            "ensemble_votes": [e for e in run.decision.key_evidence if "/" in e],
            "needs_human_review": run.decision.needs_human_review,
        },
        "metadata": {
            "steps_used": run.budget_tracker.steps_used if run.budget_tracker else None,
            "cost_usd_estimated": round(run.budget_tracker.cost_used_usd, 4) if run.budget_tracker else None,
            "generated_at": int(time.time()),
        },
    }


def main() -> int:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1

    out_path = ROOT / "landing" / "lib" / "demo-runs.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Resume support: skip topics already in the existing JSON
    existing = {}
    if out_path.exists():
        try:
            existing = {
                item["id"]: item for item in json.loads(out_path.read_text(encoding="utf-8"))
            }
            print(f"[resume] {len(existing)} entries already in pool")
        except Exception:
            existing = {}

    wf = EvidenceGateWorkflow()
    print(f"workflow mode: {'mock' if wf._mock_mode else 'LIVE'}")

    results = list(existing.values())
    started = time.time()
    for i, meta in enumerate(TOPICS, start=1):
        if meta["id"] in existing:
            print(f"  [{i}/{len(TOPICS)}] {meta['id']} (skip — already cached)")
            continue
        print(f"  [{i}/{len(TOPICS)}] {meta['id']} ... ", end="", flush=True)
        t0 = time.time()
        try:
            run = wf.run(meta["topic"])
            entry = serialize_run(run, meta)
            results.append(entry)
            # Persist incrementally so a mid-run failure doesn't lose work
            out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"OK ({time.time() - t0:.0f}s) -> verdict={entry['decision']['verdict']}")
        except Exception as e:  # noqa: BLE001
            print(f"FAIL: {e}")

    elapsed = time.time() - started
    print(f"\nDone. {len(results)} entries, {elapsed:.0f}s elapsed.")
    print(f"Output: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
