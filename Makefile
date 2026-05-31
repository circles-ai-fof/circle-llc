# Circle LLC FoF — Makefile
# M7.4 — interfaz uniforme para tasks comunes del proyecto.
#
# Uso:
#   make install      # backend deps + dashboard deps
#   make test         # full pytest suite
#   make test-ui      # TS check del dashboard
#   make dev          # arranca backend + dashboard local
#   make stop         # detiene servicios
#   make seed         # bootstrap con fuentes + runs de ejemplo
#   make seed-sources # solo fuentes (gratis)
#   make seed-runs    # solo runs (~$0.18 LLM)
#   make health       # CLI health-check vs backend local
#   make openapi      # exporta docs/openapi.json
#   make clean        # borra pycache + .next + node_modules
#   make ci           # lo que corre CI: test + test-ui

.PHONY: help install test test-ui dev stop status restart seed seed-sources seed-runs health openapi clean ci

# Default target
help:
	@echo "Circle LLC FoF — Makefile targets:"
	@echo ""
	@echo "  install         Install backend + dashboard deps"
	@echo "  test            Run full pytest suite (765 tests, ~15s)"
	@echo "  test-ui         TypeScript noEmit check on dashboard"
	@echo ""
	@echo "  dev             Start backend (:8002) + dashboard (:3001) local"
	@echo "  stop            Stop both services"
	@echo "  restart         stop + start"
	@echo "  status          Are services running?"
	@echo ""
	@echo "  seed            Bootstrap with example sources + runs"
	@echo "  seed-sources    Only sources (free, idempotent)"
	@echo "  seed-runs       Only runs (~\$$0.18 LLM if live mode)"
	@echo "  health          CLI health-check vs http://localhost:8002"
	@echo "  openapi         Dump OpenAPI spec to docs/openapi.json"
	@echo ""
	@echo "  clean           Remove pycache, .next, node_modules"
	@echo "  ci              What CI runs: test + test-ui"

install:
	@echo "→ Installing backend deps..."
	pip install -r orchestrator/requirements.txt
	@echo "→ Installing dashboard deps..."
	cd dashboard && npm install
	@echo "✓ Done."

test:
	pytest tests/ -q

test-ui:
	cd dashboard && npx tsc --noEmit

dev:
	@if [ -f scripts/start-local.sh ]; then \
		bash scripts/start-local.sh start; \
	elif [ -f start-local.ps1 ]; then \
		powershell -ExecutionPolicy Bypass -File ./start-local.ps1; \
	else \
		echo "ERROR: no launcher found"; exit 1; \
	fi

stop:
	@bash scripts/start-local.sh stop 2>/dev/null || echo "scripts/start-local.sh stop failed; try manual kill"

restart:
	@bash scripts/start-local.sh restart

status:
	@bash scripts/start-local.sh status

seed: seed-sources seed-runs

seed-sources:
	@if [ -z "$$BEARER_TOKEN" ]; then \
		echo "ERROR: BEARER_TOKEN env var required."; \
		echo "Generate one with:"; \
		echo "  TOKEN=\$$(curl -s -X POST http://localhost:8002/api/v1/auth/login \\"; \
		echo "    -H 'Content-Type: application/json' \\"; \
		echo "    -d '{\"email\":\"YOUR@EMAIL\"}' | jq -r .token)"; \
		exit 1; \
	fi
	python scripts/seed-example-sources.py

seed-runs:
	@if [ -z "$$BEARER_TOKEN" ]; then \
		echo "ERROR: BEARER_TOKEN env var required."; \
		exit 1; \
	fi
	python scripts/seed-example-runs.py

health:
	bash scripts/health-check.sh

openapi:
	@mkdir -p docs
	@if curl -s --max-time 5 -o docs/openapi.json http://localhost:8002/openapi.json; then \
		echo "✓ Wrote docs/openapi.json ($$(wc -c < docs/openapi.json) bytes)"; \
		echo "  Open with: cat docs/openapi.json | jq '.paths | keys' | head"; \
	else \
		echo "ERROR: backend not reachable at :8002. Start with 'make dev' first."; \
		exit 1; \
	fi

clean:
	@echo "→ Removing pycache..."
	find orchestrator -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find tests -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "→ Removing dashboard .next + tsbuildinfo..."
	rm -rf dashboard/.next dashboard/tsconfig.tsbuildinfo
	@echo "→ Removing node_modules (run 'make install' to restore)..."
	rm -rf dashboard/node_modules
	@echo "✓ Clean."

ci: test test-ui
	@echo "✓ CI checks passed."
