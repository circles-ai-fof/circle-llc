# circle-llc — Factory of Factories (FoF)

## Qué es este proyecto
Plataforma meta-sistémica que valida ideas de negocio en modo "evidence-gate": una landing + anuncios + métricas reales en 14 días antes de construir una sola línea de producto. Dominio: **circles-ai.ai** · Dashboard: **dashboard.circles-ai.ai**.

## Arquitectura Reganti-alineada (AI Builder's Handbook 2026)

Principio rector: **"Stay at the simplest level that handles 90% of your cases"** (Cap 10 §10.3)

```
circle-llc/
├── orchestrator/     # Python FastAPI — EvidenceGateWorkflow + 18 agentes
├── outcome-db/       # PostgreSQL + pgvector — write/eviction policies (activo en M17+)
├── landing/          # Next.js 15 — circles-ai.ai (público, live)
├── dashboard/        # Next.js 15 — admin closed-beta (live en dashboard.circles-ai.ai)
├── scripts/          # Generación de pool + seed de fuentes
└── tests/            # 1078 tests verdes
```

## Stack base (NO cambiar sin ADR)
- LLM: **Ensemble 4-LLM** Claude (Sonnet 4.6 + Haiku 4.5 + Opus 4.5) + OpenAI GPT-4o-mini + Google Gemini Flash + xAI Grok 3-mini
- Backend: Python 3.12+ + FastAPI + Pydantic v2
- Frontend: Next.js 15 + TypeScript + Tailwind
- DB: SQLite (M2 — prod en Railway volume) → Postgres + pgvector (M17+, cuando N≥3 fábricas)
- Tests: pytest (1078 verdes)
- Observabilidad: Langfuse (agentes) + Sentry (infra)
- CI: GitHub Actions (5 crons: auto-scan, auto-analyze, db-backup, executive-briefing, weekly-digest)
- Deploy: Railway (backend) + Vercel (landing + dashboard con custom domain SSL)

## 18 agentes activos

### Workflow (7)
| Agente | Rol en EvidenceGateWorkflow |
|---|---|
| `idea_hunter` | Genera ideas desde topic/trend (Step 1) — Claude |
| `idea_enricher` | Sharpens vagueness, web_search, fact-check Gemini (Step 1.5) |
| `idea_maturer` | Define ICP + value prop + riesgos (Step 2) |
| `market_validator` | Diseña test de mercado (Step 3) |
| `landing_generator` | Escribe landing copy (Step 4a) |
| `gate_decider` | PASS/KILL/ITERATE — ensemble 4-LLM Claude+GPT+Gemini+Grok (Step 4b) |
| `source_scanner` | Destila signals desde fuentes externas (R28-R29) |

### Defensas + filtros (3)
| Agente | Cuándo fira |
|---|---|
| `IdeaValidator` (M11.3+M11.4) | Step 2.5 pre-test — Opus red-team kills antes de ads |
| `adversarial_callback` (M11.1, ADR-028) | Post-gate confidence borderline → Grok devil's advocate |
| `CardValidator` (M11.0) | Por imagen de marketplace card — Claude vision filtra mockups |

### Cazador autónomo (3)
| Agente | Función |
|---|---|
| `SourceDiscoveryAgent` (M9.4) | Propone fuentes desde clusters aprobados via Gemini search |
| `LinkFollowerAgent` (M10.0) | Extrae RSS escondidos de evidence_urls de signals aprobadas |
| `executive-status` (M15.0) | Briefing ejecutivo (cerebro del WhatsApp Gateway M16+) |

### Análisis on-demand (5)
| Agente | Función |
|---|---|
| `TrendGapAnalyzer` (M5.0) | First-mover gaps cross-country |
| `NicheScout` (M5.2) | Plan de entrada al sub-niche |
| `EventScorer` (M5.3) | ¿Ir o no a la feria? |
| `SleeperDetector` (M5.4) | Ideas dormidas que despiertan |
| `MultiAgentConsensus` (M6.0) | Voting cross-agente |

20+ agentes adicionales archivados en `orchestrator/agents/_deferred/` hasta M18+.

## Estado al 2026-06-03

| | |
|---|---|
| Tests verdes | **1078** |
| Commits en GitHub | en sync con master, firmados Circle LLC <circles.fof.ai@gmail.com> |
| ADRs | **29** |
| Reglas R01-R29 | 29 |
| Endpoints API | **60+** (security, executive-status, ideas/validate, auto-analyze, scan-queue, etc) |
| Páginas dashboard | **18** (incluye Configuración M9.1 real) |
| Source kinds activos | **15** |
| Fuentes seedeadas en producción | **33** |
| LLM keys configurados | **4** (Anthropic + OpenAI + Google + xAI) |
| circles-ai.ai live | ✅ |
| dashboard.circles-ai.ai live | ✅ con SSL custom domain |
| Backend Railway live | ✅ mode=live, persistent_storage=true |
| Outcome DB | INACTIVA (M17+ cuando N≥3 fábricas, watchdog activo M11.2) |

## Sprints recientes (M8 → M15) — resumen

| Sprint | Qué entrega | ADR |
|---|---|---|
| M8.x | Production deploy: Railway backend + Vercel dashboard + Cloudflare DNS + custom domain | — |
| M9.0 | Grok como 4ª voz del ensemble + 2-2 tie → forzado iterate | — |
| M9.1 | UserSettings (i18n) + traducción al scrapear con Haiku | — |
| M9.2 | source_kind `app_marketplace` (Lovable, Claude Creations, Adorable) | — |
| M9.3 | canonical_hash dedup cross-source + times_seen | — |
| M9.4 | SourceDiscoveryAgent (Gemini search → propone fuentes) | — |
| M9.5 | source_quality scoring + smart_scan_queue | — |
| M10.0 | LinkFollowerAgent (mina evidence_urls) | — |
| M11.0 | CardValidator (Claude vision filtra mockups) | — |
| M11.1 | adversarial_callback (degrade verdicts borderline) | ADR-028 |
| M11.2 | Outcome DB watchdog + R2 backup diario | — |
| M11.3 | IdeaValidator red-team (Opus + spec porteado) | — |
| M11.4 | Wire IdeaValidator al workflow — short-circuit MATAR | — |
| — | ADRs codifican filosofía | ADR-028, ADR-029 |
| M12.0 | pain_phrase_booster (EN+ES, 21 patrones) | — |
| M12.1 | solution_type_classifier (8 buckets OpportunityScout) | — |
| M12.2 | source_kind `reviews` (App Store low-star) | — |
| M12.3 | source_kind `job_boards` (RemoteOK automation gigs) | — |
| M13.0 | SecurityValidator (13 heurísticos: typosquat, homoglyph, TLD, shorteners) | — |
| M13.1 | Prompt injection defense (27 patterns × 4 severidades EN+ES) | — |
| M14.0 | auto-tune en trend-gaps + niche-opportunities + cron auto-analyze | — |
| M15.0 | executive-status agent + endpoint (cerebro WhatsApp Gateway) | — |
| M15.1 | Daily SMTP executive briefing (cron 08 UTC = 03 Lima/Quito) | — |

## Cazador autónomo — 15 source kinds

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
| `events` | none (RSS Lu.ma/Eventbrite) | ✅ M4.13 |
| `sec_edgar` | none (RSS SEC.gov) | ✅ M4.12 |
| `google_trends` | none (RSS por país, 22 países) | ✅ M4.14 |
| `app_marketplace` | none (HTML scrape genérico) | ✅ **M9.2** (Lovable/Claude Creations/Adorable) |
| `reviews` | none (App Store JSON RSS) | ✅ **M12.2** (1-2★ = pain del cliente) |
| `job_boards` | none (RemoteOK JSON API) | ✅ **M12.3** ("automate X" = budget + pain) |
| ~~`x_twitter`~~ | $100/mo | ❌ defer indefinitely |
| ~~`linkedin`~~ | partner-only | ❌ defer indefinitely |
| ~~`instagram`~~ | own posts only | ❌ no value for B2B hunting |

## Crons GitHub Actions (5)
- `auto-scan.yml` cada 6h — scan de 33 fuentes
- `auto-analyze.yml` diario 05 UTC — precalienta trend-gaps + niches (M14.0)
- `db-backup.yml` diario 04 UTC — SQLite → Cloudflare R2 (M11.2)
- `executive-briefing.yml` diario 08 UTC — briefing ejecutivo SMTP (M15.1)
- `weekly-digest.yml` lunes 12 UTC — digest semanal (M6.2)

## Documentos clave del repo
- `ONE-PAGER.md` — resumen estratégico 1 página (para investors/socios)
- `docs/architecture.md` — arquitectura técnica completa con diagramas
- `CHANGELOG.md` — historial de sprints
- `orchestrator/decisions/ADR-*.md` — 29 decisiones formalizadas
- `orchestrator/rulebook.md` — R01-R29 reglas operativas

## Documentos de referencia (NO modificar)
- `D:/CM/IA_2026/Fabrica de Fabricas/Circle_LLC_FoF_Revision_Aishwarya_Reganti.html`
- `D:/CM/IA_2026/Fabrica de Fabricas/v2.1/`

## Autor
Cristian Molina — Circle LLC | Mayo–Junio 2026
Refactor guiado por revisión Aishwarya Naresh Reganti (LevelUp Labs)
