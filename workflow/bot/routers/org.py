"""Профиль организации: рабочий день, SLA, вилка, гео, контакты, канал, приёмка.

Доступ: только manager.
"""

from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from ...config import Settings
from ...logging_setup import get_logger
from ...models import Position, PositionRole, Role, RoleAssignment, User
from ...services import org_settings as org_service
from ..keyboards import cancel_kb, org_intake_label_kb, org_kb, org_workday_kb
from ..states import OrgFSM
from ..texts import t
from ..utils import _safe_msg, trace

log = get_logger(__name__)
router = Router(name="org")


async def _is_manager(session, user: User) -> bool:
    row = (
        (
            await session.execute(
                select(RoleAssignment)
                .join(Position, Position.id == RoleAssignment.position_id)
                .join(PositionRole, PositionRole.position_id == Position.id)
                .join(Role, Role.id == PositionRole.role_id)
                .where(
                    RoleAssignment.user_id == user.id,
                    Role.code == "manager",
                    RoleAssignment.is_active.is_(True),
                    Position.is_active.is_(True),
                )
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    return row is not None


async def _can_use(event, user: User, session, settings: Settings) -> bool:
    if user.tg_id in (settings.bot_admin_ids or []):
        return True
    if user.is_admin:
        return True
    return await _is_manager(session, user)


@router.callback_query(F.data == "org_open")
@trace
async def org_open(
    cb: CallbackQuery,
    user: User,
    session,
    settings: Settings,
    locale: str,
) -> None:
    if not await _can_use(cb, user, session, settings):
        await cb.answer(t("common.not_allowed", locale), show_alert=True)
        return

    msg = _safe_msg(cb)
    if msg is None:
        await cb.answer()
        return

    org = await org_service.get_or_create(session, user.id)
    text = (
        f"<b>{t('org.title', locale)}</b>\n\n"
        f"Рабочий день: {org.workday_start}–{org.workday_end}\n"
        f"Вилка сроков: {'вкл' if org.use_range else 'выкл'}\n"
        f"SLA: {', '.join(str(h) + 'ч' for h in org.sla_warn_hours)}\n"
        f"Гео: {'вкл' if org.geotracking_enabled else 'выкл'}\n"
        f"Телефон: {org.phone or '—'}\n"
        f"Канал: {org.promo_channel_url or '—'}\n"
        f"Кнопка приёма: {org.intake_label or '🆕 Новая заявка'}"
    )
    await msg.edit_text(text, reply_markup=org_kb())
    await cb.answer()


@router.callback_query(F.data == "org_workday")
@trace
async def org_workday(
    cb: CallbackQuery,
    user: User,
    session,
    settings: Settings,
    locale: str,
) -> None:
    if not await _can_use(cb, user, session, settings):
        await cb.answer(t("common.not_allowed", locale), show_alert=True)
        return

    msg = _safe_msg(cb)
    if msg is None:
        await cb.answer()
        return

    org = await org_service.get_or_create(session, user.id)
    await msg.edit_text(
        t(
            "org.workday_title",
            locale,
            start=org.workday_start,
            end=org.workday_end,
            days=", ".join(
                t(f"org.weekday_{day}", locale)
                for day in sorted(org.workdays or [])
            ) or t("org.no_workdays", locale),
        ),
        reply_markup=org_workday_kb(
            org.workday_start,
            org.workday_end,
            list(org.workdays or []),
        ),
    )
    await cb.answer()


@router.callback_query(F.data.in_({"org_workday_start", "org_workday_end"}))
@trace
async def org_workday_edit_time(
    cb: CallbackQuery,
    user: User,
    session,
    settings: Settings,
    state: FSMContext,
    locale: str,
) -> None:
    if not await _can_use(cb, user, session, settings):
        await cb.answer(t("common.not_allowed", locale), show_alert=True)
        return

    msg = _safe_msg(cb)
    if msg is None:
        await cb.answer()
        return

    field = "workday_start" if cb.data == "org_workday_start" else "workday_end"
    await state.set_state(
        OrgFSM.workday_start if field == "workday_start" else OrgFSM.workday_end
    )
    await state.update_data(workday_field=field)
    await msg.edit_text(
        t("org.workday_time_prompt", locale, field=t(f"org.{field}", locale)),
        reply_markup=cancel_kb(),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("org_workday_day:"))
@trace
async def org_workday_toggle_day(
    cb: CallbackQuery,
    user: User,
    session,
    settings: Settings,
    locale: str,
) -> None:
    if not await _can_use(cb, user, session, settings):
        await cb.answer(t("common.not_allowed", locale), show_alert=True)
        return

    msg = _safe_msg(cb)
    if msg is None:
        await cb.answer()
        return

    try:
        day = int((cb.data or "").partition(":")[2])
    except ValueError:
        await cb.answer(t("common.error", locale), show_alert=True)
        return
    if day not in range(1, 8):
        await cb.answer(t("common.error", locale), show_alert=True)
        return

    org = await org_service.get_or_create(session, user.id)
    workdays = set(org.workdays or [])
    if day in workdays:
        if len(workdays) == 1:
            await cb.answer(t("org.workday_at_least_one", locale), show_alert=True)
            return
        workdays.remove(day)
    else:
        workdays.add(day)

    await org_service.update_field(session, user.id, "workdays", sorted(workdays))
    await session.commit()
    await org_workday(cb, user, session, settings, locale)


@router.message(OrgFSM.workday_start, F.text == "Отмена")
@router.message(OrgFSM.workday_end, F.text == "Отмена")
@trace
async def org_workday_cancel(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    settings: Settings,
    locale: str,
) -> None:
    await state.clear()
    await msg.answer(t("common.cancelled", locale))
    org = await org_service.get_or_create(session, user.id)
    await msg.answer(
        t(
            "org.workday_title",
            locale,
            start=org.workday_start,
            end=org.workday_end,
            days=", ".join(
                t(f"org.weekday_{day}", locale)
                for day in sorted(org.workdays or [])
            ) or t("org.no_workdays", locale),
        ),
        reply_markup=org_workday_kb(
            org.workday_start,
            org.workday_end,
            list(org.workdays or []),
        ),
    )


@router.message(OrgFSM.workday_start, F.text)
@router.message(OrgFSM.workday_end, F.text)
@trace
async def org_workday_save_time(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    settings: Settings,
    locale: str,
) -> None:
    if not await _can_use(msg, user, session, settings):
        await state.clear()
        return

    value = (msg.text or "").strip()
    try:
        parsed = datetime.strptime(value, "%H:%M").time()
    except ValueError:
        await msg.answer(t("org.workday_invalid_time", locale))
        return

    data = await state.get_data()
    field = data.get("workday_field")
    if field not in {"workday_start", "workday_end"}:
        await state.clear()
        await msg.answer(t("common.error", locale))
        return

    org = await org_service.get_or_create(session, user.id)
    other_value = org.workday_end if field == "workday_start" else org.workday_start
    other = datetime.strptime(other_value, "%H:%M").time()
    if (field == "workday_start" and parsed >= other) or (
        field == "workday_end" and parsed <= other
    ):
        await msg.answer(t("org.workday_invalid_range", locale))
        return

    await org_service.update_field(session, user.id, field, parsed.strftime("%H:%M"))
    await session.commit()
    await state.clear()
    org = await org_service.get_or_create(session, user.id)
    await msg.answer(t("common.saved", locale))
    await msg.answer(
        t(
            "org.workday_title",
            locale,
            start=org.workday_start,
            end=org.workday_end,
            days=", ".join(
                t(f"org.weekday_{day}", locale)
                for day in sorted(org.workdays or [])
            ) or t("org.no_workdays", locale),
        ),
        reply_markup=org_workday_kb(
            org.workday_start,
            org.workday_end,
            list(org.workdays or []),
        ),
    )


@router.callback_query(F.data == "org_intake_label")
@trace
async def org_intake_label(
    cb: CallbackQuery,
    user: User,
    session,
    settings: Settings,
    locale: str,
) -> None:
    if not await _can_use(cb, user, session, settings):
        await cb.answer(t("common.not_allowed", locale), show_alert=True)
        return

    msg = _safe_msg(cb)
    if msg is None:
        await cb.answer()
        return

    org = await org_service.get_or_create(session, user.id)
    await msg.edit_text(
        t("org.intake_label_prompt", locale),
        reply_markup=org_intake_label_kb(org.intake_label),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("org_intake_label_set:"))
@trace
async def org_intake_label_set(
    cb: CallbackQuery,
    user: User,
    session,
    settings: Settings,
    locale: str,
) -> None:
    if not await _can_use(cb, user, session, settings):
        await cb.answer(t("common.not_allowed", locale), show_alert=True)
        return

    value = (cb.data or "").partition(":")[2]
    if not value:
        await cb.answer(t("common.error", locale), show_alert=True)
        return

    await org_service.update_field(session, user.id, "intake_label", value)
    await session.commit()
    await org_open(cb, user, session, settings, locale)


@router.callback_query(F.data == "org_intake_label_custom")
@trace
async def org_intake_label_custom(
    cb: CallbackQuery,
    user: User,
    session,
    settings: Settings,
    state: FSMContext,
    locale: str,
) -> None:
    if not await _can_use(cb, user, session, settings):
        await cb.answer(t("common.not_allowed", locale), show_alert=True)
        return

    msg = _safe_msg(cb)
    if msg is None:
        await cb.answer()
        return

    await state.set_state(OrgFSM.intake_label)
    await msg.edit_text(
        t("org.intake_label_custom", locale),
        reply_markup=cancel_kb(),
    )
    await cb.answer()


@router.message(OrgFSM.intake_label, F.text == "Отмена")
@trace
async def org_intake_label_cancel(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    await state.clear()
    from ..keyboards import build_main_kb

    await msg.answer(t("common.cancelled", locale), reply_markup=build_main_kb("manager"))


@router.message(OrgFSM.intake_label, F.text)
@trace
async def org_intake_label_save(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    settings: Settings,
    locale: str,
) -> None:
    if not await _can_use(msg, user, session, settings):
        return

    value = (msg.text or "").strip()[:64]
    if len(value) < 2:
        await msg.answer(t("org.intake_label_too_short", locale))
        return

    await org_service.update_field(session, user.id, "intake_label", value)
    await session.commit()
    await state.clear()
    from ..keyboards import build_main_kb

    await msg.answer(
        t("common.saved", locale),
        reply_markup=build_main_kb("manager", value),
    )
