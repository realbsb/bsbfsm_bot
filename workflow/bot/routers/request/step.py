"""Пошаговый ввод по логическим полям."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ....logging_setup import get_logger
from ...keyboards import cancel_inline_kb
from ...states import RequestFSM
from ...texts import t
from ...utils import trace
from ._shared import get_form_cached, show_confirm

log = get_logger(__name__)
router = Router(name="request_step")


@router.callback_query(RequestFSM.confirm, F.data == "req_step_by_step")
@trace
async def req_step_start(
    cb: CallbackQuery,
    state: FSMContext,
    session,
    locale: str,
) -> None:
    form = await get_form_cached(session, state)
    await state.update_data(
        step_index=0,
        step_fields=[f["code"] for f in form.logical],
    )
    await state.set_state(RequestFSM.step_by_step)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _ask_step(cb.message, state, session, locale)
    await cb.answer()


async def _ask_step(msg, state, session, locale: str) -> None:
    form = await get_form_cached(session, state)
    data = await state.get_data()
    idx = data.get("step_index", 0)
    if idx >= len(form.logical):
        return await _finish_steps(msg, state, locale)

    lf = form.logical[idx]
    label = lf.get("label", lf["code"])
    await msg.answer(
        t("request.step_prompt", locale, field=label),
        reply_markup=cancel_inline_kb(),
    )


@router.message(RequestFSM.step_by_step, F.voice)
@trace
async def step_voice(
    msg: Message,
    state: FSMContext,
    session,
    locale: str,
    whisper,
) -> None:
    try:
        text = await whisper.transcribe(msg.voice)
    except Exception as e:
        log.warning("whisper.failed", error=str(e))
        return await msg.answer(t("errors.whisper_error", locale))

    log.info("whisper.result", text=text[:500], length=len(text))
    await _apply_step(msg, state, session, text, locale)


@router.message(RequestFSM.step_by_step, F.text)
@trace
async def step_text(
    msg: Message,
    state: FSMContext,
    session,
    locale: str,
) -> None:
    await _apply_step(msg, state, session, msg.text or "", locale)


async def _apply_step(
    msg: Message,
    state: FSMContext,
    session,
    value: str,
    locale: str,
) -> None:
    form = await get_form_cached(session, state)
    data = await state.get_data()
    idx = data.get("step_index", 0)
    if idx >= len(form.logical):
        return

    lf = form.logical[idx]
    raw = dict(data.get("raw_fields", {}))
    raw[lf["code"]] = value.strip()
    await state.update_data(raw_fields=raw)

    label = lf.get("label", lf["code"])
    await msg.answer(t("request.step_saved", locale, field=label, value=value.strip()))

    idx += 1
    await state.update_data(step_index=idx)
    if idx >= len(form.logical):
        await _finish_steps(msg, state, locale)
    else:
        await _ask_step(msg, state, session, locale)


@router.callback_query(RequestFSM.step_by_step, F.data == "req_step_restart_current")
@trace
async def step_restart_current(
    cb: CallbackQuery,
    state: FSMContext,
    session,
    locale: str,
) -> None:
    await _ask_step(cb.message, state, session, locale)
    await cb.answer()


async def _finish_steps(
    msg,
    state: FSMContext,
    locale: str,
) -> None:
    await state.set_state(RequestFSM.confirm)
    await show_confirm(msg, state, locale)
