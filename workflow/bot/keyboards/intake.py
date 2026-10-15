"""Клавиатуры форм приёма (публичных и внутренних)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def form_kind_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📞 Позвоните мне", callback_data="form_kind:callback")],
            [InlineKeyboardButton(text="📋 Полная заявка", callback_data="form_kind:full")],
        ]
    )


def form_actions_kb(form_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📷 QR", callback_data=f"form_qr:{form_id}")],
            [InlineKeyboardButton(text="⏯ Вкл/выкл", callback_data=f"form_disable:{form_id}")],
        ]
    )
