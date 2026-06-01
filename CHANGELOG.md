# Changelog — Circle LLC FoF

Todas las notables changes del proyecto, organizadas por milestone (`Mx`).
Formato basado en [Keep a Changelog](https://keepachangelog.com/).

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
