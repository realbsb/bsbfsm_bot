"""Назначение и переназначение ответственных по стадиям проекта.

Инкапсулирует работу с ProjectStageAssignee:
- создание активной записи на (project, stage);
- замена (ревокация старой + новая запись);
- поиск кандидатов по роли среди подчинённых менеджера;
- учёт уже потраченного времени на стадии.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..logging_setup import get_logger
from ..models import (
    Incident,
    IncidentKind,
    Position,
    PositionRole,
    Project,
    ProjectStageAssignee,
    RoleAssignment,
    Stage,
    StageAssigneeState,
    User,
)

log = get_logger(__name__)


class StageAssignError(Exception):
    pass


# ============================================================
# Поиск активной записи
# ============================================================


async def get_active_assignee(
    session: AsyncSession,
    project_id: int,
    stage_id: int,
) -> ProjectStageAssignee | None:
    return (
        (
            await session.execute(
                select(ProjectStageAssignee).where(
                    ProjectStageAssignee.project_id == project_id,
                    ProjectStageAssignee.stage_id == stage_id,
                    ProjectStageAssignee.active_slot == 1,
                )
            )
        )
        .scalars()
        .first()
    )


async def get_active_assignee_for_project(
    session: AsyncSession,
    project_id: int,
) -> list[ProjectStageAssignee]:
    return (
        (
            await session.execute(
                select(ProjectStageAssignee).where(
                    ProjectStageAssignee.project_id == project_id,
                    ProjectStageAssignee.active_slot == 1,
                )
            )
        )
        .scalars()
        .all()
    )


# ============================================================
# Кандидаты по роли
# ============================================================


async def candidates_for_stage(
    session: AsyncSession,
    project: Project,
    stage: Stage,
) -> list[User]:
    """Все, у кого в должности есть нужная стадии роль.

    Ищем: RoleAssignment(manager_id=project.manager_id, active)
           → Position (active) → PositionRole(role_id == stage.responsible_role_id).
    """
    rows = (
        (
            await session.execute(
                select(User)
                .join(RoleAssignment, RoleAssignment.user_id == User.id)
                .join(Position, Position.id == RoleAssignment.position_id)
                .join(PositionRole, PositionRole.position_id == Position.id)
                .where(
                    RoleAssignment.manager_id == project.manager_id,
                    RoleAssignment.is_active.is_(True),
                    PositionRole.role_id == stage.responsible_role_id,
                    Position.is_active.is_(True),
                    User.is_active.is_(True),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


# ============================================================
# Расчёт бюджета часов на стадию
# ============================================================


def _remaining_hours(
    stage: Stage,
    started_at: datetime,
    now: datetime,
) -> tuple[int, int]:
    """Сколько часов осталось от min/max стадии с учётом потраченного.

    Никогда не меньше половины исходного.
    """
    elapsed = max((now - started_at).total_seconds() / 3600, 0)
    min_left = max(stage.min_hours - elapsed, stage.min_hours / 2)
    max_left = max(stage.max_hours - elapsed, stage.max_hours / 2)
    return int(min_left), int(max_left)


def _planned_hours_for_new_assignee(
    stage: Stage,
    started_at: datetime,
    now: datetime,
) -> int:
    """Сколько часов дать новому исполнителю.

    Берём default_sla_hours минус уже потраченное, но не меньше min/2 и не больше max.
    """
    min_left, max_left = _remaining_hours(stage, started_at, now)
    elapsed = max((now - started_at).total_seconds() / 3600, 0)
    base = stage.default_sla_hours - elapsed
    return int(max(min_left, min(base, max_left)))


# ============================================================
# Назначение
# ============================================================


async def assign(
    session: AsyncSession,
    project: Project,
    stage: Stage,
    user: User | None,
    assigned_by: User,
    planned_hours: int | None = None,
    deadline_at: datetime | None = None,
    started_at: datetime | None = None,
) -> ProjectStageAssignee:
    """Создаёт активное назначение на стадию.

    user может быть None — «без ответственного», но запись нужна
    для расчёта дедлайна. Если planned_hours не задан — считаем
    от started_at (или now) с учётом потраченного.
    """
    if await get_active_assignee(session, project.id, stage.id) is not None:
        raise StageAssignError(f"На стадию {stage.code} уже есть активный ответственный")

    now = datetime.now()
    start = started_at or now

    if planned_hours is None:
        planned_hours = _planned_hours_for_new_assignee(stage, start, now)
    deadline = deadline_at or (now + timedelta(hours=planned_hours))

    row = ProjectStageAssignee(
        project_id=project.id,
        stage_id=stage.id,
        user_id=user.id if user else None,
        active_slot=1,
        state=StageAssigneeState.ACTIVE,
        assigned_by=assigned_by.id,
        planned_hours=planned_hours,
        deadline_at=deadline,
        started_at=start,
    )
    session.add(row)
    await session.flush()

    if project.stage_id == stage.id:
        project.current_assignee_id = user.id if user is not None else None

    log.info(
        "stage_assign.created",
        project=project.id,
        stage=stage.code,
        user=user.id if user else None,
        planned_hours=planned_hours,
    )
    return row


# ============================================================
# Переназначение
# ============================================================


async def reassign(
    session: AsyncSession,
    project: Project,
    stage: Stage,
    new_user: User | None,
    assigned_by: User,
    planned_hours: int | None = None,
    reason: str = "manual",
) -> ProjectStageAssignee:
    """Заменяет ответственного.

    planned_hours по умолчанию = остаток от default_sla_hours
    (с учётом уже потраченного на стадии).
    """
    old = await get_active_assignee(session, project.id, stage.id)
    if old is not None:
        old.active_slot = None
        old.state = StageAssigneeState.REVOKED
        old.revoked_at = datetime.now()
        old.revoke_reason = reason
        session.add(
            Incident(
                project_id=project.id,
                kind=IncidentKind.REASSIGNED,
                actor_id=assigned_by.id,
                reason_text=f"stage={stage.code}, reason={reason}, old_user={old.user_id}",
            )
        )
        stage_started = old.started_at
    else:
        stage_started = datetime.now()

    now = datetime.now()
    if planned_hours is None:
        planned_hours = _planned_hours_for_new_assignee(stage, stage_started, now)
    deadline = now + timedelta(hours=planned_hours)

    new_row = ProjectStageAssignee(
        project_id=project.id,
        stage_id=stage.id,
        user_id=new_user.id if new_user else None,
        active_slot=1,
        state=StageAssigneeState.ACTIVE,
        assigned_by=assigned_by.id,
        planned_hours=planned_hours,
        deadline_at=deadline,
        started_at=stage_started,
    )
    session.add(new_row)
    await session.flush()

    if project.stage_id == stage.id:
        project.current_assignee_id = new_user.id if new_user is not None else None

    log.info(
        "stage_assign.reassigned",
        project=project.id,
        stage=stage.code,
        new_user=new_user.id if new_user else None,
        reason=reason,
        planned_hours=planned_hours,
    )
    return new_row


# ============================================================
# Завершение стадии
# ============================================================


async def complete(
    session: AsyncSession,
    project_id: int,
    stage_id: int,
) -> None:
    row = await get_active_assignee(session, project_id, stage_id)
    if row is None:
        return
    row.active_slot = None
    row.state = StageAssigneeState.COMPLETED
    row.finished_at = datetime.now()
    await session.flush()
