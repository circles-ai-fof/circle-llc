# orchestrator/ — Contexto para Claude Code

## Qué es este directorio
Backend Python del orquestador FoF. Implementa el `EvidenceGateWorkflow` (4 pasos lineales)
con 5 agentes embebidos. Sprint M1. Dominio: circles-ai.ai.

## Estructura
```
orchestrator/
├── core/
│   ├── models.py          # Pydantic: IdeaSpec, MatureIdeaSpec, GateDecision, etc.
│   └── base_agent.py      # BaseAgent con prompt caching + mock_mode
├── workflows/
│   └── evidence_gate.py   # Workflow lineal 4 pasos — el chassis principal
├── agents/
│   ├── idea_hunter.py     # Step 1: genera IdeaSpec
│   ├── idea_maturer.py    # Step 2: define ICP + value prop
│   ├── market_validator.py # Step 3: diseña test de mercado
│   ├── landing_generator.py # Step 4a: escribe landing copy
│   ├── gate_decider.py    # Step 4b: pass/kill/iterate
│   ├── SCOPES.md          # Tabla de scopes exclusivos
│   └── _deferred/         # 20+ agentes archivados hasta M12
├── rulebook.md            # R01-R12 + pendientes R13-R17
├── requirements.txt
└── .env.example
```

## Cómo correr los tests (sin API key)
```bash
cd circle-llc
pip install -r orchestrator/requirements.txt
pytest tests/ -v
```

## Cómo probar con API real
```bash
cp orchestrator/.env.example orchestrator/.env
# Editar .env con ANTHROPIC_API_KEY
python -c "
from orchestrator.workflows.evidence_gate import EvidenceGateWorkflow
wf = EvidenceGateWorkflow()
run = wf.run('fintech para PYMEs Ecuador')
print(run.summary())
"
```

## Reglas de desarrollo (del rulebook)
- R06: mock_mode=True obligatorio en CI
- R07: schema validation en outputs de agentes (Pydantic)
- R08: prompt caching en todos los system prompts
- R10: outcome_insights writable=False en M1
- R12: ≥30 golden cases antes de activar agente nuevo

## Anti-patterns prohibidos
- No crear un Governor/orquestador que decida dinámicamente qué agente llamar
- No añadir agentes de _deferred/ sin ADR aprobado
- No hacer tool use donde un single call es suficiente
