# Architecture — Circle LLC Factory of Factories

> Visión de alto nivel del sistema. Para detalles de implementación ver
> los 27 ADRs en `orchestrator/decisions/` y el `CLAUDE.md` raíz.

## Sistema completo

```
                                          USUARIO (closed-beta)
                                                  │
                                                  ▼
                                  ┌────────────────────────────────┐
                                  │ DASHBOARD (Next.js 15)          │
                                  │ Vercel / localhost:3001         │
                                  │                                 │
                                  │  16 páginas:                    │
                                  │   /                             │
                                  │   /cazar                        │
                                  │     /senales                    │
                                  │     /fuentes                    │
                                  │     /oportunidades              │
                                  │     /nichos                     │
                                  │     /bitacora                   │
                                  │   /agentes                      │
                                  │   /fabricas                     │
                                  │   /pipeline                     │
                                  │   /revision                     │
                                  │   /leads                        │
                                  │   /configuracion                │
                                  │   /digest                       │
                                  │   /admin/status                 │
                                  │   /admin/diagnose-deploy        │
                                  └─────────────┬───────────────────┘
                                                │ Bearer token (JWT)
                                                │ HTTPS / CORS allowlist
                                                ▼
                                  ┌────────────────────────────────┐
                                  │ BACKEND (FastAPI)                │
                                  │ Railway / localhost:8002         │
                                  │                                  │
                                  │  56 endpoints en 5 grupos:       │
                                  │   /api/v1/auth/*                 │
                                  │   /api/v1/gate/*                 │
                                  │   /api/v1/sources/*              │
                                  │   /api/v1/signals/*              │
                                  │   /api/v1/admin/*                │
                                  │                                  │
                                  └─────────┬──────────────┬─────────┘
                                            │              │
                                ┌───────────┘              └────────────┐
                                ▼                                       ▼
                  ┌──────────────────────────┐         ┌──────────────────────┐
                  │ WORKFLOW LINEAL (4 pasos) │         │ AGENTES ON-DEMAND   │
                  │                            │         │                      │
                  │ 1. idea_hunter             │         │ 6 invocables 1-click │
                  │ 2. idea_enricher           │         │  · trend_gap_analyz. │
                  │ 3. idea_maturer            │         │  · niche_scout       │
                  │ 4. market_validator        │         │  · event_relevance   │
                  │ 5. landing_generator       │         │  · sleeper_company   │
                  │ 6. gate_decider (ensemble) │         │  · product_arbitrage │
                  │ 7. source_scanner          │         │  · multi_agent_cons. │
                  │                            │         │                      │
                  │ Costo: ~$0.06/run          │         │ Costo: ~$0.003-0.012 │
                  └─────────────┬──────────────┘         └──────────┬───────────┘
                                │                                   │
                                ▼                                   ▼
                  ┌──────────────────────────┐         ┌──────────────────────┐
                  │ LLM ENSEMBLE              │         │ STORAGE              │
                  │                           │         │                      │
                  │ · Claude Sonnet 4.6       │         │ SQLite (M2-M5)       │
                  │ · OpenAI GPT-4o-mini      │         │ Postgres (M6+)       │
                  │ · Google Gemini           │         │                      │
                  │   (fact-check + vote)     │         │ Tables:              │
                  │                           │         │  · signals           │
                  │ Prompt caching activo     │         │  · sources           │
                  │ Mock mode si sin keys     │         │  · gate_runs         │
                  │                           │         │  · leads             │
                  └───────────────────────────┘         │  · links_log         │
                                                        │  · connected_accounts│
                                                        │  · embeddings        │
                                                        │  · autonomy          │
                                                        └──────────────────────┘
```

## El Cazador — flujo de captura

```
┌─────────────────────────────────────────────────────────────┐
│                       12 SOURCE KINDS                        │
│                                                              │
│  rss · hn · reddit · github_trending · product_hunt          │
│  youtube · bluesky · telegram · events · sec_edgar           │
│  google_trends · url                                         │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼  (cron cada 6h o manual)
            ┌────────────────────────────┐
            │ source_scanner agent        │
            │ (fetcher por kind)          │
            └────────────┬───────────────┘
                         │
                         ▼
            ┌────────────────────────────┐
            │ Heurísticas de filtrado    │
            │ · _is_spa_fallback         │
            │ · _is_corporate_descr.     │
            │ · _is_bare_homepage        │
            │ · content_type classifier  │
            │ · language detector        │
            └────────────┬───────────────┘
                         │
                         ▼
            ┌────────────────────────────┐
            │ signals (Storage)           │
            │ con auto-clasificación:     │
            │  · content_type             │
            │  · language                 │
            │  · trend_score              │
            │  · suggested_topic          │
            └────────────┬───────────────┘
                         │
                ┌────────┴────────┐
                ▼                 ▼
        Founder marca       Auto-promote
        👍 / 👎              si score≥0.85
                │                 │
                └────────┬────────┘
                         ▼
            ┌────────────────────────────┐
            │ EvidenceGateWorkflow        │
            │ (workflow lineal, 4 pasos)  │
            └────────────┬───────────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │   VERDICT    │
                  │ pass/kill/   │
                  │ iterate +    │
                  │ confidence   │
                  └──────────────┘
```

## EvidenceGateWorkflow (los 4 pasos)

```
INPUT: topic (string)
   │
   ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 1: idea_hunter                                           │
│  - Genera IdeaSpec desde topic                                │
│  - Salida: { idea, value_prop_hint }                          │
└──────┬───────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 1.5: idea_enricher                                        │
│  - Sharpens vaguedad, opcionalmente web_search                 │
│  - Fact-check Gemini (R: ENSEMBLE_GATE_ENABLED)                │
│  - Salida: { idea_refined, specificity_score, fact_checks }    │
└──────┬───────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 2: idea_maturer                                           │
│  - Define ICP + value prop + 2-3 riesgos                       │
│  - Salida: { icp, value_prop, risks }                          │
└──────┬───────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 3: market_validator                                       │
│  - Diseña test de mercado: presupuesto, días, métricas         │
│  - Salida: EvidenceTestDesign                                  │
└──────┬───────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 4a: landing_generator                                     │
│  - Genera landing copy (headline + bullets + CTA)              │
│  - Salida: LandingCopy                                         │
└──────┬───────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ STEP 4b: gate_decider (ENSEMBLE 3 LLMs)                        │
│  - Claude + GPT-4o-mini + Gemini votan PASS/KILL/ITERATE       │
│  - Si disenso ≥33%, needs_human_review=True                    │
│  - Salida: GateDecision { verdict, confidence, votes }         │
└──────┬───────────────────────────────────────────────────────┘
       │
       ▼
   RunGateResponse persistido + visible en /fabricas
```

## Agentes — los 13 lifecycles

```
EXPERIMENTAL              ACTIVE (on-demand)          ACTIVE (workflow)
(10 cases)                (30 cases, v1.0.0)          (n/a, en workflow lineal)
─────────────             ─────────────────           ──────────────────
                          trend_gap_analyzer          idea_hunter
                          niche_scout                 idea_enricher
                          event_relevance_scorer      idea_maturer
                          sleeper_company_detector    market_validator
                          product_arbitrage_eval.     landing_generator
                          multi_agent_consensus       gate_decider
                                                       source_scanner
                          ↑                            ↑
                          6 agentes                   7 agentes
                          Invocados por endpoint     EvidenceGateWorkflow
                          (botón en dashboard)        (auto via /gate/run)
                                                      o autoscan cada 6h

DEFERRED (20 agentes en _deferred/)
────────────────────────────────────
Esperan ≥3 fábricas en prod + 30 cases cada uno (criterios M6+)
```

## Crons (GitHub Actions)

```
.github/workflows/
├── eval-suite.yml         on: push, pull_request
│                          → pytest tests/ (765 verdes en ~15s)
│
├── auto-scan.yml          on: schedule cron '17 */6 * * *' (cada 6h)
│                          → POST $API_URL/api/v1/sources/scan
│                            con auto_promote_threshold=0.85
│                          Skip silencioso si AUTO_SCAN_* secrets faltan
│
└── weekly-digest.yml      on: schedule cron '0 12 * * 1' (lunes 12 UTC)
                            → POST $API_URL/api/v1/digest/send
                            Skip silencioso si SMTP_* o AUTO_SCAN_* faltan
```

## Stack tecnológico

| Capa | Tech | Justificación |
|---|---|---|
| **Backend API** | Python 3.12+ + FastAPI | Pydantic schemas R-compliant + async LLM calls |
| **Frontend** | Next.js 15 + TypeScript + Tailwind | App Router + server components donde aplica |
| **Storage** | SQLite (M2-M5) → Postgres + pgvector (M6+) | Single-tenant simple primero, multi-tenant después |
| **LLMs** | Claude Sonnet 4.6 / Haiku 4.5 + OpenAI GPT-4o-mini + Google Gemini | Ensemble en gate_decider; Haiku en idea_analyzer (cheap) |
| **Observabilidad** | Langfuse (opt-in via env) + Sentry | Tracing por agente |
| **CI** | GitHub Actions | eval-suite + auto-scan + weekly-digest |
| **Deploy** | Railway (backend) + Vercel (dashboard + landing) | DEPLOY.md tiene los pasos exactos |

## Costos LLM (typical)

| Operación | Costo USD |
|---|---|
| /gate/run (workflow completo) | ~$0.06 |
| /signals/{id}/analyze (single Haiku) | ~$0.005 |
| /signals/{id}/translate (Haiku, mocked si español) | ~$0.0005 |
| /trend-gaps/analyze (Sonnet single call) | ~$0.008 |
| /niche-opportunities/analyze | ~$0.008 |
| /events/score | ~$0.003 |
| /sleeper-companies/detect | ~$0.010 |
| /arbitrage/evaluate | ~$0.003 |
| /consensus/analyze | ~$0.012 |
| Source scan completo (sin LLM) | $0 |
| Weekly digest (sin LLM) | $0 |

**$0.06 × 100 runs/mes = $6/mes** en LLM solo.
Plus Railway backend ~$5/mes = **$11/mes total infra** para 100 ideas validadas.

---

Para más detalle: ver `README.md`, `DEPLOY.md`, `CLAUDE.md`, y los 27 ADRs.
