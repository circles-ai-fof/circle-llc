# Agent Scopes — EvidenceGateWorkflow (Sprint M1)

Cada agente tiene scope **exclusivo**. El test `test_scope_overlap.py` verifica que no haya overlaps.
Fuente: AI Builder's Handbook Cap 15 §15.5 — "responsibility fuzziness" failure mode.

| Agente | Lo que SÍ hace | Lo que NO hace |
|---|---|---|
| `idea_hunter` | Genera UNA IdeaSpec desde un topic/trend | NO valida, NO define ICP, NO diseña tests, NO hace copy, NO toma decisiones |
| `idea_enricher` | Puntúa especificidad, sharpens IdeaSpec vagas, opcionalmente usa web_search para grounding y cross-LLM fact-check | NO genera ideas nuevas, NO define ICP, NO pivota la idea, NO debate con otras IAs |
| `idea_maturer` | Define ICP + value proposition + riesgos para una IdeaSpec dada | NO genera ideas, NO diseña tests, NO escribe copy, NO toma decisiones |
| `market_validator` | Diseña el test de mercado (hipótesis, métricas, presupuesto, duración) | NO genera ideas, NO define ICP, NO escribe copy, NO toma decisiones |
| `landing_generator` | Escribe el copy de la landing page (headline, value props, CTA) | NO genera ideas, NO diseña tests, NO define ICP, NO toma decisiones |
| `gate_decider` | Evalúa métricas reales vs. thresholds → pass/kill/iterate | NO genera ideas, NO define ICP, NO diseña tests, NO escribe copy |

## Tabla de overlaps permitidos: NINGUNO

```
                    idea_hunter  idea_enricher  idea_maturer  market_validator  landing_generator  gate_decider
idea_hunter              —           ✗              ✗               ✗                 ✗               ✗
idea_enricher            ✗           —              ✗               ✗                 ✗               ✗
idea_maturer             ✗           ✗              —               ✗                 ✗               ✗
market_validator         ✗           ✗              ✗               —                 ✗               ✗
landing_generator        ✗           ✗              ✗               ✗                 —               ✗
gate_decider             ✗           ✗              ✗               ✗                 ✗               —
```

✗ = no overlap (expected). El CI falla si alguna celda se convierte en overlap activo.

## Agentes adicionales (activos, invocados solo on-demand)

| Agente | Sprint | Status | Golden cases | Scope exclusivo |
|---|---|---|---|---|
| `trend_gap_analyzer` | M5.0 → M5.1 | **ACTIVE** | **30/30** ✅ | Analiza un TrendGapItem (output de M4.11) y prioriza país + plan de validación. NO se solapa con idea_analyzer (analiza UNA señal puntual) ni con market_validator (diseña test post-promotion). Solo se invoca via POST /api/v1/trend-gaps/analyze (on-demand). Promoción a "siempre activo en workflow" requiere métrica gating de no-degradación (futuro, ver ADR-024). |
| `niche_scout` | M5.2 → M5.8 | **ACTIVE** | **30/30** ✅ v1.0.0 | Analiza una NicheOpportunity (output de M4.15) y plan de entrada al sub-niche. Scope distinto a market_validator (que diseña test general) y trend_gap_analyzer (que opera cross-país). POST /api/v1/niche-opportunities/analyze. |
| `event_relevance_scorer` | M5.3 → M5.9 | **ACTIVE** | **30/30** ✅ v1.0.0 | Decide go/skip/send_someone_else para una feria/congreso detectado por signals kind=events (M4.13). Único scope: ROI estimado de asistir. POST /api/v1/events/score. |
| `sleeper_company_detector` | M5.4 → M5.10 | **ACTIVE** | **30/30** ✅ v1.0.0 | Identifica "second-best with momentum" desde un grupo de signals kind=sec_edgar (M4.12). Razona desde cadence de filings, NO desde cifras inventadas. POST /api/v1/sleeper-companies/detect. |
| `product_arbitrage_evaluator` | M5.5 → M5.11 | **ACTIVE** | **30/30** ✅ v1.0.0 | Evalúa un trending search (signal kind=google_trends, M4.14) como oportunidad de dropshipping: producto físico? margin? recomendación test/skip/deepdive. POST /api/v1/arbitrage/evaluate. |

## Criterios para desarchivo de agentes en `_deferred/`

Un agente deferido puede ser activado cuando se cumplan **los tres**:

1. ≥3 fábricas operando en producción con datos reales
2. El eval harness tiene ≥30 golden cases para el agente candidato
3. Se demuestra con datos que el workflow o agente actual falla en la tarea — no por intuición

Fuente: AI Builder's Handbook Cap 15 §15.1 — "Build multi-agent as exception, not default."
