"""Логика «Мой день»: задачи на день, сортировка, выходные."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..logging_setup import get_logger
from ..models import (
    CalendarEvent,
    CalendarKind,
    OrgSettings,
    Position,
    PositionRole,
    Project,
    ProjectStageAssignee,
    Role,
    RoleAssignment,
    Stage,
    User,
)

log = get_logger(__name__)


async def is_day_off(
    session: AsyncSession,
    manager_id: int,
    target: date,
) -> bool:
    """Выходной ли день у менеджера. weekday: 1=ПН..7=ВС."""
    org = (
        (await session.execute(select(OrgSettings).where(OrgSettings.owner_id == manager_id)))
        .scalars()
        .first()
    )
    if org is None:
        return target.isoweekday() >= 6
    workdays = list(org.workdays or [1, 2, 3, 4, 5])
    return target.isoweekday() not in workdays


async def _user_role_codes(session: AsyncSession, user_id: int) -> set[str]:
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


async def get_planned_project_ids(
    session: AsyncSession,
    user_id: int,
    target: date,
) -> set[int]:
    """ID проектов, запланированных пользователем на день (CalendarEvent)."""
    start = datetime.combine(target, datetime.min.time())
    end = start + timedelta(days=1)
    rows = (
        (
            await session.execute(
                select(CalendarEvent.project_id).where(
                    CalendarEvent.owner_id == user_id,
                    CalendarEvent.kind == CalendarKind.WORK,
                    CalendarEvent.start_at >= start,
                    CalendarEvent.start_at < end,
                )
            )
        )
        .scalars()
        .all()
    )
    return set(rows)


async def get_overdue_project_ids(
    session: AsyncSession,
    user_id: int,
    target: date,
) -> set[int]:
    """Проекты, запланированные на прошлые дни, но не закрытые и без плана на target."""
    start_of_today = datetime.combine(target, datetime.min.time())
    past = (
        (
            await session.execute(
                select(CalendarEvent.project_id).where(
                    CalendarEvent.owner_id == user_id,
                    CalendarEvent.kind == CalendarKind.WORK,
                    CalendarEvent.start_at < start_of_today,
                )
            )
        )
        .scalars()
        .all()
    )
    if not past:
        return set()

    planned_today = await get_planned_project_ids(session, user_id, target)
    candidates = set(past) - planned_today
    if not candidates:
        return set()

    # Фильтруем закрытые
    active = (
        (
            await session.execute(
                select(Project.id).where(
                    Project.id.in_(candidates),
                    Project.closed_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    return set(active)


async def get_day_tasks(
    session: AsyncSession,
    user: User,
    target: date,
) -> tuple[list[Project], list[Project]]:
    """Возвращает (задачи на день, просроченные с прошлых дней).

    Задачи — все активные проекты пользователя, где он текущий исполнитель
    или менеджер. Плюс запланированные на этот день.
    Просроченные — из прошлых дней, не закрытые, без плана на target.
    """
    role_codes = await _user_role_codes(session, user.id)
    is_manager = "manager" in role_codes

    # Условие «причастности»
    conditions = [Project.current_assignee_id == user.id]
    if is_manager:
        conditions.append(Project.manager_id == user.id)

    from sqlalchemy import or_

    q = select(Project).where(Project.closed_at.is_(None)).where(or_(*conditions))
    active_projects = (await session.execute(q)).scalars().all()

    planned_ids = await get_planned_project_ids(session, user.id, target)
    overdue_ids = await get_overdue_project_ids(session, user.id, target)

    # Плановые: все, что явно в плане на сегодня, или просроченные
    day_tasks: list[Project] = []
    overdue_tasks: list[Project] = []
    seen: set[int] = set()

    # 1. Просроченные — в начало
    for p in active_projects:
        if p.id in overdue_ids:
            overdue_tasks.append(p)
            seen.add(p.id)

    # 2. Активные задачи пользователя (все — чтобы не терять)
    for p in active_projects:
        if p.id in seen:
            continue
        # Показываем, если:
        #  - запланировано на target, ИЛИ
        #  - это активная задача пользователя (current_assignee)
        if (
            p.id in planned_ids
            or p.current_assignee_id == user.id
            or (is_manager and p.manager_id == user.id)
        ):
            day_tasks.append(p)
            seen.add(p.id)

    return day_tasks, overdue_tasks


async def sort_tasks(
    session: AsyncSession,
    tasks: list[Project],
) -> list[Project]:
    """Сортировка: стадия (order_idx) desc, потом % (progress_percent) desc."""
    if not tasks:
        return []

    stage_ids = {p.stage_id for p in tasks}
    stages = {
        s.id: s
        for s in (await session.execute(select(Stage).where(Stage.id.in_(stage_ids))))
        .scalars()
        .all()
    }

    # Проценты — из активных ProjectStageAssignee
    project_ids = [p.id for p in tasks]
    assignees = (
        (
            await session.execute(
                select(ProjectStageAssignee).where(
                    ProjectStageAssignee.project_id.in_(project_ids),
                    ProjectStageAssignee.active_slot == 1,
                )
            )
        )
        .scalars()
        .all()
    )
    percent_by_project = {a.project_id: (a.progress_percent or 0) for a in assignees}

    def key(p: Project) -> tuple:
        st = stages.get(p.stage_id)
        order = st.order_idx if st else 0
        return (-order, -percent_by_project.get(p.id, 0))

    return sorted(tasks, key=key)


async def get_manager_id_for(session: AsyncSession, user: User) -> int:
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
    if ra and ra.manager_id:
        return ra.manager_id
    return user.id
