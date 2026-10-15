"""Токены-приглашения для заказчика."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..logging_setup import get_logger
from ..models import Project, QrKind, QrToken

log = get_logger(__name__)


def make_token() -> str:
    return secrets.token_urlsafe(24)


async def create_client_invite(
    session: AsyncSession,
    project: Project,
    ttl_days: int = 14,
) -> str:
    token = make_token()
    session.add(
        QrToken(
            project_id=project.id,
            kind=QrKind.CLIENT_LK,
            token=token,
            expires_at=datetime.utcnow() + timedelta(days=ttl_days),
        )
    )
    await session.flush()
    log.info("invite.created", project=project.id, ttl_days=ttl_days)
    return token


async def verify_token(session: AsyncSession, token: str) -> Project | None:
    qr = (await session.execute(select(QrToken).where(QrToken.token == token))).scalars().first()
    if qr is None:
        return None
    if qr.expires_at and qr.expires_at < datetime.utcnow():
        log.info("invite.expired", token=token[:8])
        return None
    qr.used_at = datetime.utcnow()
    await session.flush()
    return await session.get(Project, qr.project_id)


def build_invite_text(settings: Settings, bot_username: str, token: str) -> str:
    link = f"https://t.me/{bot_username}?start=client_{token}"
    return (
        "Спасибо за обращение! Ваша заявка принята. "
        f"Для вас создан личный кабинет в нашем боте: {link}"
    )
