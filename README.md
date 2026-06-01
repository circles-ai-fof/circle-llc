# Circle LLC — Factory of Factories (FoF)

> **Plataforma meta-sistémica que valida ideas de negocio en modo *evidence-gate***: una landing + anuncios + métricas reales en 14 días antes de construir una sola línea de producto.

🌐 **Live:** [circles-ai.ai](https://circles-ai.ai)
🛠️ **Stack:** Python (FastAPI) + Next.js 15 + Anthropic Claude + OpenAI + Gemini
📊 **Status:** 741 tests verdes · 27 ADRs · 13 agentes · 54 endpoints · 12 source kinds

---

## ¿Qué problema resuelve?

Construir un producto cuesta $50k+ y 3-6 meses. Si la idea no tenía demanda real, perdiste todo.

FoF reduce ese ciclo a **$0.06 + 14 días**:

```
                               $0.06           $200-500            $50k+
                                  │                │                  │
Idea ──→ Cazador detecta ──→ Workflow ──→ Landing + ads + ──→ Construir
         señales reales      genera plan     métricas reales       producto
              │                    │                │                  │
         señales de 12        agentes Claude    pass/kill/        sólo si
         fuentes externas      en ensemble       iterate          PASS aquí
```

Cada idea atraviesa un **EvidenceGateWorkflow** de 4 pasos con 7 agentes activos. Si el ensemble (Claude + GPT + Gemini) no confluye en PASS, se descarta.

## Los 13 agentes

| Familia | Agente | Rol | Status |
|---|---|---|---|
| **Workflow** | `idea_hunter` | Genera ideas concretas desde un topic | active |
| | `idea_enricher` | Refina vaguedad + web_search + fact-check | active |
| | `idea_maturer` | Define ICP + value prop + riesgos | active |
| | `market_validator` | Diseña test de mercado (presupuesto, días, métricas) | active |
| | `landing_generator` | Genera landing copy (headline, CTAs, value props) | active |
| | `gate_decider` | Veredicto PASS/KILL/ITERATE — ensemble Claude+GPT+Gemini | active |
| | `source_scanner` | Destila signals desde fuentes externas | active |
| **On-demand** | `trend_gap_analyzer` | First-mover gaps cross-country (M5.0/M5.1) | ✅ v1.0.0 |
| | `niche_scout` | Plan de entrada a sub-niches en mercados gigantes (M5.2/M5.8) | ✅ v1.0.0 |
| | `event_relevance_scorer` | go/skip/send_someone_else para ferias y congresos (M5.3/M5.9) | ✅ v1.0.0 |
| | `sleeper_company_detector` | "Second-best with momentum" desde filings SEC EDGAR (M5.4/M5.10) | ✅ v1.0.0 |
| | `product_arbitrage_evaluator` | Margin estimate para trending searches (M5.5/M5.11) | ✅ v1.0.0 |
| | `multi_agent_consensus` | Sintetiza N perspectives sobre decisiones high-stakes (M6.0/M6.0b) | ✅ v1.0.0 |

20+ agentes adicionales están archivados en `orchestrator/agents/_deferred/` esperando criterios de activación (≥3 fábricas en prod + 30 golden cases + falla demostrada del workflow actual).

## Los 12 source kinds del Cazador

| Kind | Auth | Implementación | Sprint |
|---|---|---|---|
| `url` | none | fetch directo de un artículo único | M2 |
| `rss` | none | feed RSS estándar | M2 |
| `hn` | none | Firebase API de Hacker News | M2 |
| `reddit` | none | endpoints `.json` públicos | M2 |
| `github_trending` | none | scrape de github.com/trending | M2 |
| `product_hunt` | none | RSS de Product Hunt | M2 |
| `youtube` | none | RSS per-channel | M3.1 |
| `bluesky` | none | XRPC público | M3.1 |
| `telegram` | none | t.me/s/ web preview | M3.1 |
| `events` | none | RSS de Lu.ma / Eventbrite / conferencias verticales | M4.13 |
| `sec_edgar` | none | SEC EDGAR `/submissions/CIKxxx.json` (User-Agent compliant) | M4.12 |
| `google_trends` | none | RSS oficial de Google Trends por país | M4.14 |

## Quick start

### 1. Clone + dependencies

```bash
git clone https://github.com/circles-ai-fof/circle-llc.git
cd circle-llc

# Backend (Python 3.12+)
pip install -r orchestrator/requirements.txt

# Dashboard (Node 20+)
cd dashboard && npm install && cd ..
```

### 2. Env config

```bash
cp orchestrator/.env.example .env
# Editar .env con tus API keys (Anthropic, OpenAI, Google)
# Mínimo necesario para empezar: ANTHROPIC_API_KEY + ALLOWED_EMAILS
```

Sin `ANTHROPIC_API_KEY` el sistema arranca en **mock mode** — todos los agentes devuelven placeholders "[Demo]" en español. Útil para CI y dev sin gastar tokens.

### 3. Arrancar local

```powershell
# Windows PowerShell
./start-local.ps1
```

```bash
# Linux/macOS (manual)
python -m uvicorn orchestrator.api:app --reload --port 8002 &
cd dashboard && npm run dev   # → :3001
```

Abre [http://localhost:3001/login](http://localhost:3001/login), meté tu email del `ALLOWED_EMAILS`, y estás dentro.

### 4. Tests

```bash
pytest tests/ -v   # 751 tests verdes, ~40s
```

### 5. Bootstrap con fuentes de ejemplo (opcional pero recomendado)

Si querés ver el dashboard con actividad real desde minuto 1 sin esperar
a configurar fuentes manualmente:

```bash
# Genera un token
TOKEN=$(curl -s -X POST http://localhost:8002/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"YOUR@EMAIL"}' | jq -r .token)

# Inserta 17 fuentes curadas (RSS, HN, Reddit, GitHub Trending, Product Hunt,
# YouTube, Bluesky, Telegram, Lu.ma events, 2 CIKs SEC EDGAR, 4 países Google Trends)
BEARER_TOKEN=$TOKEN python scripts/seed-example-sources.py

# Dispara primer escaneo
curl -X POST http://localhost:8002/api/v1/sources/scan \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}'
```

El script es **idempotente** — re-ejecutarlo no duplica fuentes. Soporta
`--dry-run` para preview sin tocar nada.

Adicionalmente, para poblar `/fabricas` y la home con runs ejecutados:

```bash
# Ejecuta 3 runs reales del workflow (cuesta ~$0.18 en LLM si live mode)
BEARER_TOKEN=$TOKEN python scripts/seed-example-runs.py

# O preview de los topics sin ejecutar
python scripts/seed-example-runs.py --dry-run --count 5
```

Cada run produce un `pass`/`kill`/`iterate` verdict con el `EvidenceGateWorkflow`
(7 agentes) y queda persistido para mostrar en el dashboard.

## Arquitectura

```
circle-llc/
├── orchestrator/     # Backend Python (FastAPI)
│   ├── core/         # storage, base_agent, language, content_type, digest, ...
│   ├── workflows/    # EvidenceGateWorkflow (4 pasos lineales)
│   ├── agents/       # 7 workflow + 6 on-demand + 20 deferred
│   ├── decisions/    # 27 ADRs documentando cada decisión arquitectural
│   ├── schemas/      # Pydantic models para todos los endpoints
│   └── api.py        # 54 endpoints FastAPI
├── dashboard/        # Next.js 15 — admin closed-beta
│   ├── app/          # 14 páginas (cazar, oportunidades, nichos, digest, ...)
│   └── components/   # Sidebar, StatsBar, RunsTable, VerdictBadge, ...
├── outcome-db/       # PostgreSQL + pgvector (INACTIVO hasta M5 multi-tenant)
├── landing/          # Next.js — circles-ai.ai (público, live)
├── scripts/          # Pool generation + seed de fuentes
├── tests/            # 741 tests verdes (pytest)
└── .github/workflows/
    ├── eval-suite.yml          # CI tests en push
    ├── auto-scan.yml           # Cron cada 6h escanea fuentes (skip si secrets falt)
    └── weekly-digest.yml       # Cron lunes 12 UTC manda digest (skip si SMTP falt)
```

## Reglas (rulebook)

El proyecto sigue **29 reglas** documentadas en `orchestrator/rulebook.md`. Las críticas:

- **R06:** `mock_mode=True` obligatorio en CI
- **R07:** schema validation en outputs de agentes (Pydantic)
- **R08:** prompt caching en todos los system prompts
- **R11:** NO crear un Governor que decida dinámicamente qué agente llamar
- **R12:** ≥30 golden cases antes de activar agente nuevo
- **R28/R29:** scope explícito por agente, sin overlap (verificado en CI)

Filosofía Reganti (AI Builder's Handbook 2026):
> *"Stay at the simplest level that handles 90% of your cases"* (Cap 10 §10.3)
> *"Build multi-agent as exception, not default"* (Cap 15 §15.1)

## Documentos clave

| Archivo | Qué es |
|---|---|
| `DEPLOY.md` | Guía deploy general (Railway + Vercel + cron secrets) |
| `docs/production-checklist.md` | Checklist deploy paso a paso con 20 items + troubleshooting |
| `scripts/preflight.sh` | Pre-deploy verification (tests + TS + git + secrets scan) |
| `CLAUDE.md` | Contexto completo para Claude Code (instrucciones del proyecto) |
| `orchestrator/rulebook.md` | Las 29 reglas del rulebook con su rationale |
| `orchestrator/agents/SCOPES.md` | Scope exclusivo de cada agente (anti-overlap) |
| `orchestrator/decisions/ADR-XXX.md` | 27 ADRs documentando cada decisión grande |
| `docs/architecture.md` | Diagrama del sistema completo con flujos del Cazador y EvidenceGateWorkflow |
| `docs/openapi.json` | Spec OpenAPI 3.1.0 (63 endpoints, 112 schemas) auto-regenerable con `make openapi` |
| `CHANGELOG.md` | Historial de milestones desde M0 hasta M7.x |
| `CONTRIBUTING.md` | Guía para colaboradores (setup + reglas + patrón de agentes) |
| `LICENSE` | Proprietary — Circle LLC. Docs bajo CC BY 4.0 |

## Roadmap

Los sprints están organizados como `MX.Y` donde `X` es el milestone y `Y` el iteración:

- **M1-M2** ✅ EvidenceGateWorkflow base + 7 agentes + landing live
- **M3** ✅ Cazador autónomo + 9 source kinds + content type classifier + language detector
- **M4** ✅ Cross-country gaps + niche detector + SEC EDGAR + Google Trends + filtros y bulk-actions
- **M5** ✅ 5 agentes on-demand activos + roadmap experimental → active
- **M6** ✅ Weekly digest + SMTP + MultiAgentConsensus
- **M7** (futuro) Deploy real Railway/Vercel + multi-tenant Postgres + 20 deferred agents activados

## Citas del founder mapeadas a código

El audio del founder del 29-may-2026 articuló 6 oportunidades estratégicas. Las 6 están materializadas en agentes:

| Cita | Agente | Endpoint |
|---|---|---|
| *"first-mover ahí, posibilidades de poderla reventar"* | `trend_gap_analyzer` | `POST /api/v1/trend-gaps/analyze` |
| *"recoger las migajas de los gigantes"* | `niche_scout` | `POST /api/v1/niche-opportunities/analyze` |
| *"en qué ferias hay que estar"* | `event_relevance_scorer` | `POST /api/v1/events/score` |
| *"segundo de a bordo... información pública financiera"* | `sleeper_company_detector` | `POST /api/v1/sleeper-companies/detect` |
| *"86 centavos / 19.99"* | `product_arbitrage_evaluator` | `POST /api/v1/arbitrage/evaluate` |
| *"agentes razonando entre ellos"* | `multi_agent_consensus` | `POST /api/v1/consensus/analyze` |

Detalles en `orchestrator/decisions/ADR-022.md` (roadmap derivado del audio) + ADR-023 a ADR-027 (sprints individuales).

## Contribuir

Closed-beta — el `ALLOWED_EMAILS` del `.env` controla quién puede loguear al dashboard. Para añadir colaboradores:

1. Add the email to `ALLOWED_EMAILS` (CSV) en el `.env` del backend deployed
2. Reiniciar backend para recargar la config
3. Compartir [https://dashboard.circles-ai.ai/login](https://dashboard.circles-ai.ai/login)

Para colaborar con código: ver **[CONTRIBUTING.md](CONTRIBUTING.md)** —
incluye el patrón paso a paso para añadir agentes y source kinds nuevos.

## Licencia

Propietario — Circle LLC (Wyoming USA). Ver [`LICENSE`](LICENSE) para los términos completos:

- **Código:** All Rights Reserved, closed-beta para colaboradores en `ALLOWED_EMAILS`
- **Documentación** (`README.md`, `docs/*`, `CONTRIBUTING.md`, ADRs): CC BY 4.0
- Permitido: fork + lectura + research educacional
- Prohibido: re-distribución comercial sin autorización

Contacto licencias / commercial: `circles.fof.ai@gmail.com`

---

**Autor:** Cristian Molina — Circle LLC | Mayo 2026
**Refactor guiado por:** Aishwarya Naresh Reganti (LevelUp Labs) — *AI Builder's Handbook 2026*
