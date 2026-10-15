"""Старт заявки: /new, Reply-кнопка."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import select

from ....logging_setup import get_logger
from ....models import RoleAssignment, User
from ....services.intake import get_form
from ...keyboards import cancel_inline_kb
from ...states import RequestFSM
from ...texts import t
from ...utils import trace

log = get_logger(__name__)
router = Router(name="request_start")


@router.message(Command("new"))
@trace
async def new_request_cmd(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    await _start_request(msg, state, user, session, locale)


@router.message(F.text == "🆕 Новая заявка")
@trace
async def new_request_btn(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    await _start_request(msg, state, user, session, locale)


async def _start_request(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    await state.clear()

    manager_id = user.id
    ra = (
        (
            await session.execute(
                select(RoleAssignment)
                .where(
                    RoleAssignment.user_id == user.id,
                    RoleAssignment.is_active.is_(True),
                )
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if ra and ra.manager_id:
        manager_id = ra.manager_id

    form = await get_form(session, manager_id)
    await state.update_data(
        manager_id=manager_id,
        raw_fields={},
        _form_def={"physical": form.physical, "logical": form.logical},
    )
    await state.set_state(RequestFSM.awaiting_details)

    await msg.answer(
        t("request.prompt_details", locale),
        reply_markup=cancel_inline_kb(),
    )
