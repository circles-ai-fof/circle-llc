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

## R18 — Specificity Gate (idea_enricher)
Todo IdeaSpec recibido del idea_hunter pasa por idea_enricher ANTES de idea_maturer.
- Score >= 3.5: passthrough
- Score < 3.5: sharpening determinista (mock) o LLM-driven (live), preserva id original
Bloquea la cascada de "vague-in vague-out" (Reganti Cap 5 §5.3).

## R19 — Multi-LLM Ensemble Opt-in (gate_decider only)
Solo el gate_decider puede operar en modo ensemble. NUNCA los agentes del workflow body.
Activación: ENSEMBLE_GATE_ENABLED=true + al menos 1 provider key adicional.
Degradación: si los providers extra fallan, retorna a single-Claude path.
Triplica costo solo en decisión final crítica — no en pasos creativos.

## R20 — Security Defaults
- API: CORS allow-list estricto (no wildcards), security headers obligatorios (CSP, HSTS, X-Frame-Options, nosniff).
- Landing/Dashboard: security headers en next.config.ts (CSP, HSTS, Referrer-Policy).
- DB: RLS activo con políticas SELECT/INSERT/UPDATE/DELETE (defense-in-depth, no solo SELECT).

## R21 — Defer Architectural Decisions Sin Datos (ADR-005)
No agregar routers, governors, ni selectors dinámicos sin N>=10 outcomes medidos.
Cualquier decisión "auto-X" (tool selection, model selection, channel selection) requiere ADR
con evidencia empírica de >=10 casos antes de codificarse en el chassis.

## R22 — Human-in-the-Loop on Ensemble Disagreement
Cuando gate_decider corre en ensemble y agreement_pct < 0.67, el run se marca
`needs_human_review=True` y NO se finaliza el verdict automáticamente.
Dashboard `/revision` lista runs pendientes. Override humano se loggea con
{decided_by, reason, original_verdict, override_verdict} para calibración futura.
NO se hace debate multi-round entre IAs (anti-pattern para clasificación).

## R23 — Tool-Use Limitado a idea_enricher (ADR-006)
Solo idea_enricher puede invocar tools (web_search) — el resto del chassis es one-shot.
Activación: IDEA_ENRICHER_RESEARCH=true. Hard cap: max_uses=3 por enrichment.
Falla graciosamente al path parametrico si el tool errors.

## R24 — Refinement Loop con Hard Cap N=3 (ADR-007)
hunter ↔ enricher pueden iterar hasta specificity_score >= 3.5 o N=3 attempts.
Nunca loops infinitos. BudgetTracker (R13) sigue siendo el cap absoluto.
Esto NO es debate (ADR-005 anti-pattern): son agentes con scopes distintos
cooperando con criterio de terminación claro.

## R25 — Cross-LLM Fact-Check, no Debate (ADR-008)
Claims numéricos del enricher se verifican con Gemini (corpus distinto).
Verdicts: SUPPORTED | UNSUPPORTED | NEEDS_VERIFICATION.
Cada UNSUPPORTED baja specificity_score en 0.5, puede re-disparar refinement loop.
Activación: FACT_CHECK_ENABLED=true + GOOGLE_API_KEY.
NO es debate: es fact-check single-shot binario.

## R28 — Autonomous Hunter Sources + Signals (ADR-011)
Las fuentes externas (RSS, HN, Reddit, GitHub trending, Product Hunt) se administran
en tabla `sources`. El agente `source_scanner` (reactivado desde `_deferred/`) las
escanea y produce `signals` con score 0.0-1.0 + evidence_urls.
Manual: founder revisa, marca 👍/👎, decide qué promover a workflow completo.
Auto: GitHub Actions cron (cada 6h) promueve signals con score ≥ 0.85.
Cap de costo: ~$0.02/source/scan + $0.06/auto-promoted-run. ~$20/mes worst case.
NO se integra X/Twitter ($100/mo) ni LinkedIn (API restricted) — esperan a M4+.

## R29 — Trend Score + Single-Item Signals + New Source Kinds (ADR-012)
+ Tres kinds nuevos GRATIS: youtube (RSS de canal), bluesky (XRPC público),
  telegram (canales públicos via t.me/s/). Sin auth.
+ signals.trend_score: +1 por cada signal previa en 7 días con tema que
  comparte keyword ≥5 chars. Cap a 5.0. Migración aditiva ALTER TABLE.
+ Mock scanner acepta 1 item con contenido (score 0.60). Items con body
  vacío (Instagram-style URLs) producen 0 signals — comportamiento honesto.
+ list() ordena por trend_score DESC, score DESC, created_at DESC.

## R27 — Closed-Beta Email Allowlist Auth (ADR-010)
Dashboard pages exigen sesión emitida por POST /api/v1/auth/login.
Solo emails en ALLOWED_EMAILS (env var) reciben token. Tokens duran 7 días.
Cada intento (allowed o rejected) se loggea en auth_attempts con IP+UA+ts
para auditoría posterior y lookup de país por IP.
Landing público y captura de leads SIGUE abierto — anti-bot tier protege.
Migración a magic-links cuando se abra beta pública (no antes).

## R26 — Layered Anti-Bot Defenses (ADR-009)
Endpoints públicos tienen 6 capas defensivas compuestas:
  L1: per-IP burst rate limit (always-on)
  L2: per-IP daily quota (always-on, tier expensive_llm más estricto)
  L3: honeypot field + dwell time (always-on en /leads)
  L4: Cloudflare Turnstile (opt-in via TURNSTILE_SECRET_KEY)
  L5: disposable-email blocklist (always-on en /leads)
  L6: shared-secret header X-Gate-Secret (opt-in via GATE_RUN_SECRET)
Honeypot trip = silent accept (no responder al bot).
Tiers cuantificados: public_form vs expensive_llm separados.
Overridable runtime via env vars (sin deploy). Detalle en ADR-009.
