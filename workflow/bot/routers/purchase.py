"""Список закупа: парсинг SH3D, редактирование, группировка, экспорт.

Сценарий:
1. Пользователь шлёт CSV/PDF из SH3D.
2. Парсер извлекает таблицу.
3. Показывается превью, кнопки «Принять» / «Править».
4. После принятия — ShoppingList в состоянии FSM.
5. Снабженец может: добавлять, удалять, группировать, экспортировать, отмечать «куплено».
"""

from __future__ import annotations

import io
import tempfile
from decimal import Decimal
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    Document,
    Message,
)
from openpyxl import Workbook
from openpyxl.styles import Font

from ...logging_setup import get_logger
from ...models import Purchase, PurchaseItem, User
from ...parsers import parse_attachments
from ...parsers.normalize import clean_number
from ..keyboards import (
    cancel_kb,
    parse_fallback_kb,
    purchase_review_kb,
    shopping_list_kb,
)
from ..states import ParseFSM, PurchaseFSM
from ..texts import t
from ..utils import trace

log = get_logger(__name__)
router = Router(name="purchase")

BOLD = Font(bold=True)


# --- Парсинг 3D ---
@router.message(F.document)
@trace
async def on_document(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    doc: Document = msg.document
    suffix = Path(doc.file_name or "").suffix.lower()
    if suffix not in (".csv", ".pdf"):
        return

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / (doc.file_name or f"file{suffix}")
        file = await msg.bot.get_file(doc.file_id)
        await msg.bot.download_file(file.file_path, path)
        try:
            table = parse_attachments([path])
        except Exception as e:
            log.warning("parse.error", error=str(e))
            table = None

    if table is None or not table.rows:
        await state.set_state(ParseFSM.manual)
        await msg.answer(t("parse.failed", locale), reply_markup=parse_fallback_kb())
        return

    agg = table.aggregated()
    preview_lines = [
        f"• {r.name} × {r.qty}" + (f" ({r.width}×{r.depth}×{r.height})" if r.width else "")
        for r in agg[:10]
    ]
    preview = "\n".join(preview_lines)
    more = f"\n… и ещё {len(agg) - 10}" if len(agg) > 10 else ""

    await state.update_data(
        parsed=[
            {
                "name": r.name,
                "width": str(r.width) if r.width else None,
                "depth": str(r.depth) if r.depth else None,
                "height": str(r.height) if r.height else None,
                "qty": str(r.qty),
                "unit": "шт",
                "price": None,
            }
            for r in agg
        ],
        source=table.source,
    )
    await state.set_state(ParseFSM.review)
    await msg.answer(
        t(
            "parse.detected",
            locale,
            rows=len(table.rows),
            agg=len(agg),
            source=table.source,
            preview=f"{preview}{more}",
        ),
        reply_markup=purchase_review_kb(),
    )
    log.info("purchase.parsed", rows=len(table.rows), agg=len(agg), source=table.source)


@router.callback_query(ParseFSM.review, F.data == "parse_accept")
@trace
async def parse_accept(
    cb: CallbackQuery,
    state: FSMContext,
    locale: str,
) -> None:
    data = await state.get_data()
    await state.update_data(shopping_list=data.get("parsed", []))
    await state.set_state(PurchaseFSM.review_parsed)
    await cb.message.edit_text(t("parse.accepted", locale))
    await _render_list(cb.message, state, locale)
    await cb.answer()


@router.callback_query(ParseFSM.review, F.data == "parse_manual")
@trace
async def parse_manual(
    cb: CallbackQuery,
    state: FSMContext,
    locale: str,
) -> None:
    await state.set_state(PurchaseFSM.add_item)
    await cb.message.edit_text(
        "Введите позицию (текст или голос):",
        reply_markup=cancel_kb(),
    )
    await cb.answer()


@router.callback_query(ParseFSM.manual, F.data == "parse_retry_csv")
@trace
async def retry_csv(
    cb: CallbackQuery,
    locale: str,
) -> None:
    await cb.message.edit_text(t("parse.send_csv", locale))
    await cb.answer()


@router.callback_query(ParseFSM.manual, F.data == "parse_retry_pdf")
@trace
async def retry_pdf(
    cb: CallbackQuery,
    locale: str,
) -> None:
    await cb.message.edit_text(t("parse.send_pdf", locale))
    await cb.answer()


@router.callback_query(ParseFSM.manual, F.data == "parse_manual")
@trace
async def retry_manual(
    cb: CallbackQuery,
    state: FSMContext,
    locale: str,
) -> None:
    await state.set_state(PurchaseFSM.add_item)
    await cb.message.edit_text(
        "Введите позицию (текст или голос):",
        reply_markup=cancel_kb(),
    )
    await cb.answer()


# --- Редактирование списка ---
@trace
async def _render_list(
    msg: Message,
    state: FSMContext,
    locale: str,
) -> None:
    data = await state.get_data()
    items = data.get("shopping_list", [])
    selected = set(data.get("selected", []))
    text = t("purchase.list_title", locale, id=data.get("project_id", 0))
    await msg.answer(text, reply_markup=shopping_list_kb(items, selected))


@router.callback_query(PurchaseFSM.review_parsed, F.data.startswith("slist_pick:"))
@trace
async def slist_pick(
    cb: CallbackQuery,
    state: FSMContext,
) -> None:
    idx = int(cb.data.split(":")[1])
    data = await state.get_data()
    selected = set(data.get("selected", []))
    selected.symmetric_difference_update({idx})
    await state.update_data(selected=list(selected))
    items = data.get("shopping_list", [])
    await cb.message.edit_reply_markup(reply_markup=shopping_list_kb(items, selected))
    await cb.answer()


@router.callback_query(PurchaseFSM.review_parsed, F.data == "slist_add")
@trace
async def slist_add(
    cb: CallbackQuery,
    state: FSMContext,
    locale: str,
) -> None:
    await state.set_state(PurchaseFSM.add_item)
    await cb.message.answer("Введите позицию (текст или голос):", reply_markup=cancel_kb())
    await cb.answer()


@router.message(PurchaseFSM.add_item, F.text == "Отмена")
@trace
async def add_cancel(
    msg: Message,
    state: FSMContext,
    locale: str,
) -> None:
    await state.set_state(PurchaseFSM.review_parsed)
    await msg.answer(t("common.cancelled", locale))
    await _render_list(msg, state, locale)


@router.message(PurchaseFSM.add_item, F.voice)
@trace
async def add_voice(
    msg: Message,
    state: FSMContext,
    locale: str,
    whisper,
) -> None:
    try:
        text = await whisper.transcribe(msg.voice)
    except Exception as e:
        log.warning("whisper.failed", error=str(e))
        return await msg.answer(t("errors.whisper_error", locale))

    await _add_item_from_text(msg, state, text, locale)


@router.message(PurchaseFSM.add_item, F.text)
@trace
async def add_text(
    msg: Message,
    state: FSMContext,
    locale: str,
) -> None:
    await _add_item_from_text(msg, state, msg.text or "", locale)


@trace
async def _add_item_from_text(
    msg: Message,
    state: FSMContext,
    text: str,
    locale: str,
) -> None:
    """Простой парсер: «Кабель ВВГ 3х2.5 20м» → name + qty."""
    parts = text.rsplit(" ", 1)
    if len(parts) == 2 and any(c.isdigit() for c in parts[1]):
        name, qty_str = parts
        qty = clean_number(qty_str) or Decimal("1")
    else:
        name, qty = text, Decimal("1")

    data = await state.get_data()
    items = data.get("shopping_list", [])
    items.append(
        {
            "name": name.strip(),
            "qty": str(qty),
            "unit": "шт",
            "price": None,
        }
    )
    await state.update_data(shopping_list=items)
    await state.set_state(PurchaseFSM.review_parsed)
    await msg.answer(t("purchase.added", locale))
    await _render_list(msg, state, locale)
    log.info("purchase.item_added", name=name, qty=str(qty))


# --- Группировка ---
@router.callback_query(PurchaseFSM.review_parsed, F.data == "slist_group")
@trace
async def slist_group(
    cb: CallbackQuery,
    state: FSMContext,
    locale: str,
) -> None:
    data = await state.get_data()
    items = data.get("shopping_list", [])
    if not items:
        return await cb.answer("Список пуст", show_alert=True)

    grouped: dict[str, list] = {}
    for it in items:
        key = it["name"].split()[0] if it["name"] else "Прочее"
        grouped.setdefault(key, []).append(it)

    lines = []
    for group, lst in sorted(grouped.items()):
        lines.append(f"<b>{group}</b>")
        for it in lst:
            lines.append(f"  • {it['name']} — {it['qty']} {it.get('unit', 'шт')}")
    await cb.message.answer("\n".join(lines))
    await cb.answer()


# --- Экспорт ---
@router.callback_query(PurchaseFSM.review_parsed, F.data == "slist_export")
@trace
async def slist_export(
    cb: CallbackQuery,
    state: FSMContext,
    locale: str,
) -> None:
    data = await state.get_data()
    items = data.get("shopping_list", [])
    if not items:
        return await cb.answer("Список пуст", show_alert=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Закуп"
    ws.append(["Наименование", "Кол-во", "Ед.", "Цена", "Сумма"])
    for c in ws[1]:
        c.font = BOLD
    for it in items:
        price = float(it.get("price") or 0)
        qty = float(it.get("qty") or 0)
        ws.append([it["name"], qty, it.get("unit", "шт"), price, qty * price])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    await cb.message.answer_document(
        BufferedInputFile(buf.read(), filename="shopping_list.xlsx"),
        caption=t("purchase.exported", locale, path="shopping_list.xlsx"),
    )
    await cb.answer()
    log.info("purchase.exported", count=len(items))


# --- Куплено ---
@router.callback_query(PurchaseFSM.review_parsed, F.data == "slist_bought")
@trace
async def slist_bought(
    cb: CallbackQuery,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    data = await state.get_data()
    items = data.get("shopping_list", [])
    project_id = data.get("project_id")

    if not items or project_id is None:
        return await cb.answer("Нечего сохранять", show_alert=True)

    purchase = Purchase(project_id=project_id, supplier_id=user.id)
    session.add(purchase)
    await session.flush()

    total = Decimal("0")
    for it in items:
        qty = Decimal(it.get("qty", "1"))
        price = Decimal(it["price"]) if it.get("price") else None
        session.add(
            PurchaseItem(
                purchase_id=purchase.id,
                common_name=it["name"],
                qty=qty,
                unit=it.get("unit", "шт"),
                price=price,
            )
        )
        if price:
            total += qty * price

    purchase.total = total
    await session.commit()
    await state.clear()

    await cb.message.edit_text(t("purchase.bought", locale))
    await cb.answer()
    log.info("purchase.bought", project=project_id, count=len(items), total=str(total))
