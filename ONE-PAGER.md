# Circle LLC — Factory of Factories

**Una sola página · Última actualización 2026-06-03 · circles-ai.ai**

---

## El problema

Construir un producto cuesta **$50.000 + 3–6 meses**.
Si la idea no tenía demanda real, perdiste todo.

El 90% de los founders LATAM construye primero y valida después.
Resultado: cementerio de buenas ideas mal calibradas.

---

## Lo que Circle LLC hace distinto

Reemplaza "construir primero, validar después" por **evidence-gate**:

> Una landing + anuncios reales en **14 días** entregan datos duros
> (CTR, conversión, $/conv) **antes** de escribir una línea de código.

```
                        $0.06       $200–500       $50k+
                          │            │               │
Idea → Cazador → Workflow → Landing + ads → CONSTRUIR
                       │
                       └─→ MATAR / PIVOTAR (87% de las ideas)
                           Costo total: $0.06 + 1 semana
```

**El 87% de las ideas mueren antes del primer dólar de ads.**
El 13% restante llega a Sprint M1 con evidencia real.

---

## Cómo funciona — arquitectura de 4 capas

### 1. Cazador autónomo (descubre ideas)

15 fuentes distintas escaneadas cada 6h sin intervención humana:

- `rss · hn · reddit · github_trending · product_hunt · youtube`
- `bluesky · telegram · events · sec_edgar · google_trends · url`
- `app_marketplace` (Lovable, Claude Creations, Adorable)
- `reviews` (App Store 1–2★ — pain directo del cliente)
- `job_boards` (RemoteOK — "automate X" = pain + budget existente)

**Auto-prioriza** las fuentes que históricamente dan ideas que pasan
el gate (`quality_score` calculado por hit_rate). Las que generan ruido
caen al fondo de la cola.

### 2. Workflow Evidence-Gate (valida cada idea)

8 agentes IA especializados en secuencia lineal — **sin Governor**:

```
idea_hunter      → genera ideas (Claude)
idea_enricher    → enriquece + fact-check (Claude + Gemini)
idea_maturer     → define ICP + value prop (Claude)
IdeaValidator    → RED-TEAM kill antes de ads (Opus, $0.06)  ← M11.3
market_validator → diseña test de mercado (Claude)
landing_generator→ escribe copy (Claude)
gate_decider     → vota PASS/KILL/ITERATE con 4 LLMs (M9.0)
adversarial_cb   → degrade verdicts borderline (M11.1)
```

### 3. Ensemble multi-LLM en decisiones críticas

`gate_decider` no usa un LLM — usa **4 modelos en paralelo**:

- **Claude Sonnet 4.6** (rigor lens)
- **GPT-4o-mini** (general knowledge)
- **Gemini Flash** (web grounding)
- **Grok-3-mini** (contrarian / X pulse)

Vota majoría 3-of-4. Empate 2-2 → **forzado ITERATE** (nunca arbitrario).
Después de votar, si confidence ∈ [0.6, 0.8], `adversarial_callback`
invoca a Grok como devil's advocate. Si encuentra ≥2 objeciones fuertes,
**degrada el verdict** a iterate.

### 4. Defensas activas (M13)

- **SecurityValidator** — typosquats, homoglyphs Unicode, TLDs free
  abusados, executable downloads, URL shorteners, label/href mismatch
- **Prompt-injection scanner** — 27 patrones EN+ES en contenido scraped
  ("ignore previous instructions", `<system>`, role-changes); rebaja
  score multiplicativamente, nunca silencia

---

## Estado del sistema · 2026-06-03

| Métrica | Valor |
|---|---|
| **Tests verdes** | **1078 / 1078** (0 regresiones) |
| Agentes IA activos | **18** (7 workflow + 8 cazador + 3 análisis) |
| Source kinds | **15** |
| Fuentes activas en producción | **33** |
| Endpoints API | **60+** |
| Páginas dashboard | **18** |
| ADRs (decisiones formalizadas) | **29** |
| LLM providers integrados | **4** (Anthropic + OpenAI + Google + xAI) |
| Crons GitHub Actions | **5** (scan + analyze + digest + backup + briefing) |
| Sprints completados | **M0 → M15.1** |
| Costo operativo mensual estimado | **~$13** (Railway + Vercel + LLMs) |

---

## URLs de producción

- 🌐 **Landing**: https://circles-ai.ai
- 📊 **Dashboard**: https://dashboard.circles-ai.ai
- ⚙️ **API**: https://circle-llc-backend-production.up.railway.app
- 📚 **Docs**: https://circle-llc-backend-production.up.railway.app/docs
- 💻 **Repo**: https://github.com/circles-ai-fof/circle-llc

---

## Por qué esta arquitectura es defensible

### 1. Linear workflow, no Governor (ADR-029)
Frameworks tipo CrewAI / AutoGen permiten "agentes que conversan
libremente". Cosa que produce 3 problemas conocidos: costo
imprevisible, debuggability cero, deadlock por loops. Circle LLC
elige linear + callbacks específicos (ADR-028). Cada run cuesta ≤6
llamadas LLM. Reproducible. Auditable.

### 2. Evidence-gate antes del producto (R29)
Regla operativa dura: **nunca construir hasta que landing + ads
muestren CTR + conversión real**. Esto no es un consejo — está
codificado en `gate_decider` y `IdeaValidator`. El sistema literal
no te deja avanzar sin evidencia.

### 3. Memoria con feedback loop (M4.1)
Cada señal embebida (384-dim sentence-transformers) + clusterada
(HDBSCAN). Cada 👍/👎 del founder recalibra qué cluster boostear.
Después de 30 días el sistema sabe qué te interesa sin que se lo
digas explícitamente.

### 4. Autonomía con safety brakes
`autonomy_level` graduable: `manual | assisted | autonomous_with_approval`.
SourceDiscoveryAgent (M9.4) y LinkFollowerAgent (M10.0) proponen
fuentes nuevas — pero el founder aprueba antes de scanear. Cap de 5
fuentes nuevas/semana via `max_new_sources_per_week`.

### 5. Producción real, no demo
Backend live en Railway con persistent volume. Dashboard live en
Vercel con cert SSL automático en dominio custom. SQLite respaldado
diario a Cloudflare R2 (free tier 10GB). Cron diario de auto-scan +
auto-analyze. Briefing ejecutivo diario al CEO por email (M15.1).

---

## Roadmap (lo que viene)

| Sprint | Qué entrega | Status |
|---|---|---|
| **M13.2–M13.4** | Security APIs externas (VirusTotal + urlscan.io + OSV) | esperando keys |
| **M16.x** | WhatsApp Gateway (CEO consulta estado por WhatsApp) | esperando Twilio |
| **M17.x** | OutcomeDB Postgres + pgvector (cuando N≥3 fábricas) | trigger automático |
| **M18.x** | Self-tuning del workflow (RLHF sobre feedback histórico) | research |

---

## Origen / créditos

- **Founder**: Cristian Molina (`circles.fof.ai@gmail.com`)
- **Arquitectura** alineada con AI Builder's Handbook 2026 de
  **Aishwarya Naresh Reganti** (LevelUp Labs)
- **Principio rector** (Cap 10 §10.3): *"Stay at the simplest level that
  handles 90% of your cases"*
- **Sistema** construido en sprints incrementales con tests verdes en cada paso

---

*Una página, datos reales, sin hype. Si querés ver más, abrí el dashboard.*
