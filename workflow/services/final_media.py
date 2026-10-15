"""Финальные медиа и очистка при архивации."""

from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..logging_setup import get_logger
from ..models import Document, MediaAsset, Project

log = get_logger(__name__)

KEEP_PHOTOS = 2
KEEP_VIDEOS = 1


async def mark_final(session: AsyncSession, project_id: int, media_id: int) -> None:
    await session.execute(update(MediaAsset).where(MediaAsset.id == media_id).values(is_final=True))
    log.info("media.mark_final", project=project_id, media=media_id)


async def cleanup_for_archive(session: AsyncSession, project: Project) -> dict:
    finals = (
        (
            await session.execute(
                select(MediaAsset).where(
                    MediaAsset.project_id == project.id,
                    MediaAsset.is_final.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )

    photos = [m for m in finals if m.type.value == "photo"][:KEEP_PHOTOS]
    videos = [m for m in finals if m.type.value == "video"][:KEEP_VIDEOS]
    keep_ids = {m.id for m in (*photos, *videos)}

    if keep_ids:
        await session.execute(
            delete(MediaAsset).where(
                MediaAsset.project_id == project.id,
                MediaAsset.id.notin_(keep_ids),
            )
        )
    else:
        await session.execute(delete(MediaAsset).where(MediaAsset.project_id == project.id))

    await session.execute(
        delete(Document).where(
            Document.project_id == project.id,
            Document.kind.notin_(["sketch", "project_pdf", "project_csv"]),
        )
    )

    log.info("archive.cleaned", project=project.id, kept_media=len(keep_ids))
    return {"kept_media": len(keep_ids)}
