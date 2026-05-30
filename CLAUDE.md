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

## Estado al 2026-05-28

| | |
|---|---|
| Tests verdes | **529** |
| Commits locales | en sync con GitHub (todos firmados Circle LLC <circles.fof.ai@gmail.com>) |
| Commits en GitHub | 79 |
| ADRs | **22** |
| Reglas R01-R29 | 29 |
| Endpoints API | 43 (+/trend-gaps, +/runs, +/signals/bulk-feedback, +/signals/bulk-delete-by-ids, +/signals/stats-by-type, +events source kind) |
| Páginas dashboard | 11 |
| circles-ai.ai live | ✅ |
| /f/techpulse-latam live | ✅ |
| Dashboard local | ✅ (Vercel deploy pendiente del founder) |
| Outcome DB | INACTIVA (M4+ cuando N≥3 fábricas) |

## Sprints M4 — resumen

| Sprint | Qué entrega | ADR |
|---|---|---|
| M4.0 | Connected Accounts + check-platform detection | ADR-018 |
| M4.1 | Preferences engine (embeddings + clustering + autonomía) | ADR-019 |
| M4.2 | Filtro `_is_corporate_description` (Asiservy ya no pasa como idea) | — |
| M4.3 | Clasificación automática de content_type con badge visual | — |
| M4.4 | Detección de idioma + traducción ES on-demand (Haiku) | ADR-020 |
| M4.5 → M4.6b | CORS + filtros + bulk-delete por tipo/fuente | ADR-021 |
| M4.7 | Distribución de señales por content_type (barra de badges) | — |
| M4.8 | Filtros persistentes en localStorage | — |
| M4.9 | Multi-select + bulk feedback / bulk delete por IDs | — |
| M4.10 | Overview ejecutivo con datos reales (replace mockData) | — |
| M4.11 | Cross-country trend gap detector (first-mover gaps) | ADR-022 |
| M4.12 | SEC EDGAR fetcher Phase 1 (filings públicas US) | ADR-022 |
| M4.13 | Eventos / Ferias como nuevo source kind | ADR-022 |
| M4.14 | Google Trends RSS por país (22 países LATAM+EU+US) | ADR-022 |
| M4.15 | Niche-en-gigante detector Phase 1 (heurístico) | ADR-022 |
| M5.0 | TrendGapAnalyzer — primer agente experimental (8º agente) | ADR-023 |
| M5.1 | TrendGapAnalyzer promovido a ACTIVE (30/30 golden cases) — v1.0.0 | ADR-024 |
| M5.2-M5.5 | 4 agentes experimentales: NicheScout, EventScorer, SleeperDetector, ArbitrageEval (12 agentes totales) | ADR-025 |
| M5.6-M5.7 | UI integration: botones "🤖" en /cazar/nichos + bulk sec_edgar en senales | — |
| M5.8-M5.11 | 4 agentes promovidos experimental → ACTIVE (5 active total, 80 nuevos cases) | ADR-026 |
| M6.1 | Weekly Digest (HTML + texto + JSON, sin SMTP todavía) + página /digest | — |
| M6.2 | SMTP send + cron weekly + botón Enviar ahora (skip silencioso sin SMTP_*) | — |
| **M6.0** | **MultiAgentConsensus — 13º agente (último del audio del founder cubierto)** | **ADR-027** |

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
