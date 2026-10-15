"""Оркестрация календарей.

Radicale — опционально, для сотрудников (свой аккаунт).
Google Calendar — через штатные ссылки, OAuth не нужен.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..integrations.caldav_client import CaldavClient, is_configured
from ..logging_setup import get_logger
from ..models import (
    CalendarEvent,
    CalendarKind,
    CalendarProvider,
    CalendarStatus,
    Project,
    User,
    UserCalendarPref,
)
from .gcal_link import make_gcal_url_from_meeting

log = get_logger(__name__)


async def _get_or_create_pref(session: AsyncSession, user_id: int) -> UserCalendarPref:
    pref = (
        (await session.execute(select(UserCalendarPref).where(UserCalendarPref.user_id == user_id)))
        .scalars()
        .first()
    )
    if pref is None:
        pref = UserCalendarPref(user_id=user_id)
        session.add(pref)
        await session.flush()
    return pref


async def create_meeting(
    session: AsyncSession,
    settings: Settings,
    project: Project,
    initiator: User,
    approver: User | None,
    participants: list[User],
    start: datetime,
    duration_minutes: int,
    summary: str,
    kind: CalendarKind = CalendarKind.MEETING,
) -> dict:
    """Создаёт встречу у всех участников.

    Returns:
        dict: {
            "group_uid": str,
            "gcal_url": str | None,  # ссылка для добавления в Google Calendar
        }
    """
    group_uid = secrets.token_hex(16)
    end = start + timedelta(minutes=duration_minutes)

    caldav = CaldavClient(settings)

    for user in participants:
        pref = await _get_or_create_pref(session, user.id)

        # Если пользователь отключил встречи — только текстовая запись
        if not pref.meetings_enabled:
            session.add(
                CalendarEvent(
                    group_uid=group_uid,
                    project_id=project.id,
                    kind=kind,
                    initiator_id=initiator.id,
                    approver_id=approver.id if approver else None,
                    owner_id=user.id,
                    provider=CalendarProvider.RADICALE,
                    external_uid=None,
                    start_at=start,
                    end_at=end,
                    status=CalendarStatus.PROPOSED,
                )
            )
            continue

        # Если Radicale настроен — создаём событие
        external_uid: str | None = None
        if is_configured(pref):
            external_uid = await caldav.create_event(
                pref=pref,
                kind=kind.value,
                project_id=project.id,
                start=start,
                duration_minutes=duration_minutes,
                summary=summary,
                group_uid=group_uid,
            )

        session.add(
            CalendarEvent(
                group_uid=group_uid,
                project_id=project.id,
                kind=kind,
                initiator_id=initiator.id,
                approver_id=approver.id if approver else None,
                owner_id=user.id,
                provider=CalendarProvider.RADICALE,
                external_uid=external_uid,
                start_at=start,
                end_at=end,
                status=CalendarStatus.PROPOSED,
            )
        )

    # Google Calendar — штатная ссылка (для заказчика)
    gcal_url: str | None = None
    if approver is not None:
        gcal_url = make_gcal_url_from_meeting(
            project_id=project.id,
            title=summary,
            start=start,
            duration_minutes=duration_minutes,
            address=project.address_text or "",
            description=project.description or "",
        )

    await session.flush()
    log.info(
        "calendar.meeting_created",
        project=project.id,
        group=group_uid,
        participants=len(participants),
        gcal=bool(gcal_url),
    )
    return {"group_uid": group_uid, "gcal_url": gcal_url}


async def cancel_meeting(
    session: AsyncSession,
    settings: Settings,
    group_uid: str,
) -> int:
    """Удаляет все записи встречи по group_uid."""
    rows = (
        (await session.execute(select(CalendarEvent).where(CalendarEvent.group_uid == group_uid)))
        .scalars()
        .all()
    )

    caldav = CaldavClient(settings)
    deleted = 0

    for ev in rows:
        if ev.provider == CalendarProvider.RADICALE and ev.external_uid:
            pref = (
                (
                    await session.execute(
                        select(UserCalendarPref).where(UserCalendarPref.user_id == ev.owner_id)
                    )
                )
                .scalars()
                .first()
            )
            if pref and await caldav.delete_event(pref, ev.external_uid):
                deleted += 1
        await session.delete(ev)

    await session.flush()
    log.info("calendar.meeting_cancelled", group=group_uid, deleted=deleted)
    return deleted
