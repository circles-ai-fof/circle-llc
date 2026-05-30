# Deploy Guide — circles-ai.ai Production

This is the M2 deployment checklist. Frontend lives on **Vercel**, backend on **Railway**.

```
┌──────────────────────────┐         ┌────────────────────────────┐
│  Vercel                  │  HTTPS  │  Railway                   │
│  - landing  (Next.js)    │ ──────▶ │  - FastAPI :8000           │
│  - dashboard (Next.js)   │         │  - SQLite on /data volume  │
└──────────────────────────┘         └────────────────────────────┘
       circles-ai.ai                       circle-llc-api.railway.app
```

---

## Backend → Railway

### 1. Create the Railway project

1. Go to https://railway.com → **New Project** → "Deploy from GitHub repo"
2. Select `circles-ai-fof/circle-llc`
3. Railway detects the `Dockerfile` automatically (or use `railway.json`)
4. Wait for the first build (~3 min)

### 2. Add a persistent volume for SQLite

Without this, lead/run data is lost on every redeploy.

1. In the service settings → **Volumes** → **New Volume**
2. Mount path: `/data`
3. Size: 1 GB is plenty for M2

### 3. Configure environment variables

In Railway → service → **Variables**, paste:

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-proj-...
GOOGLE_API_KEY=AIza...
GEMINI_MODEL=gemini-flash-latest

ENSEMBLE_GATE_ENABLED=true
IDEA_ENRICHER_RESEARCH=true
FACT_CHECK_ENABLED=true

DATABASE_PATH=/data/circle_llc.db

# Anti-bot (R26)
GATE_RUN_SECRET=<generate-a-long-random-string>
# TURNSTILE_SECRET_KEY=<add-after-creating-turnstile-site>

EXTRA_ALLOWED_ORIGINS=https://circles-ai.ai,https://www.circles-ai.ai,https://dashboard.circles-ai.ai

# Closed-beta dashboard auth (R27 / ADR-010)
# Comma-separated emails — these are the only users who can access the dashboard.
# Anyone NOT on this list gets 403 + their attempt is logged for audit.
ALLOWED_EMAILS=crisan312@hotmail.com,jfnunez@asiservy.com,cristian.molina.ia.soporte@gmail.com

# Cazador autónomo (ADR-014 follow-up) — opcional
# Cada cuánto el background loop escanea TODAS las fuentes activas.
# 0 (default) = desactivado. Cuando lo prendas: >= 15 min (el server clampa).
# Recomendado en prod: 360 (6 h). Subir gradualmente si la calidad mejora.
AUTOSCAN_INTERVAL_MINUTES=0
```

**Important**: generate `GATE_RUN_SECRET` with `openssl rand -hex 32` — anyone with this header can run \$0.06 calls or view full lead emails.

### 4. Generate a public domain

Railway → service → **Networking** → **Generate Domain**.
You'll get something like `circle-llc-api-production.up.railway.app`.

### 5. Verify

```bash
curl https://<your-railway-domain>/api/v1/health
# Expect: { "status": "ok", ... }
```

---

## Frontend → Vercel

### A. Landing (public site, already live as circles-ai.ai)

1. In the Vercel project that points at the repo, **Settings → Environments → Production → Environment Variables → Add**:
   ```
   NEXT_PUBLIC_API_URL=https://<your-railway-domain>
   ```
   Mark Production + Preview + Development.

2. **Deployments → ⋯ → Redeploy** (NEXT_PUBLIC_* requires a rebuild).

3. Verify: open `https://circles-ai.ai/f/techpulse-latam`, fill form, see Railway log `lead captured slug=techpulse-latam email=...`.

### B. Dashboard (admin panel)

The dashboard lives in `dashboard/` and is a **separate Vercel project**.

1. **https://vercel.com/new** → Import the same `circles-ai-fof/circle-llc` repo
2. In the import wizard, set **Root Directory** to `dashboard`
   (Vercel autodetects `dashboard/vercel.json` and Next.js framework.)
3. Framework: Next.js (auto)
4. Add env vars (Production + Preview + Development checked):
   ```
   NEXT_PUBLIC_API_URL=https://<your-railway-domain>
   ```
5. Deploy
6. Optionally assign a domain like `dashboard.circles-ai.ai`:
   - Project → Domains → Add → `dashboard.circles-ai.ai`
   - On your DNS: add a CNAME `dashboard` → `cname.vercel-dns.com`

#### Post-deploy smoke checklist

After the dashboard is live, verify these 6 things in order:

| # | URL                                  | What to expect |
|---|--------------------------------------|----------------|
| 1 | `/login`                             | "Solicitar acceso" form. Type one of `ALLOWED_EMAILS`. |
| 2 | After login                          | Redirected to `/cazar`. Top-right shows your email + logout. |
| 3 | `/cazar/fuentes`                     | "Fuentes" list (seeded sources from `seed_sources.py`). |
| 4 | `/cazar/señales`                     | Empty until you click "↻ Refresh" on a source or wait for autoscan. |
| 5 | `/cazar/señales` → dropdowns         | "Ordenar" + "Fuente" filters work. Server returns 422 if you tamper. |
| 6 | `/cazar` (pipeline)                  | 5 columns. Auto-refresh every 8s. Empty until your first run. |

If `/cazar` is blank with `connect-src` CSP errors in the browser console:
the `NEXT_PUBLIC_API_URL` env var is missing → Vercel Settings → Env Vars →
add → **Redeploy** (NEXT_PUBLIC_* needs a rebuild, env reload is not enough).

#### Don't forget: CORS on Railway side

The dashboard's domain MUST be on the backend's allowed origins, or
every fetch will 403/CORS-fail silently. In Railway → service → Variables:

```
EXTRA_ALLOWED_ORIGINS=https://dashboard.circles-ai.ai,https://<vercel-preview-domain>.vercel.app
```

(One line, comma-separated. Restart the service.)

### Verify lead capture end-to-end

After both deploys + Railway has the env vars + landing has NEXT_PUBLIC_API_URL:

1. Submit a lead at `circles-ai.ai/f/techpulse-latam`
2. Open `dashboard.circles-ai.ai/leads` (or the dashboard URL)
3. The lead should appear in the list (email masked)
4. Paste the `GATE_RUN_SECRET` in the admin input → emails become visible

---

## Cost expectations

| Component | Cost |
|---|---|
| Railway Starter plan | $5/month (includes 500 hours + 1 GB volume) |
| Vercel Hobby | $0 (covers landing + dashboard) |
| Anthropic / OpenAI / Gemini | ~$0.06 per gate run, ~$0 for landing traffic |
| Cloudflare Turnstile | $0 (free for unlimited sites) |
| **Total fixed** | **$5/month** + LLM usage |

---

## Operational runbook

| Symptom | Action |
|---|---|
| Bot spam on /leads | Lower `RL_FORM_BURST_MAX` env var (no redeploy) |
| /gate/run getting abused | Set `GATE_RUN_SECRET`, share only with internal callers |
| LLM bill spiking | Check Railway logs for `gate run started` frequency; tighten `RL_LLM_DAILY_MAX` |
| Lead data wrong | `railway run sqlite3 /data/circle_llc.db "SELECT * FROM leads"` |
| Need to reset SQLite | `railway run rm /data/circle_llc.db` then restart service |

---

## Sprint M3 migration (when N>=3 factories)

- Replace SQLite with Postgres + pgvector (Supabase or Railway PG)
- Set `OUTCOME_DB_WRITABLE=true`
- Migrate `leads` and `gate_runs` tables via `outcome-db/schema.sql`
- Update `storage.py` to use SQLAlchemy with the existing schema

---

## Anexo M4.10 — Deploy paso a paso con `circles.fof.ai@gmail.com`

`circles.fof.ai@gmail.com` es la **cuenta dueña del proyecto Circle LLC**:
- Linkeada al GitHub user `circles-ai-fof` (dueño del repo)
- Será la cuenta que firme commits, deploys (Railway + Vercel) y emails
- Es la primera en `ALLOWED_EMAILS` del backend (login al dashboard)

Las otras cuentas (`crisan312@hotmail.com`, `jfnunez@asiservy.com`,
`cristian.molina.ia.soporte@gmail.com`) son colaboradores aprobados
para el closed-beta.

### Backend (Railway)

1. https://railway.app/new → Sign in con `circles.fof.ai@gmail.com`
   (botón "Sign in with Google")
2. **Deploy from GitHub repo** → `circles-ai-fof/circle-llc`
3. Si Railway pide acceso al repo, autoriza desde GitHub
4. Service settings:
   - **Root directory:** `/` (raíz del repo)
   - **Build:** `pip install -r orchestrator/requirements.txt`
   - **Start:** `python -m uvicorn orchestrator.api:app --host 0.0.0.0 --port $PORT`
5. Variables (Railway UI → Variables) — copia las críticas de tu `.env`:
   ```
   ANTHROPIC_API_KEY=…
   OPENAI_API_KEY=…
   GOOGLE_API_KEY=…
   ALLOWED_EMAILS=circles.fof.ai@gmail.com,crisan312@hotmail.com,jfnunez@asiservy.com,cristian.molina.ia.soporte@gmail.com
   DATABASE_PATH=/data/circle.db
   GATE_RUN_SECRET=<openssl rand -hex 32>
   ENSEMBLE_GATE_ENABLED=true
   ```
6. **Volumen:** Railway → Volumes → New Volume, mount path `/data`, 1 GB
7. Probar: `curl https://<URL_RAILWAY>/api/v1/health` → `{"status":"ok"}`

### Dashboard (Vercel)

1. https://vercel.com/new → Sign in con `circles.fof.ai@gmail.com`
2. **Import** → `circles-ai-fof/circle-llc`
3. Configure:
   - **Framework:** Next.js
   - **Root Directory:** `dashboard` ← OBLIGATORIO (el repo es monorepo)
   - **Build:** `next build` (default)
4. Variables (Vercel UI):
   ```
   NEXT_PUBLIC_API_URL=https://<URL_RAILWAY>
   ```
5. Probar: abre la URL de Vercel → debe pintar `/login` → meter email → entrás.

### Actualizar CORS del backend

Después de saber la URL de Vercel, añade el dominio a `EXTRA_CORS_ORIGINS`
en Railway (en vez de tocar código):
```
EXTRA_CORS_ORIGINS=https://<DOMINIO_VERCEL>.vercel.app
```

Backend re-deploya solo al cambiar la env var.

### Activar el cron auto-scan

1. Generar token (login al backend deployed):
   ```bash
   curl -X POST https://<RAILWAY_URL>/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"circles.fof.ai@gmail.com"}'
   ```
   Copiá `token`.

2. https://github.com/circles-ai-fof/circle-llc/settings/secrets/actions
   - `AUTO_SCAN_API_URL` = URL Railway (sin `/` al final)
   - `AUTO_SCAN_TOKEN` = el token de arriba

3. Próximo run a las `xx:17` cada 6h. Disparar manual:
   ```bash
   gh workflow run hunter-auto-scan.yml
   ```

4. Renovar `AUTO_SCAN_TOKEN` cada 7 días (sesiones expiran).

### Costos esperados

| Servicio | Plan | Costo mensual |
|---|---|---|
| Railway (backend + volume 1GB) | Hobby | ~$5 |
| Vercel (dashboard, free tier) | Hobby | $0 |
| Anthropic / OpenAI / Gemini | pay-as-you-go | depende de uso |
| GitHub Actions cron | gratis | $0 |
| **Total infra fija** | | **~$5/mes** |

### Tiempo estimado

- Railway setup: 15-20 min
- Vercel setup: 10 min
- Configurar CORS + secrets cron: 10 min
- Pruebas end-to-end: 15 min
- **Total: ~1 hora**

### Activar el digest semanal (M6.2)

Si querés que el cron de los lunes envíe el digest semanal por email:

1. **Generar Gmail App Password** (sólo si usás Gmail):
   - Cuenta `circles.fof.ai@gmail.com` → **Security** → 2-step verification (debe estar ON)
   - → **App passwords** → Generate → copia los 16 dígitos sin espacios

2. **Añadir env vars al backend deployed** (Railway → Variables):
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=circles.fof.ai@gmail.com
   SMTP_PASSWORD=<los 16 digitos del App Password>
   DIGEST_FROM=Circle LLC <circles.fof.ai@gmail.com>
   DIGEST_TO=circles.fof.ai@gmail.com,cristian.molina.ia.soporte@gmail.com,jfnunez@asiservy.com
   ```

3. **Verificar manualmente:** http://localhost:3001/digest → botón "📨 Enviar ahora"
   - Si responde "Enviado a N destinatarios" → cron funcionará automático
   - Si responde "SMTP no configurado" → revisar env vars

4. **El cron ya está activo** (`.github/workflows/weekly-digest.yml`).
   Los lunes 12:00 UTC (~7am ET / 9am Ecuador) llama
   POST /api/v1/digest/send. Mientras los SMTP_* no estén configurados
   sale verde con `::warning::` (no spamea fallas).

### Permisos en el repo

`circles.fof.ai@gmail.com` debería ser el email principal del usuario
GitHub `circles-ai-fof` (dueño del repo), por lo que tiene acceso completo
por defecto.

Si necesitas dar acceso a colaboradores adicionales (los otros 3 emails
del closed-beta), invítalos desde:
https://github.com/circles-ai-fof/circle-llc/settings/access
