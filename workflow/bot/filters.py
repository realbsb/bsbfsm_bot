"""Фильтры aiogram по правам."""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject


class IsManager(BaseFilter):
    """True, если у user'а есть роль manager или он bot_admin."""

    async def __call__(self, event: TelegramObject, **data) -> bool:
        return bool(data.get("is_manager") or data.get("is_bot_admin"))


class CanIntake(BaseFilter):
    async def __call__(self, event: TelegramObject, **data) -> bool:
        return bool(data.get("can_intake") or data.get("is_bot_admin"))


class IsBotAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, **data) -> bool:
        return bool(data.get("is_bot_admin"))
