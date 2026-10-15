"""Публикация постов в канал и портфолио."""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import InputMediaPhoto, InputMediaVideo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..logging_setup import get_logger
from ..models import MediaAsset, PostTarget, Project, PublicPost, User

log = get_logger(__name__)


async def _collect_final_media(session: AsyncSession, project_id: int) -> list[MediaAsset]:
    rows = (
        (
            await session.execute(
                select(MediaAsset).where(
                    MediaAsset.project_id == project_id,
                    MediaAsset.is_final.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def _caption(project: Project) -> str:
    parts = [f"Объект #{project.id}"]
    if project.address_text:
        parts.append(project.address_text)
    if project.description:
        parts.append(project.description[:200])
    return "\n".join(parts)


def _build_group(media: list[MediaAsset], project: Project) -> list:
    group = []
    for i, m in enumerate(media[:10]):
        caption = _caption(project) if i == 0 else None
        if m.type.value == "photo":
            group.append(InputMediaPhoto(media=m.tg_file_id, caption=caption))
        elif m.type.value == "video":
            group.append(InputMediaVideo(media=m.tg_file_id, caption=caption))
    return group


async def publish_to_channel(
    bot: Bot,
    session: AsyncSession,
    project: Project,
    channel_id: int,
    author: User,
) -> PublicPost:
    media = await _collect_final_media(session, project.id)
    if not media:
        raise RuntimeError("Нет финальных медиа для публикации")

    group = _build_group(media, project)
    if not group:
        raise RuntimeError("Нет подходящих медиа")

    msgs = await bot.send_media_group(chat_id=channel_id, media=group)
    first = msgs[0]
    url = f"https://t.me/c/{str(channel_id).replace('-100', '')}/{first.message_id}"

    post = PublicPost(
        project_id=project.id,
        target=PostTarget.CHANNEL,
        chat_id=channel_id,
        message_id=first.message_id,
        url=url,
        author_id=author.id,
    )
    session.add(post)
    await session.flush()
    log.info("publish.channel", project=project.id, message=first.message_id)
    return post


async def publish_to_portfolio(
    bot: Bot,
    session: AsyncSession,
    project: Project,
    chat_id: int,
    author: User,
) -> PublicPost:
    media = await _collect_final_media(session, project.id)
    if not media:
        raise RuntimeError("Нет финальных медиа для портфолио")

    group = _build_group(media, project)
    if not group:
        raise RuntimeError("Нет подходящих медиа")

    msgs = await bot.send_media_group(chat_id=chat_id, media=group)
    post = PublicPost(
        project_id=project.id,
        target=PostTarget.PORTFOLIO,
        chat_id=chat_id,
        message_id=msgs[0].message_id,
        author_id=author.id,
    )
    session.add(post)
    await session.flush()
    log.info("publish.portfolio", project=project.id)
    return post
