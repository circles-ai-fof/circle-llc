# Eval Harness — Factory of Factories

Evaluaciones para los 5 agentes activos del `EvidenceGateWorkflow`. Sprint M1.

## Estructura

```
orchestrator/evals/
├── README.md                        ← este archivo
├── promptfooconfig.yaml             ← config para promptfoo (LLM evals)
├── golden_cases/
│   ├── idea_hunter.jsonl            ← 30 casos (18 happy / 9 edge / 3 adversarial)
│   ├── idea_maturer.jsonl           ← 30 casos
│   ├── market_validator.jsonl       ← 30 casos
│   ├── landing_generator.jsonl      ← 30 casos
│   └── gate_decider.jsonl           ← 30 casos (10 pass / 8 kill / 6 iterate / 6 edge)
├── code_based/
│   ├── __init__.py
│   ├── test_schema_validation.py    ← valida shapes de inputs/outputs contra Pydantic
│   ├── test_format_checks.py        ← PII, encoding UTF-8, campos no vacíos
│   └── test_length_bounds.py        ← límites de longitud según modelos
└── llm_judge/
    ├── rubric_idea_quality.md       ← rúbrica 5 criterios (1-5) para idea_hunter/maturer
    ├── rubric_gate_decision.md      ← rúbrica 4 criterios (1-5) para gate_decider
    └── calibration_dataset.jsonl   ← 50 ejemplos con labels humanas
```

## Distribución de casos

| Agente | Happy Path | Edge Case | Adversarial | Total |
|--------|-----------|-----------|-------------|-------|
| idea_hunter | 18 | 9 | 3 | 30 |
| idea_maturer | 18 | 9 | 3 | 30 |
| market_validator | 18 | 9 | 3 | 30 |
| landing_generator | 18 | 9 | 3 | 30 |
| gate_decider | 24 (10P+8K+6I) | 6 | 0 | 30 |

## Cómo correr los evals

### Code-based (pytest, sin API key)
```bash
cd circle-llc
pytest orchestrator/evals/code_based/ -v
```

### Con cobertura
```bash
pytest orchestrator/evals/code_based/ tests/evals/ -v --tb=short
```

### LLM Judge (requiere ANTHROPIC_API_KEY)
```bash
# Usar Haiku solamente — ver promptfooconfig.yaml
ANTHROPIC_API_KEY=sk-... promptfoo eval -c orchestrator/evals/promptfooconfig.yaml
```

## Reglas (del rulebook R12)

- **R12**: ≥30 golden cases antes de activar agente nuevo
- **R06**: mock_mode=True obligatorio en CI (los code_based tests NO llaman a la API)
- **R07**: schema validation en outputs (Pydantic)
- CI falla si code_based/ o tests/evals/ fallan
- LLM judge usa **Haiku 4.5 únicamente** para control de costos

## Campos requeridos por modelo

| Modelo | Campos obligatorios |
|--------|---------------------|
| IdeaSpec | title, description, target_market, problem_statement, proposed_solution, vertical_category |
| MatureIdeaSpec | idea (IdeaSpec), icp (ICPProfile), value_proposition, unfair_advantage, key_risks[] |
| EvidenceTestDesign | hypothesis, success_metrics[], failure_metrics[], test_duration_days (7-30), ad_budget_usd (50-2000), target_ctr (0.005-0.20), target_conversion_rate (0.01-0.50) |
| LandingSpec | headline (≤80), subheadline (≤160), value_props (3-5), cta_text (≤40), social_proof, domain_slug |
| GateDecision | verdict (pass/kill/iterate), confidence (0-1), rationale, key_evidence[], next_steps[], metrics |
