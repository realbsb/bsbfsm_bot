"""Общие хелперы пакета request."""

from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ....services.intake import FormDef, get_form
from ...keyboards import request_confirm_kb
from ...texts import t


async def get_form_cached(session, state: FSMContext) -> FormDef:
    data = await state.get_data()
    cached = data.get("_form_def")
    if cached:
        return FormDef(physical=cached["physical"], logical=cached["logical"])
    manager_id = data.get("manager_id")
    form = await get_form(session, manager_id)
    await state.update_data(
        _form_def={
            "physical": form.physical,
            "logical": form.logical,
        }
    )
    return form


async def render_confirm(state: FSMContext, locale: str) -> str:
    data = await state.get_data()
    raw = data.get("raw_fields", {})
    form_def = data.get("_form_def") or {}
    logical_defs = form_def.get("logical") or []

    lines = [t("request.confirm_header", locale), ""]
    if logical_defs:
        for lf in logical_defs:
            code = lf["code"]
            label = lf.get("label", code)
            value = raw.get(code) or "—"
            lines.append(f"<b>{label}:</b> {value}")
    else:
        for k, v in raw.items():
            lines.append(f"<b>{k}:</b> {v or '—'}")
    return "\n".join(lines)


async def show_confirm(
    msg: Message,
    state: FSMContext,
    locale: str,
    edit: bool = False,
) -> None:
    data = await state.get_data()
    raw_text = data.get("raw_text")
    text = await render_confirm(state, locale)

    kb = request_confirm_kb(raw_text=raw_text)

    if edit:
        try:
            await msg.edit_text(text, reply_markup=kb)
            return
        except Exception:
            pass
    await msg.answer(text, reply_markup=kb)
