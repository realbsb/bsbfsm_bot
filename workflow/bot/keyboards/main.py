"""Reply-клавиатуры: главное меню, отмена, телефон, цена."""

from __future__ import annotations

from aiogram.types import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)


def build_main_kb(
    is_manager: bool = False,
    can_intake: bool = False,
    intake_label: str | None = None,
) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text="📋 Мои задачи"), KeyboardButton(text="📅 Мой день")],
    ]
    if can_intake:
        rows.append([KeyboardButton(text=intake_label or "🆕 Новая заявка")])
    rows.append([KeyboardButton(text="⚙️ Профиль")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def main_kb() -> ReplyKeyboardMarkup:
    return build_main_kb()


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )


def skip_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить"), KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить телефон", request_contact=True)],
            [KeyboardButton(text="Ввести вручную"), KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
    )


def price_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="1"), KeyboardButton(text="2"), KeyboardButton(text="3")],
        [KeyboardButton(text="4"), KeyboardButton(text="5"), KeyboardButton(text="6")],
        [KeyboardButton(text="7"), KeyboardButton(text="8"), KeyboardButton(text="9")],
        [KeyboardButton(text="."), KeyboardButton(text="0"), KeyboardButton(text="⌫")],
        [KeyboardButton(text="ОК"), KeyboardButton(text="Отмена")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
