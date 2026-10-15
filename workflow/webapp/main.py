"""FastAPI-приложение: страница проекта, QR-редиректы, публичные формы."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import aiohttp
import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from ..config import get_settings
from ..db import Database
from ..logging_setup import get_logger, setup_logging
from ..models import (
    Document,
    DocumentItem,
    MediaAsset,
    Project,
    PublicPost,
    QrToken,
    User,
)
from .dependencies import get_db, get_tg_user
from .routers import public_forms, qr_redirect

log = get_logger(__name__)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings)
    settings.ensure_dirs()
    db = Database(settings)
    db.init()
    redis = aioredis.from_url(settings.redis_dsn, decode_responses=False)

    app.state.db = db
    app.state.settings = settings
    app.state.redis = redis

    log.info("webapp.startup", root_path=settings.webapp_root_path)
    yield

    await redis.aclose()
    await db.dispose()
    log.info("webapp.shutdown")


app = FastAPI(
    lifespan=lifespan,
    title="Workflow WebApp",
    root_path=get_settings().webapp_root_path or "",
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(qr_redirect.router)
app.include_router(public_forms.router)


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "ts": datetime.utcnow().isoformat()}


@app.get("/media/{media_id}", name="project_media")
async def project_media(
    media_id: int,
    key: str,
    tg_user: User | None = Depends(get_tg_user),
    db: Database = Depends(get_db),
):
    """Отдаёт Telegram-медиа через сервер, не раскрывая bot token в HTML."""
    async with db.session() as session:
        project, mode = await _resolve_access(session, key, tg_user)
        media = await session.get(MediaAsset, media_id)
        if project is None or mode == "denied" or media is None:
            raise HTTPException(404, "Медиа не найдено")
        if media.project_id != project.id:
            raise HTTPException(404, "Медиа не найдено")
        if media.is_final:
            allowed = mode in ("staff", "client", "delivery_public", "public")
        else:
            allowed = mode == "staff"
        if not allowed:
            raise HTTPException(404, "Медиа не найдено")
        bot_token = get_settings().bot_token
        api_url = f"https://api.telegram.org/bot{bot_token}/getFile"
        async with aiohttp.ClientSession() as client:
            async with client.get(api_url, params={"file_id": media.tg_file_id}) as response:
                if response.status != 200:
                    raise HTTPException(502, "Не удалось получить медиа")
                payload = await response.json()
        if not payload.get("ok") or not payload.get("result", {}).get("file_path"):
            raise HTTPException(502, "Не удалось получить медиа")
        file_path = payload["result"]["file_path"]

    async def stream_file():
        async with aiohttp.ClientSession() as client:
            async with client.get(
                f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
            ) as response:
                if response.status != 200:
                    return
                async for chunk in response.content.iter_chunked(64 * 1024):
                    yield chunk

    content_type = "video/mp4" if media.type.value == "video" else "image/jpeg"
    return StreamingResponse(stream_file(), media_type=content_type)


@app.get("/p/{key}", response_class=HTMLResponse)
async def project_page(
    key: str,
    request: Request,
    tg_user: User | None = Depends(get_tg_user),
    db: Database = Depends(get_db),
):
    async with db.session() as s:
        project, mode = await _resolve_access(s, key, tg_user)
        if project is None or mode == "denied":
            raise HTTPException(404, "Объект не найден")

        if mode == "redirect_channel":
            post = (
                (
                    await s.execute(
                        select(PublicPost).where(
                            PublicPost.project_id == project.id,
                            PublicPost.target == "channel",
                        )
                    )
                )
                .scalars()
                .first()
            )
            if post and post.url:
                return RedirectResponse(post.url)

        ctx = await _build_context(s, request, project, mode, tg_user)
        return templates.TemplateResponse("project.html", ctx)


async def _resolve_access(session, key: str, tg_user: User | None):
    project: Project | None = None
    qr: QrToken | None = None

    if key.isdigit():
        project = await session.get(Project, int(key))
    else:
        qr = (await session.execute(select(QrToken).where(QrToken.token == key))).scalars().first()
        if qr and (qr.expires_at is None or qr.expires_at > datetime.utcnow()):
            project = await session.get(Project, qr.project_id)

    if project is None:
        return None, "denied"

    if tg_user is not None:
        if tg_user.id in {
            project.manager_id,
            project.secretary_id,
            project.supplier_id,
            project.executor_id,
            project.current_assignee_id,
        }:
            return project, "staff"
        if project.client_user_id == tg_user.id:
            return project, "client"

    if qr is not None:
        if qr.kind == "purchase":
            return project, "purchase"
        if qr.kind == "delivery" and project.closed_at:
            return project, "delivery_public"

    post = (
        (
            await session.execute(
                select(PublicPost).where(
                    PublicPost.project_id == project.id,
                    PublicPost.target == "channel",
                )
            )
        )
        .scalars()
        .first()
    )
    if post:
        return project, "redirect_channel"

    if project.closed_at and project.is_public:
        return project, "public"

    return project, "denied"


async def _build_context(
    session, request: Request, project: Project, mode: str, tg_user: User | None
) -> dict:
    show_internal = mode == "staff"
    show_stages = mode == "staff"
    show_final = mode in ("staff", "client", "delivery_public", "public")
    show_materials = mode in ("staff", "purchase")

    materials: list[DocumentItem] = []
    if show_materials:
        materials = (
            (
                await session.execute(
                    select(DocumentItem)
                    .join(Document, Document.id == DocumentItem.document_id)
                    .where(Document.project_id == project.id)
                )
            )
            .scalars()
            .all()
        )

    stage_media: list[MediaAsset] = []
    final_media: list[MediaAsset] = []
    if show_stages:
        stage_media = (
            (
                await session.execute(
                    select(MediaAsset).where(
                        MediaAsset.project_id == project.id,
                        MediaAsset.is_final.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
    if show_final:
        final_media = (
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

    participants: list[dict] = []
    if mode == "staff":
        ids = {project.manager_id, project.secretary_id, project.supplier_id, project.executor_id}
        ids.discard(None)
        if ids:
            users = (await session.execute(select(User).where(User.id.in_(ids)))).scalars().all()
            for u in users:
                role = (
                    "manager"
                    if u.id == project.manager_id
                    else (
                        "secretary"
                        if u.id == project.secretary_id
                        else ("supplier" if u.id == project.supplier_id else "executor")
                    )
                )
                participants.append(
                    {
                        "tg_id": u.tg_id,
                        "first_name": u.first_name,
                        "username": u.username,
                        "role": role,
                    }
                )

    return {
        "request": request,
        "project": project,
        "mode": mode,
        "locale": (tg_user.locale if tg_user else "ru"),
        "show_price_internal": show_internal,
        "show_price_agreed": mode in ("staff", "client"),
        "show_media_stages": show_stages,
        "show_final_media": show_final,
        "show_materials": show_materials,
        "materials": materials,
        "stage_media": stage_media,
        "final_media": final_media,
        "participants": participants,
        "media_key": request.path_params["key"],
        "secretary_contact": None,
    }
