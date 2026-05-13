.PHONY: install install-cli install-cli-all uninstall-cli sync lint format format-check typecheck test coverage coverage-badge check evals deepeval bench-toxicity bench-rutoxic diagrams load up down nuke logs langfuse-up langfuse-down langfuse-logs smoke-api

# Local Langfuse keys baked into docker-compose's auto-provisioned project.
LANGFUSE_LOCAL_ENV := LANGFUSE_PUBLIC_KEY=pk-lf-finpaws LANGFUSE_SECRET_KEY=sk-lf-finpaws LANGFUSE_HOST=http://langfuse-web:3000

install:
	uv sync --all-extras --dev

sync:
	uv sync --all-extras --dev

# Install the `finpaws` budget CLI on PATH (tiny — base deps only).
install-cli:
	uv tool install --force .

# Install all five `finpaws*` commands on PATH (pulls the full server/agent stack).
install-cli-all:
	uv tool install --force '.[all]'

uninstall-cli:
	uv tool uninstall finpaws

lint:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

typecheck:
	uv run mypy

test:
	uv run python -m pytest -q

coverage:
	uv run python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=85

# Regenerate the README coverage badge (coverage.svg) from a fresh run.
coverage-badge:
	uv run python -m pytest --cov=app --cov-report=xml -q
	uv run --with "genbadge[coverage]" genbadge coverage -i coverage.xml -o coverage.svg -n coverage

# Full local gate: lint + formatting + strict typing + tests with coverage.
check: lint format-check typecheck coverage

evals:
	uv run python -m app.evals.runner

deepeval:
	uv run python -m app.evals.deepeval_runner

# Benchmark the rule-based toxicity detector: latency + quality on the in-house corpus.
bench-toxicity:
	uv run python scripts/benchmark_toxicity.py

# Same detector, scored against the external RuToxic corpus (~25k labelled comments, auto-downloaded).
bench-rutoxic:
	uv run python scripts/benchmark_rutoxic.py

# Re-render docs/diagrams/*.md (Mermaid) to SVG via mermaid.ink (also acts as a syntax check).
diagrams:
	uv run python scripts/render_diagrams.py

# Load test (needs the API running, e.g. `make up`). Locust web UI: http://localhost:8089
load:
	uv run locust --host http://localhost:8000

up:
	docker compose up --build

# Stop & remove containers/networks but KEEP volumes (db, grafana, langfuse, clickhouse, minio).
down:
	docker compose --profile langfuse down

# Destructive: also drop all named volumes. Wipes the databases.
nuke:
	docker compose --profile langfuse down -v

logs:
	docker compose logs -f api

# Bring up the whole stack incl. self-hosted Langfuse; API traces to it. UI: http://localhost:3001
# (login admin@finpaws.local / finpaws-local-admin). MinIO console: http://localhost:9001.
langfuse-up:
	$(LANGFUSE_LOCAL_ENV) docker compose --profile langfuse up -d --build

langfuse-down:
	docker compose --profile langfuse down

langfuse-logs:
	docker compose --profile langfuse logs -f langfuse-web langfuse-worker

smoke-api:
	./scripts/smoke_api.sh
