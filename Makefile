.PHONY: install lint format test run up down logs psql

install: ## Install runtime and dev dependencies
	uv sync

lint: ## Static checks
	uv run ruff check .
	uv run ruff format --check .

format: ## Auto-format the code
	uv run ruff check --fix .
	uv run ruff format .

test: ## Run the test suite
	uv run pytest

run: ## Run the API locally with auto-reload
	uv run uvicorn app.main:app --reload --port 8000

up: ## Start local infrastructure (PostgreSQL) and wait until healthy
	docker compose up -d --wait

down: ## Stop local infrastructure (data is kept in the pgdata volume)
	docker compose down

logs: ## Follow local infrastructure logs
	docker compose logs -f

psql: ## Open a psql shell in the local database
	docker compose exec db psql -U postgres -d globant
