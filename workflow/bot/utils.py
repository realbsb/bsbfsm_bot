"""Утилиты для бота."""

from __future__ import annotations

import functools
import inspect

from aiogram.types import CallbackQuery, Message

from ..logging_setup import get_logger

log = get_logger(__name__)


def _safe_msg(cb: CallbackQuery) -> Message | None:
    """Возвращает редактируемое сообщение callback или None для недоступного сообщения."""
    message = cb.message
    return message if isinstance(message, Message) else None


def trace(func):
    """Универсальный трассировщик: работает и с sync, и с async."""
    name = f"{func.__module__}.{func.__qualname__}"

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def awrapper(*args, **kwargs):
            log.debug("→ enter", func=name)
            try:
                result = await func(*args, **kwargs)
                log.debug("← exit", func=name, ok=True)
                return result
            except Exception as e:
                log.error("✗ error", func=name, error=str(e), exc_info=True)
                raise

        return awrapper

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        log.debug("→ enter", func=name)
        try:
            result = func(*args, **kwargs)
            log.debug("← exit", func=name, ok=True)
            return result
        except Exception as e:
            log.error("✗ error", func=name, error=str(e), exc_info=True)
            raise

    return wrapper
