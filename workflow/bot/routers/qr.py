"""Генерация и печать QR-наклеек."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ...config import Settings
from ...logging_setup import get_logger
from ...models import Project, QrKind, QrToken, User
from ...services.qr import (
    expires_for,
    make_labels_png,
    make_qr_png,
    new_token,
    qr_url,
)
from ..keyboards import qr_kind_kb
from ..texts import t
from ..utils import trace

log = get_logger(__name__)
router = Router(name="qr")


@router.message(Command("qr"))
@trace
async def qr_cmd(
    msg: Message,
    session,
    user: User,
    locale: str,
) -> None:
    args = (msg.text or "").split()
    if len(args) < 2:
        return await msg.answer("Формат: /qr &lt;project_id&gt;")

    try:
        project_id = int(args[1])
    except ValueError:
        return await msg.answer("ID должен быть числом.")

    project = await session.get(Project, project_id)
    if project is None:
        return await msg.answer(t("common.not_found", locale))

    if (
        user.id
        not in {
            project.manager_id,
            project.secretary_id,
            project.supplier_id,
            project.executor_id,
        }
        and not user.is_admin
    ):
        return await msg.answer(t("common.not_allowed", locale))

    await msg.answer(
        f"Какой QR сгенерировать для проекта #{project_id}?",
        reply_markup=qr_kind_kb(project_id),
    )


@router.callback_query(F.data.startswith("qr_make:"))
@trace
async def qr_make(
    cb: CallbackQuery,
    session,
    user: User,
    settings: Settings,
    locale: str,
) -> None:
    _, project_id_s, kind_s = cb.data.split(":")
    project_id = int(project_id_s)
    kind = QrKind(kind_s)

    project = await session.get(Project, project_id)
    if project is None:
        return await cb.answer(t("common.not_found", locale), show_alert=True)

    token = new_token()
    session.add(
        QrToken(
            project_id=project_id,
            kind=kind,
            token=token,
            expires_at=expires_for(kind, settings),
        )
    )
    await session.commit()

    url = qr_url(settings, token)
    png = make_qr_png(url)

    await cb.message.answer_photo(
        BufferedInputFile(png, filename=f"qr_{project_id}_{kind.value}.png"),
        caption=f"QR для проекта #{project_id} ({kind.value})\n{url}",
    )
    log.info("qr.generated", project=project_id, kind=kind.value)
    await cb.answer()


@router.callback_query(F.data.startswith("qr_labels:"))
@trace
async def qr_labels(
    cb: CallbackQuery,
    session,
    user: User,
    settings: Settings,
    locale: str,
) -> None:
    _, project_id_s, count_s = cb.data.split(":")
    project_id = int(project_id_s)
    count = min(int(count_s), 20)

    project = await session.get(Project, project_id)
    if project is None:
        return await cb.answer(t("common.not_found", locale), show_alert=True)

    texts = []
    for _ in range(count):
        token = new_token()
        session.add(
            QrToken(
                project_id=project_id,
                kind=QrKind.PURCHASE,
                token=token,
                expires_at=expires_for(QrKind.PURCHASE, settings),
            )
        )
        texts.append(qr_url(settings, token))
    await session.commit()

    png = make_labels_png(texts)
    await cb.message.answer_document(
        BufferedInputFile(png, filename=f"labels_{project_id}.png"),
        caption=(
            f"{count} наклеек для проекта #{project_id}. Откройте через «Поделиться» → принтер."
        ),
    )
    log.info("qr.labels", project=project_id, count=count)
    await cb.answer()
