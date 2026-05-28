# circle-llc — Factory of Factories (FoF)

## Qué es este proyecto
Plataforma meta-sistémica que valida ideas de negocio en modo "evidence-gate": una landing + anuncios + métricas reales en 14 días antes de construir una sola línea de producto. Dominio: **circles-ai.ai**.

## Arquitectura Reganti-alineada (AI Builder's Handbook 2026)

Principio rector: **"Stay at the simplest level that handles 90% of your cases"** (Cap 10 §10.3)

```
circle-llc/
├── orchestrator/     # Python FastAPI — EvidenceGateWorkflow + 7 agentes
├── outcome-db/       # PostgreSQL + pgvector — write/eviction policies (activo en M3+)
├── landing/          # Next.js 15 — circles-ai.ai (público, live)
├── dashboard/        # Next.js 15 — admin closed-beta (auth allowlist)
├── scripts/          # Generación de pool + seed de fuentes
└── tests/            # 360 tests verdes
```

## Stack base (NO cambiar sin ADR)
- LLM: Anthropic Claude (Sonnet 4.6, Haiku 4.5) + ensemble OpenAI GPT-4o-mini + Google Gemini
- Backend: Python 3.12+ + FastAPI + Pydantic
- Frontend: Next.js 15 + TypeScript + Tailwind
- DB: SQLite (M2 - prod en Railway volume) → Postgres + pgvector (M3+)
- Tests: pytest
- Observabilidad: Langfuse (agentes) + Sentry (infra)
- CI: GitHub Actions
- Deploy: Railway (backend) + Vercel (landing + dashboard)

## Los 7 agentes activos

| Agente | Rol en EvidenceGateWorkflow |
|---|---|
| `idea_hunter` | Genera ideas desde topic/trend (Step 1) — Claude |
| `idea_enricher` | Sharpens vagueness, web_search, fact-check Gemini (Step 1.5) |
| `idea_maturer` | Define ICP + value prop + riesgos (Step 2) |
| `market_validator` | Diseña test de mercado (Step 3) |
| `landing_generator` | Escribe landing copy (Step 4a) |
| `gate_decider` | PASS/KILL/ITERATE — ensemble Claude+GPT+Gemini (Step 4b) |
| `source_scanner` | Destila signals desde fuentes externas (R28-R29) |

20+ agentes adicionales están archivados en `orchestrator/agents/_deferred/` hasta M4+.

## Estado al 2026-05-27

| | |
|---|---|
| Tests verdes | **476** |
| Commits en GitHub | 46 |
| ADRs | 15 |
| Reglas R01-R29 | 29 |
| Endpoints API | 35 |
| Páginas dashboard | 11 |
| circles-ai.ai live | ✅ |
| /f/techpulse-latam live | ✅ |
| Dashboard local | ✅ (Vercel deploy pendiente del founder) |
| Outcome DB | INACTIVA (M4+ cuando N≥3 fábricas) |

## Cazador autónomo — 9 source kinds

| Kind | Auth | Status |
|---|---|---|
| `url` | none | ✅ |
| `rss` | none | ✅ |
| `hn` | none (Firebase API) | ✅ |
| `reddit` | none (.json) | ✅ |
| `github_trending` | none (scrape) | ✅ |
| `product_hunt` | none (RSS) | ✅ |
| `youtube` | none (per-channel RSS) | ✅ M3.1 |
| `bluesky` | none (XRPC) | ✅ M3.1 |
| `telegram` | none (t.me/s/) | ✅ M3.1 |
| ~~`x_twitter`~~ | $100/mo | ❌ defer M4+ |
| ~~`linkedin`~~ | partner-only | ❌ defer indefinitely |
| ~~`instagram`~~ | own posts only | ❌ no value for B2B hunting |

## Documentos de referencia (NO modificar)
- `D:/CM/IA_2026/Fabrica de Fabricas/Circle_LLC_FoF_Revision_Aishwarya_Reganti.html`
- `D:/CM/IA_2026/Fabrica de Fabricas/v2.1/`

## Autor
Cristian Molina — Circle LLC | Mayo 2026
Refactor guiado por revisión Aishwarya Naresh Reganti (LevelUp Labs)
