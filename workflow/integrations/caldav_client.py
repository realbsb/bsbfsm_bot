"""Клиент Radicale. Учётки — у каждого пользователя свои, опционально."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

import caldav

from ..bot.utils import trace
from ..config import Settings
from ..logging_setup import get_logger
from ..models import UserCalendarPref

log = get_logger(__name__)

Kind = Literal["call", "meeting", "work"]


@trace
def is_configured(pref: UserCalendarPref | None) -> bool:
    """Проверяет, задан ли у пользователя Radicale-доступ."""
    return bool(pref and pref.radicale_url and pref.radicale_username and pref.radicale_password)


class CaldavClient:
    """Клиент Radicale. Не администрирует сервер, только создаёт/удаляет события."""

    @trace
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @trace
    def _client_for(self, pref: UserCalendarPref) -> caldav.DAVClient:
        return caldav.DAVClient(
            url=pref.radicale_url,
            username=pref.radicale_username,
            password=pref.radicale_password,
        )

    @trace
    def _calendar_for(self, pref: UserCalendarPref):
        client = self._client_for(pref)
        principal = client.principal()
        calendars = principal.calendars()
        if calendars:
            return calendars[0]
        return principal.make_calendar(name="workflow")

    @trace
    async def create_event(
        self,
        pref: UserCalendarPref,
        kind: Kind,
        project_id: int,
        start: datetime,
        duration_minutes: int,
        summary: str,
        group_uid: str,
    ) -> str | None:
        if not is_configured(pref):
            log.info("caldav.skipped", owner=pref.user_id, reason="not_configured")
            return None

        try:
            calendar = self._calendar_for(pref)
            end = start + timedelta(minutes=duration_minutes)
            uid = f"{group_uid}-{pref.user_id}"
            ical = (
                "BEGIN:VCALENDAR\n"
                "VERSION:2.0\n"
                "PRODID:-//workflow//RU\n"
                "BEGIN:VEVENT\n"
                f"UID:{uid}\n"
                f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}\n"
                f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}\n"
                f"SUMMARY:{summary}\n"
                f"DESCRIPTION:project#{project_id} kind={kind}\n"
                f"CATEGORIES:{kind}\n"
                "END:VEVENT\n"
                "END:VCALENDAR\n"
            )
            calendar.save_event(ical)
            log.info("caldav.created", owner=pref.user_id, project=project_id, kind=kind)
            return uid
        except Exception as e:
            log.error("caldav.error", owner=pref.user_id, error=str(e))
            return None

    @trace
    async def delete_event(self, pref: UserCalendarPref, event_uid: str) -> bool:
        if not is_configured(pref):
            return False
        try:
            calendar = self._calendar_for(pref)
            ev = calendar.event_by_uid(event_uid)
            ev.delete()
            log.info("caldav.deleted", owner=pref.user_id, uid=event_uid)
            return True
        except Exception as e:
            log.error("caldav.delete_failed", owner=pref.user_id, error=str(e))
            return False
