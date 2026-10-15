"""Inline-клавиатуры общего назначения."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def cancel_inline_kb() -> InlineKeyboardMarkup:
    """Inline «Отмена» для FSM-шагов. Не висит в чате между сессиями."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_fsm"),
            ]
        ]
    )


def confirm_inline_kb(
    yes_data: str,
    no_data: str,
    yes_text: str = "✅ Да",
    no_text: str = "❌ Нет",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=yes_text, callback_data=yes_data),
                InlineKeyboardButton(text=no_text, callback_data=no_data),
            ]
        ]
    )


def confirm_kb(yes_data: str, no_data: str) -> InlineKeyboardMarkup:
    """Алиас для обратной совместимости."""
    return confirm_inline_kb(yes_data, no_data)


def back_kb(target: str = "back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️ Назад", callback_data=target),
            ]
        ]
    )
