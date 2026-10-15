"""Клавиатуры «Мой день» и планирования."""

from __future__ import annotations

from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ...models import Project


def day_kb() -> InlineKeyboardMarkup:
    """Кнопки под «Мой день»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📅 Завтра", callback_data="day:tomorrow"),
                InlineKeyboardButton(text="📅 Другой день", callback_data="day:other"),
            ],
            [InlineKeyboardButton(text="🗓 Перепланировать", callback_data="day:reschedule")],
        ]
    )


def day_back_kb() -> InlineKeyboardMarkup:
    """Возврат к «Сегодня»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Сегодня", callback_data="day:today")],
            [InlineKeyboardButton(text="📅 Другой день", callback_data="day:other")],
        ]
    )


def date_kb(base: date | None = None) -> InlineKeyboardMarkup:
    base = base or date.today()
    rows = []
    for offset in range(0, 7):
        d = base + timedelta(days=offset)
        label = d.strftime("%a %d.%m")
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"date:{d.isoformat()}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="day:today")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def projects_multi_kb(
    projects: list[Project],
    selected: set[int],
) -> InlineKeyboardMarkup:
    rows = []
    for p in projects:
        mark = "✅" if p.id in selected else "▫️"
        title = (p.address_text or p.client_name or f"#{p.id}")[:50]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} #{p.id} {title}",
                    callback_data=f"pick:{p.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="✔️ Подтвердить", callback_data="plan_confirm")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="day:today")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
