"""Подтверждение заявки и создание проекта."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from sqlalchemy import select

from ....config import Settings
from ....logging_setup import get_logger
from ....models import Project, Stage, User
from ....services import stage_assign, stage_schedule
from ....services.intake import apply_to_project
from ....services.invite import create_client_invite
from ...keyboards import (
    cancel_inline_kb,
    request_confirm_kb,
    request_edit_menu_kb,
)
from ...states import RequestFSM
from ...texts import t
from ...utils import trace
from ._shared import get_form_cached, render_confirm
from .validators import check_required

log = get_logger(__name__)
router = Router(name="request_confirm")


@router.callback_query(RequestFSM.confirm, F.data == "req_restart")
@trace
async def req_restart(
    cb: CallbackQuery,
    state: FSMContext,
    locale: str,
) -> None:
    await state.update_data(raw_fields={})
    await state.set_state(RequestFSM.awaiting_details)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.message.answer(
        t("request.prompt_details", locale),
        reply_markup=cancel_inline_kb(),
    )
    await cb.answer()


@router.callback_query(RequestFSM.confirm, F.data == "req_cancel")
@trace
async def req_cancel(
    cb: CallbackQuery,
    state: FSMContext,
    locale: str,
) -> None:
    await state.clear()
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.message.answer(t("common.cancelled", locale))
    await cb.answer()


@router.callback_query(RequestFSM.confirm, F.data == "req_edit_menu")
@trace
async def req_edit_menu(
    cb: CallbackQuery,
    state: FSMContext,
    session,
    locale: str,
) -> None:
    form = await get_form_cached(session, state)
    try:
        await cb.message.edit_reply_markup(reply_markup=request_edit_menu_kb(form.logical))
    except Exception:
        pass
    await cb.answer()


@router.callback_query(RequestFSM.confirm, F.data == "req_back_to_confirm")
@trace
async def req_back(
    cb: CallbackQuery,
    state: FSMContext,
    locale: str,
) -> None:
    text = await render_confirm(state, locale)
    try:
        await cb.message.edit_text(text, reply_markup=request_confirm_kb())
    except Exception:
        pass
    await cb.answer()


@router.callback_query(RequestFSM.confirm, F.data.startswith("req_edit:"))
@trace
async def req_edit_pick(
    cb: CallbackQuery,
    state: FSMContext,
    session,
    locale: str,
) -> None:
    field = cb.data.split(":")[1]
    form = await get_form_cached(session, state)
    lf = form.logical_by_code(field)
    if lf is None:
        return await cb.answer(t("common.error", locale), show_alert=True)

    await state.update_data(edit_field=field)
    await state.set_state(RequestFSM.edit_field)
    label = lf.get("label", field)
    try:
        await cb.message.edit_text(t("request.edit_prompt", locale, field=label))
    except Exception:
        await cb.message.answer(t("request.edit_prompt", locale, field=label))
    await cb.answer()


@router.callback_query(RequestFSM.confirm, F.data == "req_ok")
@trace
async def req_ok(
    cb: CallbackQuery,
    state: FSMContext,
    user: User,
    session,
    settings: Settings,
    locale: str,
) -> None:
    data = await state.get_data()
    form = await get_form_cached(session, state)
    raw = data.get("raw_fields", {})
    manager_id = data.get("manager_id") or user.id

    missing = await check_required(form, raw)
    if missing:
        return await cb.answer(
            t("request.required_missing", locale, fields=", ".join(missing)),
            show_alert=True,
        )

    await state.clear()

    stage = (
        (
            await session.execute(
                select(Stage)
                .where(Stage.manager_id == manager_id, Stage.is_active.is_(True))
                .order_by(Stage.order_idx)
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if stage is None:
        return await cb.message.edit_text(t("request.no_stages", locale))

    project = Project(
        manager_id=manager_id,
        stage_id=stage.id,
        secretary_id=user.id,
    )
    session.add(project)
    await session.flush()

    await apply_to_project(session, project, form, raw)

    candidates = await stage_assign.candidates_for_stage(session, project, stage)
    if len(candidates) == 1:
        await stage_assign.assign(session, project, stage, candidates[0], user)
    else:
        await stage_assign.assign(session, project, stage, None, user)

    await stage_schedule.recalc(session, project)

    token = await create_client_invite(session, project, settings.qr_token_ttl_days)
    bot_username = (await cb.bot.me()).username
    invite_link = f"https://t.me/{bot_username}?start=client_{token}"
    invite_text = t("request.invite_text", locale, link=invite_link)

    await session.commit()

    body = t("request.created", locale, id=project.id, stage=t(stage.name_i18n_key, locale))
    body += "\n\n"
    body += t("request.for_client_hint", locale)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("request.copy_button", locale),
                    copy_text=CopyTextButton(text=invite_text),
                ),
            ]
        ]
    )
    await cb.message.edit_text(body, reply_markup=kb)
    log.info("request.created", project=project.id, secretary=user.id)
