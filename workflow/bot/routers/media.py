"""Приём медиа: фото, видео, голос.

Два сценария:
1. Из карточки проекта — attach к текущему этапу (FSM MediaFSM.attaching).
2. Просто в чат — игнорируем (кроме случая, когда пользователь в FSM-состоянии).
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    Message,
)
from sqlalchemy import select

from ...logging_setup import get_logger
from ...models import MediaAsset, MediaType, Project, User
from ..keyboards import main_kb
from ..states import MediaFSM
from ..texts import t
from ..utils import trace

log = get_logger(__name__)
router = Router(name="media")


# --- Открытие диалога из карточки проекта ---
@router.callback_query(F.data.startswith("media:"))
@trace
async def media_open(
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

    # Проверка: причастен ли пользователь
    if user.id not in {
        project.manager_id,
        project.secretary_id,
        project.supplier_id,
        project.executor_id,
        project.current_assignee_id,
    }:
        return await cb.answer(t("common.not_allowed", locale), show_alert=True)

    await state.set_state(MediaFSM.attaching)
    await state.update_data(project_id=project_id)
    await cb.message.answer(
        f"📎 Приём материалов по проекту #{project_id}\n"
        f"Шлите фото, видео или голос. Когда закончите — «Готово».",
        reply_markup=main_kb(),
    )
    await cb.answer()


# --- Приём материалов ---
@router.message(MediaFSM.attaching, F.photo)
@trace
async def on_photo(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    data = await state.get_data()
    project_id = data.get("project_id")
    if project_id is None:
        return

    project = await session.get(Project, project_id)
    if project is None:
        return

    session.add(
        MediaAsset(
            project_id=project_id,
            stage_id=project.stage_id,
            type=MediaType.PHOTO,
            tg_file_id=msg.photo[-1].file_id,
            uploaded_by=user.id,
        )
    )
    await session.commit()
    await msg.answer(t("common.saved", locale))
    log.info("media.photo", project=project_id, user=user.id)


@router.message(MediaFSM.attaching, F.video)
@trace
async def on_video(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    data = await state.get_data()
    project_id = data.get("project_id")
    if project_id is None:
        return

    project = await session.get(Project, project_id)
    if project is None:
        return

    session.add(
        MediaAsset(
            project_id=project_id,
            stage_id=project.stage_id,
            type=MediaType.VIDEO,
            tg_file_id=msg.video.file_id,
            uploaded_by=user.id,
        )
    )
    await session.commit()
    await msg.answer(t("common.saved", locale))
    log.info("media.video", project=project_id, user=user.id)


@router.message(MediaFSM.attaching, F.voice)
@trace
async def on_voice(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    locale: str,
    whisper,
) -> None:
    data = await state.get_data()
    project_id = data.get("project_id")
    if project_id is None:
        return

    project = await session.get(Project, project_id)
    if project is None:
        return

    transcript: str | None = None
    try:
        transcript = await whisper.transcribe(msg.voice)
    except Exception as e:
        log.warning("whisper.failed", error=str(e))

    session.add(
        MediaAsset(
            project_id=project_id,
            stage_id=project.stage_id,
            type=MediaType.VOICE,
            tg_file_id=msg.voice.file_id,
            uploaded_by=user.id,
            transcript=transcript,
        )
    )
    await session.commit()

    if transcript:
        await msg.answer(transcript[:400])
    else:
        await msg.answer(t("errors.whisper_error", locale))
    log.info("media.voice", project=project_id, user=user.id, has_text=bool(transcript))


@router.message(MediaFSM.attaching, F.text == "Готово")
@trace
async def on_done(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    locale: str,
) -> None:
    data = await state.get_data()
    project_id = data.get("project_id")
    await state.clear()

    count = 0
    if project_id:
        count = len(
            (await session.execute(select(MediaAsset).where(MediaAsset.project_id == project_id)))
            .scalars()
            .all()
        )

    await msg.answer(
        f"Материалы сохранены для проекта #{project_id}. Всего: {count}.",
        reply_markup=main_kb(),
    )


@router.message(MediaFSM.attaching, F.text == "Отмена")
@trace
async def on_cancel(
    msg: Message,
    state: FSMContext,
    locale: str,
) -> None:
    await state.clear()
    await msg.answer(t("common.cancelled", locale), reply_markup=main_kb())


# --- Просмотр медиа проекта ---
@router.callback_query(F.data.startswith("media_view:"))
@trace
async def media_view(
    cb: CallbackQuery,
    user: User,
    session,
    locale: str,
) -> None:
    project_id = int(cb.data.split(":")[1])

    rows = (
        (
            await session.execute(
                select(MediaAsset)
                .where(MediaAsset.project_id == project_id)
                .order_by(MediaAsset.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )

    if not rows:
        return await cb.answer("Нет материалов", show_alert=True)

    for m in rows[:5]:
        if m.type == MediaType.PHOTO:
            await cb.message.answer_photo(m.tg_file_id)
        elif m.type == MediaType.VIDEO:
            await cb.message.answer_video(m.tg_file_id)
        elif m.type == MediaType.VOICE:
            await cb.message.answer_voice(
                m.tg_file_id,
                caption=(m.transcript or "")[:200],
            )
    await cb.answer()


# --- Пометка финальных ---
@router.callback_query(F.data.startswith("media_final:"))
@trace
async def media_final(
    cb: CallbackQuery,
    user: User,
    session,
    locale: str,
) -> None:
    media_id = int(cb.data.split(":")[1])
    media = await session.get(MediaAsset, media_id)
    if media is None:
        return await cb.answer(t("common.not_found", locale), show_alert=True)

    media.is_final = not media.is_final
    await session.commit()
    await cb.answer("✅ Финальное" if media.is_final else "▫️ Снято")
    log.info("media.toggle_final", media=media_id, value=media.is_final)
