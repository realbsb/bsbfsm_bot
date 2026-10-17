"""Карточка проекта: просмотр, карта, маршрут, участники, отчёт."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from ...logging_setup import get_logger
from ...models import Project, Stage, User
from ..keyboards import stage_actions_kb
from ..texts import t
from ..utils import trace

log = get_logger(__name__)
router = Router(name="project")


def _can_access_project(project: Project, user: User) -> bool:
    """Проверяет участие пользователя в проекте до выдачи его данных."""
    return user.id in {
        project.manager_id,
        project.secretary_id,
        project.supplier_id,
        project.executor_id,
        project.current_assignee_id,
        project.client_user_id,
    }


@router.message(Command("project"))
@trace
async def project_cmd(
    msg: Message,
    session,
    user: User,
    locale: str,
) -> None:
    args = (msg.text or "").split()

    # Без аргумента — список
    if len(args) < 2:
        rows = (
            (
                await session.execute(
                    select(Project)
                    .where(
                        (Project.manager_id == user.id)
                        | (Project.secretary_id == user.id)
                        | (Project.supplier_id == user.id)
                        | (Project.executor_id == user.id)
                        | (Project.current_assignee_id == user.id)
                        | (Project.client_user_id == user.id)
                    )
                    .order_by(Project.created_at.desc())
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )

        if not rows:
            return await msg.answer("У вас нет проектов.")

        lines = ["<b>Ваши проекты:</b>"]
        for p in rows:
            title = p.client_name or p.address_text or "—"
            lines.append(f"• <code>/project {p.id}</code> — {title}")
        return await msg.answer("\n".join(lines))

    try:
        project_id = int(args[1])
    except ValueError:
        return await msg.answer("ID должен быть числом.")

    await _render(msg, session, user, project_id, locale)


@router.callback_query(F.data.startswith("project_open:"))
@trace
async def project_open(
    cb: CallbackQuery,
    session,
    user: User,
    locale: str,
) -> None:
    project_id = int(cb.data.split(":")[1])
    await _render(cb.message, session, user, project_id, locale, edit=True)
    await cb.answer()


@trace
async def _render(
    msg: Message,
    session,
    user: User,
    project_id: int,
    locale: str,
    edit: bool = False,
) -> None:
    project = await session.get(Project, project_id)
    if project is None or not _can_access_project(project, user):
        return await msg.answer(t("common.not_found", locale))

    stage = await session.get(Stage, project.stage_id)
    stage_name = t(stage.name_i18n_key, locale) if stage else "—"

    lines = [
        f"<b>Проект #{project.id}</b>",
        f"Статус: <b>{stage_name}</b>",
    ]
    if project.client_name:
        lines.append(f"👤 {project.client_name}")
    if project.client_phone:
        lines.append(f"📞 {project.client_phone}")
    if project.address_text:
        lines.append(f"📍 {project.address_text}")
    if project.description:
        lines.append(f"📝 {project.description[:200]}")

    if project.current_assignee_id:
        assignee = await session.get(User, project.current_assignee_id)
        if assignee:
            lines.append(
                f'🔧 Текущий: <a href="tg://user?id={assignee.tg_id}">'
                f"{assignee.first_name or assignee.username}</a>"
            )

    if stage:
        if stage.media_required:
            lines.append("📎 Требуется медиа-отчёт")
        if stage.calc_required and project.price_internal:
            lines.append(f"💰 Внутренняя: {project.price_internal} ₽")

    text = "\n".join(lines)

    # Кто может завершить
    can_finish = project.current_assignee_id == user.id
    kb = stage_actions_kb(project.id, can_finish)

    if edit:
        await msg.edit_text(text, reply_markup=kb)
    else:
        await msg.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("map:"))
@trace
async def on_map(
    cb: CallbackQuery,
    session,
    user: User,
    locale: str,
) -> None:
    project_id = int(cb.data.split(":")[1])
    project = await session.get(Project, project_id)
    if project is None or not _can_access_project(project, user):
        return await cb.answer(t("common.not_found", locale), show_alert=True)
    if project.lat is None or project.lon is None:
        return await cb.answer("Координаты не указаны", show_alert=True)

    await cb.message.answer_location(
        latitude=float(project.lat),
        longitude=float(project.lon),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("route:"))
@trace
async def on_route(
    cb: CallbackQuery,
    session,
    user: User,
    locale: str,
) -> None:
    project_id = int(cb.data.split(":")[1])
    project = await session.get(Project, project_id)
    if project is None or not _can_access_project(project, user):
        return await cb.answer(t("common.not_found", locale), show_alert=True)
    if project.lat is None or project.lon is None:
        return await cb.answer("Координаты не указаны", show_alert=True)

    url = f"https://www.google.com/maps/dir/?api=1&destination={project.lat},{project.lon}"
    await cb.message.answer(f'🧭 <a href="{url}">Проложить маршрут</a>')
    await cb.answer()


@router.callback_query(F.data.startswith("profile:"))
@trace
async def on_profile_link(
    cb: CallbackQuery,
    session,
    locale: str,
) -> None:
    user_id = int(cb.data.split(":")[1])
    target = await session.get(User, user_id)
    if target is None:
        return await cb.answer(t("common.not_found", locale), show_alert=True)
    await cb.message.answer(
        f'👤 <a href="tg://user?id={target.tg_id}">{target.first_name or target.username}</a>'
    )
    await cb.answer()
