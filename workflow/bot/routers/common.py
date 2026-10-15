"""Общие хендлеры: отмена FSM."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy import select

from ...logging_setup import get_logger
from ...models import (
    OrgSettings,
    Position,
    PositionRole,
    Role,
    RoleAssignment,
    User,
)
from ..keyboards import build_main_kb
from ..texts import t
from ..utils import trace

log = get_logger(__name__)
router = Router(name="common")


async def _role_codes_for(session, user_id: int) -> set[str]:
    rows = (
        (
            await session.execute(
                select(Role.code)
                .join(PositionRole, PositionRole.role_id == Role.id)
                .join(Position, Position.id == PositionRole.position_id)
                .join(RoleAssignment, RoleAssignment.position_id == Position.id)
                .where(
                    RoleAssignment.user_id == user_id,
                    RoleAssignment.is_active.is_(True),
                    Position.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    return set(rows)


async def _manager_id_for(session, user_id: int) -> int | None:
    ra = (
        (
            await session.execute(
                select(RoleAssignment)
                .where(
                    RoleAssignment.user_id == user_id,
                    RoleAssignment.is_active.is_(True),
                )
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if ra is None:
        return None
    return ra.manager_id or user_id


async def _intake_label_for(session, manager_id: int | None) -> str | None:
    if manager_id is None:
        return None
    org = (
        (await session.execute(select(OrgSettings).where(OrgSettings.owner_id == manager_id)))
        .scalars()
        .first()
    )
    return org.intake_label if org else None


@router.callback_query(F.data == "cancel_fsm")
@trace
async def cancel_fsm(
    cb: CallbackQuery,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    await state.clear()

    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    role_codes = await _role_codes_for(session, user.id)
    is_manager = "manager" in role_codes
    can_intake = is_manager or "intake" in role_codes
    manager_id = await _manager_id_for(session, user.id)
    intake_label = await _intake_label_for(session, manager_id)

    kb = build_main_kb(
        is_manager=is_manager,
        can_intake=can_intake,
        intake_label=intake_label,
    )

    await cb.message.answer(t("common.cancelled", locale), reply_markup=kb)
    await cb.answer()
    log.info("cancel_fsm", user=user.id)
