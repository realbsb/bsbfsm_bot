"""Смена стадии: Завершено / Отказаться / Передать / Вернуть.

Правила:
- can_finish — только активный исполнитель.
- refuse — активный исполнитель И есть другие кандидаты на стадию.
- handover — активный исполнитель передаёт коллеге (менеджер подтверждает).
- rewind — только менеджер, на одну стадию назад.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from ...config import Settings
from ...logging_setup import get_logger
from ...models import (
    MediaAsset,
    MediaType,
    Project,
    Stage,
    User,
)
from ...services import stage_assign
from ...services.stage_machine import (
    StageError,
    advance,
    can_finish,
    can_rewind,
    refuse,
    rewind,
)
from ..keyboards import cancel_kb, confirm_kb, price_keyboard
from ..states import PriceFSM, StageFSM
from ..texts import t
from ..utils import trace

log = get_logger(__name__)
router = Router(name="stage")


@router.callback_query(F.data.startswith("finish:"))
@trace
async def on_finish(
    cb: CallbackQuery,
    state: FSMContext,
    user: User,
    session,
    settings: Settings,
    locale: str,
) -> None:
    project_id = int(cb.data.split(":")[1])
    project = await session.get(Project, project_id)
    if project is None:
        return await cb.answer(t("common.not_found", locale), show_alert=True)

    stage = await session.get(Stage, project.stage_id)
    if stage is None:
        return await cb.answer(
            t("errors.stage_error", locale, msg="stage missing"), show_alert=True
        )

    if not await can_finish(session, project, stage, user):
        return await cb.answer(t("stage.not_yours", locale), show_alert=True)

    if stage.media_required:
        has_media = (
            (
                await session.execute(
                    select(MediaAsset)
                    .where(
                        MediaAsset.project_id == project_id,
                        MediaAsset.stage_id == stage.id,
                    )
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if has_media is None:
            await state.set_state(StageFSM.awaiting_media)
            await state.update_data(project_id=project_id)
            return await cb.message.answer(
                t("stage.media_required", locale),
                reply_markup=cancel_kb(),
            )

    if stage.calc_required and project.price_internal is None:
        await state.set_state(PriceFSM.digits)
        await state.update_data(
            project_id=project_id,
            price_field="price_internal",
            buf="",
        )
        return await cb.message.answer(
            t("stage.calc_required", locale),
            reply_markup=price_keyboard(),
        )

    await state.set_state(StageFSM.awaiting_confirm)
    await state.update_data(project_id=project_id)

    nxt = await session.scalar(
        select(Stage)
        .where(
            Stage.manager_id == stage.manager_id,
            Stage.order_idx > stage.order_idx,
            Stage.is_active.is_(True),
        )
        .order_by(Stage.order_idx)
        .limit(1)
    )
    next_name = t(nxt.name_i18n_key, locale) if nxt else "—"
    await cb.message.edit_text(
        t("stage.confirm_finish", locale, stage=t(stage.name_i18n_key, locale), next=next_name),
        reply_markup=confirm_kb("stage_finish_yes", "stage_finish_no"),
    )
    await cb.answer()


@router.callback_query(StageFSM.awaiting_confirm, F.data == "stage_finish_yes")
@trace
async def stage_finish_yes(
    cb: CallbackQuery,
    state: FSMContext,
    user: User,
    session,
    settings: Settings,
    locale: str,
) -> None:
    data = await state.get_data()
    project_id = data["project_id"]
    project = await session.get(Project, project_id)
    if project is None:
        await state.clear()
        return await cb.answer(t("common.not_found", locale), show_alert=True)

    try:
        nxt = await advance(session, project, user)
    except StageError as e:
        await state.clear()
        return await cb.answer(
            t("errors.stage_error", locale, msg=str(e)),
            show_alert=True,
        )

    await session.commit()
    await state.clear()

    await cb.message.edit_text(
        t("stage.finished", locale, stage=t(nxt.name_i18n_key, locale)),
    )

    if project.current_assignee_id and project.current_assignee_id != user.id:
        new_assignee = await session.get(User, project.current_assignee_id)
        if new_assignee:
            try:
                await cb.bot.send_message(
                    new_assignee.tg_id,
                    f"🔔 Ваш этап по проекту #{project_id}: <b>{t(nxt.name_i18n_key, locale)}</b>",
                )
            except Exception as e:
                log.warning("stage.notify_failed", error=str(e))

    log.info("stage.finished", project=project_id, stage=nxt.code, actor=user.id)
    await cb.answer()


@router.callback_query(StageFSM.awaiting_confirm, F.data == "stage_finish_no")
@trace
async def stage_finish_no(cb: CallbackQuery, state: FSMContext, locale: str) -> None:
    await state.clear()
    await cb.message.edit_text(t("common.cancelled", locale))
    await cb.answer()


@router.callback_query(F.data.startswith("refuse:"))
@trace
async def on_refuse(
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

    stage = await session.get(Stage, project.stage_id)
    if stage is None:
        return await cb.answer(t("common.not_found", locale), show_alert=True)

    candidates = await stage_assign.candidates_for_stage(session, project, stage)
    if len(candidates) <= 1:
        return await cb.answer(t("stage.refuse_no_alternatives", locale), show_alert=True)

    await state.set_state(StageFSM.awaiting_reason)
    await state.update_data(project_id=project_id, action="refuse")
    await cb.message.answer(t("stage.refuse_reason", locale), reply_markup=cancel_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("rewind:"))
@trace
async def on_rewind(
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
    if not await can_rewind(session, project, user):
        return await cb.answer(t("stage.rewind_not_allowed", locale), show_alert=True)

    await state.set_state(StageFSM.awaiting_reason)
    await state.update_data(project_id=project_id, action="rewind")
    await cb.message.answer(t("stage.rewind_reason", locale), reply_markup=cancel_kb())
    await cb.answer()


@router.message(StageFSM.awaiting_reason, F.text == "Отмена")
@trace
async def reason_cancel(msg: Message, state: FSMContext, locale: str) -> None:
    await state.clear()
    await msg.answer(t("common.cancelled", locale))


@router.message(StageFSM.awaiting_reason, F.text | F.voice)
@trace
async def reason(
    msg: Message,
    state: FSMContext,
    user: User,
    session,
    settings: Settings,
    locale: str,
    whisper,
) -> None:
    data = await state.get_data()
    project_id = data["project_id"]
    action = data.get("action", "refuse")
    reason_text = msg.text or ""
    voice_id: str | None = None

    if msg.voice:
        voice_id = msg.voice.file_id
        try:
            reason_text = await whisper.transcribe(msg.voice)
        except Exception as e:
            log.warning("whisper.failed", error=str(e))
            reason_text = "(голос не распознан)"

    project = await session.get(Project, project_id)
    if project is None:
        await state.clear()
        return await msg.answer(t("common.not_found", locale))

    try:
        if action == "refuse":
            await refuse(session, project, user, reason_text)
            done_text = t("stage.refuse_done", locale)
        elif action == "rewind":
            prv = await rewind(session, project, user, reason_text)
            done_text = t("stage.rewind_done", locale, stage=t(prv.name_i18n_key, locale))
        else:
            await state.clear()
            return await msg.answer(t("common.error", locale))
    except StageError as e:
        await state.clear()
        return await msg.answer(t("errors.stage_error", locale, msg=str(e)))

    if voice_id and action == "refuse":
        session.add(
            MediaAsset(
                project_id=project_id,
                stage_id=project.stage_id,
                type=MediaType.VOICE,
                tg_file_id=voice_id,
                uploaded_by=user.id,
                transcript=reason_text,
            )
        )

    await session.commit()
    await state.clear()
    await msg.answer(done_text)


@router.message(StageFSM.awaiting_media, F.photo | F.video)
@trace
async def stage_media_incoming(
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

    if msg.photo:
        session.add(
            MediaAsset(
                project_id=project_id,
                stage_id=project.stage_id,
                type=MediaType.PHOTO,
                tg_file_id=msg.photo[-1].file_id,
                uploaded_by=user.id,
            )
        )
    elif msg.video:
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

    await msg.answer(
        "📎 Материал принят. Продолжайте или нажмите «Завершено» в карточке проекта.",
        reply_markup=cancel_kb(),
    )


@router.message(StageFSM.awaiting_media, F.text == "Отмена")
@trace
async def stage_media_cancel(msg: Message, state: FSMContext, locale: str) -> None:
    await state.clear()
    await msg.answer(t("common.cancelled", locale))
