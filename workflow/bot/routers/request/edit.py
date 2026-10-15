"""Редактирование одного поля из подтверждения."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ....logging_setup import get_logger
from ...states import RequestFSM
from ...texts import t
from ...utils import trace
from ._shared import show_confirm

log = get_logger(__name__)
router = Router(name="request_edit")


@router.message(RequestFSM.edit_field, F.voice)
@trace
async def edit_voice(
    msg: Message,
    state: FSMContext,
    locale: str,
    whisper,
) -> None:
    try:
        text = await whisper.transcribe(msg.voice)
    except Exception as e:
        log.warning("whisper.failed", error=str(e))
        return await msg.answer(t("errors.whisper_error", locale))

    log.info("whisper.result", text=text[:500], length=len(text))
    await _apply_edit(msg, state, text, locale)


@router.message(RequestFSM.edit_field, F.text)
@trace
async def edit_text(
    msg: Message,
    state: FSMContext,
    locale: str,
) -> None:
    await _apply_edit(msg, state, msg.text or "", locale)


async def _apply_edit(
    msg: Message,
    state: FSMContext,
    value: str,
    locale: str,
) -> None:
    data = await state.get_data()
    field = data.get("edit_field")
    if not field:
        await state.set_state(RequestFSM.confirm)
        return await show_confirm(msg, state, locale)

    raw = dict(data.get("raw_fields", {}))
    raw[field] = value.strip()
    await state.update_data(raw_fields=raw)
    await state.set_state(RequestFSM.confirm)
    await show_confirm(msg, state, locale)
