"""Выгрузка xlsx-отчёта по проекту."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from ...logging_setup import get_logger
from ...models import Project, User
from ...services.report import build_project_xlsx
from ..texts import t
from ..utils import trace

log = get_logger(__name__)
router = Router(name="report")


@router.callback_query(F.data.startswith("report:"))
@trace
async def report(
    cb: CallbackQuery,
    user: User,
    session,
    locale: str,
) -> None:
    project_id = int(cb.data.split(":")[1])
    project = await session.get(Project, project_id)
    if project is None:
        return await cb.answer(t("common.not_found", locale), show_alert=True)

    if project.manager_id != user.id and not user.is_admin:
        return await cb.answer(t("common.not_allowed", locale), show_alert=True)

    try:
        data = await build_project_xlsx(session, project)
    except Exception as e:
        log.error("report.failed", project=project_id, error=str(e))
        return await cb.answer(f"Ошибка: {e}", show_alert=True)

    await cb.message.answer_document(
        BufferedInputFile(data, filename=f"project_{project_id}.xlsx"),
        caption=f"Отчёт по проекту #{project_id}",
    )
    log.info("report.sent", project=project_id, user=user.id)
    await cb.answer()
