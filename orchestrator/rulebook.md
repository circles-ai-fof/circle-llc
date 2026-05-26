# FoF Orchestrator Rulebook — circles-ai.ai

Reglas inviolables para el orquestador de Factory of Factories.
Versión: 1.0 | Sprint M1 | Mayo 2026

---

## R01 — No avanzar sin evidence-gate aprobado
Ninguna fábrica pasa a Sprint M1 (build) sin un `GateDecision.verdict == "pass"` documentado.
Verdict requerido en `outcome-db/gate_decisions/` antes de asignar recursos de desarrollo.

## R02 — Cost cap por corrida
Cada run de `EvidenceGateWorkflow` tiene un `cost_cap_usd` configurable (default: $5.00).
Si el costo estimado supera el cap, el run aborta con `CostCapExceededError`.
Override documentado en `orchestrator/config.py` con justificación.

## R03 — Audit log inmutable
Cada LLM call registra: timestamp, agent_name, model, input_tokens, output_tokens, cost_usd, verdict (si aplica).
El log es append-only. No se puede editar ni borrar entradas.

## R04 — No PII en prompts
Ningún prompt enviado a la API de Anthropic puede contener: nombres reales de usuarios, emails, teléfonos, RUC/cédula.
El `SanitizationMiddleware` valida antes de cada `_call()`.

## R05 — Single source of truth para modelos
El modelo activo se configura en `CLAUDE_MODEL` env var.
No hay referencias hardcodeadas a versiones de modelo en el código.
Cambio de modelo requiere: (1) actualizar env var, (2) correr eval suite, (3) commit con resultado.

## R06 — Mock mode obligatorio en CI
Los tests en CI corren con `mock_mode=True`. Ningún test en `tests/` puede hacer llamadas reales a la API.
Variable `CI=true` activa mock mode automáticamente si se olvida el flag.

## R07 — Schema validation en outputs de agentes
Cada output de agente pasa por el modelo Pydantic correspondiente antes de ser usado como input del siguiente paso.
Un output malformado aborta el workflow con `AgentOutputValidationError`, no propaga silenciosamente.

## R08 — Prompt caching obligatorio
Todo system prompt usa `cache_control: {"type": "ephemeral"}`.
Reducción de costo objetivo: ≥60% en corridas repetidas del mismo workflow.

## R09 — No deployment sin tests verdes
`pytest tests/` debe pasar al 100% antes de cualquier merge a `main`.
GitHub Actions bloquea merge si algún test falla.

## R10 — Outcome DB inactiva en M1
La tabla `outcome_insights` tiene `writable=False` en Sprint M1.
Agentes no escriben insights cross-vertical hasta N≥3 fábricas operando.
Previene acumulación de ruido con datos insuficientes. (Ver `outcome-db/POLICIES.md`)

## R11 — Decisiones arquitectónicas en ADRs
Cualquier cambio que afecte: stack tecnológico, modelo de LLM, proveedor de infra, o diseño de agentes
requiere un ADR en `orchestrator/decisions/ADR-XXX.md` aprobado antes de implementar.

## R12 — Evals antes de promover agente a producción
Ningún agente nuevo puede activarse en producción sin ≥30 golden cases en `orchestrator/evals/`.
El eval suite del agente debe correr verde en CI.

---

## R13 — Step Budget por Trayectoria
Cada workflow del orquestador tiene un step_budget máximo configurado en BudgetTracker.
Default: 20 steps, $5.00 USD. Si una trayectoria supera el budget, abort con TrajectoryBudgetExceededError.
Override por workflow documentado en orchestrator/config.py con justificación.

## R14 — Canonical Goal Statement
Cada workflow crea un CanonicalGoal al inicio del run.
El canonical_goal está disponible en EvidenceGateRun para cualquier agente que lo necesite.
Previene drift from goal (Cap 15.5) — cada agente puede verificar que su output está dentro del scope.

## R15 — Scope Exclusivo Documentado
Cada agente tiene scope exclusivo documentado en SCOPES.md.
Tests de overlap corren en CI (test_scope_overlap.py): si dos agentes pueden hacer la misma tarea, falla el build.
Ver criterios de activación en _deferred/README.md.

## R16 — Per-Agent Quality Evals
Cada agente tiene su eval suite en orchestrator/evals/golden_cases/{agent_name}.jsonl.
Antes de promover output de un agente como input del siguiente, el output pasa por schema validation (R07).
Code-based evals corren en CI antes de cualquier LLM-as-judge.

## R17 — Cost Alert en 80% del Cap
Alert (no kill) cuando una corrida alcanza 80% del cost_cap_usd.
Permite ajustar antes del kill duro en 100% (R02).
Implementado en BudgetTracker._alert_fired — log warning en 80%, TrajectoryBudgetExceededError en 100%.
