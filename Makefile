.PHONY: install lint format test test-unit test-integration coverage run up down logs psql migrate revision image stack stack-down

install: ## Install runtime and dev dependencies
	uv sync

lint: ## Static checks
	uv run ruff check .
	uv run ruff format --check .

format: ## Auto-format the code
	uv run ruff check --fix .
	uv run ruff format .

test: ## Run the whole test suite (integration tests start a PostgreSQL container)
	uv run pytest

test-unit: ## Run only the fast unit tests
	uv run pytest -m "not integration"

test-integration: ## Run only the integration tests
	uv run pytest -m integration

coverage: ## Run the whole suite with a coverage report
	uv run pytest --cov --cov-report=term-missing

run: ## Run the API locally with auto-reload
	uv run uvicorn app.main:app --reload --port 8000

up: ## Start local infrastructure (PostgreSQL) and wait until healthy
	docker compose up -d --wait

down: ## Stop every container (data is kept in the pgdata volume)
	docker compose --profile app down

logs: ## Follow local infrastructure logs
	docker compose logs -f

psql: ## Open a psql shell in the local database
	docker compose exec db psql -U postgres -d globant

migrate: ## Apply database migrations to the configured database
	uv run alembic upgrade head

revision: ## Autogenerate a migration from model changes: make revision m="describe change"
	uv run alembic revision --autogenerate -m "$(m)"

image: ## Build the API container image
	docker build -t globant-challenge-api:local .

stack: ## Run the containerized stack: PostgreSQL -> migrations -> API on :8000
	docker compose --profile app up -d --build --wait

stack-down: ## Stop the containerized stack
	docker compose --profile app down
