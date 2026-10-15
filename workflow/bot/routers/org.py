"""Профиль организации: рабочий день, SLA, вилка, гео, контакты, канал, приёмка.

Доступ: только manager.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from ...config import Settings
from ...logging_setup import get_logger
from ...models import Position, PositionRole, Role, RoleAssignment, User
from ...services import org_settings as org_service
from ..keyboards import cancel_kb, org_intake_label_kb, org_kb
from ..states import OrgFSM
from ..texts import t
from ..utils import trace

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


async def _can_use(event, user, session, settings) -> bool:
    if user.tg_id in (settings.bot_admin_ids or []):
        return True
    if user.is_admin:
        return True
    return await _is_manager(session, user)


# ============================================================
# Вход
# ============================================================


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
    await cb.message.edit_text(text, reply_markup=org_kb())
    await cb.answer()


# ============================================================
# Название кнопки приёма
# ============================================================


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
        return
    org = await org_service.get_or_create(session, user.id)
    await cb.message.edit_text(
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
        return
    value = cb.data.split(":", 1)[1]
    await org_service.update_field(session, user.id, "intake_label", value)
    await session.commit()
    await cb.answer(t("common.saved", locale))
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
        return
    await state.set_state(OrgFSM.intake_label)
    await cb.message.edit_text(
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
        return await msg.answer(t("org.intake_label_too_short", locale))
    await org_service.update_field(session, user.id, "intake_label", value)
    await session.commit()
    await state.clear()
    from ..keyboards import build_main_kb

    await msg.answer(
        t("common.saved", locale),
        reply_markup=build_main_kb("manager", value),
    )
