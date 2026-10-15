"""Проверки прав на просмотр цены/медиа/проекта."""

from __future__ import annotations

from ..models import Position, PositionRole, Project, User

# Роли, видящие внутреннюю цену
PRICE_INTERNAL_ROLES = {"manager", "supplier"}

# Роли, видящие медиа этапов
MEDIA_STAGES_ROLES = {"manager", "executor"}


def can_see_internal_price(user_roles: set[str]) -> bool:
    return bool(user_roles & PRICE_INTERNAL_ROLES)


def can_see_agreed_price(user_roles: set[str], is_client: bool) -> bool:
    return is_client or bool(user_roles)


def can_see_stage_media(user_roles: set[str]) -> bool:
    return bool(user_roles & MEDIA_STAGES_ROLES)


def can_see_final_media(user_roles: set[str], is_client: bool, mode: str) -> bool:
    if mode in ("delivery_public", "public"):
        return True
    return is_client or bool(user_roles)


def is_participant(project: Project, user: User) -> bool:
    return user.id in {
        project.manager_id,
        project.secretary_id,
        project.supplier_id,
        project.executor_id,
        project.current_assignee_id,
    }


def is_client(project: Project, user: User) -> bool:
    return project.client_user_id == user.id


async def user_roles(session, user_id: int) -> set[str]:
    from sqlalchemy import select

    from ..models import Role, RoleAssignment

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
    return set(rows)
