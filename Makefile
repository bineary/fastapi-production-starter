.PHONY: up down test lint fmt migrate revision seed coverage openapi

up:
	docker compose up --build

down:
	docker compose down -v

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy app

fmt:
	uv run ruff check --fix .
	uv run ruff format .

migrate:
	uv run alembic upgrade head

revision:
	uv run alembic revision --autogenerate -m "$(m)"

seed:
	uv run python -m scripts.seed

coverage:
	uv run pytest --cov=app --cov-report=term-missing --cov-report=html

openapi:
	uv run python -m scripts.export_openapi
