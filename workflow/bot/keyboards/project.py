"""Клавиатуры карточки проекта."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ...models import Project, User


def project_kb(project: Project) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🗺 Карта", callback_data=f"map:{project.id}")],
        [InlineKeyboardButton(text="🧭 Маршрут", callback_data=f"route:{project.id}")],
    ]
    if project.current_assignee_id:
        rows.append(
            [
                InlineKeyboardButton(
                    text="👤 Текущий исполнитель",
                    callback_data=f"profile:{project.current_assignee_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def stage_actions_kb(
    project_id: int,
    can_finish: bool,
    can_refuse: bool,
    can_rewind: bool,
) -> InlineKeyboardMarkup:
    """Кнопки действий на стадии.

    can_finish — активный исполнитель.
    can_refuse — активный исполнитель И кандидатов больше одного.
    can_rewind — менеджер проекта И не первая стадия.
    """
    rows = []
    if can_finish:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Завершено",
                    callback_data=f"finish:{project_id}",
                )
            ]
        )
    if can_refuse:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🚫 Отказаться",
                    callback_data=f"refuse:{project_id}",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="↗️ Передать",
                    callback_data=f"handover:{project_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="📎 Медиа", callback_data=f"media:{project_id}")])
    rows.append([InlineKeyboardButton(text="📊 Отчёт", callback_data=f"report:{project_id}")])
    if can_rewind:
        rows.append(
            [
                InlineKeyboardButton(
                    text="↩️ Вернуть на предыдущий этап",
                    callback_data=f"rewind:{project_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def replacement_kb(users: list[User], project_id: int) -> InlineKeyboardMarkup:
    rows = []
    for u in users:
        name = u.first_name or u.username or str(u.id)
        rows.append(
            [
                InlineKeyboardButton(
                    text=name,
                    callback_data=f"replace_pick:{project_id}:{u.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="replace_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def report_kb(project_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Отчёт", callback_data=f"report:{project_id}"),
            ]
        ]
    )
