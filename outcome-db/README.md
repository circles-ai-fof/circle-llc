# outcome-db — Políticas pendientes FASE 4

**Estado:** INACTIVO en Sprint M1 (R10 del rulebook)

La Outcome DB (PostgreSQL + pgvector) almacenará insights cross-factory.
No se activa hasta N≥3 fábricas operando con datos reales.

## Pendiente en FASE 4

- `POLICIES.md` — write policy + eviction policy
- `write_gate.py` — validación de cada escritura contra POLICIES.md
- `tests/test_cross_tenant_isolation.py` — aislamiento entre fábricas
- `tests/test_outcome_db_evals.py` — memory evals separados

Ver `orchestrator/rulebook.md` R10 para los criterios de activación.
