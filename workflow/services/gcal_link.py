"""Генерация штатных ссылок Google Calendar для добавления событий.

Не требует OAuth. Пользователь нажимает ссылку — открывается Google Calendar
с предзаполненным событием, остаётся нажать «Сохранить».
"""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urlencode

from ..logging_setup import get_logger

log = get_logger(__name__)

BASE_URL = "https://calendar.google.com/calendar/render"


def _fmt(dt: datetime) -> str:
    """Формат Google: YYYYMMDDTHHMMSS (локальное время без Z)."""
    return dt.strftime("%Y%m%dT%H%M%S")


def make_gcal_url(
    title: str,
    start: datetime,
    duration_minutes: int = 60,
    details: str = "",
    location: str = "",
) -> str:
    """Возвращает ссылку на создание события в Google Calendar.

    Args:
        title: Название события.
        start: Начало (локальное время).
        duration_minutes: Длительность.
        details: Описание.
        location: Адрес.

    Returns:
        Полный URL для кнопки/ссылки.
    """
    end = start + timedelta(minutes=duration_minutes)

    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{_fmt(start)}/{_fmt(end)}",
    }
    if details:
        params["details"] = details
    if location:
        params["location"] = location

    url = f"{BASE_URL}?{urlencode(params)}"
    log.info("gcal.link_created", title=title, start=_fmt(start))
    return url


def make_gcal_url_from_meeting(
    project_id: int,
    title: str,
    start: datetime,
    duration_minutes: int,
    address: str = "",
    description: str = "",
) -> str:
    """Обёртка для встречи по проекту."""
    details = f"Проект #{project_id}"
    if description:
        details += f"\n\n{description}"
    return make_gcal_url(
        title=title,
        start=start,
        duration_minutes=duration_minutes,
        details=details,
        location=address,
    )
