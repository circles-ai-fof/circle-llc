#!/usr/bin/env bash
#
# finish-deploy.sh — M8.3 — automated Railway + Vercel deploy
#
# Pre-requisito: AMBOS CLIs autenticados.
#   railway login              (browser OAuth, una vez)
#   vercel login               (browser OAuth, una vez)
#
# Uso:
#   bash scripts/finish-deploy.sh
#
# Lo que hace:
#   1. Valida que ambos CLIs están autenticados
#   2. Lee .env local y prepara las env vars para Railway
#   3. railway init (crea proyecto circle-llc)
#   4. railway up (deploy desde Dockerfile)
#   5. railway variables set ANTHROPIC_API_KEY ...etc
#   6. Obtiene Railway URL
#   7. vercel deploy --prod desde dashboard/
#   8. vercel env add NEXT_PUBLIC_API_URL con URL real de Railway
#   9. Redeploy Vercel para pickear el env var
#  10. Genera token via curl + corre seed-example-sources.py
#  11. Smoke test final de ambos URLs

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ===========================================================================
# Step 0: Auth check
# ===========================================================================

printf "${CYAN}=== finish-deploy.sh — Railway + Vercel automated ===${NC}\n\n"

printf "${CYAN}[0/10] Verificando auth de CLIs...${NC}\n"

RAILWAY_USER=$(railway whoami 2>&1 | head -1)
if echo "$RAILWAY_USER" | grep -qi "unauthorized\|not logged"; then
    printf "${RED}FAIL${NC} Railway CLI no autenticado.\n"
    printf "  Correr en otra terminal: ${YELLOW}railway login${NC}\n"
    printf "  Después volver a correr este script.\n"
    exit 1
fi
printf "  ${GREEN}OK${NC} Railway auth: %s\n" "$RAILWAY_USER"

VERCEL_USER=$(vercel whoami 2>&1 | head -1)
if echo "$VERCEL_USER" | grep -qi "no credentials\|not authenticated"; then
    printf "${RED}FAIL${NC} Vercel CLI no autenticado.\n"
    printf "  Correr: ${YELLOW}vercel login${NC}\n"
    exit 1
fi
printf "  ${GREEN}OK${NC} Vercel auth: %s\n" "$VERCEL_USER"

# ===========================================================================
# Step 1: Load .env
# ===========================================================================

printf "\n${CYAN}[1/10] Cargando .env local...${NC}\n"

if [ ! -f .env ]; then
    printf "${RED}FAIL${NC} .env no existe. Copy orchestrator/.env.example to .env first.\n"
    exit 1
fi

# Load .env into shell so we can use ${ANTHROPIC_API_KEY} etc
set -a
# shellcheck disable=SC1090,SC2046
source <(grep -E '^[A-Z_]+=' .env | sed 's/[[:space:]]*#.*$//')
set +a

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    printf "${RED}FAIL${NC} ANTHROPIC_API_KEY missing in .env.\n"
    exit 1
fi
if [ -z "${ALLOWED_EMAILS:-}" ]; then
    printf "${RED}FAIL${NC} ALLOWED_EMAILS missing in .env.\n"
    exit 1
fi
printf "  ${GREEN}OK${NC} .env loaded\n"

# ===========================================================================
# Step 2: Railway init
# ===========================================================================

printf "\n${CYAN}[2/10] Initializing Railway project...${NC}\n"

if [ -f .railway/config.json ] || [ -f railway.json ]; then
    printf "  ${YELLOW}Already linked to Railway project — skipping init${NC}\n"
else
    railway init --name circle-llc 2>&1 | tail -3 || {
        printf "${RED}FAIL${NC} railway init failed. Check 'railway projects ls'.\n"
        exit 1
    }
    printf "  ${GREEN}OK${NC} Project 'circle-llc' initialized\n"
fi

# ===========================================================================
# Step 3: Set Railway env vars
# ===========================================================================

printf "\n${CYAN}[3/10] Setting Railway env vars...${NC}\n"

# Critical vars
railway variables --set "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY" 2>&1 | tail -1
railway variables --set "ALLOWED_EMAILS=$ALLOWED_EMAILS" 2>&1 | tail -1
railway variables --set "DATABASE_PATH=/data/circle_llc.db" 2>&1 | tail -1
GATE_SECRET=$(openssl rand -hex 32 2>/dev/null || echo "$(date +%s)$(head -c 32 /dev/urandom | base64 | tr -d /+= | head -c 32)")
railway variables --set "GATE_RUN_SECRET=$GATE_SECRET" 2>&1 | tail -1

# Optional vars (only if present in .env)
[ -n "${OPENAI_API_KEY:-}" ] && railway variables --set "OPENAI_API_KEY=$OPENAI_API_KEY" 2>&1 | tail -1
[ -n "${GOOGLE_API_KEY:-}" ] && railway variables --set "GOOGLE_API_KEY=$GOOGLE_API_KEY" 2>&1 | tail -1
[ -n "${ENSEMBLE_GATE_ENABLED:-}" ] && railway variables --set "ENSEMBLE_GATE_ENABLED=$ENSEMBLE_GATE_ENABLED" 2>&1 | tail -1
[ -n "${IDEA_ENRICHER_RESEARCH:-}" ] && railway variables --set "IDEA_ENRICHER_RESEARCH=$IDEA_ENRICHER_RESEARCH" 2>&1 | tail -1
[ -n "${FACT_CHECK_ENABLED:-}" ] && railway variables --set "FACT_CHECK_ENABLED=$FACT_CHECK_ENABLED" 2>&1 | tail -1

# SMTP (only if all 6 are set)
if [ -n "${SMTP_HOST:-}" ] && [ -n "${SMTP_USER:-}" ] && [ -n "${SMTP_PASSWORD:-}" ]; then
    railway variables --set "SMTP_HOST=$SMTP_HOST" 2>&1 | tail -1
    railway variables --set "SMTP_PORT=${SMTP_PORT:-587}" 2>&1 | tail -1
    railway variables --set "SMTP_USER=$SMTP_USER" 2>&1 | tail -1
    railway variables --set "SMTP_PASSWORD=$SMTP_PASSWORD" 2>&1 | tail -1
    [ -n "${DIGEST_FROM:-}" ] && railway variables --set "DIGEST_FROM=$DIGEST_FROM" 2>&1 | tail -1
    [ -n "${DIGEST_TO:-}" ] && railway variables --set "DIGEST_TO=$DIGEST_TO" 2>&1 | tail -1
fi

printf "  ${GREEN}OK${NC} Env vars set\n"

# ===========================================================================
# Step 4: Railway volume
# ===========================================================================

printf "\n${CYAN}[4/10] Configuring Railway volume /data...${NC}\n"
printf "  ${YELLOW}NOTE: Volume creation via CLI may not be supported.${NC}\n"
printf "  ${YELLOW}If backend reports 'persistent_storage: false' after deploy,${NC}\n"
printf "  ${YELLOW}go to Railway dashboard → Storage → New Volume → mount at /data${NC}\n"

# ===========================================================================
# Step 5: Railway up (deploy)
# ===========================================================================

printf "\n${CYAN}[5/10] Deploying backend to Railway (this takes 2-4 min)...${NC}\n"

railway up --detach 2>&1 | tail -5

printf "  ${YELLOW}Esperando que el deploy quede UP...${NC}\n"
sleep 30

# ===========================================================================
# Step 6: Get Railway URL
# ===========================================================================

printf "\n${CYAN}[6/10] Obteniendo Railway URL...${NC}\n"

# Try to get the URL via railway domain or status
RAILWAY_URL=$(railway domain 2>&1 | grep -oE "https://[a-zA-Z0-9.-]+" | head -1)

if [ -z "$RAILWAY_URL" ]; then
    printf "  ${YELLOW}No URL via 'railway domain'. Trying 'railway status'...${NC}\n"
    RAILWAY_URL=$(railway status 2>&1 | grep -oE "https://[a-zA-Z0-9.-]+\.railway\.app" | head -1)
fi

if [ -z "$RAILWAY_URL" ]; then
    printf "${RED}FAIL${NC} No pude obtener Railway URL automáticamente.\n"
    printf "  Buscala manualmente: railway dashboard → tu proyecto → Settings → Networking\n"
    printf "  Cuando la tengas, exportala: ${YELLOW}export RAILWAY_URL=https://...railway.app${NC}\n"
    printf "  Y volvé a correr este script desde aquí.\n"
    exit 1
fi

printf "  ${GREEN}OK${NC} Railway URL: %s\n" "$RAILWAY_URL"

# ===========================================================================
# Step 7: Wait for backend healthy
# ===========================================================================

printf "\n${CYAN}[7/10] Esperando que el backend responda /health...${NC}\n"

TRIES=0
until curl -s --max-time 5 "$RAILWAY_URL/api/v1/health" | grep -q '"status":"ok"'; do
    TRIES=$((TRIES + 1))
    if [ $TRIES -ge 30 ]; then
        printf "${RED}FAIL${NC} Backend no responde después de 5 min.\n"
        printf "  Check logs: ${YELLOW}railway logs${NC}\n"
        exit 1
    fi
    sleep 10
    printf "  Try %d/30...\n" "$TRIES"
done
printf "  ${GREEN}OK${NC} Backend healthy\n"

# Print health body for visibility
HEALTH=$(curl -s "$RAILWAY_URL/api/v1/health")
printf "  Health: %s\n" "$HEALTH"

# ===========================================================================
# Step 8: Vercel deploy
# ===========================================================================

printf "\n${CYAN}[8/10] Deploying dashboard a Vercel...${NC}\n"

cd "$ROOT/dashboard"

# Set env var BEFORE deploy
echo "$RAILWAY_URL" | vercel env add NEXT_PUBLIC_API_URL production 2>&1 | tail -3 || true

# Deploy with --prod and --yes to skip prompts
VERCEL_OUTPUT=$(vercel deploy --prod --yes 2>&1 | tail -20)
echo "$VERCEL_OUTPUT"

VERCEL_URL=$(echo "$VERCEL_OUTPUT" | grep -oE "https://[a-zA-Z0-9.-]+\.vercel\.app" | tail -1)

if [ -z "$VERCEL_URL" ]; then
    printf "${RED}FAIL${NC} No pude extraer Vercel URL del deploy output.\n"
    exit 1
fi

cd "$ROOT"

printf "  ${GREEN}OK${NC} Vercel URL: %s\n" "$VERCEL_URL"

# ===========================================================================
# Step 9: Update Railway CORS para incluir Vercel URL
# ===========================================================================

printf "\n${CYAN}[9/10] Actualizando CORS de Railway para incluir Vercel...${NC}\n"

railway variables --set "EXTRA_CORS_ORIGINS=$VERCEL_URL" 2>&1 | tail -1
railway variables --set "DASHBOARD_URL=$VERCEL_URL" 2>&1 | tail -1
printf "  ${GREEN}OK${NC} CORS + DASHBOARD_URL set. Railway re-deploys automáticamente.\n"

# Wait for re-deploy
sleep 30

# ===========================================================================
# Step 10: Smoke test + seed
# ===========================================================================

printf "\n${CYAN}[10/10] Smoke test + seed inicial...${NC}\n"

# Test backend health
if curl -s --max-time 5 "$RAILWAY_URL/api/v1/health" | grep -q '"status":"ok"'; then
    printf "  ${GREEN}OK${NC} Backend health\n"
else
    printf "  ${RED}WARN${NC} Backend health fallo después de re-deploy\n"
fi

# Test dashboard
if curl -s --max-time 10 -o /dev/null -w "%{http_code}" "$VERCEL_URL/login" | grep -q "200\|307\|308"; then
    printf "  ${GREEN}OK${NC} Dashboard /login responde\n"
else
    printf "  ${YELLOW}WARN${NC} Dashboard /login no responde 200 (puede estar warming up)\n"
fi

# Generate auth token + seed
FIRST_EMAIL=$(echo "$ALLOWED_EMAILS" | cut -d',' -f1)
TOKEN=$(curl -s -X POST "$RAILWAY_URL/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$FIRST_EMAIL\"}" | grep -oE '"token":"[^"]+' | sed 's/"token":"//' || true)

if [ -n "$TOKEN" ]; then
    printf "  ${GREEN}OK${NC} Auth token generado para %s\n" "$FIRST_EMAIL"
    printf "  Corriendo seed-example-sources.py...\n"
    API_URL=$RAILWAY_URL BEARER_TOKEN=$TOKEN python -X utf8 scripts/seed-example-sources.py 2>&1 | tail -5 || true
else
    printf "  ${YELLOW}WARN${NC} No pude generar token — seed manual: BEARER_TOKEN=... python scripts/seed-example-sources.py\n"
fi

# ===========================================================================
# Done
# ===========================================================================

printf "\n${GREEN}=== DEPLOY COMPLETE ===${NC}\n"
printf "  Backend:   %s\n" "$RAILWAY_URL"
printf "  Dashboard: %s\n" "$VERCEL_URL"
printf "  Login:     %s/login (with email %s)\n" "$VERCEL_URL" "$FIRST_EMAIL"
printf "\nNext steps:\n"
printf "  1. Open %s/admin/diagnose-deploy → should say READY\n" "$VERCEL_URL"
printf "  2. Configure GitHub Secrets (AUTO_SCAN_API_URL=%s + AUTO_SCAN_TOKEN)\n" "$RAILWAY_URL"
printf "  3. If you want SMTP: add SMTP_PASSWORD via Gmail App Password to Railway\n"
