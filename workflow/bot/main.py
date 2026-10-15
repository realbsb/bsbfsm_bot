"""Точка входа бота.

Поддерживает HTTP и SOCKS5 прокси для доступа к api.telegram.org.
"""

from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from sqlalchemy import select

from ..config import Settings, get_settings
from ..db import Database
from ..integrations.llm_client import LlmClient
from ..integrations.whisper_client import WhisperClient
from ..logging_setup import get_logger, setup_logging
from ..models import Position, PositionRole, Role, RoleAssignment, User
from ..services.seed import run_seed, seed_manager_stages
from .errors import setup_error_handler
from .middlewares import (
    AntiFloodMiddleware,
    DbMiddleware,
    DeepLinkMiddleware,
    LocaleMiddleware,
    RoleMiddleware,
    SettingsMiddleware,
    UserMiddleware,
)
from .routers import (
    admin,
    client,
    common,
    fallback,
    finance,
    forms,
    media,
    menu,
    org,
    price,
    profile,
    project,
    publish,
    purchase,
    qr,
    report,
    request,
    schedule,
    stage,
    start,
    team,
)

log = get_logger(__name__)


async def make_bot_session(proxy_url: str | None) -> AiohttpSession:
    if not proxy_url:
        return AiohttpSession()
    log.info("bot.session.proxy", proxy=proxy_url)
    return AiohttpSession(proxy=proxy_url)


async def _bootstrap(db: Database) -> None:
    """Seed ролей/шаблонов и создание стадий для существующих менеджеров."""
    async with db.session() as session:
        await run_seed(session)

        roles = {r.code: r for r in (await session.execute(select(Role))).scalars().all()}
        manager_role = roles.get("manager")
        if manager_role is None:
            return

        # Менеджеры: у кого в должности есть роль "manager"
        managers = (
            (
                await session.execute(
                    select(User)
                    .join(RoleAssignment, RoleAssignment.user_id == User.id)
                    .join(Position, Position.id == RoleAssignment.position_id)
                    .join(PositionRole, PositionRole.position_id == Position.id)
                    .where(
                        RoleAssignment.is_active.is_(True),
                        PositionRole.role_id == manager_role.id,
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )

        for m in managers:
            await seed_manager_stages(session, m, roles)
        await session.commit()


async def main() -> None:
    settings: Settings = get_settings()
    setup_logging(settings)
    settings.ensure_dirs()

    db = Database(settings)
    db.init()
    await _bootstrap(db)

    bot_session = await make_bot_session(settings.telegram_proxy)
    bot = Bot(
        token=settings.bot_token,
        session=bot_session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = RedisStorage.from_url(
        settings.redis_dsn,
        state_ttl=86400,
        data_ttl=86400,
    )
    dp = Dispatcher(storage=storage)
    whisper = WhisperClient(settings, bot)
    llm = LlmClient(settings)

    # Middlewares
    dp.update.middleware(AntiFloodMiddleware(rate=10, per_seconds=5))
    dp.update.middleware(SettingsMiddleware(settings))
    dp.update.middleware(DbMiddleware(db))
    dp.update.middleware(UserMiddleware())
    dp.update.middleware(RoleMiddleware())
    dp.update.middleware(LocaleMiddleware())
    dp.update.middleware(DeepLinkMiddleware())

    setup_error_handler(dp)

    # Routers — порядок важен.
    dp.include_router(common.router)
    dp.include_router(client.router)
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(profile.router)
    dp.include_router(org.router)
    dp.include_router(forms.router)
    dp.include_router(request.router)
    dp.include_router(project.router)
    dp.include_router(stage.router)
    dp.include_router(price.router)
    dp.include_router(schedule.router)
    dp.include_router(media.router)
    dp.include_router(purchase.router)
    dp.include_router(qr.router)
    dp.include_router(report.router)
    dp.include_router(finance.router)
    dp.include_router(publish.router)
    dp.include_router(team.router)
    dp.include_router(fallback.router)
    dp.include_router(menu.router)

    dp["settings"] = settings
    dp["db"] = db
    dp["whisper"] = whisper
    dp["llm"] = llm

    log.info("bot.start", proxy=settings.telegram_proxy)
    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        await llm.close()
        await db.dispose()
        await bot.session.close()
        log.info("bot.stop")


if __name__ == "__main__":
    asyncio.run(main())
