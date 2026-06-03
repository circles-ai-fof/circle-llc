# Catálogo de Agentes — Circle LLC Factory of Factories

> **Versión:** 2026-06-03 (M15.1)
> **Total agentes activos:** 20 (más el chassis `EvidenceGateWorkflow` y el `multi_llm` ensemble dispatcher)
> **Modelos integrados:** Claude (Sonnet 4.6 / Haiku 4.5 / Opus 4.5) · OpenAI GPT-4o-mini · Google Gemini Flash · xAI Grok 3-mini

Este documento describe cada componente IA del sistema, qué hace, qué controla, cómo opera y cómo se integra con los 4 modelos LLM. Es la referencia canónica para nuevos contribuidores y para auditoría arquitectónica.

Para arquitectura técnica completa ver [`docs/architecture.md`](docs/architecture.md). Para el organigrama visual ver [`docs/organigrama.html`](docs/organigrama.html) (HTML) o [`docs/organigrama.docx`](docs/organigrama.docx) (Word).

---

## 🧩 0. El Orquestador (chassis del sistema)

No es un agente — es el **andamio determinístico** que ejecuta los agentes en orden y conecta sus salidas. La filosofía explícita (ADR-029) es **linear, no Governor**: el orden está hard-coded en código, ningún LLM decide qué llamar.

### 0.1 `EvidenceGateWorkflow` (`orchestrator/workflows/evidence_gate.py`)

**Qué es:** la línea de ensamblaje principal. Toma un `topic: str` como entrada y produce un `EvidenceGateRun` con `decision: GateDecision`.

**Flujo determinístico (M11.4 wired):**

```
Step 1   idea_hunter      → IdeaSpec
Step 1.5 idea_enricher    → IdeaSpec enriched
Step 2   idea_maturer     → MatureIdeaSpec
Step 2.5 IdeaValidator    → MATAR/PIVOTAR/AVANZAR  ← opt-in (M11.4)
                            └─ MATAR: short-circuit, skip steps 3-4b
Step 3   market_validator → EvidenceTestDesign
Step 4a  landing_generator→ LandingSpec
Step 4b  gate_decider     → GateDecision (4-LLM ensemble)
Step 4c  adversarial_callback → degrade verdict if borderline
```

**Por qué linear:** Reganti Cap 10 §10.3 (*"Stay at the simplest level"*) + 3 fallos conocidos de Governor (costo imprevisible, debuggability cero, loops). Ver ADR-029.

**Estado:** producción · 1078 tests verdes lo cubren

---

### 0.2 `multi_llm` (`orchestrator/core/multi_llm.py`)

**Qué es:** el dispatcher del ensemble 4-LLM usado por `gate_decider` y `adversarial_callback`.

**Función:** dado un `(prompt, system)` lanza la llamada en paralelo a los 4 providers configurados y devuelve un `EnsembleResult` con votos individuales + verdict mayoritario.

**Política de voto (M9.0):**

| Voters disponibles | Majority rule | Notas |
|---|---|---|
| 4/4 | 3-of-4 majority | 2-2 tie → forzado iterate |
| 3/3 (legacy) | 2-of-3 majority | unchanged from M3.x |
| 2/2 | unanimous | else iterate |
| 1/1 | that vote wins | degrade graceful |

**Confidence cap:** `avg(confidence) × agreement_pct`. 4/4 unánime preserva 1.0; 3/4 multiplica × 0.75; 2-2 tie cae a 0.5.

**Por qué Grok como 4ª voz:** training sobre X catches hype patterns que Claude+GPT+Gemini (RLHF-similares) pierden. Empíricamente el mejor "abogado del diablo".

**Activación:** `ENSEMBLE_GATE_ENABLED=true`. Cada provider es opcional — el ensemble degrada gracefully si falta una key.

---

### 0.3 `BaseAgent` (`orchestrator/core/base_agent.py`)

**Qué es:** la clase abstracta que TODOS los agentes heredan. Provee:

- `_client`: instancia de Anthropic SDK (cacheada singleton)
- `mock_mode`: cuando `ANTHROPIC_API_KEY` ausente, devuelve placeholders determinísticos (R06 obligatorio en CI)
- `_call(prompt, system)` — método para invocar Claude con prompt caching automático (R08)
- `_extract_json(text)` — parser tolerante para outputs LLM (markdown fences, prosa preambling)

**Por qué prompt caching:** los system prompts son largos (300-2000 tokens). Anthropic cobra solo el 10% del costo para cache hits. R08 obliga su uso.

---

### 0.4 Storage layer (`orchestrator/core/storage.py`)

**Qué es:** SQLite-backed stores que persisten las salidas de los agentes:

- `signals_store` — output de `source_scanner` (con auto-aplicación de M12.0 pain_boost + M12.1 solution_type + M13.1 injection scan + M9.3 dedup)
- `runs_store` — output de `EvidenceGateWorkflow.run()`
- `sources_store` — fuentes con `quality_score` (M9.5)
- `embeddings_store` — vectores 384-dim para clustering (M4.1)
- `user_settings_store` — i18n + autonomy knobs (M9.1)
- `autonomy_store` — nivel de autonomía del cazador (manual / assisted / autonomous_with_approval)

**Migración futura:** SQLite → Postgres + pgvector cuando N≥3 fábricas (M17+, watchdog activo M11.2 cuenta cuándo activarlo).

---

## 📋 1. Agentes del Workflow (7)

Orden de ejecución hard-coded en `EvidenceGateWorkflow`. Cada uno cubre UN paso y NO se comunica directamente con los demás (todo pasa por el chassis).

### 1.1 `idea_hunter` — Generador de ideas

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/idea_hunter.py` |
| Posición | Step 1 |
| LLM | Claude Sonnet 4.6 (single call) |
| Costo | ~$0.005 |
| Entrada | `topic: str` (e.g. "fintech para PYMEs Ecuador") |
| Salida | `IdeaSpec` (title, summary, target_segment, mechanism, evidence_hint) |
| Mock mode | Devuelve placeholder en español neutro |
| Status | ACTIVE · cubierto por ≥30 golden cases |

**Qué hace:** transforma un topic vago en una idea estructurada con ICP + mecanismo + hint de evidencia. No valida — solo genera.

**Qué controla:** el formato Pydantic `IdeaSpec` para que el resto del workflow tenga input válido. R07: schema validation enforced.

**Cómo opera:** un solo prompt con system prompt cacheado (R08). Si el output no parsea como JSON válido → retry una vez → fallback a placeholder.

---

### 1.2 `idea_enricher` — Sharpen + fact-check

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/idea_enricher.py` |
| Posición | Step 1.5 |
| LLM | Claude Sonnet 4.6 + Gemini (fact-check opcional) |
| Costo | ~$0.008 |
| Entrada | `IdeaSpec` |
| Salida | `IdeaSpec` enriched + `enrichment_meta` |
| Activaciones | `IDEA_ENRICHER_RESEARCH=true` (web_search) · `FACT_CHECK_ENABLED=true` (Gemini fact-check de números) |
| Status | ACTIVE |

**Qué hace:** detecta vagueness en la `IdeaSpec` (TAM "millones", ICP "PYMEs", mecanismo abstracto) y la sharpeniza con datos concretos. Si `IDEA_ENRICHER_RESEARCH=true` usa la tool nativa `web_search` de Anthropic para grounding.

**Qué controla:** la calidad mínima del input que llega a `idea_maturer`. Si después de N intentos sigue vago, escala a `needs_human_review`.

**Cómo opera:**
1. Heurístico detecta cláusulas vagas
2. Si vague → Claude refina
3. Si `FACT_CHECK_ENABLED` → Gemini valida números citados
4. Loop hasta sharp o `attempts_used == max`

---

### 1.3 `idea_maturer` — ICP + Value Prop

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/idea_maturer.py` |
| Posición | Step 2 |
| LLM | Claude Sonnet 4.6 |
| Costo | ~$0.005 |
| Entrada | `IdeaSpec` |
| Salida | `MatureIdeaSpec` (icp, value_proposition, risks, success_metrics) |
| Status | ACTIVE |

**Qué hace:** convierte la idea sharpenizada en una propuesta madura con ICP concreto, value prop accionable, y riesgos enumerados.

**Qué controla:** la entrada a la etapa de validación. Si `MatureIdeaSpec.icp` es genérico o `value_proposition` no es falsable, el workflow degrada.

**Cómo opera:** single Claude call con prompt cacheado. Schema-validated output.

---

### 1.4 `IdeaValidator` ⚔️ — Red-team pre-test (M11.3+M11.4)

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/idea_validator.py` |
| Posición | Step 2.5 (entre maturer y market_validator) |
| LLM | Claude **Opus 4.5** (override `IDEA_VALIDATOR_MODEL`) + opcional web_search |
| Costo | $0.06 (sin web) / $0.10 (con web_search) |
| Entrada | `MatureIdeaSpec` |
| Salida | `ValidatorResult` con verdict ∈ {MATAR, PIVOTAR, AVANZAR_CON_EVIDENCIA} |
| Activación | `IDEA_VALIDATOR_ENABLED=true` (opt-in) |
| Status | ACTIVE — hooked en workflow vía M11.4 |

**Qué hace:** **mata ideas antes de gastar $50 en ads**. Actúa como inversor escéptico / operador con cicatrices. Identifica la suposición más letal, diseña un experimento de $50 + 1 semana, responde 3 preguntas obligatorias (60-day pre-mortem / quién paga hoy / impacto económico).

**Qué controla:** decide si el workflow sigue (AVANZAR) o se corta sin spend (MATAR). Cuando MATAR, `EvidenceGateWorkflow` genera un `GateDecision` sintético con verdict='kill' y rationale = lethal_assumption + experiment.

**Cómo opera:**
1. Carga 8 vectores de ataque (DEMANDA, WTP, distribución, CAC, defensibilidad, timing, regulación, ejecución)
2. Single Opus call con system prompt verbatim de la spec
3. Si `IDEA_VALIDATOR_RESEARCH=true` → activa tool `web_search` para citar fuentes reales
4. Parsea JSON estructurado → `ValidatorResult`
5. Workflow lee `verdict` y decide cut-or-continue

**Fail-closed:** cualquier error (LLM down, JSON malformado, key ausente) → returns MATAR por defecto. Es asimétrico: false MATAR = $0 perdido; false AVANZAR = $50 ad spend.

---

### 1.5 `market_validator` — Diseña el test de mercado

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/market_validator.py` |
| Posición | Step 3 |
| LLM | Claude Sonnet 4.6 |
| Costo | ~$0.005 |
| Entrada | `MatureIdeaSpec` |
| Salida | `EvidenceTestDesign` (target_ctr, target_conversion_rate, ad_budget_usd, test_duration_days) |
| Status | ACTIVE |

**Qué hace:** diseña QUÉ medir y CÓMO en el test de landing + ads. Setea umbrales falsables: "PASS si CTR >= X% AND conversión >= Y% AND $/conv <= Z".

**Qué controla:** los criterios que después usa `gate_decider` para decidir. Si los thresholds son irreales, todo lo demás falla.

---

### 1.6 `landing_generator` — Copy de la landing

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/landing_generator.py` |
| Posición | Step 4a |
| LLM | Claude Sonnet 4.6 |
| Costo | ~$0.008 (más tokens output) |
| Entrada | `MatureIdeaSpec` |
| Salida | `LandingSpec` (headline, subheadline, cta, value_prop_bullets, domain_slug) |
| Status | ACTIVE |

**Qué hace:** escribe el copy de la landing real que va a recibir el tráfico de ads. Headline + subheadline + CTA + bullets de valor.

**Qué controla:** la conversión potencial. Mal copy = test inválido (no estás midiendo demanda, estás midiendo si el copy convence).

---

### 1.7 `gate_decider` 🚪 — El juez final con ensemble 4-LLM

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/gate_decider.py` |
| Posición | Step 4b |
| LLM | **Ensemble: Claude + GPT-4o-mini + Gemini Flash + Grok 3-mini** |
| Costo | $0.025-$0.045 (4 calls) |
| Entrada | `MatureIdeaSpec` + `EvidenceTestDesign` + `MetricsSnapshot` real (CTR, conv, cost) |
| Salida | `GateDecision` (verdict: pass\|kill\|iterate, confidence, rationale, key_evidence, next_steps) |
| Activación | `ENSEMBLE_GATE_ENABLED=true` |
| Status | ACTIVE — el gate canónico del sistema |

**Qué hace:** vota PASS / KILL / ITERATE con los 4 LLMs en paralelo. Aplica reglas auto-rule primero (auto-pass si métricas exceden 1.5×; auto-kill si CTR < target/3 con 1000+ impressions), después escala a ensemble para casos borderline.

**Qué controla:** TODO el sistema. Su veredicto determina si se construye o se mata.

**Cómo opera:**
1. Aplica reglas determinísticas (auto-pass / auto-kill / borderline)
2. Si borderline → invoca `multi_llm.gate_ensemble_vote()`
3. Tally:
   - 3-of-4 majority → respeta verdict
   - 2-2 tie → forzado iterate (M9.0)
   - Confidence × agreement_pct
4. Si needs_human_review (agreement < 67%) → flag para revisión manual

---

## 🛡️ 2. Defensas + filtros (3)

### 2.1 `adversarial_callback` 🔍 (M11.1, ADR-028)

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/core/adversarial.py` |
| Posición | Step 4c (después del ensemble) |
| LLM | Grok 3-mini (preferido) → Claude Haiku (fallback) |
| Costo | $0.005 por invocación · ~30% de los runs caen en band |
| Entrada | `verdict, confidence, rationale, evidence` |
| Salida | `AdversarialResult` con `objections[]` y `final_verdict` (possibly degraded) |
| Activación | `ADVERSARIAL_CALLBACK_ENABLED=true` (opt-in M11.1) |
| Status | ACTIVE · ADR-028 codifica por qué NO es Governor |

**Qué hace:** cuando `gate_decider` vota con confidence ∈ [0.6, 0.8] (borderline), Grok actúa como abogado del diablo y busca **objeciones específicas** al verdict. Si encuentra ≥2 "strong" → degrade el verdict a iterate.

**Por qué NO es Governor:**
- Hard-coded en `gate_decider` (no LLM decide quién llamar)
- One-shot direction (callback no puede llamar de vuelta)
- Bounded by confidence band (0.6-0.8)
- Fixed role: "encontrá 3 razones por qué este verdict está mal"

Ver ADR-028 para criterios de revisita (false-PASS rate > 15%, callback > 50%, costo > $50/mo).

---

### 2.2 `CardValidator` 🎴 (M11.0)

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/card_validator.py` |
| Posición | On-demand sobre signals tipo `app_marketplace` |
| LLM | **Claude Haiku 4.5 con vision** |
| Costo | $0.002 por imagen |
| Entrada | `image_url: str` |
| Salida | `CardValidation` (kind: real_app\|mockup\|unknown, confidence, rationale, score_multiplier) |
| Status | ACTIVE |

**Qué hace:** inspecciona la imagen de un app card (Lovable, Claude Creations, Adorable) y decide si es app real o mockup Figma.

**Heurísticos del prompt:**
- Real: números/nombres/fechas concretos, interaction states, imperfecciones de uso real
- Mockup: lorem ipsum, sombras Figma, typography over-perfect, UI repetida
- Logo solo / arte abstracto → UNKNOWN (no adivina)

**Qué controla:** el `score_multiplier` que se aplica downstream:
- mockup → 0.3× (severo)
- real_app → 1.0×
- unknown → 0.85× (mild penalty)

**Budget:** `MAX_VALIDATIONS_PER_DAY=50` para acotar costo (~$3/mes).

---

### 2.3 SecurityValidator (M13.0) + Prompt Injection Scanner (M13.1)

**No son agentes** — son módulos heurísticos puros (sin LLM) en `orchestrator/core/security_validator.py` y `orchestrator/core/prompt_injection.py`. Se invocan automáticamente desde `SignalsStore.add()` antes de guardar.

| Capa | Qué chequea |
|---|---|
| `validate_url(url, link_text)` | 13 heurísticos: typosquat (Levenshtein), homoglyph (Unicode), TLD abusado, URL shortener, executable download, IP host, @ spoofing, label/href mismatch, deep subdomain, plain http |
| `scan_for_injection(text)` | 27 patterns en EN+ES × 4 severidades (CRITICAL/HIGH/MEDIUM/LOW). Penalty multiplicativo al score (-50% CRITICAL, -20% HIGH, -10% MEDIUM, floor 0.05) |

Verdict scale: SAFE / SUSPICIOUS / DANGEROUS / UNKNOWN. **Bias seguro:** cualquier duda → SUSPICIOUS, nunca SAFE.

---

## 🕷️ 3. Cazador autónomo (4)

### 3.1 `source_scanner` (R28-R29)

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/source_scanner.py` |
| LLM | Claude Haiku 4.5 |
| Costo | $0.001-$0.003 por scan |
| Entrada | `RawFetchedItem[]` desde uno de los 15 source_kinds |
| Salida | `Signal[]` persistidas a `signals_store` |
| Frecuencia | cron `auto-scan.yml` cada 6h |
| Status | ACTIVE |

**Qué hace:** destila items raw (RSS entries, posts Reddit, reviews App Store, etc.) en `Signal` estructurados con theme, score, excerpt, evidence_urls, suggested_topic.

**Qué controla:** la entrada a TODO el resto del cazador.

**Cómo opera:**
1. `fetch_by_kind()` trae items raw
2. Claude Haiku resume cada batch a Signal
3. **Antes de persistir** se aplica:
   - M13.1 `scan_for_injection()` → penalty si detecta override patterns
   - M12.0 `apply_boost()` → boost si detecta frases de dolor real
   - M12.1 `classify_solution()` → tag con taxonomía 8-way
   - M9.3 `canonical_hash` → dedup cross-source (bump `times_seen`)
4. `signals_store.add()` persiste

---

### 3.2 `SourceDiscoveryAgent` 🔭 (M9.4)

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/source_discovery.py` |
| LLM | **Gemini Flash (con grounding)** → Claude Haiku (fallback) |
| Costo | $0.005 por discovery |
| Entrada | `keywords: list[str]` (de clusters aprobados M4.1) |
| Salida | `ProposedSource[]` con kind + target + reason |
| Activación | `AUTO_DISCOVERY_ENABLED` (M9.1 setting) |
| Status | ACTIVE |

**Qué hace:** dado un set de keywords de un cluster que el founder aprobó (👍), pide a Gemini que **proponga 3-5 nuevas fuentes** (RSS feeds, subreddits, telegram channels, etc.) que cubran ese tema.

**Por qué Gemini:** tiene Google Search grounding activo — ideal para "qué blogs/comunidades existen sobre X". Claude no tiene grounding nativo gratuito.

**Cómo opera:**
1. Pide a Gemini con `response_mime_type=application/json` (forzado, M9.4 fix)
2. Parsea la lista
3. Filtra contra:
   - Schemas soportados (kind ∈ {rss, reddit, hn, ...})
   - Sources ya existentes (dedup)
4. Cap en 5 propuestas/call
5. Las propuestas quedan en queue de aprobación (`/cazar/fuentes` con badge "🤖 Sugerido")

**Safety brake:** `user_settings.max_new_sources_per_week=5` limita aceptación.

---

### 3.3 `LinkFollowerAgent` 🔗 (M10.0)

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/link_follower.py` |
| LLM | **Ninguno — 100% heurístico** |
| Costo | $0 |
| Entrada | `signal_id` con `evidence_urls[]` |
| Salida | `ProposedSource[]` |
| Status | ACTIVE |

**Qué hace:** mina las `evidence_urls` de signals aprobadas para descubrir RSS feeds escondidos.

**3 patterns determinísticos:**
1. `github.com/<user>/<repo>` → propone `releases.atom` (score 0.75)
2. `reddit.com/r/<sub>` → propone `reddit` source con target=sub (score 0.65)
3. `<link rel="alternate" type="application/rss+xml">` en el HTML → feed URL (score 0.85)

**Fail-soft:** si la URL no responde, devuelve solo las propuestas pattern-based sin crashear.

---

### 3.4 `executive-status` 🎙️ (M15.0)

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/executive_status.py` |
| LLM | Claude Sonnet 4.6 (override `EXEC_STATUS_MODEL`) |
| Costo | $0.005-$0.01 por briefing |
| Entrada | `question: Optional[str]` |
| Salida | `ExecutiveBriefing` (summary, body, highlights, risks, asks, snapshot) |
| Modes | REPORT (briefing standalone) · QA (respuesta a pregunta) |
| Status | ACTIVE — el cerebro del WhatsApp Gateway (M16+) |

**Qué hace:** lee el estado de **18 fuentes en tiempo real** (signals counts, sources quality, runs verdicts, agents enabled, autonomy_level, últimos 5 commits del repo) y produce briefing estructurado en español.

**Output forzado por system prompt:**
- HEADLINE (1-2 oraciones)
- HIGHLIGHTS (hasta 6 bullets)
- RIESGOS (hasta 6 bullets)
- PRÓXIMOS PASOS (hasta 6 bullets)

**Reglas no negociables del prompt:**
1. Solo hechos observados (no inventa)
2. Tono operativo honesto en español neutro
3. Sin markdown pesado (renderiza bien en WhatsApp + email)
4. Si dato falta → "no disponible"

**Canales que lo consumen:**
- Dashboard (botón)
- Cron diario `executive-briefing.yml` → SMTP al CEO
- WhatsApp Gateway (M16+) cuando esté activo

---

## 🔬 4. Análisis on-demand (8)

Agentes que el founder dispara explícitamente desde el dashboard. NO corren en el workflow ni en crons (excepto `auto-analyze.yml` que precalienta los top-3 de M5.0+M5.2 diariamente — M14.0).

### 4.1 `TrendGapAnalyzer` (M5.0)

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/trend_gap_analyzer.py` |
| Pareja con heurístico | `signals_store.cross_country_gaps()` |
| LLM | Claude Sonnet 4.6 |
| Costo | $0.008 |
| Entrada | `TrendGapItem` (validated_in, missing_in, opportunity_score) |
| Salida | `TrendGapAnalysis` (priority_country, timing_hypothesis, adoption_pattern, go_to_market, risks_per_country) |
| Status | ACTIVE v1.0.0 (30/30 golden cases — ADR-024) |

**Qué hace:** dada una "first-mover gap" detectada heurísticamente (idea validada en US, ausente en EC/MX/CO), produce análisis profundo: qué país atacar primero, timing hypothesis, patrón de adopción, GTM, riesgos por país.

---

### 4.2 `NicheScout` (M5.2)

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/niche_scout.py` |
| LLM | Claude Sonnet 4.6 |
| Costo | $0.008 |
| Entrada | `parent_market`, `parent_size`, `leader_niche`, `underexplored_niches[]` |
| Salida | Plan de entrada al sub-niche más prometedor |
| Status | ACTIVE v1.0.0 (ADR-026) |

**Qué hace:** dado un "gigante" del mercado, identifica el sub-niche sub-explorado más prometedor y diseña un plan de entrada concreto.

---

### 4.3 `EventRelevanceScorer` (M5.3)

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/event_relevance_scorer.py` |
| LLM | Claude Sonnet 4.6 |
| Costo | $0.008 |
| Entrada | Datos del evento (nombre, audiencia, costo, fecha, oradores) |
| Salida | Recomendación ir/no-ir con scoring |
| Status | ACTIVE v1.0.0 (ADR-026) |

**Qué hace:** ¿Vale la pena ir a esa feria/congreso? Scoring multi-dimensional sobre ROI esperado vs costo + tiempo.

---

### 4.4 `SleeperCompanyDetector` (M5.4)

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/sleeper_company_detector.py` |
| LLM | Claude Sonnet 4.6 |
| Costo | $0.008 |
| Entrada | Datos de la empresa (revenue, signals, traction) |
| Salida | Score de "sleeper" — empresa subestimada que está despertando |
| Status | ACTIVE v1.0.0 (ADR-026) |

**Qué hace:** detecta companies dormidas que están empezando a moverse (incremento de hiring, señales de revenue, cambios de estrategia) — oportunidad de partnership/adquisición early.

---

### 4.5 `ProductArbitrageEvaluator` (M5.5)

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/product_arbitrage_evaluator.py` |
| LLM | Claude Sonnet 4.6 |
| Costo | $0.008 |
| Entrada | Producto + 2+ mercados con precios |
| Salida | Recomendación de arbitraje viable |
| Status | ACTIVE v1.0.0 (ADR-026) |

**Qué hace:** ¿Hay arbitraje cross-mercado para este producto? Calcula viabilidad considerando logística, regulación, márgenes y duración esperada de la ventana.

---

### 4.6 `MultiAgentConsensus` (M6.0)

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/multi_agent_consensus.py` |
| LLM | Sonnet (3 personas distintas en prompts) |
| Costo | $0.025 (3 calls + sintetizador) |
| Entrada | Tema de análisis |
| Salida | Consensus con verdict + voto por persona |
| Status | ACTIVE v1.0.0 (ADR-027) |

**Qué hace:** simula 3 "personas" especializadas (e.g., investor + operator + skeptic) que votan independientemente sobre un mismo tema. Sintetizador final reconcilia.

---

### 4.7 `idea_analyzer` (M3.5)

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/idea_analyzer.py` |
| LLM | Claude Sonnet 4.6 |
| Costo | $0.008 |
| Entrada | `Signal` (theme + excerpt + URL) |
| Salida | Análisis detallado guardado en `signals.analysis_json` |
| Trigger | Botón "Analizar" en `/cazar/senales` |
| Status | ACTIVE |

**Qué hace:** cuando el founder ve una señal interesante, click en "Analizar" dispara este agente que produce un análisis profundo (oportunidad, riesgos, competidores, ICP candidato).

---

### 4.8 `link_analyzer`

| Campo | Valor |
|---|---|
| Archivo | `orchestrator/agents/link_analyzer.py` |
| LLM | Claude Sonnet 4.6 |
| Costo | $0.005 |
| Entrada | URL libre del founder |
| Salida | Idea estructurada extraída de la URL |
| Status | ACTIVE |

**Qué hace:** el founder pega una URL (artículo, web de un producto, video YouTube) y este agente la convierte en señal estructurada lista para que el resto del sistema la consuma.

---

## 🎯 Resumen — cómo se relacionan los modelos LLM con cada agente

| Modelo | Usado por | Cuándo |
|---|---|---|
| **Claude Sonnet 4.6** | idea_hunter, idea_enricher, idea_maturer, market_validator, landing_generator, executive-status, todos los M5.x, idea_analyzer, link_analyzer | Razonamiento estructurado, output JSON, calidad/costo balance |
| **Claude Haiku 4.5** | source_scanner, CardValidator (vision), translator | Volumen alto + costo bajo (filtros, traducciones, vision rápida) |
| **Claude Opus 4.5** | **IdeaValidator** | Adversarial reasoning donde el costo extra paga (kill antes de $50 ads) |
| **OpenAI GPT-4o-mini** | gate_decider (ensemble), idea_validator parse opcional | Voto independiente con priores diferentes a Claude |
| **Google Gemini Flash** | gate_decider (ensemble), idea_enricher fact-check, SourceDiscoveryAgent | Web grounding + tool use cuando hace falta search live |
| **xAI Grok 3-mini** | gate_decider (ensemble), adversarial_callback | Contrarian voice / X training catches hype patterns |

**Cuándo se usan los 4 en paralelo:** SOLO en `gate_decider` (Step 4b del workflow) cuando `ENSEMBLE_GATE_ENABLED=true`. Es el único lugar donde el costo extra del ensemble paga por su tasa de catch real (Reganti Cap 8 §8.6).

---

## 🔐 Reglas operativas (R01–R29) que aplican a los agentes

- **R06**: `mock_mode=True` obligatorio en CI — todos los agentes tienen fallback determinístico
- **R07**: schema validation Pydantic en outputs — ningún agente devuelve JSON libre
- **R08**: prompt caching en todos los system prompts — ahorra 90% en hits
- **R10**: `outcome_insights` writable=False hasta M17+ (no se persiste insight derivado de runs todavía)
- **R12**: ≥30 golden cases antes de activar un agente experimental → ACTIVE
- **R29**: nunca construir hasta que landing + ads den evidencia real (evidence-gate)

## 🚫 Anti-patterns prohibidos (ADR-029)

- ❌ Governor / orquestador que decide dinámicamente qué agente llamar
- ❌ Free conversation between agents (loops y costo imprevisible)
- ❌ Tool use cuando un single call es suficiente
- ❌ Bypass de `security_validator.validate_url()` en ingestión
- ❌ Pasar contenido scraped a LLM sin `prompt_injection.scan_for_injection()` previo

---

## 📚 Referencias cruzadas

- [`docs/architecture.md`](docs/architecture.md) — arquitectura técnica con diagramas ASCII
- [`docs/organigrama.html`](docs/organigrama.html) — organigrama visual de agentes
- [`docs/organigrama.docx`](docs/organigrama.docx) — versión Word para presentaciones
- [`ONE-PAGER.md`](ONE-PAGER.md) — resumen estratégico
- [`orchestrator/decisions/ADR-028.md`](orchestrator/decisions/ADR-028.md) — Selective adversarial callback
- [`orchestrator/decisions/ADR-029.md`](orchestrator/decisions/ADR-029.md) — No Governor anti-pattern
- [`orchestrator/rulebook.md`](orchestrator/rulebook.md) — R01–R29 completo
- [`CHANGELOG.md`](CHANGELOG.md) — historial de cada agente

---

*Catálogo mantenido por Cristian Molina — Circle LLC · Junio 2026*
