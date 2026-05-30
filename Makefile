# Nightview — convenience targets for the full-stack dev loop.
# Usage:  make help

.PHONY: help install dev backend frontend stop seed seed-global typecheck clean

ROOT      := $(shell pwd)
BACKEND   := $(ROOT)/backend
FRONTEND  := $(ROOT)/frontend
VENV      := $(BACKEND)/.venv
PY        := $(VENV)/bin/python
UVICORN   := $(VENV)/bin/uvicorn
LOG_DIR   := /tmp

BACK_LOG  := $(LOG_DIR)/nightview-backend.log
FRONT_LOG := $(LOG_DIR)/nightview-frontend.log

help: ## Show this help.
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install backend Python deps + frontend Node deps (one-time setup).
	cd $(BACKEND) && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd $(FRONTEND) && npm install

dev: stop ## Start backend + frontend in the background. Open http://localhost:5173.
	@echo "→ backend  http://localhost:8000 (log: $(BACK_LOG))"
	@cd $(BACKEND) && nohup $(UVICORN) app.main:app --port 8000 --log-level warning > $(BACK_LOG) 2>&1 &
	@echo "→ frontend http://localhost:5173 (log: $(FRONT_LOG))"
	@cd $(FRONTEND) && nohup npx vite --host 127.0.0.1 --port 5173 > $(FRONT_LOG) 2>&1 &
	@sleep 3
	@grep -m1 "Local" $(FRONT_LOG) 2>/dev/null || echo "  (frontend still starting — tail $(FRONT_LOG))"

backend: ## Run the backend in the foreground.
	cd $(BACKEND) && $(UVICORN) app.main:app --port 8000 --log-level info

frontend: ## Run the frontend in the foreground.
	cd $(FRONTEND) && npx vite --host 127.0.0.1 --port 5173

stop: ## Kill any backend or frontend processes on :8000 / :5173.
	@lsof -ti tcp:8000 tcp:5173 2>/dev/null | xargs -r kill -9 2>/dev/null || true
	@pkill -9 -f "vite$$" 2>/dev/null || true
	@pkill -9 -f "uvicorn" 2>/dev/null || true
	@echo "stopped"

seed: ## Regenerate the curated-seed Parquet (~107 cities).
	cd $(BACKEND) && $(PY) ../scripts/ingest_seed.py

seed-global: ## Regenerate the global Parquet via geonamescache (~2,894 cities).
	cd $(BACKEND) && $(PY) ../scripts/ingest_global.py

typecheck: ## Lint + typecheck both halves.
	cd $(FRONTEND) && ./node_modules/.bin/tsc -p tsconfig.json --noEmit
	cd $(BACKEND) && $(PY) -m py_compile app/*.py

clean: stop ## Stop servers and remove Python bytecode caches.
	find $(BACKEND) -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	find $(BACKEND) -name "*.pyc" -delete 2>/dev/null || true
	@echo "cleaned"
