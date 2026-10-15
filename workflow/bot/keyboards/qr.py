"""Клавиатуры QR-кодов."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def qr_kind_kb(project_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛒 Закуп (1 шт)",
                    callback_data=f"qr_make:{project_id}:purchase",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📦 Закуп (5 шт)",
                    callback_data=f"qr_labels:{project_id}:5",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏁 Сдача",
                    callback_data=f"qr_make:{project_id}:delivery",
                )
            ],
        ]
    )
