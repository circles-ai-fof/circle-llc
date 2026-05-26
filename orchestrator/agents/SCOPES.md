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

## Criterios para desarchivo de agentes en `_deferred/`

Un agente deferido puede ser activado cuando se cumplan **los tres**:

1. ≥3 fábricas operando en producción con datos reales
2. El eval harness tiene ≥30 golden cases para el agente candidato
3. Se demuestra con datos que el workflow o agente actual falla en la tarea — no por intuición

Fuente: AI Builder's Handbook Cap 15 §15.1 — "Build multi-agent as exception, not default."
