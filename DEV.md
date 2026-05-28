# DEV.md — Guía de desarrollo local

Para producción ver `DEPLOY.md`. Esta guía es para correr el stack en tu máquina.

## Arranque rápido (un comando)

```powershell
cd D:\CM\IA_2026\ClaudeCode\circle-llc
.\start-local.ps1
```

El script:
1. Mata cualquier proceso colgado en `:8002` y `:3001`.
2. Carga `.env` y exporta `ANTHROPIC_API_KEY` + `ALLOWED_EMAILS` al ambiente.
3. Arranca el backend (uvicorn) en una ventana nueva de PowerShell.
4. Espera al `/api/v1/health` (máx 30s).
5. Arranca el dashboard (`npm run dev`) en otra ventana.

Cuando termine verás:
```
Backend:   http://localhost:8002/api/v1/health
Dashboard: http://localhost:3001/login
```

Email para login: cualquiera de los 3 en `ALLOWED_EMAILS` de `.env`.

### Variantes

```powershell
.\start-local.ps1 -CleanDashboard   # también borra .next antes
.\start-local.ps1 -Stop             # detiene los servicios
```

## Arranque manual (si no usas PowerShell)

### Backend

```bash
cd D:\CM\IA_2026\ClaudeCode\circle-llc

# Git Bash / WSL: exporta las vars del .env primero
source <(grep -E "^(ANTHROPIC_API_KEY|OPENAI_API_KEY|GOOGLE_API_KEY|ALLOWED_EMAILS|GEMINI_MODEL|ENSEMBLE_GATE_ENABLED|IDEA_ENRICHER_RESEARCH|FACT_CHECK_ENABLED|DATABASE_PATH|GATE_RUN_SECRET)=" .env | sed 's/^/export /')

# Arranca uvicorn
python -m uvicorn orchestrator.api:app --reload --port 8002 --host 127.0.0.1
```

Verifica:
```bash
curl http://localhost:8002/api/v1/health
# {"status":"ok","version":"0.1.0","mode":"live", ...}    ← mode debe ser "live"
```

Si `mode` dice `"mock"`, las vars no se exportaron al proceso de Python.

### Dashboard

```bash
cd D:\CM\IA_2026\ClaudeCode\circle-llc\dashboard

# .env.local debe existir con NEXT_PUBLIC_API_URL=http://localhost:8002
cat .env.local

# Arranca dev server
npm run dev:clean   # limpia .next + arranca, recomendado primer arranque del día
# o
npm run dev         # subsecuentes
```

Verifica: http://localhost:3001/login

## Troubleshooting

### "Internal Server Error" en cualquier ruta del dashboard

Causa común: `.next/` corrupto después de un `next build`. El dev server
intenta servir chunks de prod que tienen IDs distintos a los del dev.

Fix:
```bash
cd dashboard
npm run clean       # borra .next, tsconfig.tsbuildinfo, node_modules/.cache
npm run dev
```

### Login: "Aún no estás habilitado"

Causa: el backend no tiene tu email en `ALLOWED_EMAILS`. Probablemente
arrancó sin cargar `.env`.

Verifica:
```bash
curl http://localhost:8002/api/v1/diagnostic | python -m json.tool
# Mira "ANTHROPIC_API_KEY: not set" en el log del backend
```

Fix: usar `start-local.ps1` o exportar las vars manualmente (ver arriba).

### Login: "Network error"

Causa: el dashboard no puede llegar al backend.

1. Verifica que el backend corre en `:8002` (no en `:8000` que es otro proyecto):
   ```bash
   netstat -ano | findstr ":8002"
   ```
2. Verifica `.env.local` del dashboard:
   ```bash
   cat dashboard/.env.local
   # NEXT_PUBLIC_API_URL=http://localhost:8002
   ```
3. Si cambiaste el `.env.local`, reinicia `npm run dev` (NEXT_PUBLIC_* requiere
   rebuild del dev server).

### "Mock signal from rss" en /cazar/señales

Estas son señales viejas de antes del fix del scanner. Solución:
1. Click **🗑️ Borrar mocks** en la página
2. Click **🔄 Re-escanear limpio** para regenerar con títulos reales

### El backend dice "EvidenceGateWorkflow starting in mock_mode"

`ANTHROPIC_API_KEY` no está en el ambiente del proceso Python. uvicorn lo
carga al iniciar la app — si no está, todo el workflow corre en modo demo.

Fix: usar `start-local.ps1` o exportar la var ANTES de arrancar uvicorn
(uvicorn `--env-file` carga DESPUÉS del import de la app, demasiado tarde
para el init de `EvidenceGateWorkflow`).

## Endpoints útiles para debug

```bash
# Estado del backend
curl http://localhost:8002/api/v1/health
# {status, version, mode, persistent_storage, autoscan_enabled, server_time}

# Diagnóstico público (sin auth)
curl http://localhost:8002/api/v1/diagnostic

# Stats privados (requiere auth)
TOKEN=$(curl -s -X POST http://localhost:8002/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"crisan312@hotmail.com"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -H "Authorization: Bearer $TOKEN" http://localhost:8002/api/v1/stats
```

## Tests

```bash
cd D:\CM\IA_2026\ClaudeCode\circle-llc
python -m pytest           # corre suite completa (~20s en mock mode)
python -m pytest -k hunter # filtra por keyword
python -m pytest --co      # lista todos los tests sin correrlos
```

## Comandos git para esta máquina

El repo está en `circles-ai-fof/circle-llc`. La cuenta con write access es
`circles.fof.ai@gmail.com` (NO `crisan312`).

Si `git push` falla con 403:
```bash
# Limpia credentials cacheadas
cmd /c "cmdkey /delete:LegacyGeneric:target=git:https://github.com"
# Próximo push pedirá username + PAT
# Username: circles-ai-fof
# Password: tu PAT (NO la contraseña del Gmail)
```

Genera un PAT en https://github.com/settings/tokens?type=beta para `circles.fof.ai@gmail.com`
con Contents: Read and write sobre el repo `circle-llc`.

## Estructura del proyecto

```
circle-llc/
├── orchestrator/        ← backend FastAPI (35 endpoints, 8 agentes activos)
│   ├── api.py           ← 2226 LOC (refactor diferido a M4)
│   ├── core/            ← storage, anti_bot, source_fetcher, webhooks
│   ├── agents/          ← idea_hunter, idea_analyzer, source_scanner, ...
│   ├── workflows/       ← evidence_gate.py (chassis lineal)
│   ├── evals/           ← golden_cases (180) + rubrics + run_calibration.py
│   └── decisions/       ← ADR-001 .. ADR-017
├── dashboard/           ← Next.js 15 + TypeScript
│   ├── app/             ← 11 páginas: login, cazar, fuentes, señales, ...
│   ├── components/      ← Sidebar, AuthGuard, etc.
│   └── lib/auth.ts      ← authFetch, getSession, login/logout
├── landing/             ← Next.js 15 — circles-ai.ai público
├── tests/               ← pytest (483 tests verdes)
├── .github/workflows/   ← evals.yml (CI) + auto-scan.yml (cron 6h)
├── Dockerfile           ← multistage para Railway
├── railway.json         ← deploy config
└── DEV.md / DEPLOY.md   ← esta guía / guía de producción
```

## Performance / costos

| Acción | Costo |
|---|---|
| Login | $0 |
| GET /signals, /stats, /diagnostic | $0 |
| POST /signals/{id}/analyze | ~$0.005 (Haiku) |
| POST /signals/analyze-batch (10 señales) | ~$0.05 |
| POST /gate/run-from-sources | ~$0.06 (Sonnet ensemble) |
| Auto-scan en background (6h) | $0 si scoring rule-based, ~$0.001/source si LLM |

## Lecturas recomendadas

- `CLAUDE.md` — overview del proyecto
- `orchestrator/decisions/ADR-017.md` — última auditoría de seguridad/DX
- `orchestrator/rulebook.md` — R01-R29 (reglas anti-pattern)
- `DEPLOY.md` — Railway + Vercel para producción
