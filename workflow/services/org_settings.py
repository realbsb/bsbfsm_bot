"""CRUD для OrgSettings: чтение, обновление отдельных полей."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..logging_setup import get_logger
from ..models import OrgSettings

log = get_logger(__name__)


async def get_or_create(session: AsyncSession, owner_id: int) -> OrgSettings:
    org = (
        (await session.execute(select(OrgSettings).where(OrgSettings.owner_id == owner_id)))
        .scalars()
        .first()
    )
    if org is None:
        org = OrgSettings(
            owner_id=owner_id,
            use_range=True,
            workday_start="09:00",
            workday_end="18:00",
            workdays=[1, 2, 3, 4, 5],
            sla_warn_hours=[24, 2],
            geotracking_enabled=False,
            geotracking_points=["start", "end"],
        )
        session.add(org)
        await session.flush()
        log.info("org_settings.created", owner=owner_id)
    return org


async def get(session: AsyncSession, owner_id: int) -> OrgSettings | None:
    return (
        (await session.execute(select(OrgSettings).where(OrgSettings.owner_id == owner_id)))
        .scalars()
        .first()
    )


async def update_field(
    session: AsyncSession,
    owner_id: int,
    field: str,
    value,
) -> OrgSettings:
    org = await get_or_create(session, owner_id)
    if not hasattr(org, field):
        raise ValueError(f"У OrgSettings нет поля {field}")
    setattr(org, field, value)
    await session.flush()
    log.info("org_settings.updated", owner=owner_id, field=field)
    return org
