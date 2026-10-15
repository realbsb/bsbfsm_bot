"""ARQ-воркер: фоновые задачи.

Cron:
- каждые 30 минут — SLA (предупреждения + просрочки)
- каждый день в 9:00 — дайджест менеджерам
"""

from __future__ import annotations

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select

from ..config import get_settings
from ..db import Database
from ..logging_setup import get_logger, setup_logging
from ..models import (
    IntakeEntry,
    Project,
    ProjectStageAssignee,
    User,
)
from ..services import sla as sla_service
from ..services import stage_machine
from ..services.export_finance import close_project_and_export
from ..services.final_media import cleanup_for_archive

log = get_logger(__name__)


# ============================================================
# Фоновые задачи
# ============================================================


async def transcribe_voice(ctx: dict, file_id: str) -> str:
    whisper = ctx.get("whisper")
    bot = ctx.get("bot")
    if whisper is None or bot is None:
        return ""
    try:
        # TODO: реализация после фикса volume
        return ""
    except Exception as e:
        log.error("worker.transcribe_failed", file_id=file_id, error=str(e))
        return ""


async def export_finance(ctx: dict, project_id: int) -> None:
    db: Database = ctx["db"]
    settings = ctx["settings"]
    async with db.session() as s:
        project = await s.get(Project, project_id)
        if project is None:
            log.warning("worker.export.project_missing", project=project_id)
            return
        try:
            files = await close_project_and_export(s, settings, project)
            await cleanup_for_archive(s, project)
            await s.commit()
            log.info("worker.export.done", project=project_id, files=list(files.keys()))
        except Exception as e:
            log.error("worker.export.failed", project=project_id, error=str(e))


async def archive_project(ctx: dict, project_id: int) -> None:
    db: Database = ctx["db"]
    async with db.session() as s:
        project = await s.get(Project, project_id)
        if project is None:
            return
        await cleanup_for_archive(s, project)
        await s.commit()
        log.info("worker.archive.done", project=project_id)


async def check_sla(ctx: dict) -> None:
    """SLA: предупреждения + просрочки."""
    db: Database = ctx["db"]
    bot = ctx.get("bot")
    warned = 0
    expired = 0

    async with db.session() as s:
        # --- Предупреждения ---
        warnings = await sla_service.collect_due_warnings(s)
        for w in warnings:
            user = await s.get(User, w["user_id"])
            project = await s.get(Project, w["project_id"])
            if not user or not project:
                continue
            locale = user.locale or "ru"
            key = "sla.warn_1" if w["warn_idx"] == 0 else "sla.warn_2"
            text = _t(
                key,
                locale,
                name=user.first_name or "коллега",
                project_id=project.id,
                hours=int(w["hours_left"]),
            )
            if bot:
                try:
                    await bot.send_message(user.tg_id, text)
                except Exception as e:
                    log.warning("worker.sla.warn_send_failed", user=user.id, error=str(e))
            await sla_service.mark_warned(s, w["assignee_id"], w["field"])
            warned += 1

        # --- Просрочки ---
        for e in await sla_service.collect_expired(s):
            a = await s.get(ProjectStageAssignee, e["assignee_id"])
            if a is None:
                continue
            await stage_machine.mark_expired(s, a)

            if bot and e["user_id"]:
                u = await s.get(User, e["user_id"])
                if u:
                    try:
                        await bot.send_message(
                            u.tg_id,
                            _t(
                                "sla.expired_assignee", u.locale or "ru", project_id=e["project_id"]
                            ),
                        )
                    except Exception as ex:
                        log.warning("worker.sla.expired_send_failed", user=u.id, error=str(ex))

            if bot:
                project = await s.get(Project, e["project_id"])
                if project:
                    mgr = await s.get(User, project.manager_id)
                    if mgr:
                        try:
                            await bot.send_message(
                                mgr.tg_id,
                                _t(
                                    "sla.expired_manager", mgr.locale or "ru", project_id=project.id
                                ),
                            )
                        except Exception as ex:
                            log.warning("worker.sla.expired_mgr_failed", user=mgr.id, error=str(ex))

            expired += 1

        await s.commit()

    log.info("worker.sla.checked", warned=warned, expired=expired)


async def daily_digest(ctx: dict) -> None:
    db: Database = ctx["db"]
    bot = ctx.get("bot")
    if bot is None:
        return

    async with db.session() as s:
        managers = (await s.execute(select(User).where(User.is_active.is_(True)))).scalars().all()

        for m in managers:
            projects = (
                (
                    await s.execute(
                        select(Project).where(
                            Project.manager_id == m.id,
                            Project.closed_at.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
            if not projects:
                continue
            text = f"📊 У вас {len(projects)} активных проектов."
            try:
                await bot.send_message(m.tg_id, text)
            except Exception as e:
                log.warning("worker.digest.send_failed", user=m.id, error=str(e))


async def notify_manager_request(ctx: dict, request_id: int) -> None:
    db: Database = ctx["db"]
    bot = ctx.get("bot")
    if bot is None:
        return

    async with db.session() as s:
        req = await s.get(IntakeEntry, request_id)
        if req is None:
            return
        manager = await s.get(User, req.manager_id)
        if manager is None:
            return
        try:
            await bot.send_message(
                manager.tg_id,
                f"📥 <b>Новая заявка</b>\n\n{req.summary_text}",
            )
        except Exception as e:
            log.warning("worker.notify_request_failed", error=str(e))

    log.info("worker.notify_manager_request.done", request=request_id)


# ============================================================
# Хелпер локализации (t() из бота тянет aiogram-зависимости)
# ============================================================


def _t(key: str, locale: str, **kwargs) -> str:
    """Обёртка: используем тот же t(), что и бот.

    Импорт внутри функции — чтобы не тянуть aiogram при импорте tasks.py.
    """
    from ..bot.texts import t as _bot_t

    return _bot_t(key, locale, **kwargs)


# ============================================================
# Lifecycle
# ============================================================


async def startup(ctx: dict) -> None:
    settings = get_settings()
    setup_logging(settings)
    settings.ensure_dirs()

    db = Database(settings)
    db.init()

    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    from ..bot.main import make_bot_session

    bot = Bot(
        token=settings.bot_token,
        session=await make_bot_session(settings.telegram_proxy),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    ctx["settings"] = settings
    ctx["db"] = db
    ctx["bot"] = bot
    log.info("worker.startup", proxy=settings.telegram_proxy)


async def shutdown(ctx: dict) -> None:
    db: Database = ctx.get("db")
    if db:
        await db.dispose()
    bot = ctx.get("bot")
    if bot:
        await bot.session.close()
    log.info("worker.shutdown")


# ============================================================
# ARQ settings
# ============================================================


class WorkerSettings:
    functions = [
        transcribe_voice,
        export_finance,
        archive_project,
        check_sla,
        daily_digest,
        notify_manager_request,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_dsn)
    cron_jobs = [
        cron(check_sla, minute={0, 30}),
        cron(daily_digest, hour={9}, minute={0}),
    ]
