"""Первый запуск, регистрация, главное меню, deep-link."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
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
from ...services.invite import verify_token
from ...services.seed import seed_new_manager
from ..keyboards import build_main_kb, lang_kb
from ..texts import SUPPORTED_LOCALES, detect_locale, t
from ..utils import trace

log = get_logger(__name__)
router = Router(name="start")


@router.message(CommandStart())
@trace
async def cmd_start(
    msg: Message,
    command: CommandObject,
    state: FSMContext,
    user: User,
    session,
    settings: Settings,
    locale: str,
) -> None:
    await state.clear()

    payload = (command.args or "").strip()
    if payload:
        return await _handle_deeplink(msg, payload, user, session, locale, settings)

    if user.locale not in SUPPORTED_LOCALES:
        user.locale = detect_locale(msg.from_user.language_code)
        await session.flush()
        locale = user.locale

    await _greet(msg, state, user, session, locale, settings)


async def _greet(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    locale: str,
    settings: Settings,
) -> None:
    ra = await _active_role_assignment(session, user.id)
    if ra is not None:
        role_codes = await _role_codes_for(session, user.id)
        is_manager = "manager" in role_codes
        can_intake = is_manager or "intake" in role_codes
        manager_id = ra.manager_id or user.id
        intake_label = await _intake_label(session, manager_id)
        kb = build_main_kb(
            is_manager=is_manager,
            can_intake=can_intake,
            intake_label=intake_label,
        )
        return await msg.answer(
            t("start.welcome_back", locale, name=user.first_name or ""),
            reply_markup=kb,
        )

    any_manager = await session.scalar(
        select(RoleAssignment)
        .join(Position, Position.id == RoleAssignment.position_id)
        .join(PositionRole, PositionRole.position_id == Position.id)
        .join(Role, Role.id == PositionRole.role_id)
        .where(Role.code == "manager", RoleAssignment.is_active.is_(True))
        .limit(1)
    )

    if any_manager is None:
        return await _bootstrap_first_manager(msg, user, session, locale)

    await _start_client_intake(msg, state, user, session, locale)


async def _bootstrap_first_manager(
    msg: Message,
    user: User,
    session,
    locale: str,
) -> None:
    """Первый в системе — становится manager'ом."""
    await seed_new_manager(session, user)

    # Создаём RoleAssignment на должность manager
    manager_pos = (
        (
            await session.execute(
                select(Position).where(
                    Position.manager_id == user.id,
                    Position.code == "manager",
                )
            )
        )
        .scalars()
        .first()
    )
    if manager_pos is not None:
        session.add(
            RoleAssignment(
                user_id=user.id,
                position_id=manager_pos.id,
                manager_id=None,
                assigned_by=None,
                is_active=True,
            )
        )
    await session.commit()

    intake_label = await _intake_label(session, user.id)
    kb = build_main_kb(is_manager=True, can_intake=True, intake_label=intake_label)
    log.info("user.promoted_to_manager", user=user.id)
    await msg.answer(t("start.welcome_new_manager", locale), reply_markup=kb)


async def _start_client_intake(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    await msg.answer(
        t("start.welcome_client", locale),
        reply_markup=ReplyKeyboardRemove(),
    )
    log.info("user.client_arrived", user=user.id)


async def _handle_deeplink(
    msg: Message,
    payload: str,
    user: User,
    session,
    locale: str,
    settings: Settings,
) -> None:
    log.info("start.deeplink", user=user.id, payload=payload[:32])

    if payload.startswith("client_"):
        token = payload[len("client_") :]
        project = await verify_token(session, token)
        if project is None:
            return await _show_client_lk(msg, session, user, locale, fallback=True)
        if project.client_user_id is None:
            project.client_user_id = user.id
            await session.commit()
            log.info("client.linked", project=project.id, user=user.id)
        return await _show_client_lk(msg, session, user, locale)

    if payload.startswith("join_"):
        return await _handle_join(msg, payload, user, session, locale)

    if payload.startswith("order_"):
        return await _handle_order(msg, payload, user, session, locale)

    await _greet(msg, None, user, session, locale, settings)  # type: ignore[arg-type]


async def _handle_join(
    msg: Message,
    payload: str,
    user: User,
    session,
    locale: str,
) -> None:
    """join_<manager_id>_<position_id> — сотрудник входит в команду."""
    parts = payload.split("_")
    if len(parts) != 3:
        return await msg.answer(t("common.error", locale))
    try:
        manager_id = int(parts[1])
        position_id = int(parts[2])
    except ValueError:
        return await msg.answer(t("common.error", locale))

    manager = await session.get(User, manager_id)
    if manager is None:
        return await msg.answer(t("team.invite_manager_missing", locale))

    position = await session.get(Position, position_id)
    if position is None or position.manager_id != manager_id:
        return await msg.answer(t("team.invite_role_missing", locale))

    existing = (
        (
            await session.execute(
                select(RoleAssignment).where(
                    RoleAssignment.user_id == user.id,
                    RoleAssignment.position_id == position_id,
                    RoleAssignment.manager_id == manager_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if existing:
        return await msg.answer(t("team.already_in_team", locale))

    session.add(
        RoleAssignment(
            user_id=user.id,
            position_id=position_id,
            manager_id=manager_id,
            assigned_by=manager_id,
            is_active=True,
        )
    )

    # Снимаем менеджера с этой должности, если он сам её занимал
    mgr_ra = (
        (
            await session.execute(
                select(RoleAssignment).where(
                    RoleAssignment.user_id == manager_id,
                    RoleAssignment.position_id == position_id,
                    RoleAssignment.is_active.is_(True),
                )
            )
        )
        .scalars()
        .first()
    )
    if mgr_ra is not None:
        mgr_ra.is_active = False
        log.info("team.self_unassigned", manager=manager_id, position=position.code)

    await session.commit()

    role_codes = await _role_codes_for(session, user.id)
    is_manager = "manager" in role_codes
    can_intake = is_manager or "intake" in role_codes
    intake_label = await _intake_label(session, manager_id)
    kb = build_main_kb(
        is_manager=is_manager,
        can_intake=can_intake,
        intake_label=intake_label,
    )
    log.info("team.joined", user=user.id, manager=manager_id, position=position.code)
    await msg.answer(
        t("team.joined_success", locale, manager=manager.first_name or "менеджер"),
        reply_markup=kb,
    )


async def _handle_order(
    msg: Message,
    payload: str,
    user: User,
    session,
    locale: str,
) -> None:
    await msg.answer(t("start.order_hello", locale))


async def _show_client_lk(
    msg: Message,
    session,
    user: User,
    locale: str,
    fallback: bool = False,
) -> None:
    from ...models import Project, Stage
    from ..keyboards import client_project_kb

    project = (
        (
            await session.execute(
                select(Project)
                .where(Project.client_user_id == user.id, Project.closed_at.is_(None))
                .order_by(Project.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )

    if project is None:
        text = (
            t("client.no_project_fallback", locale) if fallback else t("client.no_project", locale)
        )
        return await msg.answer(text, reply_markup=ReplyKeyboardRemove())

    stage = await session.get(Stage, project.stage_id)
    lines = [
        f"<b>Заявка #{project.id}</b>",
        f"Статус: <b>{t(stage.name_i18n_key, locale) if stage else '—'}</b>",
    ]
    if project.address_text:
        lines.append(f"📍 {project.address_text}")
    if project.price_agreed:
        lines.append(f"💰 Согласовано: {project.price_agreed} ₽")
        paid = (project.prepay_paid or 0) + (project.final_paid or 0)
        lines.append(f"Внесено: {paid} ₽")

    await msg.answer("\n".join(lines), reply_markup=client_project_kb(project.id))


async def _active_role_assignment(session, user_id: int) -> RoleAssignment | None:
    return (
        (
            await session.execute(
                select(RoleAssignment).where(
                    RoleAssignment.user_id == user_id,
                    RoleAssignment.is_active.is_(True),
                )
            )
        )
        .scalars()
        .first()
    )


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


async def _intake_label(session, manager_id: int) -> str | None:
    org = (
        (await session.execute(select(OrgSettings).where(OrgSettings.owner_id == manager_id)))
        .scalars()
        .first()
    )
    return org.intake_label if org else None


@router.message(Command("lang"))
@trace
async def cmd_lang(msg: Message, user: User, locale: str) -> None:
    await msg.answer(t("profile.locale", locale), reply_markup=lang_kb(user.locale))


@router.callback_query(F.data.startswith("lang:"))
@trace
async def on_lang(cb: CallbackQuery, user: User, session) -> None:
    code = cb.data.split(":")[1]
    if code not in SUPPORTED_LOCALES:
        return await cb.answer("Unsupported")
    user.locale = code
    await session.commit()
    name = {"ru": "Русский", "en": "English", "kz": "Қазақша"}[code]
    await cb.message.edit_text(t("profile.locale_changed", code, name=name))
    await cb.answer()
