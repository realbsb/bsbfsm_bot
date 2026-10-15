"""Личный кабинет заказчика.

Заказчик видит:
- статус заявки,
- согласованную сумму и этап оплаты,
- финальные медиа,
- кнопку «Добавить в Google Calendar» для встреч,
- кнопку «Принять работы» после сдачи.
"""

from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select

from ...logging_setup import get_logger
from ...models import (
    CalendarEvent,
    MediaAsset,
    Project,
    ProjectEvent,
    Stage,
    User,
)
from ...services.gcal_link import make_gcal_url_from_meeting
from ..keyboards import client_project_kb, main_kb
from ..texts import t
from ..utils import trace

log = get_logger(__name__)
router = Router(name="client")


@router.callback_query(F.data.startswith("client_view:"))
@trace
async def client_view(
    cb: CallbackQuery,
    user: User,
    session,
    locale: str,
) -> None:
    project_id = int(cb.data.split(":")[1])
    project = await session.get(Project, project_id)
    if project is None or project.client_user_id != user.id:
        return await cb.answer(t("common.not_allowed", locale), show_alert=True)

    await _render_project(cb.message, project, session, locale, edit=True)
    await cb.answer()


@router.callback_query(F.data.startswith("client_accept:"))
@trace
async def client_accept(
    cb: CallbackQuery,
    user: User,
    session,
    locale: str,
) -> None:
    project_id = int(cb.data.split(":")[1])
    project = await session.get(Project, project_id)
    if project is None or project.client_user_id != user.id:
        return await cb.answer(t("common.not_allowed", locale), show_alert=True)

    if project.closed_at is None:
        return await cb.answer("Работы ещё не сданы.", show_alert=True)

    session.add(
        ProjectEvent(
            project_id=project_id,
            actor_id=user.id,
            type="client_accept",
        )
    )
    await session.commit()

    await cb.message.edit_text("✅ Приёмка подтверждена. Спасибо!")
    log.info("client.accepted", project=project_id, user=user.id)
    await cb.answer()


@router.callback_query(F.data.startswith("client_meeting:"))
@trace
async def client_meeting(
    cb: CallbackQuery,
    user: User,
    session,
    locale: str,
) -> None:
    """Показывает кнопку «Добавить в Google Calendar» для ближайшей встречи."""
    project_id = int(cb.data.split(":")[1])
    project = await session.get(Project, project_id)
    if project is None or project.client_user_id != user.id:
        return await cb.answer(t("common.not_allowed", locale), show_alert=True)

    meeting = (
        (
            await session.execute(
                select(CalendarEvent)
                .where(
                    CalendarEvent.project_id == project_id,
                    CalendarEvent.approver_id == user.id,
                    CalendarEvent.start_at >= datetime.utcnow(),
                )
                .order_by(CalendarEvent.start_at)
                .limit(1)
            )
        )
        .scalars()
        .first()
    )

    if meeting is None:
        return await cb.answer("Нет предстоящих встреч", show_alert=True)

    gcal_url = make_gcal_url_from_meeting(
        project_id=project.id,
        title=f"Встреча по проекту #{project.id}",
        start=meeting.start_at,
        duration_minutes=int((meeting.end_at - meeting.start_at).total_seconds() // 60),
        address=project.address_text or "",
        description=project.description or "",
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📅 Добавить в Google Calendar", url=gcal_url),
            ]
        ]
    )
    await cb.message.answer(
        f"Встреча: {meeting.start_at.strftime('%d.%m.%Y %H:%M')}",
        reply_markup=kb,
    )
    await cb.answer()


@trace
async def _render_project(
    msg: Message,
    project: Project,
    session,
    locale: str,
    edit: bool = False,
) -> None:
    stage = await session.get(Stage, project.stage_id)
    lines = [
        f"<b>Заявка #{project.id}</b>",
        f"Статус: <b>{t(stage.name_i18n_key, locale) if stage else '—'}</b>",
    ]

    if project.address_text:
        lines.append(f"📍 {project.address_text}")

    if project.description:
        lines.append(f"📝 {project.description[:200]}")

    if project.price_agreed:
        lines.append(f"💰 Согласовано: {project.price_agreed} ₽")
        paid = (project.prepay_paid or 0) + (project.final_paid or 0)
        lines.append(f"Внесено: {paid} ₽")

    # Финальные медиа — количество
    final_media_count = (
        (
            await session.execute(
                select(MediaAsset).where(
                    MediaAsset.project_id == project.id,
                    MediaAsset.is_final.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    if final_media_count:
        lines.append(f"🖼 Финальные материалы: {len(final_media_count)}")

    text = "\n".join(lines)

    kb = client_project_kb(project.id)
    if edit:
        await msg.edit_text(text, reply_markup=kb)
    else:
        await msg.answer(text, reply_markup=kb)


@router.message(F.text == "📋 Мои заявки")
@trace
async def my_requests(
    msg: Message,
    user: User,
    session,
    locale: str,
) -> None:
    """Список заявок заказчика."""
    rows = (
        (
            await session.execute(
                select(Project)
                .where(Project.client_user_id == user.id)
                .order_by(Project.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    if not rows:
        return await msg.answer(
            "У вас пока нет заявок.",
            reply_markup=main_kb(),
        )

    lines = ["<b>Ваши заявки:</b>"]
    for p in rows:
        status = "закрыта" if p.closed_at else "в работе"
        lines.append(f"• #{p.id} — {status}")

    await msg.answer("\n".join(lines), reply_markup=main_kb())
