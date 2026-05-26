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
```

**Important**: generate `GATE_RUN_SECRET` with `openssl rand -hex 32` — anyone with this header can run \$0.06 calls.

### 4. Generate a public domain

Railway → service → **Networking** → **Generate Domain**.
You'll get something like `circle-llc-api-production.up.railway.app`.

### 5. Verify

```bash
curl https://<your-railway-domain>/api/v1/health
# Expect: { "status": "ok", ... }
```

---

## Frontend → Vercel (already deployed)

### 1. Set the API URL env var

In Vercel → both projects (landing + dashboard) → **Settings → Environment Variables**:

```
NEXT_PUBLIC_API_URL=https://<your-railway-domain>
```

Apply to **Production** + **Preview** + **Development**.

### 2. Re-deploy

In Vercel, trigger a new deployment so the env var bakes in (Next.js needs a rebuild for `NEXT_PUBLIC_*`).

### 3. Verify lead capture end-to-end

1. Open `https://circles-ai.ai/f/techpulse-latam` in an incognito window
2. Fill the form, submit
3. In Railway logs, you should see `lead captured slug=techpulse-latam email=...`
4. Hit your API: `GET https://<railway>/api/v1/leads` (TODO — not yet exposed; query SQLite directly via `sqlite3 /data/circle_llc.db "SELECT * FROM leads"`)

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
