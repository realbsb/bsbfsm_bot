"""Логика переходов между стадиями.

- advance  — завершить текущую, перейти на следующую.
- refuse   — исполнитель отказывается (стадия та же, reassignment_allowed).
- handover — исполнитель передаёт коллеге (стадия та же, reassignment_allowed).
- rewind   — менеджер возвращает проект на предыдущую стадию (косяки).
- mark_expired — worker помечает просрочку.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..logging_setup import get_logger
from ..models import (
    Incident,
    IncidentKind,
    Project,
    ProjectStageLog,
    Stage,
    StageAssigneeState,
    User,
)
from . import stage_assign, stage_schedule

log = get_logger(__name__)


class StageError(Exception):
    pass


# ============================================================
# Проверки
# ============================================================


async def can_finish(
    session: AsyncSession,
    project: Project,
    stage: Stage,
    user: User,
) -> bool:
    """Только активный исполнитель стадии может её завершить."""
    active = await stage_assign.get_active_assignee(session, project.id, stage.id)
    if active is None or active.user_id is None:
        return False
    return active.user_id == user.id


async def can_rewind(
    session: AsyncSession,
    project: Project,
    user: User,
) -> bool:
    """Возврат на предыдущую стадию — только менеджер проекта."""
    return user.id == project.manager_id


async def next_stage(session: AsyncSession, stage: Stage) -> Stage | None:
    return (
        (
            await session.execute(
                select(Stage)
                .where(
                    Stage.manager_id == stage.manager_id,
                    Stage.order_idx > stage.order_idx,
                    Stage.is_active.is_(True),
                )
                .order_by(Stage.order_idx)
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def prev_stage(session: AsyncSession, stage: Stage) -> Stage | None:
    return (
        (
            await session.execute(
                select(Stage)
                .where(
                    Stage.manager_id == stage.manager_id,
                    Stage.order_idx < stage.order_idx,
                    Stage.is_active.is_(True),
                )
                .order_by(Stage.order_idx.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


# ============================================================
# Переходы
# ============================================================


async def advance(
    session: AsyncSession,
    project: Project,
    actor: User,
) -> Stage:
    current = await session.get(Stage, project.stage_id)
    if current is None:
        raise StageError("Текущая стадия не найдена")

    if not await can_finish(session, project, current, actor):
        raise StageError("Завершить стадию может только её исполнитель")

    nxt = await next_stage(session, current)
    if nxt is None:
        raise StageError("Это последний этап")

    await stage_assign.complete(session, project.id, current.id)
    project.stage_id = nxt.id

    candidates = await stage_assign.candidates_for_stage(session, project, nxt)
    if len(candidates) == 1:
        await stage_assign.assign(session, project, nxt, candidates[0], actor)
    else:
        await stage_assign.assign(session, project, nxt, None, actor)

    session.add(
        ProjectStageLog(
            project_id=project.id,
            stage_id=nxt.id,
            actor_id=actor.id,
            action="advance",
        )
    )
    await stage_schedule.recalc(session, project)

    log.info("stage.advance", project=project.id, to=nxt.code, actor=actor.id)
    return nxt


async def refuse(
    session: AsyncSession,
    project: Project,
    actor: User,
    reason: str,
) -> None:
    """Исполнитель отказывается от стадии."""
    current = await session.get(Stage, project.stage_id)
    if current is None:
        raise StageError("Текущая стадия не найдена")

    active = await stage_assign.get_active_assignee(session, project.id, current.id)
    if active is None or active.user_id != actor.id:
        raise StageError("Вы не исполнитель этой стадии")

    active.reassignment_allowed = True
    active.reassignment_reason = "refused"
    active.explanation_text = (active.explanation_text or "") + f"\n[refuse] {reason}"

    session.add(
        Incident(
            project_id=project.id,
            kind=IncidentKind.REFUSE,
            actor_id=actor.id,
            reason_text=reason,
        )
    )
    session.add(
        ProjectStageLog(
            project_id=project.id,
            stage_id=current.id,
            actor_id=actor.id,
            action="refuse",
            reason=reason,
        )
    )
    await session.flush()
    log.warning("stage.refuse", project=project.id, stage=current.code, actor=actor.id)


async def handover(
    session: AsyncSession,
    project: Project,
    actor: User,
    to_user: User,
    reason: str | None = None,
) -> None:
    """Исполнитель передаёт стадию коллеге (нужно подтверждение менеджера)."""
    current = await session.get(Stage, project.stage_id)
    if current is None:
        raise StageError("Текущая стадия не найдена")

    active = await stage_assign.get_active_assignee(session, project.id, current.id)
    if active is None or active.user_id != actor.id:
        raise StageError("Вы не исполнитель этой стадии")

    active.reassignment_allowed = True
    active.reassignment_reason = "handover"
    note = f"[handover→{to_user.id}] {reason or ''}".strip()
    active.explanation_text = (active.explanation_text or "") + f"\n{note}"

    session.add(
        ProjectStageLog(
            project_id=project.id,
            stage_id=current.id,
            actor_id=actor.id,
            action="handover",
            reason=note,
        )
    )
    await session.flush()
    log.info("stage.handover", project=project.id, to=to_user.id, actor=actor.id)


async def rewind(
    session: AsyncSession,
    project: Project,
    actor: User,
    reason: str,
) -> Stage:
    """Менеджер возвращает проект на предыдущую стадию."""
    from datetime import datetime as _dt

    if not await can_rewind(session, project, actor):
        raise StageError("Возврат доступен только менеджеру проекта")

    current = await session.get(Stage, project.stage_id)
    if current is None:
        raise StageError("Текущая стадия не найдена")

    prv = await prev_stage(session, current)
    if prv is None:
        raise StageError("Некуда возвращаться")

    active = await stage_assign.get_active_assignee(session, project.id, current.id)
    if active is not None:
        active.active_slot = None
        active.state = StageAssigneeState.REVOKED
        active.revoked_at = _dt.now()
        active.revoke_reason = "rewind"

    project.stage_id = prv.id

    candidates = await stage_assign.candidates_for_stage(session, project, prv)
    if len(candidates) == 1:
        await stage_assign.assign(session, project, prv, candidates[0], actor)
    else:
        await stage_assign.assign(session, project, prv, None, actor)

    session.add(
        Incident(
            project_id=project.id,
            kind=IncidentKind.REFUSE,
            actor_id=actor.id,
            reason_text=f"rewind from {current.code} to {prv.code}: {reason}",
        )
    )
    session.add(
        ProjectStageLog(
            project_id=project.id,
            stage_id=prv.id,
            actor_id=actor.id,
            action="rewind",
            reason=reason,
        )
    )
    await stage_schedule.recalc(session, project)

    log.warning("stage.rewind", project=project.id, to=prv.code, actor=actor.id)
    return prv


async def mark_expired(
    session: AsyncSession,
    assignee_row,
) -> None:
    assignee_row.reassignment_allowed = True
    if not assignee_row.reassignment_reason:
        assignee_row.reassignment_reason = "sla_expired"
    session.add(
        Incident(
            project_id=assignee_row.project_id,
            kind=IncidentKind.SLA_EXPIRED,
            actor_id=None,
            reason_text=f"stage_assignee_id={assignee_row.id}",
        )
    )
    await session.flush()
    log.warning(
        "stage.sla_expired",
        project=assignee_row.project_id,
        assignee=assignee_row.id,
    )


# ============================================================
# Backward-compat: routers/request.py (старый) ещё импортирует _pick_assignee.
# TODO: удалить после переписывания routers/request.py → intake.py
# ============================================================


async def _pick_assignee(
    session: AsyncSession,
    project: Project,
    stage: Stage,
) -> int | None:
    """Устаревшая обёртка. Возвращает user_id первого кандидата."""
    candidates = await stage_assign.candidates_for_stage(session, project, stage)
    if candidates:
        return candidates[0].id
    return project.manager_id
