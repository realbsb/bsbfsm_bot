"""Конструктор публичных форм заявок (для менеджера).

Два типа:
- callback: «позвоните мне» — имя + телефон.
- full: полноценная заявка — имя, телефон, адрес, что нужно, время звонка.
"""

from __future__ import annotations

import secrets

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    Message,
)
from sqlalchemy import select

from ...config import Settings
from ...logging_setup import get_logger
from ...models import RequestForm, RequestFormKind, User
from ...services.qr import make_qr_png
from ..keyboards import form_actions_kb, form_kind_kb
from ..states import FormFSM
from ..utils import trace

log = get_logger(__name__)
router = Router(name="forms")

PRESET_FIELDS = {
    "callback": [
        {"key": "name", "label": "Имя", "type": "text", "required": True},
        {"key": "phone", "label": "Телефон", "type": "phone", "required": True},
    ],
    "full": [
        {"key": "name", "label": "Имя", "type": "text", "required": True},
        {"key": "phone", "label": "Телефон", "type": "phone", "required": True},
        {"key": "address", "label": "Адрес объекта", "type": "text", "required": False},
        {"key": "wish", "label": "Что нужно сделать", "type": "textarea", "required": True},
        {"key": "when", "label": "Удобное время звонка", "type": "datetime", "required": False},
    ],
}


@router.message(Command("forms"))
@trace
async def forms_list(
    msg: Message,
    user: User,
    session,
    settings: Settings,
    locale: str,
) -> None:
    rows = (
        (await session.execute(select(RequestForm).where(RequestForm.manager_id == user.id)))
        .scalars()
        .all()
    )

    if not rows:
        return await msg.answer(
            "У вас пока нет форм. Создайте первую:",
            reply_markup=form_kind_kb(),
        )

    lines = ["<b>Ваши формы:</b>"]
    for f in rows:
        status = "✅" if f.is_active else "⏸"
        url = f"{settings.bot_webapp_base_url}/request/{f.slug}"
        lines.append(f"{status} <b>{f.title}</b>\n{url}")

    await msg.answer("\n\n".join(lines), reply_markup=form_kind_kb())


@router.callback_query(F.data.startswith("form_kind:"))
@trace
async def form_kind(
    cb: CallbackQuery,
    state: FSMContext,
    user: User,
    locale: str,
) -> None:
    kind = cb.data.split(":")[1]
    if kind not in ("callback", "full"):
        return await cb.answer("Неверный тип")

    await state.set_state(FormFSM.pick_title)
    await state.update_data(kind=kind)
    await cb.message.edit_text("Введите название формы (например, «Заявка на баню»):")
    await cb.answer()


@router.message(FormFSM.pick_title, F.text)
@trace
async def form_title(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    settings: Settings,
    locale: str,
) -> None:
    data = await state.get_data()
    kind = data["kind"]
    title = (msg.text or "").strip()

    if len(title) < 3:
        return await msg.answer("Название слишком короткое.")

    fields = PRESET_FIELDS.get(kind, PRESET_FIELDS["callback"])
    slug = secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:12]

    form = RequestForm(
        manager_id=user.id,
        slug=slug,
        title=title,
        kind=RequestFormKind(kind),
        fields_json=fields,
    )
    session.add(form)
    await session.commit()
    await state.clear()

    url = f"{settings.bot_webapp_base_url}/request/{slug}"

    await msg.answer(
        f"✅ Форма «{title}» создана.\n\n"
        f"Ссылка: {url}\n"
        f"Slug: <code>{slug}</code>\n\n"
        f"Поля: {', '.join(f['label'] for f in fields)}",
        reply_markup=form_actions_kb(form.id),
    )
    log.info("form.created", manager=user.id, slug=slug, kind=kind)


@router.callback_query(F.data.startswith("form_qr:"))
@trace
async def form_qr(
    cb: CallbackQuery,
    session,
    user: User,
    settings: Settings,
    locale: str,
) -> None:
    form_id = int(cb.data.split(":")[1])
    form = await session.get(RequestForm, form_id)
    if form is None or form.manager_id != user.id:
        return await cb.answer("Недоступно", show_alert=True)

    url = f"{settings.bot_webapp_base_url}/request/{form.slug}"
    png = make_qr_png(url, box_size=8)

    await cb.message.answer_photo(
        BufferedInputFile(png, filename=f"form_{form.slug}.png"),
        caption=f"QR для формы «{form.title}»\n{url}",
    )
    await cb.answer()


@router.callback_query(F.data.startswith("form_disable:"))
@trace
async def form_disable(
    cb: CallbackQuery,
    session,
    user: User,
    locale: str,
) -> None:
    form_id = int(cb.data.split(":")[1])
    form = await session.get(RequestForm, form_id)
    if form is None or form.manager_id != user.id:
        return await cb.answer("Недоступно", show_alert=True)

    form.is_active = not form.is_active
    await session.commit()
    await cb.answer("Активна" if form.is_active else "Отключена")
