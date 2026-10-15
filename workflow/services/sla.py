"""SLA: предупреждения о дедлайне и просрочка."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..logging_setup import get_logger
from ..models import (
    OrgSettings,
    Project,
    ProjectStageAssignee,
    StageAssigneeState,
)

log = get_logger(__name__)


async def _org_settings(
    session: AsyncSession,
    manager_id: int,
) -> OrgSettings | None:
    return (
        (await session.execute(select(OrgSettings).where(OrgSettings.owner_id == manager_id)))
        .scalars()
        .first()
    )


def _warn_field_for_index(idx: int) -> str | None:
    return {0: "warned_1_at", 1: "warned_2_at"}.get(idx)


async def collect_due_warnings(
    session: AsyncSession,
    now: datetime | None = None,
) -> list[dict]:
    """Список предупреждений к отправке."""
    now = now or datetime.now()

    rows = (
        (
            await session.execute(
                select(ProjectStageAssignee).where(
                    ProjectStageAssignee.active_slot == 1,
                    ProjectStageAssignee.state == StageAssigneeState.ACTIVE,
                    ProjectStageAssignee.user_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )

    out: list[dict] = []
    for a in rows:
        project = await session.get(Project, a.project_id)
        if project is None:
            continue
        org = await _org_settings(session, project.manager_id)
        warn_list = list(org.sla_warn_hours) if org else [24, 2]

        hours_left = (a.deadline_at - now).total_seconds() / 3600
        if hours_left <= 0:
            continue

        for idx, warn_h in enumerate(warn_list):
            field = _warn_field_for_index(idx)
            if field is None or getattr(a, field) is not None:
                continue
            if hours_left <= warn_h:
                out.append(
                    {
                        "assignee_id": a.id,
                        "project_id": a.project_id,
                        "stage_id": a.stage_id,
                        "user_id": a.user_id,
                        "hours_left": round(hours_left, 1),
                        "warn_h": warn_h,
                        "warn_idx": idx,
                        "field": field,
                    }
                )
                break
    return out


async def mark_warned(
    session: AsyncSession,
    assignee_id: int,
    field: str,
    now: datetime | None = None,
) -> None:
    a = await session.get(ProjectStageAssignee, assignee_id)
    if a is None:
        return
    setattr(a, field, now or datetime.now())
    await session.flush()


async def collect_expired(
    session: AsyncSession,
    now: datetime | None = None,
) -> list[dict]:
    now = now or datetime.now()
    rows = (
        (
            await session.execute(
                select(ProjectStageAssignee).where(
                    ProjectStageAssignee.active_slot == 1,
                    ProjectStageAssignee.state == StageAssigneeState.ACTIVE,
                    ProjectStageAssignee.deadline_at < now,
                    ProjectStageAssignee.reassignment_allowed.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )

    return [
        {
            "assignee_id": a.id,
            "project_id": a.project_id,
            "stage_id": a.stage_id,
            "user_id": a.user_id,
        }
        for a in rows
    ]
