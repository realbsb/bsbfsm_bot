# Архитектура Workflow
Field Workflow CRM состоит из:

- **CRM** — заявки, заказчики, ЛК, приглашения.
- **FSM-ядра** — управление стадиями проекта.
- **Field Service** — назначение исполнителей/снабженцев, планирование дня, маршруты.
- **Lite ERP** — закуп, финансы, экспорт в бухгалтерию и 1С.

Полностью локально. Никаких внешних API, кроме Telegram (через прокси).


## Общая схема
Интернет
│
▼
192.168.0.1:1080 — прокси для api.telegram.org (РФ)
192.168.0.1:443 — Angie (workflow.realbsb.ru)
│
▼
192.168.0.150 (Orange Pi 4 Pro, 6 ГБ RAM)
├── workflow-bot (Docker, network_mode: host)
├── workflow-webapp (Docker, uvicorn 127.0.0.1:8080)
├── workflow-worker (Docker, arq)
└── workflow-radicale (Docker, CalDAV)
│
├── MariaDB (нативно, схема workflow)
├── Redis (нативно, БД 1)
└── Whisper (опционально)

┌────────────────────────────────────────────────────────┐
│ Сервер (Orange Pi 4 Pro 6 ГБ / 150 ГБ M.2)             │
│                                                        │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐ │
│ │ NextCloud    │ │ MariaDB      │ │ Redis            │ │
│ │ + CODE       │◄┤ схема ncp    │ │                  │ │
│ └──────────────┘ │ схема wf     │ └────────┬─────────┘ │
│                  └──────┬───────┘          │           │
│                         │                  │           │
│ ┌──────────────┐ ┌──────┴───────┐ ┌────────┴─────────┐ │
│ │ whisper      │ │ workflow-    │ │ workflow-        │ │
│ │ (контейнер)  │◄┤ bot          │ │ worker (arq)     │ │
│ └──────────────┘ └──────┬───────┘ └──────────────────┘ │
│                         │                              │
│                  ┌──────┴───────┐ ┌──────────────────┐ │
│                  │ workflow-    │ │ Radicale         │ │
│                  │ webapp       │ │ (CalDAV)         │ │
│                  └──────┬───────┘ └──────────────────┘ │
│                         │                              │
│                  ┌──────┴───────┐                      │
│                  │ /exports     │                      │
│                  │ /archive     │                      │
│                  └──────────────┘                      │
└─────────────────────────┬──────────────────────────────┘
                          │
                          │ HTTPS (reverse-proxy NCP)
                          ▼
                Пользователи Telegram
                          │
                          │ HTTP (интрасет)
                          ▼
             ┌───────────────────────┐
             │ LLM-узел (опц.)       │
             │ Ollama / llama.cpp    │
             └───────────────────────┘

## Компоненты

| Компонент | Что делает |
|---|---|
| `workflow-bot` | aiogram 3, 17 роутеров, FSM |
| `workflow-webapp` | FastAPI, страница проекта, QR-редиректы, публичные формы |
| `workflow-worker` | arq: SLA-проверки, экспорт, дайджест |
| `workflow-radicale` | CalDAV для сотрудников |
| Whisper | Транскрипция голосовых (ваш контейнер) |
| LLM (опционально) | Разбор команд, отдельный узел в интрасете |

## Потоки данных

### Голосовое сообщение
Пользователь → voice в бот → whisper-контейнер → текст
                       │
                       ▼
            ┌──────────────────────────┐
            │ правила (regex+словари)  │
            └──────────┬───────────────┘
                       │ уверены?
                ┌──────┴──────┐
                │             │
                да           нет
                │             │
                ▼             ▼
       применение LLM-узел
                │
       ┌────────┴────────┐
       │                 │
   доступна          недоступна
       │                 │
       ▼                 ▼
              применение анкета по шагам

### Заявка → сдача
Секретарь      Менеджер           Снабженец           Исполнитель
│                  │                  │                    │
├── заявка ────────┤                  │                    │
│    (WebCal)      │                  │                    │
│                  │                  │                    │
│                расчёт               │                    │
│              (PDF 3D)               │                    │
│                  │                  │                    │
│           согласование ─────────────┤                    │
│             (встреча)               │                    │
│                  │                  │                    │
│                  ├── предоплата     │                    │
│                  ├── назначение ────┤                    │
│                  │                  │                    │
│                  │                закуп ────────────────►│
│                  │              (закупка)                │
│                  │                  │                    │
│                  │                материалы ─────────────┤
│                  │                  │               подготовка
│                  │                  │              (фото/видео)
│                  │                  │                    │
│                  │              ────┴── реализация ──────┤
│                  │                                       │
│                  │                ───── готово ──────────┤
│                  │                                       │
│                сдача ◄───────────────────────────────────┘
│              (встреча)
│              (оплата)
│                  │
│              закрытие
│              (экспорт)
│              (архив)
│            (публикация)

## Хранилище

| Путь | Что |
|---|---|
| `/var/lib/workflow/exports/<year>/` | Экспорт финансов (xlsx, xml) |
| `/var/lib/workflow/archive/<year>/` | Архив проектов (tar.gz) |
| `/var/lib/workflow/media/` | Кэш медиа (если нужно) |
| `/var/lib/workflow/backup/<ts>/` | Бэкапы БД и архива |

## Удаление финансов

При закрытии проекта (`/close <id>`):

1. Генерируются 4 файла: `accounting_*.xlsx`, `supplier_*.xlsx`, `1c_*.xml`, `book_<year>.xlsx`.
2. Записи фиксируются в `finance_export`.
3. Поля `price_internal`, `price_agreed`, `prepay_paid`, `final_paid` обнуляются.
4. Удаляются `purchase` и `purchase_item` по проекту.
5. Медиа: остаются только финальные (2 фото + 1 видео).
6. Документы: остаются `sketch`, `project_pdf`, `project_csv`.

## Права

| Поле/раздел | manager | secretary | supplier | executor | client |
|---|---|---|---|---|---|
| price_internal | ✅ | ❌ | ✅ | ❌ | ❌ |
| price_agreed | ✅ | ❌ | ❌ | ❌ | ✅ |
| медиа этапов | ✅ | ❌ | ❌ | ✅ | ❌ |
| финальные медиа | ✅ | ✅ | ✅ | ✅ | ✅ |
| публикация в канал | ✅ | ✅ | ❌ | ❌ | ❌ |
| публикация в портфолио | ✅ | ❌ | ❌ | ✅ | ❌ |
| закрытие проекта | ✅ | ❌ | ❌ | ❌ | ❌ |

## Статусы

По умолчанию (шаблон):

1. `request` — Заявка (secretary)
2. `planning` — Планирование (secretary)
3. `negotiation` — Согласование (manager, calc, client_meeting)
4. `purchase` — Закуп (supplier)
5. `preparation` — Подготовка (supplier, media)
6. `realization` — Реализация (executor, media, client_meeting)
7. `ready` — Готово (executor, media)
8. `delivered` — Сдано (manager, calc, client_meeting)

Каждый менеджер может:
- переименовать стадию,
- добавить/удалить,
- поменять порядок,
- изменить ответственного,
- включить/выключить обязательный медиа-отчёт или расчёт,
- задать SLA.

## Календари

- **Radicale** — опционально, каждый сотрудник вводит свои креды в профиле.
- **Google Calendar** — через штатные ссылки (`calendar.google.com/calendar/render?action=TEMPLATE`). OAuth не нужен.

## i18n

- Языки: `ru`, `en`, `kz`
- Автоопределение из `language_code` Telegram при первом запуске
- Ручное переключение через `/lang` или профиль
- Fallback на `ru`

## Безопасность

- Все данные — в локальной БД и на диске сервера
- LLM — опциональный узел в интрасете, при недоступности — деградация
- Whisper — локальный контейнер
- WebApp-авторизация — через `initData` Telegram (HMAC)
- QR-токены — одноразовые, с TTL для закупа

workflow/
│
├── .env.example                          # шаблон переменных окружения
├── .gitignore                            # игнорируемое
├── .dockerignore                         # не копируем в образ
├── pyproject.toml                        # зависимости и настройки
├── README.md                             # как поднять, обновить, использовать
├── CHANGELOG.md                          # история изменений
├── LICENSE                               # внутренний
├── Makefile                              # удобные команды
│
├── Dockerfile.bot                        # образ для бота и воркера
├── Dockerfile.webapp                     # образ для WebApp
├── docker-compose.yml                    # сервисы приложения (без MariaDB и NCP)
│
├── alembic.ini                           # конфиг Alembic
│
├── alembic/                              # миграции
│   ├── env.py                            # async-окружение
│   ├── script.py.mako                    # шаблон миграции
│   └── versions/
│       ├── 0001_initial.py               # начальная схема
│       └── 0002_project_priority.py      # пример расширения
│
├── locales/                              # переводы
│   ├── __init__.py
│   ├── ru.json                           # русский (fallback)
│   ├── en.json                           # английский
│   └── kz.json                           # казахский
│
├── scripts/                              # служебные скрипты
│   ├── backup.sh                         # бэкап БД + архива
│   └── make_icons.py                     # генерация иконок WebApp
│
├── docs/                                 # документация
│   ├── architecture.md                   # архитектурная схема и потоки
│   ├── deployment.md                     # развёртывание на Orange Pi + NCP
│   ├── i18n.md                           # как добавлять языки
│   └── migrations.md                     # процедура обновления БД
│
├── tests/                                # тесты
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_parsers.py
│   ├── test_stage_machine.py
│   └── test_access.py
│
└── workflow/                             # Python-пакет
    │
    ├── __init__.py                       # версия
    ├── config.py                         # настройки (Pydantic Settings)
    ├── logging_setup.py                  # structlog
    ├── db.py                             # Database, Base
    ├── models.py                         # все ORM-модели
    │
    ├── parsers/                          # парсинг SH3D
    │   ├── __init__.py
    │   ├── models.py                     # ParsedRow, ParsedTable
    │   ├── normalize.py                  # clean_number, decode_bytes
    │   ├── csv_parser.py                 # CSV (CP866)
    │   ├── pdf_parser.py                 # PDF через pdftotext -layout
    │   └── sh3d.py                       # общий интерфейс
    │
    ├── integrations/                     # внешние сервисы
    │   ├── __init__.py
    │   ├── whisper_client.py             # обёртка Whisper-контейнера
    │   ├── llm_client.py                 # опциональный LLM-узел
    │   ├── caldav_client.py              # Radicale (по пользователю)
    │   ├── google_calendar.py            # Google Calendar API
    │   └── google_oauth.py               # OAuth для заказчиков
    │
    ├── services/                         # бизнес-логика
    │   ├── __init__.py
    │   ├── access.py                     # права на цену/медиа
    │   ├── audit.py                      # запись в AuditLog
    │   ├── calendar_service.py           # оркестрация встреч (Radicale+Google)
    │   ├── export_finance.py             # экспорт финансов
    │   ├── final_media.py                # финальные медиа и очистка
    │   ├── invite.py                     # токены-приглашения
    │   ├── publish.py                    # посты в канал/портфолио
    │   ├── qr.py                         # генерация QR и наклеек
    │   ├── report.py                     # xlsx-отчёт по проекту
    │   ├── seed.py                       # seed ролей и шаблонов
    │   ├── seed_cli.py                   # CLI для seed
    │   ├── seed_demo.py                  # демо-данные (только dev)
    │   ├── sla.py                        # проверка просрочек
    │   └── stage_machine.py              # переходы стадий
    │
    ├── bot/                              # aiogram
    │   ├── __init__.py
    │   ├── main.py                       # точка входа
    │   ├── keyboards.py                  # все клавиатуры
    │   ├── middlewares.py                # БД, User, Locale, AntiFlood, DeepLink, RoleBootstrap
    │   ├── errors.py                     # глобальный error handler
    │   ├── antiflood.py                  # утилита антифлуда
    │   ├── filters.py                    # фильтры ролей
    │   ├── states.py                     # FSM-состояния
    │   ├── texts.py                      # i18n: t(), detect_locale()
    │   └── routers/                      # 17 роутеров
    │       ├── __init__.py
    │       ├── admin.py                  # /assign, /managers
    │       ├── client.py                 # ЛК заказчика
    │       ├── fallback.py               # анкета при деградации
    │       ├── finance.py                # /close, экспорт
    │       ├── media.py                  # приём медиа
    │       ├── price.py                  # цифровая клавиатура
    │       ├── profile.py                # профиль, команда, язык
    │       ├── project.py                # карточка, карта, маршрут
    │       ├── publish.py                # публикации
    │       ├── purchase.py               # список закупа
    │       ├── qr.py                     # генерация QR
    │       ├── report.py                 # выгрузка отчёта
    │       ├── request.py                # заявка (FSM)
    │       ├── schedule.py               # планирование дня
    │       ├── stage.py                  # Завершено / Отказаться / Замена
    │       └── start.py                  # /start, регистрация
    │
    ├── webapp/                           # FastAPI
    │   ├── __init__.py
    │   ├── main.py                       # приложение