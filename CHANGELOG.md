# Changelog — Circle LLC FoF

Todas las notables changes del proyecto, organizadas por milestone (`Mx`).
Formato basado en [Keep a Changelog](https://keepachangelog.com/).

---

## [M16.x] — Catalogación + plan de migración Postgres (2026-06-03)

Estado del repo: **1078 tests**, **30 ADRs**, **20 agentes activos catalogados**, **60+ endpoints**, **15 source kinds**, **33 fuentes en producción**.

### Added — M16.1: catálogo de agentes + organigrama
- `AGENTES.md` — catálogo completo de los 20 agentes activos con función, control, operación, LLM y costo por categoría (workflow / defensas / cazador / on-demand). Tabla LLM→agente. Sección R01-R29 + anti-patterns prohibidos.
- `docs/organigrama.html` — visual auto-contenido con CSS inline (dark theme + print-friendly), 4 capas color-coded, cadena Step 1→4b, cards de los 4 LLM providers, resumen ejecutivo con métricas.
- `docs/organigrama.docx` — versión Word del organigrama (US Letter, headers + footers + page numbers, 7 tablas, portada).
- `docs/generate_organigrama_docx.js` — script reproducible docx-js para regenerar el DOCX si cambia el catálogo.

### Added — M16.2: cleanup .gitignore
- `*.tsbuildinfo` añadido a `.gitignore`.
- `dashboard/tsconfig.tsbuildinfo` removido del tracking.

### Added — M16.3: ADR-030 plan de migración SQLite → Postgres + pgvector
- `orchestrator/decisions/ADR-030.md` — pre-condiciones (N≥3 fábricas, pgvector necesario, contention >5%, backup R2 saludable 30d, tests ≥1500), stack target (Postgres 16 + pgvector ≥0.7 + Alembic + psycopg async), migration steps con DUAL_WRITE window de 2h y rollback documentado, multi-tenant via RLS como sub-decisión separada.

### Verified
- Backend Railway healthy: mode=live, persistent_storage=true, EvidenceGateWorkflow active.
- 1078 tests verdes (109s wall time).

### Flagged
- `api.circles-ai.ai` SSL: certificado con wrong principal (SEC_E_WRONG_PRINCIPAL). El dominio Railway directo funciona; el custom domain requiere reconfigurar cert. **Pendiente sprint M16.4**.

---

## [M15.x] — CEO informado + cazador 100% autónomo (2026-06-03)

Estado del repo: **1078 tests**, **29 ADRs**, **18 agentes active**, **60+ endpoints**, **15 source kinds**, **33 fuentes en producción**.

### Added — M15.0: executive-status agent (18º agente)
- `orchestrator/agents/executive_status.py` — el "cerebro" del WhatsApp Gateway, expuesto como REST
- POST `/api/v1/executive-status` con 2 modos: REPORT (briefing standalone) y QA (responde pregunta)
- Lee signals + sources + runs + agents + git commits + features y produce briefing estructurado (HEADLINE / HIGHLIGHTS / RIESGOS / PRÓXIMOS PASOS)
- Tono operativo honesto en español neutro, sin markdown pesado ni emojis (renderiza bien en WhatsApp + email)
- Costo: ~$0.005-0.01 por call con Sonnet 4.6
- Mock-mode placeholder cuando ANTHROPIC_API_KEY ausente

### Added — M15.1: daily SMTP briefing
- POST `/api/v1/executive-status/send-email` — genera briefing + envía vía SMTP
- HTML inline-styled (Gmail-friendly) + texto plano fallback
- `.github/workflows/executive-briefing.yml` — cron diario 08:00 UTC (= 03:00 Lima/Quito)
- Reusa SMTP_* envs de M6.2; falla suave si no están configurados
- Reusa AUTO_SCAN_* secrets ya existentes

### Added — M14.0: auto-tune + auto-analyze
- Param `auto_tune=true` (default) en GET `/trend-gaps` y `/niche-opportunities`
- Baja thresholds dinámicamente cuando hay <30 señales o <2 feedback → pagina nunca vacía durante ramp-up
- POST `/api/v1/admin/auto-analyze` — precalienta análisis LLM sobre top-N items
- `.github/workflows/auto-analyze.yml` — cron diario 05:00 UTC, cap 6 análisis/día (~$0.05/día)

### Added — M13.0 + M13.1: SecurityValidator + prompt injection defense
- `orchestrator/core/security_validator.py` — 13 heurísticos: typosquat (Levenshtein vs 35 trusted), homoglyph (Cyrillic/Greek), TLDs abusados, URL shorteners, executable downloads, label/href mismatch
- POST `/api/v1/security/validate-url` con verdicts SAFE/SUSPICIOUS/DANGEROUS/UNKNOWN
- `orchestrator/core/prompt_injection.py` — 27 patrones EN+ES en 4 severidades (CRITICAL/HIGH/MEDIUM/LOW)
- Penalty multiplicativo en SignalsStore.add: CRITICAL -50%, HIGH -20%, MEDIUM -10%
- `sanitize_for_llm()` reemplaza `<system>`, `[INST]`, `<|im_start|>` con placeholders
- POST `/api/v1/security/scan-text` para auditoría ad-hoc

### Added — M12.0-M12.3: OpportunityScout-inspired enhancements
- **M12.0** `orchestrator/core/pain_phrases.py` — boost score cuando hay frases de dolor real EN+ES (21 patterns)
- **M12.1** `orchestrator/core/solution_type.py` — clasificador heurístico en 8 buckets (app_movil, webapp_saas, sitio_web, automatizacion_agente, extension, marketplace, infoproducto_contenido, servicio)
- **M12.2** source_kind `reviews` — App Store low-star RSS (Notion, ChatGPT)
- **M12.3** source_kind `job_boards` — RemoteOK con filter "automate X"

### Added — M11.0-M11.4: defensas + IdeaValidator
- **M11.0** CardValidator (vision Claude) — filtra mockups Figma de apps reales
- **M11.1** `adversarial_callback` — degrade verdicts borderline (0.6-0.8 confidence)
- **M11.2** Watchdog Outcome DB + R2 backup diario (`db-backup.yml`)
- **M11.3** IdeaValidator red-team (Opus + web_search opcional) — MATAR/PIVOTAR/AVANZAR_CON_EVIDENCIA
- **M11.4** Wire IdeaValidator al workflow — short-circuit MATAR antes de ads
- **ADR-028** Selective adversarial callback (controlled, caller-driven)
- **ADR-029** No Governor anti-pattern al workflow level

### Added — M10.0: LinkFollowerAgent
- Mina evidence_urls de signals aprobadas para descubrir feeds RSS escondidos
- 3 patterns: github.com/X/Y → releases.atom, reddit.com/r/X → reddit kind, `<link rel=alternate>`
- POST `/api/v1/signals/{id}/discover-feeds`

### Added — M9.0-M9.5: autonomía del cazador
- **M9.0** Grok como 4ª voz del ensemble (Claude+GPT+Gemini+Grok) + 2-2 tie → forzado iterate
- **M9.1** UserSettings (i18n) + traducción al scrapear con Haiku
- **M9.2** source_kind `app_marketplace` (Lovable, Claude Creations, Adorable)
- **M9.3** canonical_hash dedup cross-source + times_seen
- **M9.4** SourceDiscoveryAgent (Gemini search → propone fuentes)
- **M9.5** source_quality scoring + smart_scan_queue (top 30% cada 6h, mid 40% cada 12h, bottom cada 48h)

### Tests
- 1078 verdes (de 741 al inicio de M9) · +337 tests · 0 regresiones
- Nuevos archivos: test_multi_llm_4way, test_user_settings, test_canonical_hash_dedup, test_source_quality, test_link_follower, test_card_validator, test_outcome_db_watchdog, test_adversarial_callback, test_app_marketplace, test_source_discovery, test_idea_validator, test_workflow_idea_validator_hook, test_pain_phrases, test_solution_type, test_reviews_and_jobs, test_security_validator, test_prompt_injection, test_auto_tune_and_analyze, test_executive_status

### Infra
- 5 crons GitHub Actions: auto-scan (cada 6h), auto-analyze (diario 05 UTC), db-backup (diario 04 UTC), executive-briefing (diario 08 UTC), weekly-digest (lunes 12 UTC)
- LLM providers integrados: 4 (Anthropic + OpenAI + Google + xAI)
- Producción Railway con persistent volume + Cloudflare R2 backup

---

## [M8.x] — Production deploy (2026-06-01)

### Added
- Backend live en Railway con `mode:live` + `persistent_storage:true`
- Dashboard live en Vercel con custom domain `dashboard.circles-ai.ai` + SSL Let's Encrypt
- Cloudflare DNS records para circles-ai.ai (CNAME a Vercel/Railway)
- `scripts/finish-deploy.sh` — automated Railway + Vercel deploy
- `scripts/preflight.sh` — 23 checks antes de deploy
- `docs/production-checklist.md` — guía paso-a-paso 20 items en 5 fases

### Fixed
- M9.4 Gemini drift: `response_mime_type=application/json` para forzar JSON
- M9.2 schema regex: agregado `app_marketplace` a SourceCreate
- Bug CORS env var name mismatch (EXTRA_ALLOWED_ORIGINS vs EXTRA_CORS_ORIGINS)

---

## [M7.x] — Operacional + polish (2026-05-30 → 31)

Estado del repo después de M7.x: **100 commits**, **775 tests**, **27 ADRs**,
**13 agentes active**, **56 endpoints**, **16 páginas dashboard**, **12 source kinds**.

### Added
- `scripts/start-local.sh` — launcher Linux/macOS/WSL con start/stop/restart/status (M7.3)
- `Makefile` con 14 targets (`make install`, `make test`, `make dev`, `make seed`, ...) (M7.4)
- `docs/openapi.json` — OpenAPI 3.1.0 spec auto-regenerable (63 endpoints, 112 schemas) (M7.5)
- `tests/test_no_orphan_endpoints.py` — anti-regression que verifica cada endpoint tenga test (M7.6)
- `GET /api/v1/admin/diagnose-deploy` + página `/admin/diagnose-deploy` — detector misconfig (M7.7)
- `dashboard/types/run.ts` — tipos canónicos `Verdict` y `Run` (M7.8)
- `docs/architecture.md` — 5 diagramas ASCII (sistema, Cazador, Workflow, agentes, crons) (M7.9)
- `CONTRIBUTING.md` — guía completa para colaboradores (M7.9)
- `scripts/bench.py` — performance benchmark P50/P95/mean (M7.10)
- 15 SQL indexes en signals/gate_runs/sessions/sources/leads/links_log (M7.10)
- `scripts/seed-example-sources.py` — 17 fuentes curadas idempotentes (M7.1)
- `scripts/seed-example-runs.py` — 3-8 runs del workflow (M7.2)
- Página `/admin/status` con introspección del sistema (M7.0)
- `scripts/health-check.sh` — 14 checks CLI contra backend (M7.0)
- `tests/test_e2e_smoke.py` — flujo completo del founder (M7.0)

### Removed
- `dashboard/lib/mockData.ts` — deuda técnica eliminada (M7.8)

### Performance
- Hot-paths < 100ms P95 con 1000 signals: list() todas 70ms, niche/gaps 63ms, stats 12ms

---

## [M6.x] — MultiAgentConsensus + Weekly Digest (2026-05-30)

### Added
- `multi_agent_consensus` agente (M6.0/M6.0b) — sintetiza N perspectives, R11-compliant, 30/30 cases v1.0.0 (ADR-027)
- Botón "🧠 Sintetizar con tu gut feeling" en `/cazar/oportunidades` (M6.0c)
- `GET/POST /api/v1/digest/{data,preview,text,send}` — weekly digest HTML/text/JSON (M6.1)
- Página `/digest` con copy-HTML + descargar + texto plano (M6.1)
- `.github/workflows/weekly-digest.yml` cron lunes 12 UTC (M6.2)
- SMTP send con skip silencioso si vars faltan (M6.2)
- Botón "📨 Enviar ahora" en `/digest` (M6.2)

---

## [M5.x] — 5 agentes experimentales → ACTIVE on-demand (2026-05-30)

### Added
- `trend_gap_analyzer` — first-mover cross-country (M5.0/M5.1, ADR-023/024) — **primer agente experimental → active demostrando el patrón**
- `niche_scout` — sub-niches en gigantes (M5.2/M5.8)
- `event_relevance_scorer` — go/skip/send para eventos (M5.3/M5.9)
- `sleeper_company_detector` — second-best con momentum (M5.4/M5.10)
- `product_arbitrage_evaluator` — margin estimate dropshipping (M5.5/M5.11)
- Los 5 agentes con 30/30 golden cases cada uno y v1.0.0 (ADR-025/026)
- UI integration: 4 botones nuevos en el dashboard (M5.6/M5.7)

### Notes
- 100% del audio del founder (29-may-2026) cubierto en código + tests + docs

---

## [M4.x] — Cazador funcional + features audio del founder (2026-05-28 → 30)

### Added
- M4.0 — Connected Accounts + check-platform detection (ADR-018)
- M4.1 — Preferences engine: embeddings + clustering + autonomy (ADR-019)
- M4.2 — Filtro `_is_corporate_description`
- M4.3 — Clasificación automática de content_type con badge visual
- M4.4 — Detección de idioma + traducción ES on-demand (ADR-020)
- M4.5/M4.6/M4.6b — CORS PUT/DELETE + filtros + bulk-delete por tipo/fuente (ADR-021)
- M4.7 — Barra de distribución por content_type
- M4.8 — Persistir filtros en localStorage
- M4.9 — Multi-select + bulk feedback / bulk delete por IDs
- M4.10 — Overview ejecutivo con datos REALES (replace mockData)
- M4.11 — Cross-country trend gap detector (ADR-022)
- M4.12 — SEC EDGAR fetcher Phase 1 (ADR-022)
- M4.13 — Eventos / Ferias source kind (ADR-022)
- M4.14 — Google Trends RSS por país
- M4.15 — Niche-en-gigante detector (ADR-022)

---

## [M3.x] — Cazador autónomo (2026-05-27 → 28)

### Added
- 9 source kinds: rss, hn, reddit, github_trending, product_hunt, youtube, bluesky, telegram, url (R28/ADR-011, R29/ADR-012)
- File upload + links bitácora (ADR-013)
- Auto-promotion + IdeaAnalyzer (M3.5)
- 30 golden cases + ADR-015
- Stats sidebar + CSV export (M3.7)
- LLM-judge + webhooks Slack (M3.8)
- Server-side search LIKE (M3.9, ADR-016)
- Auth en review endpoints (M3.12)
- Enrich con og:tags + ADR-017 security headers (M3.17)
- SPA fallback detection (M3.18)
- `idea_summary` + `country_focus` en SignalAnalysis (M3.11)

---

## [M2.x] — Deploy real + persistencia (2026-05-26)

### Added
- SQLite persistence + Dockerfile + Railway deploy config (M2)
- Leads viewer endpoints + dashboard page
- Closed-beta auth + real-pool demo + dashboard auth guard
- `/cazar` — end-to-end idea_hunter UI con live pipeline

---

## [M1.x] — Base del EvidenceGateWorkflow (2026-05-25)

### Added
- 5 agentes activos: idea_hunter, idea_maturer, market_validator, landing_generator, gate_decider
- LLM-judge harness con 82% accuracy
- Multi-LLM ensemble Claude + GPT-4o-mini + Gemini (M1.5)
- Human-in-the-loop on ensemble disagreement (R22)
- Dynamic factory page `/f/[slug]` + LeadForm
- Cross-LLM fact-check (M1.6)
- Layered anti-bot defenses (R26 / ADR-009)
- Langfuse tracing + R13-R17 + canonical goal (OBS-04/05/06)

---

## [M0] — Bootstrap (2026-05-24)

### Added
- Refactor: 35 → 5 agentes per Reganti review (OBS-01)
- Eval harness con 150 golden cases (OBS-02)
- FastAPI backend + Next.js 15 landing en `circles-ai.ai`
- GitHub Actions eval suite

---

## Convenciones

- **feat(MX.Y):** nueva feature
- **fix(MX.Y):** bug fix
- **docs(...):** documentación
- **chore(...):** maintenance
- **perf(MX.Y):** performance improvement
- **test(MX.Y):** tests
- **refactor(...):** refactor sin cambio funcional
- **ci(...):** CI/CD
- **ux(MX.Y):** ux improvement

Cada commit tiene su body con tests, regresiones, y `Co-Authored-By` cuando aplica.
