"""Fallback для устаревшего FSM VoiceFallbackFSM.

Оставлен для совместимости. Сейчас не используется — парсинг в request.py.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...logging_setup import get_logger
from ..keyboards import cancel_inline_kb
from ..states import RequestFSM, VoiceFallbackFSM
from ..texts import t
from ..utils import trace

log = get_logger(__name__)
router = Router(name="fallback")


@router.message(VoiceFallbackFSM.question, F.text)
@trace
async def on_answer(
    msg: Message,
    state: FSMContext,
    locale: str,
) -> None:
    from .request import _parse_by_markers

    text = (msg.text or "").strip()
    if text == "Отмена":
        await state.clear()
        return await msg.answer(t("common.cancelled", locale))

    parsed = _parse_by_markers(text)
    await state.update_data(raw_fields=parsed, raw_text=text)
    await state.set_state(RequestFSM.confirm)
    await msg.answer(
        t("request.parsed_short", locale, count=len(parsed)),
        reply_markup=cancel_inline_kb(),
    )


@router.callback_query(VoiceFallbackFSM.question, F.data == "skip_field")
@trace
async def on_skip(
    cb: CallbackQuery,
    state: FSMContext,
    locale: str,
) -> None:
    await state.clear()
    await cb.message.edit_text(t("common.cancelled", locale))
    await cb.answer()
