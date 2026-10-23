COMPOSE = docker compose
TEST_COMPOSE = docker compose -p receipt-bot-tests --profile local --profile test
UV = uv
OCR_EXTRA = $(if $(filter Linux,$(shell uname -s)),--extra ocr,)

.PHONY: install run up down logs test lint format check

install:
	$(UV) sync --frozen --extra dev $(OCR_EXTRA)

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
	trap '$(TEST_COMPOSE) stop >/dev/null' EXIT; \
	$(TEST_COMPOSE) up --build --wait --wait-timeout 900 postgres llm; \
	$(TEST_COMPOSE) run --build --rm --no-deps test

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

format:
	.venv/bin/ruff format .

check: lint test
