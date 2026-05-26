# Outcome DB — Políticas de Escritura y Evicción

**Estado en Sprint M1:** INACTIVO — `writable = False` (R10 del rulebook)
**Referencia:** AI Builder's Handbook Cap 14 §14.7 — cross-user leakage, memory poisoning, runaway growth

---

## 1. Write Policy

### 1.1 ¿Qué se escribe?

Solo se persisten **insights cross-factory** que cumplan TODOS los criterios:

| Criterio | Requisito |
|---|---|
| Origen | Fábrica con ≥ 10 días de operación continua |
| Tipo de dato | Insight de comportamiento de mercado, NO datos de usuario individual |
| Identificadores de usuario | Prohibidos. Todo PII debe sanitizarse antes de llegar al gate |
| Datos de negocio propietarios | Prohibidos sin `cross_vertical=True` + redacción manual |
| Schema | Debe pasar validación Pydantic `InsightCandidate` |

### 1.2 Niveles de Confianza (confidence_level)

| Nivel | Criterio | TTL | Nota |
|---|---|---|---|
| `ANECDOTAL` | N = 1 fábrica con datos suficientes | 90 días | Solo referencial |
| `PRELIMINARY` | N < 10 fábricas con datos suficientes | 180 días | No usar en decisiones críticas |
| `PREDICTIVE` | N ≥ 10 fábricas con datos suficientes | Sin TTL | Revisión quarterly obligatoria |

La asignación de nivel es **automática** en `write_gate.py` en base a `source_data_points`:
- `source_data_points == 1` → `ANECDOTAL`
- `1 < source_data_points < 10` → `PRELIMINARY`
- `source_data_points >= 10` → `PREDICTIVE`

### 1.3 Schema Pydantic (fuente de verdad)

```python
class ConfidenceLevel(str, Enum):
    ANECDOTAL = "anecdotal"
    PRELIMINARY = "preliminary"
    PREDICTIVE = "predictive"

class InsightCandidate(BaseModel):
    factory_id: UUID          # ID único de la fábrica origen
    content: str              # Texto del insight (sanitizado de PII)
    confidence_level: ConfidenceLevel
    source_data_points: int   # Número de fábricas/casos que sustentan el insight
    tags: List[str]           # Categorías: ["pricing", "icp", "validation", ...]
    cross_vertical: bool = False  # True = puede compartirse entre verticales con redacción
    relevance_score: float = 1.0  # 0.0–1.0; calculado post-escritura
```

### 1.4 Sanitización PII

El `write_gate.py` rechaza (retorna `WriteDecision(allowed=False)`) cualquier `content` que contenga:
- Emails (`\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b`)
- Teléfonos (`\b(\+?[0-9]{7,15})\b` con contexto)
- Nombres propios en formato `Nombre Apellido` detectados por heurística (a futuro NER)
- URLs que identifiquen usuarios individuales

Actualmente la sanitización es **regex-based**. En M6+ se reemplaza por un modelo NER.

---

## 2. Eviction Policy

| Condición | Acción | Plazo |
|---|---|---|
| `confidence_level = ANECDOTAL` | Expiración automática | 90 días desde `created_at` |
| `confidence_level = PRELIMINARY` | Expiración automática | 180 días desde `created_at` |
| `confidence_level = PREDICTIVE` | Sin TTL | Revisión manual quarterly |
| `relevance_score < 0.3` durante 3 meses consecutivos | Mover a tabla `archived_insights` | Al cumplir el mes 3 |
| Fábrica origen eliminada | Marcar `orphaned=True` | Inmediato; purgar tras 30 días |

La columna `expires_at` en `outcome_insights` materializa el TTL para que un cron job nocturno ejecute la evicción. `PREDICTIVE` tiene `expires_at = NULL`.

---

## 3. Activation Criteria

La Outcome DB pasa de `writable=False` a `writable=True` cuando se cumplen **todos**:

1. **N ≥ 3 fábricas** con ≥ 10 días de operación continua cada una
2. **Eval harness maduro**: ≥ 30 golden cases en `tests/outcome_db/` pasando en CI
3. **`write_gate.py` testeado**: cobertura ≥ 90 % en `tests/outcome_db/test_write_gate.py`
4. **ADR aprobado** documentando la decisión de activación
5. **Review de seguridad** completado por al menos un senior engineer

La flag de control es `OUTCOME_DB_WRITABLE` en el archivo `.env` del orquestador.
Mientras `OUTCOME_DB_WRITABLE=false`, el `write_gate.py` retorna `WriteDecision(allowed=False, reason="M1_MODE: outcome-db inactive")` sin procesar nada.

---

## 4. Cross-Tenant Isolation Rules

### 4.1 Datos privados por fábrica

- Los insights de la fábrica A **nunca** son visibles desde la fábrica B salvo `cross_vertical=True`.
- Row-Level Security (RLS) en PostgreSQL aplica `factory_id = current_setting('app.current_factory_id')` en `SELECT`.
- Las queries deben siempre setear `SET app.current_factory_id = '<uuid>'` antes de leer.

### 4.2 Insights cross-vertical

- `cross_vertical=True` permite que el insight aparezca en queries de otras fábricas.
- **Condición obligatoria**: el `content` debe haber sido revisado manualmente por un humano para eliminar datos propietarios antes de marcar `cross_vertical=True`.
- El `write_gate.py` no puede marcar `cross_vertical=True` automáticamente. Solo lectura post-review.

### 4.3 Audit trail

- Toda lectura de un insight por una fábrica distinta a la origen se registra en `factory_access_log`.
- El log incluye: `reader_factory_id`, `insight_id`, `accessed_at`, `query_context` (hash).

### 4.4 Data residency

- En M1, todos los datos residen en una única instancia PostgreSQL.
- En M12+, cada fábrica con contrato DEDICATED tendrá su propia instancia (ver ADR pendiente).

---

## 5. Anti-patterns Prohibidos (Cap 14 §14.7)

| Anti-pattern | Por qué está prohibido |
|---|---|
| Escribir insights con PII embebido | Cross-user leakage |
| Incrementar `relevance_score` automáticamente sin evidencia | Memory poisoning |
| Escribir sin TTL para niveles ANECDOTAL/PRELIMINARY | Runaway growth |
| Compartir insights entre fábricas sin `cross_vertical=True` + review | Cross-tenant leakage |
| Activar `writable=True` antes de los activation criteria | Datos de baja calidad envenenan el corpus |

---

_Versión: 1.0 — Sprint M1 — Fase 4 Reganti_
_Próxima revisión: cuando se cumpla activation criteria o al cierre de Sprint M6_
