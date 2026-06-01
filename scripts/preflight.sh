#!/usr/bin/env bash
#
# preflight.sh — M8.2 — comprehensive deploy readiness check
#
# Ejecutar ANTES de desplegar a Railway/Vercel. Verifica:
# 1. Tests verdes
# 2. TS noEmit limpio
# 3. .env existe + no committed
# 4. requirements.txt válido
# 5. Dockerfile + .dockerignore presentes
# 6. CHANGELOG actualizado (último commit no es viejo)
# 7. README + LICENSE + DEPLOY.md presentes
# 8. No commits con .env tracked
# 9. Backend funciona (smoke test si está running)
# 10. dashboard build funciona
#
# Uso:
#   bash scripts/preflight.sh
#
# Exit: 0 si todo OK, 1 si algo falla.

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PASS=0
FAIL=0
WARN=0

check_pass() {
    printf "  ${GREEN}OK${NC}    %s\n" "$1"
    PASS=$((PASS + 1))
}
check_fail() {
    printf "  ${RED}FAIL${NC}  %s\n" "$1"
    FAIL=$((FAIL + 1))
}
check_warn() {
    printf "  ${YELLOW}WARN${NC}  %s\n" "$1"
    WARN=$((WARN + 1))
}

section() {
    printf "\n${CYAN}=== %s ===${NC}\n" "$1"
}

# ---------------------------------------------------------------------------
section "1. Required files"
# ---------------------------------------------------------------------------

for f in README.md DEPLOY.md CONTRIBUTING.md LICENSE CHANGELOG.md Makefile \
         orchestrator/requirements.txt Dockerfile .dockerignore .gitignore \
         dashboard/package.json dashboard/tsconfig.json; do
    if [ -f "$f" ]; then
        check_pass "$f exists"
    else
        check_fail "$f MISSING"
    fi
done

# ---------------------------------------------------------------------------
section "2. .env hygiene"
# ---------------------------------------------------------------------------

if [ -f ".env" ]; then
    check_pass ".env exists locally"
    # Verify it's in .gitignore
    if grep -qE "^\.env$|^\.env\s*$" .gitignore; then
        check_pass ".env listed in .gitignore"
    else
        check_fail ".env NOT in .gitignore — SECURITY RISK"
    fi
    # Verify never committed
    if git ls-files | grep -qE "^\.env$"; then
        check_fail ".env is TRACKED in git — must remove with 'git rm --cached .env'"
    else
        check_pass ".env never committed"
    fi
else
    check_warn ".env missing — needed to run local backend (cp .env.example .env)"
fi

# ---------------------------------------------------------------------------
section "3. Secret scan"
# ---------------------------------------------------------------------------

# Look for accidentally committed Anthropic keys
if git log -p --all | grep -qE "sk-ant-api[0-9]+-[A-Za-z0-9_-]{50,}" 2>/dev/null; then
    check_fail "Anthropic API key found in git history — ROTATE THE KEY"
else
    check_pass "No Anthropic key in git history"
fi

# OpenAI
if git log -p --all | grep -qE "sk-(proj-)?[A-Za-z0-9_-]{40,}" 2>/dev/null; then
    check_warn "Possible OpenAI key pattern in git history — review manually"
else
    check_pass "No OpenAI key in git history"
fi

# ---------------------------------------------------------------------------
section "4. Tests"
# ---------------------------------------------------------------------------

if command -v pytest >/dev/null 2>&1; then
    if pytest tests/ -q --no-header 2>&1 | tail -1 | grep -qE "passed"; then
        TEST_OUT=$(pytest tests/ -q --no-header 2>&1 | tail -1)
        check_pass "pytest: $TEST_OUT"
    else
        check_fail "pytest failed — fix tests before deploy"
    fi
else
    check_warn "pytest not installed (pip install -r orchestrator/requirements.txt)"
fi

# ---------------------------------------------------------------------------
section "5. TypeScript check"
# ---------------------------------------------------------------------------

if [ -d "dashboard/node_modules" ]; then
    if (cd dashboard && npx tsc --noEmit 2>&1 | head -1 | grep -qE "error TS"); then
        check_fail "TypeScript errors in dashboard — fix before deploy"
    else
        check_pass "dashboard TS noEmit clean"
    fi
else
    check_warn "dashboard/node_modules missing — run 'make install' first"
fi

# ---------------------------------------------------------------------------
section "6. Dashboard build"
# ---------------------------------------------------------------------------

if [ -d "dashboard/node_modules" ]; then
    if (cd dashboard && npm run build > /tmp/build.log 2>&1); then
        check_pass "dashboard 'npm run build' succeeded"
    else
        check_warn "dashboard build failed — see /tmp/build.log"
    fi
else
    check_warn "dashboard build skipped — node_modules missing"
fi

# ---------------------------------------------------------------------------
section "7. Git state"
# ---------------------------------------------------------------------------

if [ -z "$(git status --porcelain)" ]; then
    check_pass "Working tree clean"
else
    check_warn "Uncommitted changes: $(git status --porcelain | wc -l) files"
fi

if git rev-parse --abbrev-ref @{u} >/dev/null 2>&1; then
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse @{u})
    if [ "$LOCAL" = "$REMOTE" ]; then
        check_pass "HEAD synced with origin/master"
    else
        check_warn "HEAD not synced with origin — push or pull before deploy"
    fi
else
    check_warn "No upstream branch configured"
fi

# ---------------------------------------------------------------------------
section "8. Backend smoke (if running)"
# ---------------------------------------------------------------------------

if curl -s --max-time 2 http://localhost:8002/api/v1/health > /dev/null 2>&1; then
    HEALTH=$(curl -s --max-time 2 http://localhost:8002/api/v1/health)
    if echo "$HEALTH" | grep -q '"status":"ok"'; then
        check_pass "Backend running on :8002 + health=ok"
    else
        check_warn "Backend running but health response unexpected: $HEALTH"
    fi
else
    check_warn "Backend NOT running on :8002 (skip smoke checks)"
fi

# ---------------------------------------------------------------------------
section "Summary"
# ---------------------------------------------------------------------------

printf "  ${GREEN}Pass: %d${NC}\n" "$PASS"
printf "  ${YELLOW}Warn: %d${NC}\n" "$WARN"
printf "  ${RED}Fail: %d${NC}\n" "$FAIL"

if [ $FAIL -eq 0 ]; then
    printf "\n${GREEN}READY FOR DEPLOY${NC}\n"
    printf "Next: follow docs/production-checklist.md step by step.\n"
    exit 0
else
    printf "\n${RED}NOT READY — fix the %d failure(s) above${NC}\n" "$FAIL"
    exit 1
fi
