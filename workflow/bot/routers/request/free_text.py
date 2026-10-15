"""Приём свободного текста или голоса."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ....logging_setup import get_logger
from ...states import RequestFSM
from ...texts import t
from ...utils import trace
from ._shared import show_confirm
from .parser import parse_text

log = get_logger(__name__)
router = Router(name="request_free_text")


@router.message(RequestFSM.awaiting_details, F.voice)
@trace
async def on_voice(
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

    if not text:
        return await msg.answer(t("request.prompt_details", locale))

    await _process_text(msg, state, text, locale)


@router.message(RequestFSM.awaiting_details, F.text)
@trace
async def on_text(
    msg: Message,
    state: FSMContext,
    locale: str,
) -> None:
    await _process_text(msg, state, msg.text or "", locale)


async def _process_text(
    msg: Message,
    state: FSMContext,
    text: str,
    locale: str,
) -> None:
    parsed = await parse_text(text, llm=None)
    raw_fields = parsed or {}
    await state.update_data(raw_fields=raw_fields, raw_text=text)
    await state.set_state(RequestFSM.confirm)
    await show_confirm(msg, state, locale)
