"""Профиль пользователя: язык, Radicale, встречи, согласия, вход в команду/организацию."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup
from sqlalchemy import select

from ...logging_setup import get_logger
from ...models import Position, PositionRole, Role, RoleAssignment, User, UserCalendarPref
from ..keyboards import (
    build_main_kb,
    cancel_kb,
    lang_kb,
    profile_kb,
)
from ..states import ProfileFSM
from ..texts import t
from ..utils import trace

log = get_logger(__name__)
router = Router(name="profile")


# ============================================================
# Хелперы
# ============================================================


async def _get_pref(session, user_id: int) -> UserCalendarPref:
    pref = (
        (await session.execute(select(UserCalendarPref).where(UserCalendarPref.user_id == user_id)))
        .scalars()
        .first()
    )
    if pref is None:
        pref = UserCalendarPref(user_id=user_id)
        session.add(pref)
        await session.flush()
    return pref


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


async def _main_kb_for(session, user: User) -> ReplyKeyboardMarkup:
    from ...models import OrgSettings, Position, PositionRole, Role, RoleAssignment

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
                    Position.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    role_codes = set(rows)
    is_manager = "manager" in role_codes
    can_intake = is_manager or "intake" in role_codes

    manager_id = None
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
    if ra:
        manager_id = ra.manager_id or user.id

    intake_label = None
    if manager_id:
        org = (
            (await session.execute(select(OrgSettings).where(OrgSettings.owner_id == manager_id)))
            .scalars()
            .first()
        )
        intake_label = org.intake_label if org else None

    return build_main_kb(
        is_manager=is_manager,
        can_intake=can_intake,
        intake_label=intake_label,
    )


async def _roles_for(session, user_id: int) -> list[str]:
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
    return list(set(rows))


async def _show_profile(msg, user, session, locale, edit: bool = False) -> None:
    role_codes = await _roles_for(session, user.id)
    pref = await _get_pref(session, user.id)

    roles_text = (
        ", ".join(t(f"roles.{r}", locale) for r in role_codes)
        if role_codes
        else t("profile.no_roles", locale)
    )
    radicale_status = "✅" if pref.radicale_username else "—"
    meetings_status = "✅" if pref.meetings_enabled else "—"

    text = (
        f"<b>{t('profile.title', locale)}</b>\n"
        f"ID: <code>{user.id}</code>\n"
        f"Telegram: @{user.username or '—'}\n"
        f"{t('profile.roles', locale)}: {roles_text}\n"
        f"Radicale: {radicale_status}\n"
        f"Встречи: {meetings_status}"
    )

    is_manager = "manager" in role_codes
    kb = profile_kb(is_manager=is_manager, can_manage_org=is_manager)

    if edit:
        try:
            await msg.edit_text(text, reply_markup=kb)
        except Exception:
            await msg.answer(text, reply_markup=kb)
    else:
        await msg.answer(text, reply_markup=kb)


# ============================================================
# Вход в профиль
# ============================================================


@router.message(Command("profile"))
@trace
async def profile_cmd(msg: Message, user: User, session, locale: str) -> None:
    await _show_profile(msg, user, session, locale)


@router.message(F.text == "⚙️ Профиль")
@trace
async def profile_btn(msg: Message, user: User, session, locale: str) -> None:
    await _show_profile(msg, user, session, locale)


@router.callback_query(F.data == "profile_back")
@trace
async def profile_back(cb: CallbackQuery, user: User, session, locale: str) -> None:
    await _show_profile(cb.message, user, session, locale, edit=True)
    await cb.answer()


# ============================================================
# Язык
# ============================================================


@router.callback_query(F.data == "profile_lang")
@trace
async def profile_lang(cb: CallbackQuery, user: User, locale: str) -> None:
    await cb.message.edit_text(
        t("profile.locale", locale),
        reply_markup=lang_kb(user.locale),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("lang:"))
@trace
async def on_lang(cb: CallbackQuery, user: User, session) -> None:
    code = cb.data.split(":")[1]
    if code not in ("ru", "en", "kz"):
        return await cb.answer("Unsupported")
    user.locale = code
    await session.commit()
    name = {"ru": "Русский", "en": "English", "kz": "Қазақша"}[code]
    await cb.message.edit_text(t("profile.locale_changed", code, name=name))
    await cb.answer()


# ============================================================
# Встречи
# ============================================================


@router.callback_query(F.data == "profile_meetings")
@trace
async def meetings_toggle(cb: CallbackQuery, user: User, session, locale: str) -> None:
    pref = await _get_pref(session, user.id)
    pref.meetings_enabled = not pref.meetings_enabled
    await session.commit()
    await cb.answer("Встречи включены" if pref.meetings_enabled else "Встречи отключены")


# ============================================================
# Согласия
# ============================================================


@router.callback_query(F.data == "profile_consents")
@trace
async def consents(cb: CallbackQuery, user: User, session, locale: str) -> None:

    # TODO(этап5): WebApp-страницы /legal/*
    text = (
        "<b>Согласия</b>\n\n"
        f"Обработка ПД: {'✅' if user.pd_consent_at else '—'}\n"
        f"Геолокация: {'✅' if user.geo_consent_at else '—'}\n"
        f"Оферта: {'✅' if user.offer_accepted_at else '—'}\n\n"
        "Нажмите, чтобы согласиться."
    )
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Согласие на ПД", callback_data="consent_pd")],
            [InlineKeyboardButton(text="✅ Согласие на гео", callback_data="consent_geo")],
            [InlineKeyboardButton(text="✅ Принять оферту", callback_data="consent_offer")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="profile_back")],
        ]
    )
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except Exception:
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data == "consent_pd")
@trace
async def consent_pd(cb: CallbackQuery, user: User, session, locale: str) -> None:
    from datetime import datetime

    user.pd_consent_at = datetime.utcnow()
    user.pd_consent_version = "2026-10-04"
    await session.commit()
    await cb.answer("Сохранено")


@router.callback_query(F.data == "consent_geo")
@trace
async def consent_geo(cb: CallbackQuery, user: User, session, locale: str) -> None:
    from datetime import datetime

    user.geo_consent_at = datetime.utcnow()
    await session.commit()
    await cb.answer("Сохранено")


@router.callback_query(F.data == "consent_offer")
@trace
async def consent_offer(cb: CallbackQuery, user: User, session, locale: str) -> None:
    from datetime import datetime

    user.offer_accepted_at = datetime.utcnow()
    user.offer_version = "2026-10-04"
    await session.commit()
    await cb.answer("Сохранено")


# ============================================================
# Radicale
# ============================================================


@router.callback_query(F.data == "profile_radicale")
@trace
async def radicale_open(
    cb: CallbackQuery,
    state: FSMContext,
    session,
    user: User,
    locale: str,
) -> None:
    pref = await _get_pref(session, user.id)

    if pref.radicale_username:
        text = (
            f"Текущий URL: <code>{pref.radicale_url or '—'}</code>\n"
            f"Логин: <code>{pref.radicale_username}</code>\n\n"
            f"Отправьте новый URL или «-», чтобы удалить доступ."
        )
    else:
        text = (
            "Введите URL Radicale-сервера.\n"
            "Например: <code>http://192.168.0.1:5232</code>\n\n"
            "Или отправьте «-», чтобы отменить."
        )

    await state.set_state(ProfileFSM.radicale_url)
    await cb.message.edit_text(text, reply_markup=cancel_kb())
    await cb.answer()


@router.message(
    StateFilter(
        ProfileFSM.radicale_url,
        ProfileFSM.radicale_username,
        ProfileFSM.radicale_password,
    ),
    F.text == "Отмена",
)
@trace
async def radicale_cancel(
    msg: Message, state: FSMContext, user: User, session, locale: str
) -> None:
    await state.clear()
    kb = await _main_kb_for(session, user)
    await msg.answer(t("common.cancelled", locale), reply_markup=kb)


@router.message(ProfileFSM.radicale_url, F.text)
@trace
async def radicale_url(
    msg: Message,
    state: FSMContext,
    session,
    user: User,
    locale: str,
) -> None:
    text = (msg.text or "").strip()

    if text == "-":
        pref = await _get_pref(session, user.id)
        pref.radicale_url = None
        pref.radicale_username = None
        pref.radicale_password = None
        await session.commit()
        await state.clear()
        kb = await _main_kb_for(session, user)
        return await msg.answer("Доступ Radicale удалён.", reply_markup=kb)

    if not text.startswith("http"):
        return await msg.answer("URL должен начинаться с http:// или https://")

    await state.update_data(radicale_url=text)
    await state.set_state(ProfileFSM.radicale_username)
    await msg.answer("Введите логин Radicale:", reply_markup=cancel_kb())


@router.message(ProfileFSM.radicale_username, F.text)
@trace
async def radicale_username(msg: Message, state: FSMContext) -> None:
    await state.update_data(radicale_username=(msg.text or "").strip())
    await state.set_state(ProfileFSM.radicale_password)
    await msg.answer("Введите пароль Radicale:", reply_markup=cancel_kb())


@router.message(ProfileFSM.radicale_password, F.text)
@trace
async def radicale_password(
    msg: Message,
    state: FSMContext,
    session,
    user: User,
) -> None:
    data = await state.get_data()
    pref = await _get_pref(session, user.id)
    pref.radicale_url = data["radicale_url"]
    pref.radicale_username = data["radicale_username"]
    pref.radicale_password = (msg.text or "").strip()
    await session.commit()
    await state.clear()

    try:
        await msg.delete()
    except Exception:
        pass

    kb = await _main_kb_for(session, user)
    await msg.answer("✅ Radicale-доступ сохранён.", reply_markup=kb)
    log.info("profile.radicale_saved", user=user.id)


# ============================================================
# Формы заявок (менеджер) — проксируем в forms.py
# ============================================================


@router.callback_query(F.data == "forms_open")
@trace
async def forms_open_proxy(cb: CallbackQuery, user: User, session, locale: str) -> None:
    from ...models import RequestForm
    from ..keyboards import form_kind_kb

    rows = (
        (await session.execute(select(RequestForm).where(RequestForm.manager_id == user.id)))
        .scalars()
        .all()
    )

    if not rows:
        await cb.message.edit_text(
            t("forms.empty", locale),
            reply_markup=form_kind_kb(),
        )
    else:
        lines = [t("forms.title", locale)]
        for f in rows:
            status = "✅" if f.is_active else "⏸"
            lines.append(f"{status} {f.title}")
        await cb.message.edit_text(
            "\n".join(lines),
            reply_markup=form_kind_kb(),
        )
    await cb.answer()
