#!/usr/bin/env bash
#
# start-local.sh — M7.3 — launcher para Linux/macOS/WSL
#
# Equivalente al start-local.ps1 (Windows-only) pero para shells POSIX.
# Arranca backend (FastAPI :8002) + dashboard (Next.js :3001) cargando
# las env vars de .env.
#
# Uso:
#   ./scripts/start-local.sh              # arranca todo
#   ./scripts/start-local.sh stop         # detiene servicios
#   ./scripts/start-local.sh restart      # stop + start
#   ./scripts/start-local.sh status       # ¿están corriendo?
#
# Logs:
#   /tmp/circle-llc-backend.log
#   /tmp/circle-llc-dashboard.log

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT=8002
DASHBOARD_PORT=3001
BACKEND_LOG=/tmp/circle-llc-backend.log
DASHBOARD_LOG=/tmp/circle-llc-dashboard.log
BACKEND_PID_FILE=/tmp/circle-llc-backend.pid
DASHBOARD_PID_FILE=/tmp/circle-llc-dashboard.pid

# Colores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ACTION="${1:-start}"

# ----- Helpers -----

is_port_in_use() {
    local port=$1
    if command -v lsof >/dev/null 2>&1; then
        lsof -i ":$port" -t >/dev/null 2>&1
    else
        # Fallback: use ss or netstat
        ss -ltn 2>/dev/null | grep -q ":$port" || netstat -ltn 2>/dev/null | grep -q ":$port"
    fi
}

kill_port() {
    local port=$1
    if command -v lsof >/dev/null 2>&1; then
        local pids
        pids=$(lsof -i ":$port" -t 2>/dev/null || true)
        if [ -n "$pids" ]; then
            echo -e "  ${YELLOW}Killing PIDs on port $port: $pids${NC}"
            for pid in $pids; do
                kill -TERM "$pid" 2>/dev/null || true
            done
            sleep 1
            # Force kill if still alive
            for pid in $pids; do
                kill -KILL "$pid" 2>/dev/null || true
            done
        fi
    fi
}

# ----- Actions -----

cmd_status() {
    echo -e "${CYAN}=== Service status ===${NC}"
    if is_port_in_use $BACKEND_PORT; then
        echo -e "  ${GREEN}OK${NC} Backend  listening on :$BACKEND_PORT"
    else
        echo -e "  ${RED}DOWN${NC} Backend  NOT listening on :$BACKEND_PORT"
    fi
    if is_port_in_use $DASHBOARD_PORT; then
        echo -e "  ${GREEN}OK${NC} Dashboard listening on :$DASHBOARD_PORT"
    else
        echo -e "  ${RED}DOWN${NC} Dashboard NOT listening on :$DASHBOARD_PORT"
    fi
}

cmd_stop() {
    echo -e "${CYAN}=== Stopping services ===${NC}"
    kill_port $BACKEND_PORT
    kill_port $DASHBOARD_PORT
    rm -f "$BACKEND_PID_FILE" "$DASHBOARD_PID_FILE"
    echo -e "  ${GREEN}Done.${NC}"
}

cmd_start() {
    echo -e "${CYAN}=== Starting circle-llc local ===${NC}"

    # Check .env exists
    if [ ! -f "$ROOT/.env" ]; then
        echo -e "${RED}ERROR: .env not found at $ROOT/.env${NC}"
        echo "Copy orchestrator/.env.example to .env and fill in the keys first."
        exit 1
    fi

    # Free ports if in use
    if is_port_in_use $BACKEND_PORT; then
        echo -e "  ${YELLOW}Port $BACKEND_PORT in use — killing${NC}"
        kill_port $BACKEND_PORT
    fi
    if is_port_in_use $DASHBOARD_PORT; then
        echo -e "  ${YELLOW}Port $DASHBOARD_PORT in use — killing${NC}"
        kill_port $DASHBOARD_PORT
    fi
    sleep 1

    # Load .env into current shell
    set -a
    # shellcheck disable=SC1090,SC2046
    source <(grep -E '^[A-Z_]+=' "$ROOT/.env" | sed 's/[[:space:]]*#.*$//')
    set +a

    if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
        echo -e "  ${GREEN}ANTHROPIC_API_KEY: set${NC} (live mode)"
    else
        echo -e "  ${YELLOW}ANTHROPIC_API_KEY: not set${NC} (mock mode)"
    fi

    # Start backend
    echo -e "  Starting backend on :$BACKEND_PORT..."
    cd "$ROOT"
    nohup python -m uvicorn orchestrator.api:app --reload --port $BACKEND_PORT --host 127.0.0.1 \
        > "$BACKEND_LOG" 2>&1 &
    BACKEND_PID=$!
    echo $BACKEND_PID > "$BACKEND_PID_FILE"
    disown $BACKEND_PID 2>/dev/null || true

    # Wait for backend (max 30s)
    local tries=0
    until curl -s --max-time 2 -o /dev/null "http://127.0.0.1:$BACKEND_PORT/api/v1/health" 2>/dev/null; do
        tries=$((tries + 1))
        if [ $tries -ge 15 ]; then
            echo -e "  ${RED}Backend did not come up in 30s. Check $BACKEND_LOG${NC}"
            exit 1
        fi
        sleep 2
    done
    local mode
    mode=$(curl -s "http://127.0.0.1:$BACKEND_PORT/api/v1/health" | python -c "import sys,json; print(json.load(sys.stdin).get('mode','?'))" 2>/dev/null || echo "?")
    echo -e "  ${GREEN}OK${NC} Backend ready (mode=$mode)"

    # Start dashboard
    echo -e "  Starting dashboard on :$DASHBOARD_PORT..."
    cd "$ROOT/dashboard"
    nohup npm run dev > "$DASHBOARD_LOG" 2>&1 &
    DASHBOARD_PID=$!
    echo $DASHBOARD_PID > "$DASHBOARD_PID_FILE"
    disown $DASHBOARD_PID 2>/dev/null || true

    # Wait for dashboard (max 90s — Next.js compile is slow first time)
    tries=0
    until curl -s --max-time 2 -o /dev/null "http://127.0.0.1:$DASHBOARD_PORT/login" 2>/dev/null; do
        tries=$((tries + 1))
        if [ $tries -ge 45 ]; then
            echo -e "  ${YELLOW}Dashboard slow to come up. Check $DASHBOARD_LOG${NC}"
            break
        fi
        sleep 2
    done
    echo -e "  ${GREEN}OK${NC} Dashboard ready"

    echo
    echo -e "${GREEN}=== Services running ===${NC}"
    echo -e "  Backend:   http://localhost:$BACKEND_PORT/api/v1/health"
    echo -e "  Dashboard: http://localhost:$DASHBOARD_PORT/login"
    echo
    echo "Allowed emails:"
    if [ -n "${ALLOWED_EMAILS:-}" ]; then
        echo "$ALLOWED_EMAILS" | tr ',' '\n' | sed 's/^/  - /'
    else
        echo -e "  ${YELLOW}(none — set ALLOWED_EMAILS in .env)${NC}"
    fi
    echo
    echo "Logs: $BACKEND_LOG · $DASHBOARD_LOG"
    echo "To stop: ./scripts/start-local.sh stop"
}

cmd_restart() {
    cmd_stop
    sleep 2
    cmd_start
}

case "$ACTION" in
    start) cmd_start ;;
    stop) cmd_stop ;;
    restart) cmd_restart ;;
    status) cmd_status ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
