COMPOSE = docker compose
TEST_COMPOSE = TELEGRAM_API_KEY= OPENAI_BASE_URL= OPENAI_MODEL= OPENAI_API_KEY= $(COMPOSE) -p receipt-bot-tests
UV = uv

.PHONY: install run up down logs test lint format check

install:
	$(UV) sync --frozen --extra dev

run:
	$(COMPOSE) up --build app

up:
	$(COMPOSE) up --build -d app

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f app

test:
	@set -e; \
	trap '$(TEST_COMPOSE) down >/dev/null' EXIT; \
	$(TEST_COMPOSE) run --build --rm -e TEST_POSTGRES_DSN=postgresql://receipt:receipt@postgres:5432/receipt app python -m pytest -q

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

format:
	.venv/bin/ruff format .

check: lint test
