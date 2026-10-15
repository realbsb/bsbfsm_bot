"""Расчёт min/max даты завершения проекта.

Считаем от ProjectSchedule.started_at (фиксированная дата старта).
Из суммы сроков вычитаем уже потраченное время, но не даём уйти
ниже половины исходного бюджета.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..logging_setup import get_logger
from ..models import (
    Project,
    ProjectSchedule,
    ProjectStageAssignee,
    Stage,
)

log = get_logger(__name__)


async def _get_or_create_schedule(
    session: AsyncSession,
    project: Project,
) -> ProjectSchedule:
    sched = (
        (
            await session.execute(
                select(ProjectSchedule).where(ProjectSchedule.project_id == project.id)
            )
        )
        .scalars()
        .first()
    )
    if sched is None:
        now = datetime.now()
        sched = ProjectSchedule(
            project_id=project.id,
            started_at=now,
            min_finish_at=now,
            max_finish_at=now,
        )
        session.add(sched)
        await session.flush()
    return sched


async def recalc(session: AsyncSession, project: Project) -> ProjectSchedule:
    """Пересчитывает ProjectSchedule.

    Формула:
      remaining_min = Σ min_hours всех оставшихся стадий
      remaining_max = Σ max_hours всех оставшихся стадий
      elapsed       = now - started_at
      budget_min    = max(remaining_min - elapsed, remaining_min / 2)
      budget_max    = max(remaining_max - elapsed, remaining_max / 2)
      min_finish_at = now + budget_min
      max_finish_at = now + budget_max
    """
    sched = await _get_or_create_schedule(session, project)

    stages: list[Stage] = (
        (
            await session.execute(
                select(Stage)
                .where(Stage.manager_id == project.manager_id, Stage.is_active.is_(True))
                .order_by(Stage.order_idx)
            )
        )
        .scalars()
        .all()
    )

    current = await session.get(Stage, project.stage_id)
    if current is None:
        return sched

    # Оставшиеся стадии — от текущей включительно
    remaining = [s for s in stages if s.order_idx >= current.order_idx]

    remaining_min = sum(s.min_hours for s in remaining) or 0
    remaining_max = sum(s.max_hours for s in remaining) or 0

    now = datetime.now()
    elapsed = max((now - sched.started_at).total_seconds() / 3600, 0)

    budget_min = max(remaining_min - elapsed, remaining_min / 2)
    budget_max = max(remaining_max - elapsed, remaining_max / 2)

    sched.recalculated_at = now
    sched.min_finish_at = now + timedelta(hours=budget_min)
    sched.max_finish_at = now + timedelta(hours=budget_max)
    await session.flush()

    log.info(
        "schedule.recalc",
        project=project.id,
        remaining_min_h=int(remaining_min),
        remaining_max_h=int(remaining_max),
        elapsed_h=int(elapsed),
        budget_min_h=int(budget_min),
        budget_max_h=int(budget_max),
    )
    return sched


async def budget_for_stage(
    session: AsyncSession,
    project: Project,
    stage: Stage,
) -> tuple[int, int]:
    """Сколько часов осталось на конкретную стадию (min, max).

    Считаем от started_at активного назначения (или now, если нет).
    """
    active = (
        (
            await session.execute(
                select(ProjectStageAssignee).where(
                    ProjectStageAssignee.project_id == project.id,
                    ProjectStageAssignee.stage_id == stage.id,
                    ProjectStageAssignee.active_slot == 1,
                )
            )
        )
        .scalars()
        .first()
    )

    now = datetime.now()
    start = active.started_at if active else now
    elapsed = max((now - start).total_seconds() / 3600, 0)

    min_left = max(stage.min_hours - elapsed, stage.min_hours / 2)
    max_left = max(stage.max_hours - elapsed, stage.max_hours / 2)
    return int(min_left), int(max_left)
