"""Глобальный обработчик ошибок aiogram."""

from __future__ import annotations

import traceback

from aiogram import Bot
from aiogram.types import ErrorEvent
from sqlalchemy.exc import SQLAlchemyError

from ..logging_setup import get_logger

log = get_logger(__name__)


async def on_error(event: ErrorEvent, bot: Bot) -> None:
    exc = event.exception
    update = event.update

    tb = traceback.format_exc()

    ctx = {
        "update_id": getattr(update, "update_id", None),
        "exception": exc.__class__.__name__,
        "message": str(exc)[:500],
    }

    if isinstance(exc, SQLAlchemyError):
        log.error("db.error", tb=tb, **ctx)
    else:
        log.error("handler.error", tb=tb, **ctx)

    user_msg = None
    if update.message:
        user_msg = update.message
    elif update.callback_query and update.callback_query.message:
        user_msg = update.callback_query.message

    if user_msg is None:
        return

    from .texts import t

    try:
        await user_msg.answer(t("common.error", "ru"))
    except Exception as e:
        log.warning("errors.reply_failed", error=str(e))


def setup_error_handler(dp) -> None:
    dp.errors.register(on_error)
