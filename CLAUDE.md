# circle-llc — Factory of Factories (FoF)

## Qué es este proyecto
Plataforma meta-sistémica que valida ideas de negocio en modo "evidence-gate": una landing + anuncios + métricas reales en 14 días antes de construir una sola línea de producto. Dominio: **circles-ai.ai**.

## Arquitectura Reganti-alineada (AI Builder's Handbook 2026)

Principio rector: **"Stay at the simplest level that handles 90% of your cases"** (Cap 10 §10.3)

```
circle-llc/
├── orchestrator/     # Python FastAPI — EvidenceGateWorkflow + 5 agentes
├── outcome-db/       # PostgreSQL + pgvector — write/eviction policies (activo en M3+)
├── landing/          # Next.js 15 — circles-ai.ai (público)
├── dashboard/        # Next.js 15 — dashboard ejecutivo (privado)
├── shared/           # Auth, UI, validators compartidos
└── tests/            # unit, integration, e2e
```

## Stack base (NO cambiar sin ADR)
- LLM: Anthropic Claude (Opus 4.7, Sonnet 4.6, Haiku 4.5)
- Backend: Python 3.12+ + FastAPI + Pydantic
- Frontend: Next.js 15 + TypeScript + Tailwind + shadcn/ui
- DB: PostgreSQL + pgvector (Supabase)
- ORM: SQLAlchemy (Py) / Drizzle (TS)
- Tests: pytest (Py) / Vitest + Playwright (TS)
- Observabilidad: Langfuse (agentes) + Sentry (infra)
- CI: GitHub Actions

## Los 5 agentes activos de Sprint M1

| Agente | Rol en EvidenceGateWorkflow |
|---|---|
| `idea_hunter` | Genera ideas desde tendencias (Step 1) |
| `idea_maturer` | Define ICP + value prop (Step 2) |
| `market_validator` | Diseña test de mercado (Step 3) |
| `landing_generator` | Genera landing copy (Step 4a) |
| `gate_decider` | Evalúa métricas → pass/kill/iterate (Step 4b) |

30+ agentes adicionales están archivados en `orchestrator/agents/_deferred/` hasta M12+.

## Documentos de referencia (NO modificar)
- `D:/CM/IA_2026/Fabrica de Fabricas/Circle_LLC_FoF_Revision_Aishwarya_Reganti.html`
- `D:/CM/IA_2026/Fabrica de Fabricas/v2.1/` — arquitectura v2.1

## Autor
Cristian Molina — Circle LLC | Mayo 2026
Refactor guiado por revisión Aishwarya Naresh Reganti (LevelUp Labs)
