"""Клавиатуры профиля пользователя и организации."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ...models import Role


def lang_kb(current: str) -> InlineKeyboardMarkup:
    langs = [("ru", "Русский"), ("en", "English"), ("kz", "Қазақша")]
    rows = []
    for code, name in langs:
        mark = "✅ " if code == current else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}{name}",
                    callback_data=f"lang:{code}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_kb(
    is_manager: bool,
    can_manage_org: bool,
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🌐 Язык", callback_data="profile_lang")],
        [InlineKeyboardButton(text="📅 Radicale", callback_data="profile_radicale")],
        [InlineKeyboardButton(text="🔔 Встречи", callback_data="profile_meetings")],
        [InlineKeyboardButton(text="📄 Согласия", callback_data="profile_consents")],
    ]
    if is_manager:
        rows.append([InlineKeyboardButton(text="👥 Команда", callback_data="team_open")])
        rows.append([InlineKeyboardButton(text="📋 Формы заявок", callback_data="forms_open")])
    if can_manage_org:
        rows.append([InlineKeyboardButton(text="🏢 Организация", callback_data="org_open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def team_role_kb(roles: list[Role], locale: str) -> InlineKeyboardMarkup:
    """Устаревшее, оставлено для совместимости с forms.py."""
    from ..texts import t

    rows = []
    for r in roles:
        rows.append(
            [
                InlineKeyboardButton(
                    text=t(r.name_i18n_key, locale) if r.name_i18n_key else r.code,
                    callback_data=f"team_role:{r.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="profile_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def org_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Рабочий день", callback_data="org_workday")],
            [InlineKeyboardButton(text="⏰ SLA-предупреждения", callback_data="org_sla")],
            [InlineKeyboardButton(text="🔀 Вилка сроков", callback_data="org_range")],
            [InlineKeyboardButton(text="📍 Геотрекинг", callback_data="org_geo")],
            [InlineKeyboardButton(text="📞 Контакты", callback_data="org_contacts")],
            [InlineKeyboardButton(text="📢 Канал продвижения", callback_data="org_promo")],
            [
                InlineKeyboardButton(
                    text="🆕 Название кнопки приёма", callback_data="org_intake_label"
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="profile_back")],
        ]
    )


def org_workday_kb(start: str, end: str, workdays: list[int]) -> InlineKeyboardMarkup:
    """Настройка часов и рабочих дней организации."""
    day_names = [(1, "Пн"), (2, "Вт"), (3, "Ср"), (4, "Чт"), (5, "Пт"), (6, "Сб"), (7, "Вс")]
    rows = [
        [InlineKeyboardButton(text=f"Начало: {start}", callback_data="org_workday_start")],
        [InlineKeyboardButton(text=f"Конец: {end}", callback_data="org_workday_end")],
    ]
    rows.append([
        InlineKeyboardButton(
            text=f"{'✅' if day in workdays else '▫️'} {name}",
            callback_data=f"org_workday_day:{day}",
        )
        for day, name in day_names[:4]
    ])
    rows.append([
        InlineKeyboardButton(
            text=f"{'✅' if day in workdays else '▫️'} {name}",
            callback_data=f"org_workday_day:{day}",
        )
        for day, name in day_names[4:]
    ])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="org_open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def org_intake_label_kb(current: str | None) -> InlineKeyboardMarkup:
    """Выбор названия кнопки приёма. Пресеты + ввод."""
    presets = [
        ("🆕 Новая заявка", "🆕 Новая заявка"),
        ("🆕 Новая запись", "🆕 Новая запись"),
        ("🆕 Новый клиент", "🆕 Новый клиент"),
        ("🆕 Новая информация", "🆕 Новая информация"),
    ]
    rows = []
    for label, value in presets:
        mark = "✅ " if current == value else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}{label}",
                    callback_data=f"org_intake_label_set:{value}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="✏️ Ввести своё",
                callback_data="org_intake_label_custom",
            )
        ]
    )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="org_open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
