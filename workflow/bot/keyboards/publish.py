"""Клавиатуры публикации."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def publish_kb(project_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 В канал", callback_data=f"pub_channel:{project_id}")],
            [
                InlineKeyboardButton(
                    text="🖼 В портфолио", callback_data=f"pub_portfolio:{project_id}"
                )
            ],
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="pub_skip")],
        ]
    )
