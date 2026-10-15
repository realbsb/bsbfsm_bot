"""Админ: только для BOT_ADMIN_IDS и is_admin.

Команды:
- /admin — справка
- /health — состояние системы
- /managers — список менеджеров
- /botadmins — кто в BOT_ADMIN_IDS
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select

from ...config import Settings
from ...logging_setup import get_logger
from ...models import Position, PositionRole, Project, Role, RoleAssignment, User
from ..utils import trace

log = get_logger(__name__)
router = Router(name="admin")


@trace
def _is_admin(user: User, settings: Settings) -> bool:
    return user.is_admin or user.tg_id in settings.bot_admin_ids


@router.message(Command("admin"))
@trace
async def admin_menu(msg: Message, user: User, settings: Settings, locale: str) -> None:
    if not _is_admin(user, settings):
        return
    await msg.answer(
        "<b>Админ-команды:</b>\n"
        "/managers — список менеджеров\n"
        "/botadmins — список админов из .env\n"
        "/health — состояние системы"
    )


@router.message(Command("botadmins"))
@trace
async def botadmins(msg: Message, user: User, settings: Settings, locale: str) -> None:
    if not _is_admin(user, settings):
        return
    ids = settings.bot_admin_ids or []
    if not ids:
        return await msg.answer("BOT_ADMIN_IDS пуст.")
    await msg.answer(
        "<b>BOT_ADMIN_IDS (внешний список):</b>\n" + "\n".join(f"<code>{i}</code>" for i in ids)
    )


@router.message(Command("managers"))
@trace
async def managers(msg, user, session, settings, locale):
    if not _is_admin(user, settings):
        return
    role = (await session.execute(select(Role).where(Role.code == "manager"))).scalars().first()
    if role is None:
        return await msg.answer("Роль manager не найдена")
    rows = (
        (
            await session.execute(
                select(User)
                .join(RoleAssignment, RoleAssignment.user_id == User.id)
                .join(Position, Position.id == RoleAssignment.position_id)
                .join(PositionRole, PositionRole.position_id == Position.id)
                .where(
                    PositionRole.role_id == role.id,
                    RoleAssignment.is_active.is_(True),
                    Position.is_active.is_(True),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return await msg.answer("Менеджеров нет.")
    lines = ["<b>Менеджеры:</b>"]
    for u in rows:
        lines.append(f"• <code>{u.id}</code> — {u.first_name} (@{u.username or '—'})")
    await msg.answer("\n".join(lines))


@router.message(Command("health"))
@trace
async def health(msg: Message, user: User, session, settings: Settings, locale: str) -> None:
    if not _is_admin(user, settings):
        return
    users_count = (await session.execute(select(func.count()).select_from(User))).scalar() or 0
    projects_count = (
        await session.execute(
            select(func.count()).select_from(Project).where(Project.closed_at.is_(None))
        )
    ).scalar() or 0
    lines = [
        "<b>Состояние системы</b>",
        f"Пользователей: {users_count}",
        f"Активных проектов: {projects_count}",
        f"Redis: {settings.redis_host}:{settings.redis_port}/{settings.redis_db}",
        f"DB: {settings.db_host}:{settings.db_port}/{settings.db_name}",
        f"LLM: {'on' if settings.llm_enabled else 'off'}",
    ]
    await msg.answer("\n".join(lines))
