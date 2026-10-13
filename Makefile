.PHONY: install lint format test run

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
