# orchestrator/ — Contexto para Claude Code

## Qué es este directorio
Backend Python del orquestador FoF. Implementa el `EvidenceGateWorkflow` (4 pasos lineales con 7 agentes) + 11 agentes adicionales activos (defensas, cazador autónomo, análisis on-demand). Domain: circles-ai.ai. Backend live en Railway.

## Estructura
```
orchestrator/
├── core/
│   ├── models.py            # Pydantic: IdeaSpec, MatureIdeaSpec, GateDecision, etc.
│   ├── base_agent.py        # BaseAgent con prompt caching + mock_mode
│   ├── multi_llm.py         # M9.0 ensemble Claude+GPT+Gemini+Grok
│   ├── storage.py           # SQLite-backed stores + auto-tune helpers
│   ├── source_fetcher.py    # 15 source_kinds dispatcher
│   ├── preferences.py       # M4.1 embeddings + HDBSCAN clustering
│   ├── pain_phrases.py      # M12.0 EN+ES pain detector
│   ├── solution_type.py     # M12.1 8-bucket classifier
│   ├── security_validator.py # M13.0 URL safety heuristics
│   ├── prompt_injection.py  # M13.1 injection scanner
│   ├── adversarial.py       # M11.1 selective callback
│   ├── translator.py        # M9.1 scrape-time translation
│   └── ...
├── workflows/
│   └── evidence_gate.py     # Workflow lineal — Step 1→1.5→2→2.5(M11.4)→3→4a→4b
├── agents/
│   ├── idea_hunter.py       # Step 1: genera IdeaSpec
│   ├── idea_enricher.py     # Step 1.5: sharpens vagueness + Gemini fact-check
│   ├── idea_maturer.py      # Step 2: ICP + value prop
│   ├── idea_validator.py    # M11.3 Step 2.5: red-team pre-test (Opus)
│   ├── market_validator.py  # Step 3: diseña test
│   ├── landing_generator.py # Step 4a: copy
│   ├── gate_decider.py      # Step 4b: pass/kill/iterate ensemble 4-LLM
│   ├── source_scanner.py    # R28: destila signals
│   ├── source_discovery.py  # M9.4: propone fuentes via Gemini
│   ├── link_follower.py     # M10.0: extrae RSS de evidence_urls
│   ├── card_validator.py    # M11.0: vision filtra mockups
│   ├── executive_status.py  # M15.0: briefing para el CEO
│   ├── trend_gap_analyzer.py     # M5.0 análisis on-demand
│   ├── niche_scout.py            # M5.2
│   ├── event_scorer.py           # M5.3
│   ├── sleeper_detector.py       # M5.4
│   ├── multi_agent_consensus.py  # M6.0
│   ├── SCOPES.md                 # Tabla de scopes exclusivos por agente
│   └── _deferred/                # 20+ agentes archivados hasta M18+
├── decisions/                    # 29 ADRs (ADR-001 → ADR-029)
├── rulebook.md                   # R01-R29 reglas operativas
├── requirements.txt
└── .env.example
```

## Cómo correr los tests (sin API key)
```bash
cd circle-llc
pip install -r orchestrator/requirements.txt
pytest tests/ -v
# 1078 tests verdes
```

## Cómo probar con API real
```bash
cp orchestrator/.env.example orchestrator/.env
# Editar .env con ANTHROPIC_API_KEY (mínimo) + OPENAI/GOOGLE/XAI (ensemble completo)
python -c "
from orchestrator.workflows.evidence_gate import EvidenceGateWorkflow
wf = EvidenceGateWorkflow()
run = wf.run('fintech para PYMEs Ecuador')
print(run.summary())
"
```

## Reglas de desarrollo (del rulebook + ADRs)
- R06: mock_mode=True obligatorio en CI
- R07: schema validation en outputs de agentes (Pydantic)
- R08: prompt caching en todos los system prompts
- R10: outcome_insights writable=False hasta M17+ (N≥3 fábricas)
- R12: ≥30 golden cases antes de activar agente nuevo
- ADR-028: callbacks selectivos son OK SOLO si están hard-coded + bounded + one-shot
- ADR-029: workflow body se mantiene LINEAR — no Governor

## Anti-patterns prohibidos
- No crear un Governor/orquestador que decida dinámicamente qué agente llamar (ADR-029)
- No añadir agentes de `_deferred/` sin ADR aprobado
- No hacer tool use donde un single call es suficiente
- No bypassear `security_validator.validate_url()` en ingestión de URLs externas (M13.0)
- No pasar contenido scraped a un LLM sin pasar primero por `prompt_injection.scan_for_injection()` (M13.1)

## Ensemble 4-LLM (M9.0) — cuándo usarlo
Solo en `gate_decider`. Activado vía `ENSEMBLE_GATE_ENABLED=true`. Reganti Cap 8 §8.6: "Ensembles only where they buy real accuracy. Use for the FINAL gate decision, never for the workflow's body."

Voting policy:
- 4 voters: 3-of-4 majority → respeta verdict
- 2-2 tie pass/kill: FORZADO iterate (M9.0)
- 3 voters (legacy): 2-of-3 unchanged
- Confidence cap: avg_conf × agreement_pct

Provider order: Claude → OpenAI → Gemini → Grok (xAI). Cada uno opcional; degrada gracefully.

## Crons activos (5 GitHub Actions)
- `auto-scan.yml` cada 6h — scan de las 33 fuentes
- `auto-analyze.yml` diario 05 UTC — precalienta trend-gaps + niches (M14.0)
- `db-backup.yml` diario 04 UTC — SQLite → Cloudflare R2 (M11.2)
- `executive-briefing.yml` diario 08 UTC — briefing SMTP al CEO (M15.1)
- `weekly-digest.yml` lunes 12 UTC — digest semanal (M6.2)

## Estado actual (2026-06-03)
- 1078 tests verdes
- 18 agentes activos
- 29 ADRs
- 15 source_kinds
- 60+ endpoints REST
- 4 LLM providers (Anthropic + OpenAI + Google + xAI)
- Backend live en Railway con persistent volume

Ver `../CLAUDE.md` (root) para contexto del proyecto completo.
Ver `../docs/architecture.md` para diagramas + flujo end-to-end.
Ver `../ONE-PAGER.md` para resumen estratégico.
