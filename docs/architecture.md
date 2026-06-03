# Arquitectura — Circle LLC Factory of Factories

> **Última actualización:** 2026-06-03 (M15.1 deployado)
> **Estado:** producción live, 1078 tests verdes, 18 agentes, 15 source kinds

Documento técnico canónico de la arquitectura. Para el resumen estratégico
de 1 página ver [`../ONE-PAGER.md`](../ONE-PAGER.md). Para historial de
cambios ver [`../CHANGELOG.md`](../CHANGELOG.md).

---

## 1. Visión sistémica

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CAZADOR AUTÓNOMO                              │
│                                                                       │
│  15 source_kinds → fetch → security_validator (M13) →                │
│    prompt_injection scan (M13.1) → SignalsStore.add →                │
│      pain_boost (M12.0) + solution_type tag (M12.1) +                │
│        canonical_hash dedup (M9.3) → cluster (M4.1)                  │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  EVIDENCE-GATE WORKFLOW (LINEAR)                      │
│                                                                       │
│  idea_hunter → idea_enricher → idea_maturer                          │
│       │                                                               │
│       └──→ IdeaValidator (M11.3) [opt-in]                            │
│            │                                                          │
│            ├─ MATAR  → short-circuit, $0 ads gastados (M11.4)        │
│            ├─ PIVOTAR → return precondition                          │
│            └─ AVANZAR ↓                                              │
│                                                                       │
│       market_validator → landing_generator → gate_decider            │
│                                                          │            │
│                                                          ▼            │
│                              ENSEMBLE 4-LLM (M9.0)                    │
│                          Claude + GPT + Gemini + Grok                 │
│                          (3-of-4 majority, 2-2 → iterate)             │
│                                                          │            │
│                                                          ▼            │
│                          adversarial_callback (M11.1)                 │
│                          conf ∈ [0.6, 0.8] → Grok devil's advocate    │
│                          ≥2 strong objections → degrade to iterate    │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        ANÁLISIS DERIVADOS                             │
│                                                                       │
│  TrendGapAnalyzer (M5.0) — first-mover gaps cross-country            │
│  NicheScout (M5.2)       — sub-niches dentro de gigantes             │
│  EventScorer (M5.3)      — ir o no a una feria                       │
│  SleeperDetector (M5.4)  — ideas dormidas que despiertan             │
│  ArbitrageEval (M5.5)    — diferencia de precio entre mercados       │
│  MultiAgentConsensus (M6.0) — voting cross-agente                    │
│  SourceDiscoveryAgent (M9.4) — propone fuentes via Gemini search     │
│  LinkFollowerAgent (M10.0)   — extrae feeds de evidence_urls         │
│  CardValidator (M11.0)       — vision filtra mockups                 │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      CANAL DE COMUNICACIÓN                            │
│                                                                       │
│  executive-status agent (M15.0) ← cerebro común                      │
│       │                                                               │
│       ├─ Dashboard (web)         — circles-ai.ai                     │
│       ├─ SMTP daily briefing     — M15.1 (08 UTC cron)               │
│       ├─ WhatsApp Gateway        — M16+ (esperando Twilio/Meta)      │
│       └─ Weekly Digest           — M6.2 (lunes 12 UTC)               │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Capa de datos · 15 source_kinds

| Kind | Endpoint / método | Quality | Notas |
|---|---|---|---|
| `url` | httpx HTML scrape | medio | Página individual |
| `rss` | feedparser stdlib | alto | Blogs / news / atom |
| `hn` | Firebase API JSON | alto | Top + Show HN |
| `reddit` | `.json` endpoint | alto | Subreddit posts |
| `github_trending` | HTML scrape CSS | medio | Trending repos |
| `product_hunt` | RSS oficial | alto | Daily launches |
| `youtube` | per-channel RSS | medio | Videos del canal |
| `bluesky` | XRPC API | medio | Búsqueda |
| `telegram` | `t.me/s/<ch>` scrape | medio | Canal público |
| `events` | RSS (Lu.ma / Eventbrite) | alto | Ferias / congresos |
| `sec_edgar` | RSS 10-K/Q (SEC.gov) | alto | Filings públicas US |
| `google_trends` | RSS por país (22 países) | alto | Trending searches |
| **`app_marketplace`** (M9.2) | HTML scrape genérico | medio | Lovable, Claude Creations, Adorable |
| **`reviews`** (M12.2) | App Store JSON RSS | **muy alto** | 1-2★ = pain del cliente |
| **`job_boards`** (M12.3) | RemoteOK JSON API | **muy alto** | "automate X" = budget + pain |

**No incluidos (deferred):**
- ~~`x_twitter`~~ — $100/mes API
- ~~`linkedin`~~ — partner-only
- ~~`instagram`~~ — no valor B2B

---

## 3. 18 agentes activos

### Workflow (7)

| Agente | Step | Modelo | Costo |
|---|---|---|---|
| `idea_hunter` | 1 | Claude Sonnet | $0.005 |
| `idea_enricher` | 1.5 | Claude + Gemini fact-check | $0.008 |
| `idea_maturer` | 2 | Claude Sonnet | $0.005 |
| `market_validator` | 3 | Claude Sonnet | $0.005 |
| `landing_generator` | 4a | Claude Sonnet | $0.008 |
| `gate_decider` | 4b | Ensemble 4-LLM | $0.025-0.045 |
| `source_scanner` | n/a | Claude Haiku | $0.001-0.003 |

### Defensas + filtros (3)

| Agente | Cuándo fira | Costo |
|---|---|---|
| **IdeaValidator** (M11.3) | Step 2.5, pre-test | $0.06 (Opus) |
| **adversarial_callback** (M11.1) | Post-gate confidence borderline | $0.005 (Grok) |
| **CardValidator** (M11.0) | Por imagen de marketplace card | $0.002 (Claude Vision) |

### Cazador autónomo (3)

| Agente | Función | Costo |
|---|---|---|
| **SourceDiscoveryAgent** (M9.4) | Propone fuentes desde clusters aprobados | $0.005 (Gemini search) |
| **LinkFollowerAgent** (M10.0) | Extrae RSS escondidos de evidence_urls | $0 (heurístico) |
| **executive-status** (M15.0) | Briefing ejecutivo | $0.008 (Sonnet) |

### Análisis on-demand (5)

| Agente | Función | Status |
|---|---|---|
| TrendGapAnalyzer (M5.0) | First-mover cross-country | ACTIVE v1.0.0 |
| NicheScout (M5.2) | Plan de entrada al sub-niche | ACTIVE v1.0.0 |
| EventScorer (M5.3) | ¿ir o no a la feria? | ACTIVE v1.0.0 |
| SleeperDetector (M5.4) | Ideas dormidas que despiertan | ACTIVE v1.0.0 |
| ArbitrageEval (M5.5) | Arbitraje cross-mercado | ACTIVE v1.0.0 |
| MultiAgentConsensus (M6.0) | Voting cross-agente | ACTIVE v1.0.0 |

---

## 4. Ensemble 4-LLM (M9.0) — el corazón de gate_decider

```
                  ┌─────────┐
   prompt    ────▶│ Claude  │ ──▶ vote_1
                  └─────────┘
                  ┌─────────┐
                  │ GPT     │ ──▶ vote_2     ┌────────────┐
   (mismo) ───▶  │ 4o-mini │              ──▶│  TALLY     │──▶ verdict
                  └─────────┘                 │            │     +
                  ┌─────────┐                 │ 3-of-4 maj │   confidence
                  │ Gemini  │ ──▶ vote_3      │ 2-2 = iter │
   (mismo) ───▶  │  Flash  │                 │            │
                  └─────────┘                 └────────────┘
                  ┌─────────┐                       ▲
                  │  Grok   │ ──▶ vote_4            │
   (mismo) ───▶  │ 3-mini  │ ──────────────────────┘
                  └─────────┘
```

**Por qué Grok como 4ª voz:** Su entrenamiento sobre X catches hype
patterns que Claude+GPT+Gemini (RLHF-similares) tienden a perderse.
Empíricamente el mejor "abogado del diablo" del set.

**Por qué 2-2 → ITERATE:** `Counter.most_common` devuelve insertion-order
en empates → winner arbitrario. M9.0 explícitamente fuerza `iterate`
cuando hay tie pass/kill — pedimos más evidencia en vez de adivinar.

**Confidence cap por agreement:**
- 4/4 unánime → confidence × 1.0
- 3/4 majority → confidence × 0.75
- 2-2 tie → iterate forzado, confidence × 0.5

Después del ensemble, si `final_confidence ∈ [0.6, 0.8]` se dispara
`adversarial_callback` (M11.1, ADR-028) que invoca Grok como red-team
buscando objeciones específicas. ≥2 strong objections → degrade a iterate.

---

## 5. Memoria + autonomía (M4.1 + M9.4)

```
Signal ─→ embedding (sentence-transformers 384-dim)
   │                                  │
   ▼                                  ▼
   feedback (up/down)        signal_embeddings table
                                      │
                                      ▼
                              HDBSCAN clustering
                                      │
                                      ▼
                            score_against_feedback()
                                      │
                                      ▼
                      suggest_sources_from_clusters()
                                      │
                                      ▼
                            SourceDiscoveryAgent (M9.4)
                                      │
                                      ▼
                            Proposals → /cazar/fuentes
                                      │
                                      ▼
                            Founder approves → SourcesStore.add
```

**Autonomy levels (`autonomy_store`):**
- `manual` — founder agrega fuentes manualmente, sin sugerencias
- `assisted` — sistema sugiere keywords; founder aprueba/rechaza
- `autonomous_with_approval` — sistema PROPONE fuentes automáticamente;
  pending approval antes de scanear

**Safety brake:** `user_settings.max_new_sources_per_week` (default 5)
limita cuántas fuentes el agente puede proponer/semana.

---

## 6. Defensas activas (M13)

### URL Security (M13.0)

13 heurísticos sin red:

| Check | Severidad |
|---|---|
| Typosquat (Levenshtein 1-2 vs 35 trusted domains) | strong |
| Homoglyph (Cyrillic а, Greek ο) | strong |
| URL shortener (oculta destino) | strong |
| Executable download (.exe/.apk/.msi) | strong |
| Userinfo @ spoofing | strong |
| Non-http(s) scheme | strong |
| Plain http:// | weak |
| Abused TLD (.tk/.ml/.cf/.gq) | weak |
| Punycode (IDN) | weak |
| Deep subdomain (≥5 labels) | weak |
| Excessive hyphens (≥4) | weak |
| Label/href mismatch | strong |
| Malformed URL | strong |

**Verdict tiers:** SAFE / SUSPICIOUS / DANGEROUS / UNKNOWN.
Bias seguro: cualquier strong signal → DANGEROUS; cualquier duda →
SUSPICIOUS o UNKNOWN, nunca SAFE.

### Prompt Injection (M13.1)

27 patterns × 4 severidades en EN+ES:

| Severidad | Penalty | Ejemplos |
|---|---|---|
| CRITICAL | -50% multiplicativo | "ignore previous instructions", "olvida lo anterior" |
| HIGH | -20% | `<system>`, `[INST]`, "you are now", "actúa como" |
| MEDIUM | -10% | "send all data to", "reveal system prompt" |
| LOW | -0% (audit only) | imperative chains in content |

Score floor `0.05` — nunca se anula del todo (la señal queda visible
para audit, no silenciada).

`sanitize_for_llm()` reemplaza markers estructurales (`<system>`,
`[INST]`, `<|im_start|>`) con placeholders `[REDACTED:reason]` antes
de pasar a LLM downstream.

---

## 7. Stack tecnológico

| Capa | Tecnología | Versión |
|---|---|---|
| Backend | Python + FastAPI + Pydantic v2 | 3.12+ |
| Frontend | Next.js + TypeScript + Tailwind | 15 |
| Storage | SQLite (M2) → Postgres + pgvector (M17+) | Railway volume |
| Tests | pytest | 9.0+ |
| LLMs | Anthropic SDK + OpenAI SDK + google-genai + xAI (OpenAI-compat) | latest |
| Observability | Langfuse (agentes) + Sentry (infra) | self-hosted |
| Backup | Cloudflare R2 (free tier 10GB) | s3-compatible |
| CI/CD | GitHub Actions | 5 crons activos |
| Deploy | Railway (backend) + Vercel (frontend) | live |
| DNS | Cloudflare | circles-ai.ai zone |

---

## 8. Crons GitHub Actions

| Workflow | Frecuencia | Qué hace |
|---|---|---|
| `auto-scan.yml` | cada 6h | Escanea las 33 fuentes → SignalsStore.add |
| `auto-analyze.yml` | diario 05 UTC | Precalienta análisis LLM sobre top trend-gaps + niches (M14.0) |
| `db-backup.yml` | diario 04 UTC | Sube SQLite a Cloudflare R2 + GH artifact fallback |
| `executive-briefing.yml` | diario 08 UTC | executive-status → SMTP al CEO |
| `weekly-digest.yml` | lunes 12 UTC | Resumen semanal HTML+texto al digest list |

---

## 9. ADRs (decisiones arquitectónicas)

29 ADRs codificados en `orchestrator/decisions/ADR-001.md` → `ADR-029.md`.

Los más críticos para entender la filosofía:

- **ADR-019** — Preferences engine (embeddings + clustering)
- **ADR-022** — Cross-country trend gap detector
- **ADR-023/024** — TrendGapAnalyzer experimental → ACTIVE
- **ADR-025/026** — 4 agentes experimentales → ACTIVE
- **ADR-027** — MultiAgentConsensus (13º agente)
- **ADR-028** — Selective adversarial callback (la ÚNICA excepción al "no Governor")
- **ADR-029** — Why no dynamic tool-use Governor at workflow level

---

## 10. Costos operativos (estimado)

| Item | Costo/mes |
|---|---|
| Railway (backend Hobby + volume) | $5 |
| Vercel (frontend free tier) | $0 |
| Cloudflare (DNS + R2 backups) | $0 |
| LLMs — workflow runs (100/mes × $0.06) | $6 |
| LLMs — executive briefing diario | $0.24 |
| LLMs — auto-analyze diario (6 calls × $0.008) | $1.50 |
| LLMs — adversarial callback (~30% de runs × $0.005) | $0.15 |
| LLMs — IdeaValidator si enabled (Opus, $0.06/run × 50%) | $1.50 |
| **TOTAL estimado** | **~$15/mes** |

---

## 11. Documentos de referencia (NO modificar)

- `D:/CM/IA_2026/Fabrica de Fabricas/Circle_LLC_FoF_Revision_Aishwarya_Reganti.html`
- `D:/CM/IA_2026/Fabrica de Fabricas/v2.1/`

---

## 12. Para nuevos contribuidores

1. Leé este documento
2. Después el [`../ONE-PAGER.md`](../ONE-PAGER.md) para entender el por qué
3. Después el [`../README.md`](../README.md) para setup local
4. Después [`../CONTRIBUTING.md`](../CONTRIBUTING.md) para convenciones
5. Antes de tocar el workflow lineal, leé **ADR-029** (No Governor) y
   entendé por qué la simplicidad es la decisión arquitectónica explícita

---

*Documento generado y mantenido por Cristian Molina. Última actualización: M15.1 deployado a producción.*
