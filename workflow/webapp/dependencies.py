"""Зависимости FastAPI: БД, Telegram-пользователь, Redis."""

from __future__ import annotations

from fastapi import Header, Request
from sqlalchemy import select

from ..config import get_settings
from ..db import Database
from ..logging_setup import get_logger
from ..models import User
from .tg_auth import verify_init_data

log = get_logger(__name__)


async def get_db(request: Request) -> Database:
    return request.app.state.db


async def get_tg_user(
    request: Request,
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> User | None:
    if not x_telegram_init_data:
        return None

    settings = get_settings()
    parsed = verify_init_data(
        x_telegram_init_data,
        settings.bot_token,
        max_age_seconds=settings.webapp_initdata_max_age,
    )
    if not parsed:
        log.warning("webapp.auth.failed")
        return None

    user_obj = parsed.get("user") or {}
    tg_id = user_obj.get("id") if isinstance(user_obj, dict) else None
    if tg_id is None:
        return None

    db: Database = request.app.state.db
    async with db.session() as s:
        return (await s.execute(select(User).where(User.tg_id == int(tg_id)))).scalars().first()
