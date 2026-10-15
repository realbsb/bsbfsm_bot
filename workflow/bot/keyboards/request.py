"""Клавиатуры FSM заявки. Динамические по полям формы."""

from __future__ import annotations

from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup


def request_confirm_kb(raw_text: str | None = None) -> InlineKeyboardMarkup:
    """Подтверждение распознанной заявки.

    Если raw_text задан и ≤ 256 символов — добавляется кнопка копирования.
    """
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="✅ Всё верно", callback_data="req_ok")],
        [InlineKeyboardButton(text="✏️ Изменить поле", callback_data="req_edit_menu")],
        [InlineKeyboardButton(text="📝 Пошагово", callback_data="req_step_by_step")],
    ]

    if raw_text and len(raw_text) <= 256:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📋 Скопировать распознанное",
                    copy_text=CopyTextButton(text=raw_text),
                )
            ]
        )

    rows.append([InlineKeyboardButton(text="🔄 Заново", callback_data="req_restart")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="req_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def request_edit_menu_kb(logical_fields: list[dict]) -> InlineKeyboardMarkup:
    """Меню выбора логического поля для редактирования."""
    rows: list[list[InlineKeyboardButton]] = []
    for f in logical_fields:
        label = f.get("label", f["code"])
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"req_edit:{f['code']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="req_back_to_confirm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def request_step_done_kb(
    restart_callback: str = "req_step_restart_current",
) -> InlineKeyboardMarkup:
    """После ответа на шаге — подтверждение этого поля."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Дальше", callback_data="req_step_next")],
            [InlineKeyboardButton(text="🔄 Заново", callback_data=restart_callback)],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="req_cancel")],
        ]
    )


def request_step_final_kb() -> InlineKeyboardMarkup:
    """После последнего шага."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Проверить", callback_data="req_step_finish")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="req_cancel")],
        ]
    )
