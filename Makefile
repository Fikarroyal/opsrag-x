SHELL := /bin/bash
VENV ?= .venv
PY := $(VENV)/bin/python
# Default: local SQLite file (no PostgreSQL needed). PostgreSQL: make seed DB_URL=postgresql+psycopg://postgres:postgres@localhost:5432/opsragx
DB_URL ?= sqlite:///$(CURDIR)/data/opsragx.db
export DATABASE_URL ?= $(DB_URL)

.PHONY: local setup dev test seed ingest embed lint format typecheck benchmark health demo build up down data

local:            ## run everything locally with SQLite (no Docker/PostgreSQL): http://localhost:8000
	$(PY) scripts/run_local.py

setup:            ## create venv, install backend/mcp deps and frontend deps
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q -r backend/requirements-dev.txt
	cd frontend && npm install

data:             ## regenerate deterministic synthetic data and SOP PDF
	$(PY) scripts/generate_demo_data.py
	$(PY) scripts/generate_sop_pdf.py

seed:             ## migrations + seed synthetic inventory/incidents/logs/history (idempotent)
	$(PY) scripts/bootstrap.py

ingest:           ## ingest SOP PDF + infrastructure doc and create embeddings
	$(PY) scripts/ingest_documents.py
	$(PY) scripts/create_embeddings.py

embed:
	$(PY) scripts/create_embeddings.py

dev:              ## run MCP server, backend and frontend (Ctrl+C stops all)
	@trap 'kill 0' INT TERM; \
	(cd mcp-server && DATA_DIR=$(CURDIR)/data $(CURDIR)/$(PY) server.py) & \
	(cd backend && $(CURDIR)/$(VENV)/bin/uvicorn app.main:app --reload --port 8000) & \
	(cd frontend && npm run dev) & \
	wait

test:             ## backend tests (SQLite in-memory + hashing embedder, no external services)
	cd backend && EMBEDDING_BACKEND=hashing LLM_ENABLED=false ../$(PY) -m pytest

lint:             ## ruff + black check + mypy + eslint
	$(VENV)/bin/ruff check .
	$(VENV)/bin/black --check .
	$(VENV)/bin/mypy backend/app
	cd mcp-server && ../$(VENV)/bin/mypy .
	cd frontend && npm run lint && npm run typecheck

format:
	$(VENV)/bin/ruff check --fix .
	$(VENV)/bin/black .

typecheck:
	$(VENV)/bin/mypy backend/app

benchmark:        ## run experiments A-D on the 50-item benchmark (writes data/processed/benchmark_results.json)
	$(PY) scripts/run_benchmark.py

health:           ## check backend /api/health, MCP server and run a demo investigation
	$(PY) scripts/health_check.py

demo:             ## bootstrap, then run the INC-2026-001 demo investigation against the running stack
	$(PY) scripts/bootstrap.py --if-empty
	$(PY) scripts/health_check.py --investigate INC-2026-001

build:
	cd frontend && npm run build

up:
	docker compose up --build -d

down:
	docker compose down
