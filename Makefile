.PHONY: help build up down logs migrate seed test lint fmt backup

help:
	@echo "make build    — собрать образы"
	@echo "make up       — поднять сервисы"
	@echo "make down     — остановить"
	@echo "make logs     — логи"
	@echo "make migrate  — миграции"
	@echo "make seed     — seed ролей и шаблонов"
	@echo "make test     — тесты"
	@echo "make lint     — линтер"
	@echo "make fmt      — форматирование"
	@echo "make backup   — ручной бэкап"

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200 workflow-bot workflow-worker workflow-webapp

migrate:
	docker compose exec workflow-bot alembic upgrade head

seed:
	docker compose exec workflow-bot python -m workflow.services.seed_cli

test:
	pytest -v

lint:
	ruff check workflow tests

fmt:
	ruff format workflow tests

backup:
	bash scripts/backup.sh
