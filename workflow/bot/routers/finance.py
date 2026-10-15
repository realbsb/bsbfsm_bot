"""Закрытие проекта: экспорт финансов, архивация, публикация.

/close — список открытых проектов менеджера.
/close <id> — закрыть конкретный.
"""

from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from ...config import Settings
from ...logging_setup import get_logger
from ...models import Project, User
from ...services.export_finance import close_project_and_export
from ...services.final_media import cleanup_for_archive
from ..keyboards import confirm_kb, publish_kb
from ..texts import t
from ..utils import trace

log = get_logger(__name__)
router = Router(name="finance")


@router.message(Command("close"))
@trace
async def close_cmd(
    msg: Message,
    user: User,
    session,
    settings: Settings,
    locale: str,
) -> None:
    args = (msg.text or "").split()

    # Без аргумента — список открытых
    if len(args) < 2:
        rows = (
            (
                await session.execute(
                    select(Project).where(
                        Project.manager_id == user.id,
                        Project.closed_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )

        if not rows:
            return await msg.answer("Нет открытых проектов.")

        lines = ["<b>Открытые проекты:</b>"]
        for p in rows:
            lines.append(f"• <code>/close {p.id}</code> — {p.client_name or p.address_text or '—'}")
        return await msg.answer("\n".join(lines))

    # С аргументом — закрыть
    try:
        project_id = int(args[1])
    except ValueError:
        return await msg.answer("ID должен быть числом.")

    project = await session.get(Project, project_id)
    if project is None:
        return await msg.answer(t("common.not_found", locale))
    if project.manager_id != user.id and not user.is_admin:
        return await msg.answer(t("common.not_allowed", locale))
    if project.closed_at is not None:
        return await msg.answer("Проект уже закрыт.")

    await msg.answer(
        f"Закрыть проект #{project_id}?\n"
        f"Это выгрузит финансы, очистит медиа и удалит финансовые поля из БД.",
        reply_markup=confirm_kb(f"close_yes:{project_id}", "close_no"),
    )


@router.callback_query(F.data.startswith("close_yes:"))
@trace
async def close_yes(
    cb: CallbackQuery,
    user: User,
    session,
    settings: Settings,
    locale: str,
) -> None:
    project_id = int(cb.data.split(":")[1])
    project = await session.get(Project, project_id)
    if project is None:
        return await cb.answer(t("common.not_found", locale), show_alert=True)
    if project.manager_id != user.id and not user.is_admin:
        return await cb.answer(t("common.not_allowed", locale), show_alert=True)

    project.closed_at = datetime.utcnow()

    try:
        files = await close_project_and_export(session, settings, project)
        await cleanup_for_archive(session, project)
        await session.commit()
    except Exception as e:
        log.error("finance.close_failed", project=project_id, error=str(e))
        await session.rollback()
        return await cb.message.edit_text(t("finance.export_failed", locale, error=str(e)))

    lines = "\n".join(f"• {k}: <code>{v}</code>" for k, v in files.items())
    await cb.message.edit_text(t("finance.export_done", locale, files=lines))
    await cb.message.answer(
        t("publish.title", locale),
        reply_markup=publish_kb(project_id),
    )
    log.info("finance.closed", project=project_id, files=list(files.keys()))
    await cb.answer()


@router.callback_query(F.data == "close_no")
@trace
async def close_no(
    cb: CallbackQuery,
    locale: str,
) -> None:
    await cb.message.edit_text(t("common.cancelled", locale))
    await cb.answer()
