# Production Deployment Checklist

> Lista paso-a-paso para llevar el proyecto de `localhost` a producción.
> Imprimí esta página antes de empezar — tachá items conforme avanzas.

**Tiempo estimado total:** ~60 min si es la primera vez.

---

## ⚙️ Pre-deploy (local — antes de tocar Railway/Vercel)

- [ ] `bash scripts/preflight.sh` — todos los checks PASS o WARN aceptable
- [ ] `git status` — working tree clean
- [ ] `git push origin master` — todo subido a GitHub
- [ ] `make health` — backend local OK (opcional pero recomendado)
- [ ] **Tienes acceso a:**
  - [ ] Cuenta Railway con plan Hobby ($5/mes mínimo)
  - [ ] Cuenta Vercel (free tier sobra)
  - [ ] Cuenta `circles.fof.ai@gmail.com` con 2FA habilitado
  - [ ] Anthropic API key (`sk-ant-api03-...`)
  - [ ] OpenAI API key (`sk-proj-...`) — opcional pero recomendado
  - [ ] Google AI Studio API key — opcional para fact-check

---

## 🚂 Backend (Railway) — ~20 min

### Paso 1: Crear proyecto

- [ ] https://railway.app/new
- [ ] **Sign in con Google** usando `circles.fof.ai@gmail.com`
- [ ] **Deploy from GitHub repo** → seleccionar `circles-ai-fof/circle-llc`
- [ ] Autorizar Railway en GitHub si lo pide

### Paso 2: Service settings

- [ ] Root directory: `/` (raíz del repo)
- [ ] Build: dejar default (usa Dockerfile)
- [ ] Start: dejar default (Dockerfile CMD)

### Paso 3: Variables de entorno

En Railway → Variables → New Variable, agregar UNA POR UNA:

**Críticas (obligatorias):**
- [ ] `ANTHROPIC_API_KEY=sk-ant-api03-...`
- [ ] `ALLOWED_EMAILS=circles.fof.ai@gmail.com,jfnunez@asiservy.com,cristian.molina.ia.soporte@gmail.com`
- [ ] `DATABASE_PATH=/data/circle_llc.db`
- [ ] `GATE_RUN_SECRET=` ← generar con `openssl rand -hex 32`
- [ ] `DASHBOARD_URL=https://YOUR-VERCEL-URL.vercel.app` (placeholder por ahora)

**Opcionales (mejoran funcionalidad):**
- [ ] `OPENAI_API_KEY=sk-proj-...` ← activa ensemble vote en gate_decider
- [ ] `GOOGLE_API_KEY=AIza...` ← activa fact-check con Gemini
- [ ] `ENSEMBLE_GATE_ENABLED=true`
- [ ] `IDEA_ENRICHER_RESEARCH=true`
- [ ] `FACT_CHECK_ENABLED=true`

**SMTP (para weekly digest — opcional):**
- [ ] `SMTP_HOST=smtp.gmail.com`
- [ ] `SMTP_PORT=587`
- [ ] `SMTP_USER=circles.fof.ai@gmail.com`
- [ ] `SMTP_PASSWORD=` ← Gmail App Password de 16 dígitos (ver paso 5)
- [ ] `DIGEST_FROM=Circle LLC <circles.fof.ai@gmail.com>`
- [ ] `DIGEST_TO=circles.fof.ai@gmail.com`

**CORS (configurable post-Vercel):**
- [ ] `EXTRA_CORS_ORIGINS=https://YOUR-VERCEL-URL.vercel.app`

### Paso 4: Volumen persistente

- [ ] Railway → Storage → New Volume
- [ ] **Mount path:** `/data`
- [ ] **Size:** 1 GB
- [ ] Asociar al service del backend
- [ ] Verificar: en el deploy log, la DB se inicializa en `/data/circle_llc.db`

### Paso 5: Gmail App Password (si querés SMTP)

- [ ] https://myaccount.google.com/security
- [ ] **2-Step Verification** debe estar **ON**
- [ ] **App passwords** → Generate
- [ ] App name: `circle-llc-smtp`
- [ ] Copiá los 16 dígitos (formato: `xxxx xxxx xxxx xxxx`)
- [ ] Pegalos SIN ESPACIOS en `SMTP_PASSWORD` en Railway

### Paso 6: Verificar deploy

- [ ] Railway → tu proyecto → ver Deploy Logs
- [ ] Confirmar: `INFO: Started server process` aparece sin errors
- [ ] Railway te asigna una URL: `https://circle-llc-production-xxxx.up.railway.app`
- [ ] **Probá:**
  ```bash
  curl https://<RAILWAY_URL>/api/v1/health
  # Esperado: {"status":"ok","mode":"live","persistent_storage":true,...}
  ```
- [ ] Si `mode=mock`: falta `ANTHROPIC_API_KEY`
- [ ] Si `persistent_storage=false`: falta volumen `/data`

---

## 🎨 Dashboard (Vercel) — ~15 min

### Paso 7: Crear proyecto

- [ ] https://vercel.com/new
- [ ] Sign in con `circles.fof.ai@gmail.com` (Google)
- [ ] **Import Git Repository** → `circles-ai-fof/circle-llc`
- [ ] Authorize Vercel en GitHub

### Paso 8: Configure project

- [ ] **Framework Preset:** Next.js (auto-detectado)
- [ ] **Root Directory:** `dashboard` ← **OBLIGATORIO, no dejar `/`**
- [ ] **Build Command:** `next build` (default)
- [ ] **Output Directory:** `.next` (default)
- [ ] **Install Command:** `npm install` (default)

### Paso 9: Variables de entorno

- [ ] `NEXT_PUBLIC_API_URL=https://<RAILWAY_URL>` ← URL real del paso 6, sin `/` al final

### Paso 10: Deploy

- [ ] Click **Deploy**
- [ ] Esperar ~2 min de build
- [ ] Vercel te asigna: `https://circle-llc-xxxx.vercel.app`

### Paso 11: Actualizar CORS del backend

- [ ] Volver a Railway → Variables
- [ ] Editar `EXTRA_CORS_ORIGINS` = URL real de Vercel
- [ ] Editar `DASHBOARD_URL` = misma URL de Vercel
- [ ] Railway re-deploya automáticamente (~1 min)

### Paso 12: Smoke test end-to-end

- [ ] Abrí `https://<VERCEL_URL>/login`
- [ ] Email: `circles.fof.ai@gmail.com` (debe estar en `ALLOWED_EMAILS`)
- [ ] Esperado: login OK → redirige a home
- [ ] Si error CORS: verificar `EXTRA_CORS_ORIGINS` en Railway
- [ ] Si 401: el email no está en `ALLOWED_EMAILS`

---

## ⏰ GitHub Actions (crons) — ~5 min

### Paso 13: Generar token para crons

- [ ] Login al backend deployed:
  ```bash
  curl -X POST https://<RAILWAY_URL>/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"circles.fof.ai@gmail.com"}' | jq -r .token
  ```
- [ ] Copiá el token (válido 7 días)

### Paso 14: Configurar GitHub Secrets

- [ ] https://github.com/circles-ai-fof/circle-llc/settings/secrets/actions
- [ ] **New repository secret:**
  - [ ] `AUTO_SCAN_API_URL` = `https://<RAILWAY_URL>` (sin `/` al final)
  - [ ] `AUTO_SCAN_TOKEN` = el token del paso 13

### Paso 15: Disparar manual para verificar

- [ ] https://github.com/circles-ai-fof/circle-llc/actions
- [ ] **Hunter Auto-Scan** workflow → Run workflow → branch master
- [ ] Esperar ~30s
- [ ] Verificar: corre verde con output `HTTP 200`
- [ ] **Weekly Digest** workflow → Run workflow → branch master
- [ ] Verificar: corre verde, output `Enviado a N destinatarios` o
      `SMTP no configurado` (si no configuraste SMTP)

---

## 🌱 Bootstrap inicial — ~5 min

### Paso 16: Seed fuentes de ejemplo

- [ ] Generar token (puede ser el mismo del paso 13 si no expiró):
  ```bash
  TOKEN=$(curl -s -X POST https://<RAILWAY_URL>/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"circles.fof.ai@gmail.com"}' | jq -r .token)
  ```
- [ ] Insertar 17 fuentes:
  ```bash
  API_URL=https://<RAILWAY_URL> BEARER_TOKEN=$TOKEN \
    python scripts/seed-example-sources.py
  ```
- [ ] Verificar en dashboard: `/cazar/fuentes` muestra 17 fuentes

### Paso 17: Primer scan manual (opcional)

- [ ] En `/cazar/fuentes` clickear **▶ Escanear ahora**
- [ ] Esperar ~30s (depende de cuántas fuentes responden)
- [ ] Verificar: `/cazar/senales` muestra las primeras señales capturadas

### Paso 18: Primer run (opcional, cuesta $0.06)

- [ ] Abrir `/cazar` (home del founder)
- [ ] Click **Nueva fábrica**
- [ ] Topic: `fintech para PYMEs Ecuador con reconciliación bancaria automática`
- [ ] Ejecutar — espera ~60s
- [ ] Verificar: verdict aparece (pass/kill/iterate) con confidence + landing
- [ ] Visible en `/fabricas` + home

---

## 🩺 Verificación final

### Paso 19: `/admin/diagnose-deploy`

- [ ] Abrir `https://<VERCEL_URL>/admin/diagnose-deploy`
- [ ] Esperado: **READY FOR PRODUCTION** (verde)
- [ ] Si hay warnings, revisá fix_hint de cada uno y aplicá

### Paso 20: `/admin/status`

- [ ] Abrir `https://<VERCEL_URL>/admin/status`
- [ ] Verificar:
  - [ ] **Mode:** `live`
  - [ ] **Storage:** `persistent`
  - [ ] **Agentes:** 13 listados
  - [ ] **CORS origins:** ≥7 incluyendo tu Vercel URL
  - [ ] **Allowlist emails:** ≥1

---

## 🎉 Done

Si llegaste hasta acá:
- ✅ Backend live en `https://<RAILWAY_URL>`
- ✅ Dashboard live en `https://<VERCEL_URL>`
- ✅ Auto-scan corre cada 6h automático
- ✅ Weekly digest llega cada lunes 12 UTC
- ✅ 17 fuentes capturando señales 24/7
- ✅ `/admin/diagnose-deploy` muestra **READY**

**Costo mensual aproximado:**
- Railway Hobby: $5/mes
- Vercel free tier: $0
- LLMs (100 runs/mes a $0.06): $6/mes
- **Total: ~$11/mes**

## 🚨 Troubleshooting rápido

| Síntoma | Fix |
|---|---|
| `mode: mock` en /api/v1/health | Falta `ANTHROPIC_API_KEY` en Railway |
| `persistent_storage: false` | Volumen `/data` no montado |
| Login devuelve 403 | Email no está en `ALLOWED_EMAILS` |
| CORS error en browser | Falta `EXTRA_CORS_ORIGINS=<vercel_url>` en Railway |
| Cron Hunter-Auto-Scan en rojo | Falta `AUTO_SCAN_API_URL` o `AUTO_SCAN_TOKEN` en GH Secrets |
| Cron Weekly-Digest en warning | Faltan SMTP_* envs (opcional) |
| `npm run build` falla en Vercel | Root directory NO está en `dashboard` |
| Backend 500 en `/api/v1/stats` | Volumen `/data` no se montó — la DB se pierde al reiniciar |

---

## 📞 Si algo se rompe

1. Logs Railway: dashboard → Deployments → click el latest → Logs
2. Logs Vercel: dashboard → Deployments → click → Runtime Logs
3. Logs GH Actions: github.com/circles-ai-fof/circle-llc/actions
4. Re-run `/admin/diagnose-deploy` — los fix_hints suelen ser concretos
5. Email owner: `circles.fof.ai@gmail.com`
