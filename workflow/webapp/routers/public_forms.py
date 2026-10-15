"""Публичные формы заявок: рендер и приём."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from ...logging_setup import get_logger
from ...models import IncomingRequest, RequestForm
from ...services.csrf import make_token, verify_token
from ...services.rate_limit import IpRateLimiter
from ..dependencies import get_db

log = get_logger(__name__)

router = APIRouter(prefix="/request", tags=["public-forms"])

templates = Jinja2Templates(
    directory=str(__import__("pathlib").Path(__file__).resolve().parent.parent / "templates")
)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/{slug}", response_class=HTMLResponse)
async def show_form(
    slug: str,
    request: Request,
    db=Depends(get_db),
):
    settings = request.app.state.settings
    async with db.session() as s:
        form = (
            (
                await s.execute(
                    select(RequestForm).where(
                        RequestForm.slug == slug,
                        RequestForm.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .first()
        )
        if form is None:
            raise HTTPException(404, "Форма не найдена")

    csrf = make_token(settings, slug)
    return templates.TemplateResponse(
        "public_form.html",
        {
            "request": request,
            "form": form,
            "csrf_token": csrf,
            "root_path": settings.webapp_root_path,
        },
    )


@router.post("/{slug}")
async def submit_form(
    slug: str,
    request: Request,
    db=Depends(get_db),
):
    settings = request.app.state.settings
    ip = _client_ip(request)

    limiter = IpRateLimiter(settings)
    try:
        if not await limiter.allow(ip, key_prefix="form"):
            raise HTTPException(429, "Слишком много запросов")
    finally:
        await limiter.close()

    form_data = await request.form()
    csrf = form_data.get("csrf_token", "")
    if not verify_token(settings, csrf, slug):
        log.warning("form.csrf_invalid", slug=slug, ip=ip)
        raise HTTPException(403, "Недействительный CSRF-токен")

    async with db.session() as s:
        form = (
            (
                await s.execute(
                    select(RequestForm).where(
                        RequestForm.slug == slug,
                        RequestForm.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .first()
        )
        if form is None:
            raise HTTPException(404, "Форма не найдена")

        payload = {k: v for k, v in form_data.items() if k != "csrf_token"}

        # Строим summary_text
        lines = [f"Заявка ({form.kind.value}): {form.title}"]
        for field in form.fields_json or []:
            key = field.get("key")
            label = field.get("label", key)
            value = payload.get(key, "")
            if value:
                lines.append(f"{label}: {value}")

        summary = "\n".join(lines)

        req = IncomingRequest(
            form_id=form.id,
            manager_id=form.manager_id,
            payload_json=payload,
            summary_text=summary,
            source_ip=ip,
            user_agent=request.headers.get("user-agent", "")[:256],
        )
        s.add(req)
        await s.flush()

        # Уведомляем менеджера через бота (через очередь arq)
        try:
            redis = request.app.state.redis
            await redis.enqueue_job("notify_manager_request", req.id)
        except Exception as e:
            log.warning("form.notify_failed", error=str(e))

        await s.commit()

    return RedirectResponse(
        url=f"{settings.webapp_root_path}/request/{slug}/thanks",
        status_code=303,
    )


@router.get("/{slug}/thanks", response_class=HTMLResponse)
async def thanks(slug: str, request: Request):
    return templates.TemplateResponse(
        "public_form_thanks.html",
        {"request": request, "slug": slug},
    )
