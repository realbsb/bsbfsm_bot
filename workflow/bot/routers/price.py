"""Ввод сумм: price_internal, price_agreed.

Цифровая клавиатура (ReplyKeyboard). Один FSM для всех денежных полей.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...logging_setup import get_logger
from ...models import Project, User
from ..keyboards import confirm_kb, main_kb, price_keyboard
from ..states import PriceFSM
from ..texts import t
from ..utils import trace

log = get_logger(__name__)
router = Router(name="price")


@router.message(PriceFSM.digits)
@trace
async def on_digit(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    text = (msg.text or "").strip()

    if text == "Отмена":
        await state.clear()
        return await msg.answer(t("common.cancelled", locale), reply_markup=main_kb())

    data = await state.get_data()
    buf: str = data.get("buf", "")

    if text == "⌫":
        buf = buf[:-1]
        await state.update_data(buf=buf)
        return await msg.answer(
            f"Ввод: {buf or '—'}",
            reply_markup=price_keyboard(),
        )

    if text == "ОК":
        try:
            amount = Decimal(buf)
        except (InvalidOperation, ValueError):
            return await msg.answer(
                t("price.invalid", locale),
                reply_markup=price_keyboard(),
            )

        await state.update_data(amount=str(amount))
        await state.set_state(PriceFSM.confirm)
        return await msg.answer(
            t("price.confirm", locale, amount=str(amount)),
            reply_markup=confirm_kb("price_yes", "price_no"),
        )

    if text not in "0123456789.":
        return await msg.answer(
            t("price.enter", locale),
            reply_markup=price_keyboard(),
        )

    if text == "." and "." in buf:
        return

    buf = (buf + text)[:14]
    await state.update_data(buf=buf)
    await msg.answer(f"Ввод: {buf}", reply_markup=price_keyboard())


@router.callback_query(PriceFSM.confirm, F.data == "price_yes")
@trace
async def price_yes(
    cb: CallbackQuery,
    state: FSMContext,
    session,
    locale: str,
) -> None:
    data = await state.get_data()
    amount = Decimal(data["amount"])
    project_id = data.get("project_id")
    field = data.get("price_field", "price_internal")

    project = await session.get(Project, project_id)
    if project is None:
        await state.clear()
        return await cb.answer(t("common.not_found", locale), show_alert=True)

    setattr(project, field, amount)
    await session.commit()
    await state.clear()

    await cb.message.edit_text(t("price.saved", locale, amount=str(amount)))
    log.info("price.saved", project=project_id, field=field, amount=str(amount))
    await cb.answer()


@router.callback_query(PriceFSM.confirm, F.data == "price_no")
@trace
async def price_no(
    cb: CallbackQuery,
    state: FSMContext,
    locale: str,
) -> None:
    await state.set_state(PriceFSM.digits)
    await state.update_data(buf="")
    await cb.message.edit_text(
        t("price.enter", locale),
        reply_markup=price_keyboard(),
    )
    await cb.answer()


# --- Ввод согласованной суммы (менеджер) ---
@router.callback_query(F.data.startswith("set_agreed:"))
@trace
async def set_agreed(
    cb: CallbackQuery,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    project_id = int(cb.data.split(":")[1])
    project = await session.get(Project, project_id)
    if project is None:
        return await cb.answer(t("common.not_found", locale), show_alert=True)
    if project.manager_id != user.id and not user.is_admin:
        return await cb.answer(t("common.not_allowed", locale), show_alert=True)

    await state.set_state(PriceFSM.digits)
    await state.update_data(
        project_id=project_id,
        price_field="price_agreed",
        buf="",
    )
    await cb.message.answer(
        t("price.enter", locale),
        reply_markup=price_keyboard(),
    )
    await cb.answer()


# --- Ввод предоплаты / финала ---
@router.callback_query(F.data.startswith("set_prepay:"))
@trace
async def set_prepay(
    cb: CallbackQuery,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    project_id = int(cb.data.split(":")[1])
    project = await session.get(Project, project_id)
    if project is None:
        return await cb.answer(t("common.not_found", locale), show_alert=True)
    if project.manager_id != user.id and not user.is_admin:
        return await cb.answer(t("common.not_allowed", locale), show_alert=True)

    await state.set_state(PriceFSM.digits)
    await state.update_data(
        project_id=project_id,
        price_field="prepay_paid",
        buf="",
    )
    await cb.message.answer(
        "Введите сумму предоплаты:",
        reply_markup=price_keyboard(),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("set_final:"))
@trace
async def set_final(
    cb: CallbackQuery,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    project_id = int(cb.data.split(":")[1])
    project = await session.get(Project, project_id)
    if project is None:
        return await cb.answer(t("common.not_found", locale), show_alert=True)
    if project.manager_id != user.id and not user.is_admin:
        return await cb.answer(t("common.not_allowed", locale), show_alert=True)

    await state.set_state(PriceFSM.digits)
    await state.update_data(
        project_id=project_id,
        price_field="final_paid",
        buf="",
    )
    await cb.message.answer(
        "Введите сумму финального расчёта:",
        reply_markup=price_keyboard(),
    )
    await cb.answer()
