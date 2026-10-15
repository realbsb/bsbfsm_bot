"""Тесты переходов стадий."""

from __future__ import annotations

from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import BigInteger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from workflow.db import Base
from workflow.models import (
    Project,
    ProjectStageAssignee,
    Role,
    Stage,
    StageAssigneeState,
    User,
)
from workflow.services.stage_machine import StageError, advance, rewind


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(_type, _compiler, **_kwargs):
    return "INTEGER"


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _setup(session):
    manager_role = Role(code="manager", name_i18n_key="roles.manager")
    exec_role = Role(code="executor", name_i18n_key="roles.executor")
    session.add_all([manager_role, exec_role])
    await session.flush()

    manager = User(id=1, tg_id=1, first_name="M")
    executor = User(id=2, tg_id=2, first_name="E")
    session.add_all([manager, executor])
    await session.flush()

    s1 = Stage(
        id=1,
        manager_id=manager.id,
        order_idx=1,
        code="start",
        name_i18n_key="stages.request",
        responsible_role_id=manager_role.id,
    )
    s2 = Stage(
        id=2,
        manager_id=manager.id,
        order_idx=2,
        code="work",
        name_i18n_key="stages.realization",
        responsible_role_id=exec_role.id,
    )
    s3 = Stage(
        id=3,
        manager_id=manager.id,
        order_idx=3,
        code="done",
        name_i18n_key="stages.delivered",
        responsible_role_id=manager_role.id,
    )
    session.add_all([s1, s2, s3])
    await session.flush()

    return manager, executor, s1, s2, s3


async def _create_project(session, manager, stage, assignee):
    project = Project(
        id=1,
        manager_id=manager.id,
        stage_id=stage.id,
        current_assignee_id=assignee.id,
    )
    session.add(project)
    await session.flush()
    session.add(
        ProjectStageAssignee(
            id=1,
            project_id=project.id,
            stage_id=stage.id,
            user_id=assignee.id,
            active_slot=1,
            state=StageAssigneeState.ACTIVE,
            assigned_by=manager.id,
            planned_hours=72,
            deadline_at=datetime.now(),
        )
    )
    await session.flush()
    return project


@pytest.mark.asyncio
async def test_advance_moves_to_next(session: AsyncSession):
    manager, executor, s1, s2, _s3 = await _setup(session)

    project = await _create_project(session, manager, s1, manager)

    nxt = await advance(session, project, manager)
    assert nxt.id == s2.id
    assert project.stage_id == s2.id
    assert project.current_assignee_id is None


@pytest.mark.asyncio
async def test_advance_fails_on_last_stage(session: AsyncSession):
    manager, executor, _s1, _s2, s3 = await _setup(session)

    project = await _create_project(session, manager, s3, manager)

    with pytest.raises(StageError):
        await advance(session, project, manager)


@pytest.mark.asyncio
async def test_rewind_moves_back(session: AsyncSession):
    manager, executor, s1, s2, _s3 = await _setup(session)

    project = await _create_project(session, manager, s2, executor)

    prv = await rewind(session, project, manager, "не могу")
    assert prv.id == s1.id
    assert project.stage_id == s1.id
    assert project.current_assignee_id is None
