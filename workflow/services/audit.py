"""Запись в AuditLog."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..logging_setup import get_logger
from ..models import AuditLog

log = get_logger(__name__)


async def record(
    session: AsyncSession,
    actor_id: int | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            payload_json=payload,
        )
    )
    await session.flush()
    log.debug("audit.record", action=action, entity=entity, entity_id=entity_id)


async def record_and_log(
    session: AsyncSession,
    actor_id: int | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    **payload: Any,
) -> None:
    await record(session, actor_id, action, entity, entity_id, payload or None)
    log.info(f"audit.{action}", entity=entity, entity_id=entity_id, **payload)
