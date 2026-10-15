"""Клавиатуры клиента (личный кабинет)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def client_project_kb(project_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Детали", callback_data=f"client_view:{project_id}")],
            [InlineKeyboardButton(text="📅 Встреча", callback_data=f"client_meeting:{project_id}")],
            [
                InlineKeyboardButton(
                    text="✅ Принять работы", callback_data=f"client_accept:{project_id}"
                )
            ],
        ]
    )
