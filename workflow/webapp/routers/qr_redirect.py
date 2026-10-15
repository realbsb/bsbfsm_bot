"""Редиректы по QR: пост в канале, публичная страница, ЛК."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from ...logging_setup import get_logger
from ...models import Project, PublicPost, QrToken, User
from ..dependencies import get_db, get_tg_user

log = get_logger(__name__)

router = APIRouter(prefix="/qr", tags=["qr"])


@router.get("/{token}", response_class=HTMLResponse)
async def redirect_by_token(
    token: str,
    request: Request,
    db=Depends(get_db),
    tg_user: User | None = Depends(get_tg_user),
):
    settings = request.app.state.settings
    root = settings.webapp_root_path

    async with db.session() as s:
        qr = (await s.execute(select(QrToken).where(QrToken.token == token))).scalars().first()
        if qr is None:
            raise HTTPException(404, "Not found")

        if qr.expires_at and qr.expires_at < datetime.utcnow():
            raise HTTPException(410, "Expired")

        project = await s.get(Project, qr.project_id)
        if project is None:
            raise HTTPException(404, "Project not found")

        if tg_user is not None:
            if tg_user.id in {
                project.manager_id,
                project.secretary_id,
                project.supplier_id,
                project.executor_id,
                project.current_assignee_id,
            }:
                return RedirectResponse(f"{root}/p/{project.id}")
            if project.client_user_id == tg_user.id:
                return RedirectResponse(f"{root}/p/{project.id}")

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

        if project.closed_at and project.is_public:
            return RedirectResponse(f"{root}/p/{project.id}")

        return HTMLResponse(
            "<html><body><h1>Объект не найден</h1>"
            "<p>Возможно, ссылка устарела или недоступна.</p></body></html>",
            status_code=404,
        )
