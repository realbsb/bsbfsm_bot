"""Публикация итогов: канал и портфолио.

Канал — менеджер и секретарь.
Портфолио — менеджер и исполнитель.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ...config import Settings
from ...logging_setup import get_logger
from ...models import Project, User
from ...services.publish import publish_to_channel, publish_to_portfolio
from ..texts import t
from ..utils import trace

log = get_logger(__name__)
router = Router(name="publish")


@trace
async def _resolve_channel_id(session) -> int | None:
    """Канал берём из настроек менеджера. Пока — из User.is_admin + поле channel_id."""
    # В будущем — отдельная таблица manager_channel.
    # Сейчас возвращаем None, если не настроено.
    return None


@router.callback_query(F.data.startswith("pub_channel:"))
@trace
async def pub_channel(
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

    # Права: менеджер или секретарь
    if user.id not in {project.manager_id, project.secretary_id} and not user.is_admin:
        return await cb.answer(t("common.not_allowed", locale), show_alert=True)

    channel_id = await _resolve_channel_id(session)
    if channel_id is None:
        return await cb.answer(
            "Канал не настроен. Обратитесь к администратору.",
            show_alert=True,
        )

    try:
        post = await publish_to_channel(cb.bot, session, project, channel_id, user)
        await session.commit()
    except Exception as e:
        log.error("publish.channel_failed", project=project_id, error=str(e))
        return await cb.message.edit_text(f"Ошибка: {e}")

    await cb.message.edit_text(t("publish.channel_done", locale, url=post.url or ""))
    await cb.answer()


@router.callback_query(F.data.startswith("pub_portfolio:"))
@trace
async def pub_portfolio(
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

    # Права: менеджер или исполнитель
    if user.id not in {project.manager_id, project.executor_id} and not user.is_admin:
        return await cb.answer(t("common.not_allowed", locale), show_alert=True)

    try:
        await publish_to_portfolio(cb.bot, session, project, cb.from_user.id, user)
        await session.commit()
    except Exception as e:
        log.error("publish.portfolio_failed", project=project_id, error=str(e))
        return await cb.message.edit_text(f"Ошибка: {e}")

    await cb.message.edit_text(t("publish.portfolio_done", locale))
    await cb.answer()


@router.callback_query(F.data == "pub_skip")
@trace
async def pub_skip(
    cb: CallbackQuery,
    locale: str,
) -> None:
    await cb.message.edit_text(t("publish.skipped", locale))
    await cb.answer()
