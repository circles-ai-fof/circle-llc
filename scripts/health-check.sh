#!/usr/bin/env bash
#
# health-check.sh — M7.0 — diagnóstico desde CLI.
#
# Verifica que el backend está respondiendo + que los endpoints clave
# devuelven los códigos correctos sin autenticación (401) y con auth (200).
#
# Uso:
#   ./scripts/health-check.sh                     # local default :8002
#   ./scripts/health-check.sh https://prod.url    # remote URL
#   BEARER_TOKEN=xxx ./scripts/health-check.sh    # con auth para validar 200
#
# Sale exit 0 si todo OK, exit 1 si algún check falla.

set -e

API_URL="${1:-${API_URL:-http://localhost:8002}}"
TOKEN="${BEARER_TOKEN:-}"

# Colors (POSIX-safe)
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'  # No color

PASS=0
FAIL=0

check_status() {
  local description="$1"
  local url="$2"
  local expected="$3"
  local headers="$4"
  local actual
  actual=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
    ${headers:+-H "$headers"} "$url" 2>/dev/null || echo "000")
  if [ "$actual" = "$expected" ]; then
    printf "  ${GREEN}✓${NC} %-50s [HTTP %s]\n" "$description" "$actual"
    PASS=$((PASS + 1))
  else
    printf "  ${RED}✗${NC} %-50s [HTTP %s, esperado %s]\n" "$description" "$actual" "$expected"
    FAIL=$((FAIL + 1))
  fi
}

check_json_field() {
  local description="$1"
  local url="$2"
  local field="$3"
  local headers="$4"
  local body
  body=$(curl -s --max-time 10 ${headers:+-H "$headers"} "$url" 2>/dev/null || echo "{}")
  if echo "$body" | python -c "import sys, json; d=json.load(sys.stdin); sys.exit(0 if '$field' in d else 1)" 2>/dev/null; then
    printf "  ${GREEN}✓${NC} %-50s [field '%s' present]\n" "$description" "$field"
    PASS=$((PASS + 1))
  else
    printf "  ${RED}✗${NC} %-50s [field '%s' MISSING]\n" "$description" "$field"
    FAIL=$((FAIL + 1))
  fi
}

printf "${BLUE}=== Circle LLC FoF — Health Check ===${NC}\n"
printf "API URL: %s\n" "$API_URL"
printf "Auth:    %s\n\n" "${TOKEN:+(provided)}${TOKEN:-(none — only unauth checks)}"

printf "${BLUE}--- 1. Backend reachable ---${NC}\n"
check_status "GET /api/v1/health" "$API_URL/api/v1/health" "200" ""
check_json_field "Health body has 'status'" "$API_URL/api/v1/health" "status" ""
check_json_field "Health body has 'mode'" "$API_URL/api/v1/health" "mode" ""

printf "\n${BLUE}--- 2. Auth gates working (esperado 401 sin token) ---${NC}\n"
check_status "GET /api/v1/stats" "$API_URL/api/v1/stats" "401" ""
check_status "GET /api/v1/sources" "$API_URL/api/v1/sources" "401" ""
check_status "GET /api/v1/signals" "$API_URL/api/v1/signals" "401" ""
check_status "GET /api/v1/runs" "$API_URL/api/v1/runs" "401" ""
check_status "GET /api/v1/trend-gaps" "$API_URL/api/v1/trend-gaps" "401" ""
check_status "GET /api/v1/niche-opportunities" "$API_URL/api/v1/niche-opportunities" "401" ""
check_status "GET /api/v1/admin/status" "$API_URL/api/v1/admin/status" "401" ""
check_status "GET /api/v1/digest/data" "$API_URL/api/v1/digest/data" "401" ""

printf "\n${BLUE}--- 3. Diagnostic público ---${NC}\n"
check_status "GET /api/v1/diagnostic (público)" "$API_URL/api/v1/diagnostic" "200" ""
check_json_field "diagnostic body has 'mode'" "$API_URL/api/v1/diagnostic" "mode" ""
check_json_field "diagnostic body has 'features'" "$API_URL/api/v1/diagnostic" "features" ""

if [ -n "$TOKEN" ]; then
  printf "\n${BLUE}--- 4. Endpoints autenticados (con BEARER_TOKEN) ---${NC}\n"
  AUTH_HEADER="Authorization: Bearer $TOKEN"
  check_status "GET /api/v1/stats con auth" "$API_URL/api/v1/stats" "200" "$AUTH_HEADER"
  check_status "GET /api/v1/admin/status con auth" "$API_URL/api/v1/admin/status" "200" "$AUTH_HEADER"
  check_json_field "admin/status body has 'agents'" "$API_URL/api/v1/admin/status" "agents" "$AUTH_HEADER"
  check_json_field "admin/status body has 'crons'" "$API_URL/api/v1/admin/status" "crons" "$AUTH_HEADER"
else
  printf "\n${YELLOW}--- 4. Skip: endpoints con auth (set BEARER_TOKEN para correr) ---${NC}\n"
fi

printf "\n${BLUE}=== Resultado ===${NC}\n"
printf "  ${GREEN}Pass: %d${NC}\n" "$PASS"
printf "  ${RED}Fail: %d${NC}\n" "$FAIL"

if [ $FAIL -eq 0 ]; then
  printf "\n${GREEN}✓ Todos los checks OK.${NC}\n"
  exit 0
else
  printf "\n${RED}✗ %d checks fallaron.${NC}\n" "$FAIL"
  exit 1
fi
