"""Управление командой менеджера.

Доступ: только manager (или BOT_ADMIN_IDS).
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from ...config import Settings
from ...logging_setup import get_logger
from ...models import (
    OrgSettings,
    Position,
    PositionRole,
    Role,
    RoleAssignment,
    User,
)
from ..keyboards import (
    invite_link_kb,
    position_edit_kb,
    position_flags_kb,
    position_pick_kb,
    positions_list_kb,
    team_checklist_kb,
    team_kb,
)
from ..states import TeamFSM
from ..texts import t
from ..utils import trace

log = get_logger(__name__)
router = Router(name="team")


async def _can_use(event, user, session, settings) -> bool:
    if user.tg_id in (settings.bot_admin_ids or []):
        return True
    if user.is_admin:
        return True
    # Есть ли роль manager
    rows = (
        (
            await session.execute(
                select(Role.code)
                .join(PositionRole, PositionRole.role_id == Role.id)
                .join(Position, Position.id == PositionRole.position_id)
                .join(RoleAssignment, RoleAssignment.position_id == Position.id)
                .where(
                    RoleAssignment.user_id == user.id,
                    RoleAssignment.is_active.is_(True),
                    Role.code == "manager",
                )
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    return rows is not None


# ============================================================
# Вход
# ============================================================


@router.message(Command("team"))
@trace
async def cmd_team(msg: Message, user: User, session, settings: Settings, locale: str) -> None:
    if not await _can_use(msg, user, session, settings):
        return
    await _show_team(msg, user, session, locale)


@router.callback_query(F.data == "team_open")
@trace
async def cb_team_open(
    cb: CallbackQuery, user: User, session, settings: Settings, locale: str
) -> None:
    if not await _can_use(cb, user, session, settings):
        return
    await _show_team(cb.message, user, session, locale, edit=True)
    await cb.answer()


async def _show_team(msg, user, session, locale, edit: bool = False) -> None:
    members = await _team_members(session, user.id)
    org = (
        (await session.execute(select(OrgSettings).where(OrgSettings.owner_id == user.id)))
        .scalars()
        .first()
    )

    org_ready = bool(org and org.phone)
    if not members and not org_ready:
        kb = team_checklist_kb()
        text = t("team.checklist_intro", locale)
    else:
        kb = team_kb(has_members=bool(members))
        text = _team_text(members, locale)

    try:
        if edit:
            await msg.edit_text(text, reply_markup=kb)
        else:
            await msg.answer(text, reply_markup=kb)
    except Exception:
        await msg.answer(text, reply_markup=kb)


# ============================================================
# Добавить подчинённого
# ============================================================


@router.callback_query(F.data == "team_add")
@trace
async def cb_team_add(
    cb: CallbackQuery, user: User, session, state: FSMContext, settings: Settings, locale: str
) -> None:
    if not await _can_use(cb, user, session, settings):
        return
    positions = (
        (
            await session.execute(
                select(Position)
                .where(
                    Position.manager_id == user.id,
                    Position.is_active.is_(True),
                )
                .order_by(Position.id)
            )
        )
        .scalars()
        .all()
    )
    await state.set_state(TeamFSM.pick_role)
    await cb.message.edit_text(
        t("team.pick_position", locale),
        reply_markup=position_pick_kb(positions),
    )
    await cb.answer()


@router.callback_query(TeamFSM.pick_role, F.data.startswith("team_add_pos:"))
@trace
async def cb_team_pick_position(
    cb: CallbackQuery, user: User, session, state: FSMContext, settings: Settings, locale: str
) -> None:
    if not await _can_use(cb, user, session, settings):
        await state.clear()
        return
    position_id = int(cb.data.split(":")[1])
    position = await session.get(Position, position_id)
    if position is None or position.manager_id != user.id:
        await state.clear()
        return await cb.answer(t("common.error", locale), show_alert=True)

    bot_info = await cb.bot.me()
    invite_url = f"https://t.me/{bot_info.username}?start=join_{user.id}_{position.id}"

    await state.clear()
    await cb.message.edit_text(
        t("team.invite_ready", locale, role=position.name, link=invite_url),
        reply_markup=invite_link_kb(invite_url),
    )
    await cb.answer()
    log.info("team.invite_generated", manager=user.id, position=position.code)


# ============================================================
# Профессии (должности)
# ============================================================


@router.callback_query(F.data == "team_positions")
@trace
async def cb_positions(
    cb: CallbackQuery, user: User, session, settings: Settings, locale: str
) -> None:
    if not await _can_use(cb, user, session, settings):
        return
    positions = (
        (
            await session.execute(
                select(Position)
                .where(
                    Position.manager_id == user.id,
                    Position.is_active.is_(True),
                )
                .order_by(Position.id)
            )
        )
        .scalars()
        .all()
    )

    lines = [t("team.positions_title", locale), ""]
    for p in positions:
        flags = await _flags_for(session, p.id)
        flag_names = ", ".join(t(f"roles.{f}", locale) for f in flags) or "—"
        lines.append(f"• <b>{p.name}</b> — {flag_names}")

    await cb.message.edit_text(
        "\n".join(lines),
        reply_markup=positions_list_kb(positions),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("team_pos_edit:"))
@trace
async def cb_pos_edit(
    cb: CallbackQuery, user: User, session, settings: Settings, locale: str
) -> None:
    if not await _can_use(cb, user, session, settings):
        return
    pos_id = int(cb.data.split(":")[1])
    pos = await session.get(Position, pos_id)
    if pos is None or pos.manager_id != user.id:
        return await cb.answer(t("common.not_found", locale), show_alert=True)

    flags = await _flags_for(session, pos_id)
    flag_names = ", ".join(t(f"roles.{f}", locale) for f in flags) or "—"
    await cb.message.edit_text(
        f"<b>{pos.name}</b>\nКод: <code>{pos.code}</code>\nФлаги: {flag_names}",
        reply_markup=position_edit_kb(pos_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("team_pos_rename:"))
@trace
async def cb_pos_rename(
    cb: CallbackQuery, user: User, session, state: FSMContext, settings: Settings, locale: str
) -> None:
    if not await _can_use(cb, user, session, settings):
        return
    pos_id = int(cb.data.split(":")[1])
    pos = await session.get(Position, pos_id)
    if pos is None or pos.manager_id != user.id:
        return await cb.answer(t("common.not_found", locale), show_alert=True)
    await state.set_state(TeamFSM.rename_position)
    await state.update_data(position_id=pos_id)
    await cb.message.edit_text(
        t("team.position_rename_prompt", locale),
        reply_markup=None,
    )
    await cb.answer()


@router.message(TeamFSM.rename_position, F.text)
@trace
async def on_pos_rename(
    msg: Message, user: User, session, state: FSMContext, settings: Settings, locale: str
) -> None:
    if not await _can_use(msg, user, session, settings):
        await state.clear()
        return
    data = await state.get_data()
    pos_id = data["position_id"]
    pos = await session.get(Position, pos_id)
    if pos is None or pos.manager_id != user.id:
        await state.clear()
        return
    name = (msg.text or "").strip()[:64]
    if len(name) < 2:
        return await msg.answer(t("team.position_name_too_short", locale))
    pos.name = name
    await session.commit()
    await state.clear()
    await msg.answer(t("common.saved", locale))


@router.callback_query(F.data.startswith("team_pos_flags:"))
@trace
async def cb_pos_flags(
    cb: CallbackQuery, user: User, session, settings: Settings, locale: str
) -> None:
    if not await _can_use(cb, user, session, settings):
        return
    pos_id = int(cb.data.split(":")[1])
    pos = await session.get(Position, pos_id)
    if pos is None or pos.manager_id != user.id:
        return await cb.answer(t("common.not_found", locale), show_alert=True)

    active = await _flags_for(session, pos_id)
    await cb.message.edit_text(
        t("team.position_flags_prompt", locale, name=pos.name),
        reply_markup=position_flags_kb(pos_id, active),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("team_pos_flag:"))
@trace
async def cb_pos_flag_toggle(
    cb: CallbackQuery, user: User, session, settings: Settings, locale: str
) -> None:
    if not await _can_use(cb, user, session, settings):
        return
    _, pos_id_s, flag_code = cb.data.split(":")
    pos_id = int(pos_id_s)
    pos = await session.get(Position, pos_id)
    if pos is None or pos.manager_id != user.id:
        return await cb.answer(t("common.not_found", locale), show_alert=True)

    role = (await session.execute(select(Role).where(Role.code == flag_code))).scalars().first()
    if role is None:
        return await cb.answer(t("common.error", locale), show_alert=True)

    existing = (
        (
            await session.execute(
                select(PositionRole).where(
                    PositionRole.position_id == pos_id,
                    PositionRole.role_id == role.id,
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        await session.delete(existing)
    else:
        session.add(PositionRole(position_id=pos_id, role_id=role.id))
    await session.commit()

    active = await _flags_for(session, pos_id)
    await cb.message.edit_reply_markup(reply_markup=position_flags_kb(pos_id, active))
    await cb.answer()


@router.callback_query(F.data.startswith("team_pos_delete:"))
@trace
async def cb_pos_delete(
    cb: CallbackQuery, user: User, session, settings: Settings, locale: str
) -> None:
    if not await _can_use(cb, user, session, settings):
        return
    pos_id = int(cb.data.split(":")[1])
    pos = await session.get(Position, pos_id)
    if pos is None or pos.manager_id != user.id:
        return await cb.answer(t("common.not_found", locale), show_alert=True)

    # Есть ли активные назначения?
    active = (
        (
            await session.execute(
                select(RoleAssignment)
                .where(
                    RoleAssignment.position_id == pos_id,
                    RoleAssignment.is_active.is_(True),
                )
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if active is not None:
        return await cb.answer(t("team.position_has_assignments", locale), show_alert=True)

    pos.is_active = False
    await session.commit()
    await cb.answer(t("common.saved", locale))
    await cb_positions(cb, user, session, settings, locale)


@router.callback_query(F.data == "team_pos_new")
@trace
async def cb_pos_new(
    cb: CallbackQuery, user: User, session, state: FSMContext, settings: Settings, locale: str
) -> None:
    if not await _can_use(cb, user, session, settings):
        return
    await state.set_state(TeamFSM.new_position_name)
    await cb.message.edit_text(t("team.position_new_prompt", locale))
    await cb.answer()


@router.message(TeamFSM.new_position_name, F.text)
@trace
async def on_pos_new(
    msg: Message, user: User, session, state: FSMContext, settings: Settings, locale: str
) -> None:
    if not await _can_use(msg, user, session, settings):
        await state.clear()
        return
    name = (msg.text or "").strip()[:64]
    if len(name) < 2:
        return await msg.answer(t("team.position_name_too_short", locale))

    # Код генерируем из имени
    import re

    code = re.sub(r"[^a-z0-9]+", "_", name.lower())[:24] or "pos"
    # Проверка уникальности
    existing = (
        (
            await session.execute(
                select(Position).where(
                    Position.manager_id == user.id,
                    Position.code == code,
                )
            )
        )
        .scalars()
        .first()
    )
    if existing:
        import secrets

        code = code + "_" + secrets.token_hex(2)

    pos = Position(manager_id=user.id, code=code, name=name, is_active=True)
    session.add(pos)
    await session.commit()
    await state.clear()
    await msg.answer(t("common.saved", locale))


# ============================================================
# Хелперы
# ============================================================


async def _flags_for(session, position_id: int) -> set[str]:
    rows = (
        (
            await session.execute(
                select(Role.code)
                .join(PositionRole, PositionRole.role_id == Role.id)
                .where(PositionRole.position_id == position_id)
            )
        )
        .scalars()
        .all()
    )
    return set(rows)


async def _team_members(session, manager_id: int) -> list[tuple[User, Position]]:
    rows = (
        await session.execute(
            select(User, Position)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .join(Position, Position.id == RoleAssignment.position_id)
            .where(
                RoleAssignment.manager_id == manager_id,
                RoleAssignment.is_active.is_(True),
                Position.is_active.is_(True),
            )
            .order_by(Position.name, User.first_name)
        )
    ).all()
    return [(u, p) for u, p in rows]


def _team_text(members: list[tuple[User, Position]], locale: str) -> str:
    if not members:
        return t("team.empty", locale)
    lines = [t("team.title", locale), ""]
    for u, p in members:
        name = u.first_name or u.username or f"id{u.id}"
        lines.append(f"• {name} — {p.name}")
    return "\n".join(lines)
