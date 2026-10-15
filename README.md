# Workflow — система учёта проектов в Telegram

Field Workflow CRM для монтажно-отделочных объектов.
Полностью локальная: бот, парсер SH3D, экспорт финансов, WebApp, календари.

## Состав

- **workflow-bot** — aiogram 3
- **workflow-webapp** — FastAPI + Jinja2 (страница проекта, QR-редиректы)
- **workflow-worker** — arq (фоновые задачи)
- **radicale** — CalDAV для сотрудников
- **whisper** — существующий контейнер (внешний)
- **MariaDB** — из NCP, отдельная схема `workflow`

### Структура

workflow/ — Python-пакет
bot/ — aiogram
webapp/ — FastAPI, страница проекта, QR-редиректы
worker/ — arq, SLA-проверки, экспорт, дайджест
parsers/ — 3D CSV/PDF
integrations/ — Whisper, LLM, CalDAV, Google
services/ — бизнес-логика
locales/ — ru, en, kz
alembic/ — миграции
tests/ — тесты парсеров, stage_machine, access
scripts/ — бэкап
docs/ — архитектура

### Роли

manager — управляет проектами, назначает команду
secretary — создаёт заявки, звонит заказчику
supplier — закуп
executor — работы на объекте
admin — вне проектов, назначает менеджеров
Один пользователь может совмещать роли.

### Статусы
По умолчанию: Заявка → Планирование → Согласование → Закуп → Подготовка → Реализация → Готово → Сдано.
Каждый менеджер может переименовать, добавить, удалить стадии.

### Голосовой ввод
Whisper — существующий контейнер
LLM — опциональна, отдельный узел в интрасете
Если LLM недоступна — анкета по шагам

### QR-коды
Закуп — deep-link на страницу проекта (без цен)
Сдача — deep-link на публичную страницу
Печать — PDF с сеткой наклеек

### Экспорт финансов
После сдачи проекта:
accounting_<id>.xlsx — для бухгалтерии
supplier_<id>.xlsx — для снабженца
1c_<id>.xml — для 1С
book_<year>.xlsx — общая книга
Все финансовые поля удаляются из БД после успешного экспорта.

### Сценарии
Создание заявки
Секретарь → /new → имя, телефон, пожелания (голос/текст) → время созвона → готово.
Создаётся WebCal-событие, выводится приглашение для заказчика.

Завершение этапа
Карточка проекта → «Завершено» → (медиа-отчёт, если нужен) → (расчёт, если нужен) → подтверждение.
Исполнитель следующего этапа получает уведомление.

Отказ от работы
Карточка проекта → «Отказаться» → причина (голос/текст) → проект возвращается на предыдущий этап.

Закрытие проекта
/close <id> → подтверждение → экспорт 4 файлов → удаление финансов из БД → очистка медиа → публикация.

### Архивация
Медиа: остаются 2 фото + 1 видео с последнего этапа
Документы: эскиз, проект PDF/CSV
Финансы: только экспортные файлы
Путь: /var/lib/workflow/archive/<year>/

## Установка

### 0. Клонирование и настройка

```bash
git clone <repo> /opt/workflow
cd /opt/workflow
cp .env.example .env
# отредактировать .env

### 1. Создание схемы MariaDB
CREATE DATABASE workflow CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'workflow'@'%' IDENTIFIED BY 'change_me';
GRANT ALL PRIVILEGES ON workflow.* TO 'workflow'@'%';
FLUSH PRIVILEGES;

### 2. Docker
  workflow-bot:
    image: workflow-bot:arm64
    container_name: workflow-bot
    restart: unless-stopped
    env_file: ./workflow/.env
    volumes:
      - ./workflow:/app
      - /var/lib/workflow/exports:/var/lib/workflow/exports
      - /var/lib/workflow/archive:/var/lib/workflow/archive
      - /var/lib/workflow/media:/var/lib/workflow/media
      - /var/run/docker.sock:/var/run/docker.sock:ro
    depends_on:
      - mariadb
      - redis
    networks: [ncp]

  workflow-webapp:
    image: workflow-webapp:arm64
    container_name: workflow-webapp
    restart: unless-stopped
    env_file: ./workflow/.env
    volumes:
      - ./workflow:/app
      - /var/lib/workflow/exports:/var/lib/workflow/exports:ro
    networks: [ncp]

  workflow-worker:
    image: workflow-bot:arm64
    container_name: workflow-worker
    command: ["arq", "workflow.worker.tasks.WorkerSettings"]
    restart: unless-stopped
    env_file: ./workflow/.env
    volumes:
      - ./workflow:/app
      - /var/lib/workflow/exports:/var/lib/workflow/exports
      - /var/run/docker.sock:/var/run/docker.sock:ro
    depends_on:
      - redis
      - mariadb
    networks: [ncp]

  radicale:
    image: tomsquest/docker-radicale:latest
    container_name: radicale
    restart: unless-stopped
    volumes:
      - ./radicale/data:/data
      - ./radicale/config:/config:ro
    networks: [ncp]

networks:
  ncp:
    external: true

Миграции:
docker compose exec workflow-bot alembic upgrade head

Seed ролей и шаблонов:
docker compose exec workflow-bot python -m workflow.services.seed_cli

Запуск:
docker compose up -d workflow-bot workflow-webapp workflow-worker radicale

# Workflow — система учёта проектов в Telegram

Field Workflow CRM для монтажно-отделочных объектов. Полностью локальная.

## Быстрый старт

```bash
git clone <repo> /opt/workflow
cd /opt/workflow
cp .env.example .env
# отредактировать .env
docker compose up -d
docker compose exec workflow-bot alembic upgrade head
docker compose exec workflow-bot python -m workflow.services.seed_cli

## Тесты
pip install -e ".[dev]"
pytest -v

## Бэкап
sudo crontab -e
0 3 * * * /opt/workflow/scripts/backup.sh

## Обновление
git pull
docker compose build
docker compose exec workflow-bot alembic upgrade head
docker compose up -d
