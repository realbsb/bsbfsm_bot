"""Кнопки главного Reply-меню."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import select

from ...logging_setup import get_logger
from ...models import Project, Stage, User
from ..texts import t
from ..utils import trace

log = get_logger(__name__)
router = Router(name="menu")


@router.message(F.text == "📋 Мои задачи")
@trace
async def my_tasks(msg: Message, user: User, session, locale: str) -> None:
    rows = (
        (
            await session.execute(
                select(Project)
                .where(
                    Project.closed_at.is_(None),
                    (Project.current_assignee_id == user.id) | (Project.manager_id == user.id),
                )
                .order_by(Project.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )

    from .profile import _main_kb_for

    kb = await _main_kb_for(session, user)

    if not rows:
        await msg.answer(t("menu.no_tasks", locale), reply_markup=kb)
        return

    lines = [t("menu.tasks_title", locale)]
    for p in rows:
        stage = await session.get(Stage, p.stage_id)
        stage_name = t(stage.name_i18n_key, locale) if stage else "—"
        marker = "🔧" if p.current_assignee_id == user.id else "•"
        title = p.client_name or p.address_text or "—"
        lines.append(f"{marker} #{p.id} — {title} [{stage_name}]")

    await msg.answer("\n".join(lines), reply_markup=kb)
    log.info("menu.my_tasks", user=user.id, count=len(rows))


@router.message()
@trace
async def fallback_menu(msg: Message, state: FSMContext, user: User, session, locale: str) -> None:
    current = await state.get_state()
    if current is not None:
        return

    from .profile import _main_kb_for

    kb = await _main_kb_for(session, user)
    await msg.answer(t("menu.fallback", locale), reply_markup=kb)
