"""Клавиатуры управления командой."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ...models import Position


def team_kb(has_members: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="➕ Добавить подчинённого", callback_data="team_add")],
        [InlineKeyboardButton(text="🔧 Профессии", callback_data="team_positions")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="profile_back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def team_checklist_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏢 Настроить организацию", callback_data="org_open")],
            [InlineKeyboardButton(text="➕ Всё равно добавить", callback_data="team_add")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="profile_back")],
        ]
    )


def position_pick_kb(positions: list[Position]) -> InlineKeyboardMarkup:
    rows = []
    for p in positions:
        rows.append(
            [
                InlineKeyboardButton(
                    text=p.name,
                    callback_data=f"team_add_pos:{p.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="team_open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def invite_link_kb(invite_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Открыть ссылку", url=invite_url)],
            [InlineKeyboardButton(text="✅ Готово", callback_data="team_open")],
        ]
    )


def positions_list_kb(positions: list[Position]) -> InlineKeyboardMarkup:
    rows = []
    for p in positions:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {p.name}",
                    callback_data=f"team_pos_edit:{p.id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="➕ Новая профессия",
                callback_data="team_pos_new",
            )
        ]
    )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="team_open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def position_edit_kb(position_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Переименовать", callback_data=f"team_pos_rename:{position_id}"
                )
            ],
            [InlineKeyboardButton(text="🎛 Флаги", callback_data=f"team_pos_flags:{position_id}")],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить", callback_data=f"team_pos_delete:{position_id}"
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="team_positions")],
        ]
    )


def position_flags_kb(position_id: int, active_flags: set[str]) -> InlineKeyboardMarkup:
    flags = [
        ("intake", "📥 Приём"),
        ("supply", "🛒 Закуп"),
        ("execute", "🔧 Исполнение"),
        ("plan", "📅 Планирование"),
        ("calc", "💰 Расчёт"),
        ("media", "📸 Медиа"),
        ("client_meeting", "📞 Встреча с клиентом"),
        ("manage_team", "👥 Управление командой"),
        ("manage_org", "🏢 Управление организацией"),
        ("close", "✅ Закрытие проекта"),
    ]
    rows = []
    for code, label in flags:
        mark = "✅ " if code in active_flags else "▫️ "
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}{label}",
                    callback_data=f"team_pos_flag:{position_id}:{code}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=f"team_pos_edit:{position_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
