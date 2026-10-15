"""Клавиатуры закупа и парсинга."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ...models import Shop


def purchase_review_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Принять", callback_data="parse_accept")],
            [InlineKeyboardButton(text="✏️ Править вручную", callback_data="parse_manual")],
        ]
    )


def parse_fallback_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Прислать CSV", callback_data="parse_retry_csv")],
            [InlineKeyboardButton(text="📑 Прислать PDF", callback_data="parse_retry_pdf")],
            [InlineKeyboardButton(text="✏️ Ввести вручную", callback_data="parse_manual")],
            [InlineKeyboardButton(text="🎙 Голосом", callback_data="parse_voice")],
        ]
    )


def shopping_list_kb(items: list[dict], selected: set[int]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for i, item in enumerate(items):
        mark = "✅" if i in selected else "▫️"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {item['name']} — {item['qty']} {item.get('unit', 'шт')}",
                    callback_data=f"slist_pick:{i}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="➕ Добавить", callback_data="slist_add"),
            InlineKeyboardButton(text="🗂 Группы", callback_data="slist_group"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="📤 Экспорт", callback_data="slist_export"),
            InlineKeyboardButton(text="🛒 Куплено", callback_data="slist_bought"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def shop_picker_kb(shops: list[Shop], selected_id: int | None = None) -> InlineKeyboardMarkup:
    rows = []
    for s in shops:
        mark = "✅" if s.id == selected_id else "▫️"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {s.name}",
                    callback_data=f"shop_pick:{s.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ Новый магазин", callback_data="shop_new")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
