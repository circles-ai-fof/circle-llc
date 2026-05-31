# Contributing — Circle LLC FoF

Closed-beta hasta M7+. Este documento es para colaboradores aprobados (en
`ALLOWED_EMAILS` del `.env` del backend deployed).

---

## Setup local

```bash
# 1. Clone + deps
git clone https://github.com/circles-ai-fof/circle-llc.git
cd circle-llc
make install

# 2. Config
cp orchestrator/.env.example .env
# Editá .env con tus API keys (mínimo: ANTHROPIC_API_KEY + ALLOWED_EMAILS)

# 3. Arrancar
make dev               # backend :8002 + dashboard :3001

# 4. Smoke test
make health            # 14/14 ✓ esperado
make test              # 765 tests verdes esperado
```

Para verificar deploy-readiness: `/admin/diagnose-deploy` muestra issues
y fix_hints accionables.

---

## Reglas del proyecto (rulebook)

29 reglas viven en `orchestrator/rulebook.md`. Las que importan al
contribuir:

| Regla | Qué exige |
|---|---|
| **R06** | `mock_mode=True` obligatorio en CI (sin API keys reales) |
| **R07** | Schema validation Pydantic en outputs de agentes |
| **R08** | Prompt caching activo en todos los system prompts |
| **R11** | **NO** crear un Governor que enrute agentes dinámicamente |
| **R12** | ≥30 golden cases antes de activar un agente nuevo |
| **R28/R29** | Scope explícito por agente sin overlap (verificado en CI) |

Si tu PR viola R11 (Governor) o R12 (cases insuficientes), el reviewer
lo va a bloquear con link al rulebook.

---

## Cómo añadir un agente nuevo

Patrón demostrado 6 veces (TrendGapAnalyzer M5.0→M5.1, NicheScout
M5.2→M5.8, EventScorer M5.3→M5.9, SleeperDetector M5.4→M5.10,
ArbitrageEval M5.5→M5.11, MultiAgentConsensus M6.0→M6.0b):

### Phase 1 — experimental (10 cases mínimo)

```
1. orchestrator/agents/<nombre>.py
   class TuAgenteAgent(BaseAgent):
       AGENT_NAME = "tu_agente"
       AGENT_VERSION = "0.1.0"
       EXPERIMENTAL = True
       
       @property
       def system_prompt(self) -> str:
           return _SYSTEM
       
       def analyze(self, ...) -> TuAgenteOutput:
           if self._mock_mode:
               return self._mock_analyze(...)
           prompt = self._build_prompt(...)
           return self._extract_json(self._call(prompt))

2. orchestrator/schemas/api.py
   Pydantic Request + Response

3. orchestrator/api.py
   @app.post("/api/v1/<scope>/...") con auth + validation

4. tests/api/test_hunter.py
   10 golden cases mock_mode (la barrera mínima)

5. orchestrator/agents/SCOPES.md
   Nueva fila explicando el scope exclusivo + counter 10/30

6. orchestrator/decisions/ADR-XXX.md
   Decisión + alternatives considered + roadmap
```

### Phase 2 — promover a active(on-demand) (30 cases totales)

```
1. Añadir 20 cases más cubriendo:
   - determinism (mismo input → mismo output en mock)
   - schema caps (max_length boundary tests)
   - range/calibration (confidence [0, 0.85] monotónica)
   - recommendation logic (valores en set válido)
   - localization (español detectable)
   - cost/mock invariants (cost=0.0 en mock)
   - response shape (dict keys exactos)
   - robustness (empty, max, special chars)
   - domain-specific (reglas únicas del agente)

2. EXPERIMENTAL = False
   AGENT_VERSION = "1.0.0"  # bump major

3. SCOPES.md: experimental 10/30 → ACTIVE 30/30 ✅ v1.0.0

4. ADR explícito documentando la promoción + criterios futuros para
   active(workflow) (sin métrica gating no se promueve más allá)
```

### Phase 3 — active(workflow) (futuro, M6+)

Requiere:
- N≥100 invocaciones reales del founder en producción
- Telemetría comparando verdict CON vs SIN tu agente
- Demostrar no-degradación del verdict accuracy
- ADR explícito de integración al EvidenceGateWorkflow

---

## Cómo añadir un source kind nuevo

```
1. orchestrator/core/source_fetcher.py
   def fetch_<kind>(target: str, max_items: int) -> List[FetchedItem]:
       # use stdlib urllib o requests si ya está
       # respeta TOS — User-Agent identificable
       
2. fetch_by_kind() dispatch:
   if kind == "<kind>": return fetch_<kind>(target, max_items)

3. orchestrator/schemas/api.py — añadir kind al regex pattern:
   pattern="^(rss|hn|...|<tu_kind>)$"
   (en SourceItem Y en SignalsDeleteByTypeRequest)

4. dashboard/app/cazar/fuentes/page.tsx — añadir a KIND_LABELS,
   KIND_NEEDS_TARGET, KIND_PLACEHOLDERS

5. dashboard/app/cazar/senales/page.tsx — añadir a SOURCE_KINDS array

6. tests/api/test_hunter.py — al menos 3 tests:
   - sources/POST acepta el kind
   - signals?kind=X filter funciona
   - delete-by-type con source_kind=X funciona

7. scripts/seed-example-sources.py — añadir 1 ejemplo a EXAMPLE_SOURCES
```

---

## Convenciones de código

### Python (backend)

- Type hints obligatorios en función signatures (`def foo(x: int) -> str:`)
- Pydantic `BaseModel` para schemas de API (NO dataclass para schemas
  externos — sí para internal data classes)
- snake_case en variables y functions, PascalCase en classes
- Comentarios en español para lógica de negocio; inglés para infra
- Imports ordenados: stdlib → third-party → local (orchestrator)

### TypeScript (frontend)

- `type` para shapes simples, `interface` para shapes extensibles
- Imports relativos solo dentro del mismo dir; usá `@/` para imports cross-dir
- Strings en español en UI; nombres de variables en inglés
- Estilos inline para componentes one-off; `globals.css` solo para
  utilities globales

### Commits

Formato:
```
<tipo>(<sprint>): <título corto>

<body opcional explicando POR QUÉ>

<footer con tests/regresiones>
```

Ejemplos:
- `feat(M6.1): Weekly Digest — HTML + JSON + texto`
- `fix(M4.5b): autonomy via POST alias`
- `docs(README): primer README.md del repo`
- `chore(M7.8): eliminar mockData.ts`

Tipos: feat / fix / docs / chore / refactor / test / perf

---

## Testing

```bash
make test               # full pytest suite
make test-ui            # TS noEmit del dashboard
make ci                 # ambos (lo que valida GitHub Actions)
```

Antes de PR:
1. ✅ `make ci` verde
2. ✅ `make health` 14/14 ✓ contra backend local
3. ✅ Si añadiste endpoint: confirmá que aparece en
   `tests/test_no_orphan_endpoints.py` (corre auto en CI)
4. ✅ Si añadiste agente: SCOPES.md actualizado + ADR escrito

---

## Filosofía Reganti (AI Builder's Handbook 2026)

Citado en cada ADR. Los caps que más influencian decisiones:

- **Cap 10 §10.3** *"Stay at the simplest level that handles 90% of your cases"*
  → Heurística sin LLM cuando alcance; LLM cuando aporte razonamiento real.
- **Cap 15 §15.1** *"Build multi-agent as exception, not default"*
  → Workflow lineal por default; agentes on-demand para casos puntuales.
- **Cap 15 §15.5** *"Responsibility fuzziness"*
  → SCOPES.md con scope exclusivo verificado por test.

---

## Recursos

- **README.md** — overview + quick start
- **DEPLOY.md** — guía paso a paso para deploy
- **CLAUDE.md** — contexto para Claude Code
- **docs/architecture.md** — diagramas del sistema
- **docs/openapi.json** — spec OpenAPI 3.1.0
- **orchestrator/rulebook.md** — las 29 reglas con rationale
- **orchestrator/agents/SCOPES.md** — scope exclusivo por agente
- **orchestrator/decisions/ADR-XXX.md** — 27 ADRs con alternatives

Si hay duda de patrón: mirá ADR-022 a ADR-027 (los más recientes,
con el patrón experimental → active demostrado).

---

## Contacto

- **Owner:** Cristian Molina — `circles.fof.ai@gmail.com`
- **Bugs / feature requests:** abrir issue en
  https://github.com/circles-ai-fof/circle-llc/issues
- **Email del proyecto:** `circles.fof.ai@gmail.com`
