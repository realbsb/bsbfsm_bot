# WebApp

## Адрес

Два варианта:

1. **Поддомен:** `https://workflow.realbsb.ru` — проще, `WEBAPP_ROOT_PATH=` (пусто).
2. **Путь:** `https://realbsb.ru/workflow` — `WEBAPP_ROOT_PATH=/workflow`.

## Схема (через путь)
Интернет
│
▼
192.168.0.1:443 (Angie, realbsb.ru)
│ location /workflow/ { proxy_pass http://192.168.0.150:8080/; }
▼
192.168.0.150:8080 (FastAPI, uvicorn --root-path /workflow)
│
▼
WebApp

`proxy_pass` со слэшем в конце срезает `/workflow/` из пути.

## Angie-конфиг

См. `docs/angie.conf`.

## Переменные

| Переменная | Назначение |
|---|---|
| `BOT_WEBAPP_BASE_URL` | Публичный HTTPS-адрес (с путём, если через путь) |
| `WEBAPP_ROOT_PATH` | Префикс пути (`/workflow` или пусто) |
| `WEBAPP_HOST` | Адрес прослушивания (127.0.0.1) |
| `WEBAPP_PORT` | Порт (8080) |
| `WEBAPP_INITDATA_MAX_AGE` | Максимальный возраст initData |
| `WEBAPP_SECRET` | Секрет для CSRF-токенов |
| `WEBAPP_RATE_LIMIT_PER_MINUTE` | Rate-limit для форм |

## Страницы

| Путь | Назначение |
|---|---|
| `/p/{id}` | Страница проекта |
| `/qr/{token}` | Редирект по QR |
| `/request/{slug}` | Публичная форма заявки |
| `/request/{slug}/thanks` | Спасибо |
| `/oauth/google/start` | Начало OAuth |
| `/oauth/google/callback` | Callback |
| `/health` | Health-check |

## CSRF

Формы защищены CSRF-токеном:
- При GET — сервер генерирует подписанный токен (HMAC-SHA256 с `WEBAPP_SECRET`).
- При POST — проверяем подпись, TTL 1 час.
- Дополнительно: rate-limit по IP и honeypot-поле.

## Режимы доступа к странице проекта

| Кто | Что видит |
|---|---|
| Сотрудник | Полная карточка, участники, медиа этапов |
| Заказчик | Цена согласованная, оплата, финальные медиа |
| QR закупа | Список материалов, контакт секретаря |
| QR сдачи | Финальные фото/видео |
| Есть пост в канале | Редирект на пост |
| Публичный сданный | Публичная страница |
| Остальные | 404 |
