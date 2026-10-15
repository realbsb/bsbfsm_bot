"""Мидлвари: БД, пользователь, роль, локаль, антифлуд, deep-link."""

from __future__ import annotations

import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.types import User as TgUser
from sqlalchemy import select

from ..db import Database
from ..logging_setup import get_logger
from ..models import Position, PositionRole, Role, RoleAssignment, User
from .utils import trace

log = get_logger(__name__)


class DbMiddleware(BaseMiddleware):
    @trace
    def __init__(self, db: Database) -> None:
        self._db = db

    @trace
    async def __call__(self, handler, event, data):
        async with self._db.session() as session:
            data["session"] = session
            return await handler(event, data)


class UserMiddleware(BaseMiddleware):
    @trace
    async def __call__(self, handler, event: TelegramObject, data):
        session = data["session"]
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        user = (
            (await session.execute(select(User).where(User.tg_id == tg_user.id))).scalars().first()
        )

        if user is None:
            from ..bot.texts import detect_locale

            user = User(
                tg_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                locale=detect_locale(tg_user.language_code),
            )
            session.add(user)
            await session.flush()
            log.info("user.created", user=user.id, tg_id=tg_user.id)

        data["user"] = user
        return await handler(event, data)


class RoleMiddleware(BaseMiddleware):
    """Кладёт в data: role_codes, is_manager, can_intake, is_bot_admin."""

    @trace
    async def __call__(self, handler, event: TelegramObject, data):
        user: User | None = data.get("user")
        session = data.get("session")
        settings = data.get("settings")

        if user is None or session is None:
            data["role_codes"] = set()
            data["is_manager"] = False
            data["can_intake"] = False
            data["is_bot_admin"] = False
            return await handler(event, data)

        rows = (
            (
                await session.execute(
                    select(Role.code)
                    .join(PositionRole, PositionRole.role_id == Role.id)
                    .join(Position, Position.id == PositionRole.position_id)
                    .join(RoleAssignment, RoleAssignment.position_id == Position.id)
                    .where(
                        RoleAssignment.user_id == user.id,
                        RoleAssignment.is_active.is_(True),
                        Position.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        role_codes = set(rows)

        is_bot_admin = False
        if user.is_admin:
            is_bot_admin = True
        if settings is not None and user.tg_id in (settings.bot_admin_ids or []):
            is_bot_admin = True

        data["role_codes"] = role_codes
        data["is_manager"] = "manager" in role_codes
        data["can_intake"] = ("intake" in role_codes) or ("manager" in role_codes)
        data["is_bot_admin"] = is_bot_admin
        return await handler(event, data)


class LocaleMiddleware(BaseMiddleware):
    @trace
    async def __call__(self, handler, event: TelegramObject, data):
        user: User | None = data.get("user")
        data["locale"] = user.locale if user else "ru"
        return await handler(event, data)


class SettingsMiddleware(BaseMiddleware):
    @trace
    def __init__(self, settings) -> None:
        self._settings = settings

    @trace
    async def __call__(self, handler, event: TelegramObject, data):
        data["settings"] = self._settings
        return await handler(event, data)


class AntiFloodMiddleware(BaseMiddleware):
    @trace
    def __init__(self, rate: int = 10, per_seconds: int = 5) -> None:
        self._rate = rate
        self._per = per_seconds
        self._buckets: dict[int, list[float]] = {}

    @trace
    async def __call__(self, handler, event: TelegramObject, data):
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        now = time.monotonic()
        bucket = self._buckets.setdefault(tg_user.id, [])
        bucket[:] = [t for t in bucket if now - t < self._per]

        if len(bucket) >= self._rate:
            log.warning("antiflood.blocked", user=tg_user.id)
            if isinstance(event, Message):
                await event.answer("Слишком много сообщений. Подождите.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Слишком часто.", show_alert=False)
            return None

        bucket.append(now)
        return await handler(event, data)


class DeepLinkMiddleware(BaseMiddleware):
    @trace
    async def __call__(self, handler, event: TelegramObject, data):
        if isinstance(event, Message):
            text = event.text or ""
            if text.startswith("/start "):
                data["deep_link"] = text.split(" ", 1)[1].strip()
            elif text == "/start":
                data["deep_link"] = None
        return await handler(event, data)
