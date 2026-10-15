"""CLI для seed и ручного приглашения.

Использование:
    python -m workflow.services.seed_cli
    python -m workflow.services.seed_cli invite <manager_tg_id> <user_tg_id> <position_code>
    python -m workflow.services.seed_cli show
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from ..config import get_settings
from ..db import Database
from ..logging_setup import get_logger, setup_logging
from ..models import Position, RoleAssignment, User
from .seed import run_seed

log = get_logger(__name__)


async def _run_seed() -> None:
    settings = get_settings()
    setup_logging(settings)
    db = Database(settings)
    db.init()
    async with db.session() as session:
        await run_seed(session)
    await db.dispose()
    log.info("seed_cli.done")


async def _invite(manager_tg_id: int, user_tg_id: int, position_code: str) -> None:
    settings = get_settings()
    setup_logging(settings)
    db = Database(settings)
    db.init()

    async with db.session() as session:
        manager = (
            (await session.execute(select(User).where(User.tg_id == manager_tg_id)))
            .scalars()
            .first()
        )
        if manager is None:
            print(f"ERROR: manager tg_id={manager_tg_id} не найден")
            await db.dispose()
            return

        user = (
            (await session.execute(select(User).where(User.tg_id == user_tg_id))).scalars().first()
        )
        if user is None:
            user = User(tg_id=user_tg_id, first_name="Invited", locale="ru")
            session.add(user)
            await session.flush()
            print(f"USER created: id={user.id} tg_id={user_tg_id}")

        position = (
            (
                await session.execute(
                    select(Position).where(
                        Position.manager_id == manager.id,
                        Position.code == position_code,
                    )
                )
            )
            .scalars()
            .first()
        )
        if position is None:
            print(f"ERROR: position '{position_code}' не найдена у manager={manager.id}")
            await db.dispose()
            return

        existing = (
            (
                await session.execute(
                    select(RoleAssignment).where(
                        RoleAssignment.user_id == user.id,
                        RoleAssignment.position_id == position.id,
                        RoleAssignment.manager_id == manager.id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing:
            existing.is_active = True
            print(f"EXISTS: user={user.id} уже в position={position.id}, обновлён на active=True")
        else:
            session.add(
                RoleAssignment(
                    user_id=user.id,
                    position_id=position.id,
                    manager_id=manager.id,
                    assigned_by=manager.id,
                    is_active=True,
                )
            )
            print(f"OK: user={user.id} добавлен в position={position.id} ({position.name})")

        # Снимаем менеджера с этой должности, если он сам её занимал
        # и если новый пользователь — не сам менеджер
        if user.id != manager.id:
            mgr_ra = (
                (
                    await session.execute(
                        select(RoleAssignment).where(
                            RoleAssignment.user_id == manager.id,
                            RoleAssignment.position_id == position.id,
                            RoleAssignment.is_active.is_(True),
                        )
                    )
                )
                .scalars()
                .first()
            )
            if mgr_ra is not None:
                mgr_ra.is_active = False
                print(
                    f"SELF-UNASSIGN: менеджер {manager.id} снят с position={position.id} ({position.name})"
                )

        await session.commit()

    await db.dispose()


async def _show() -> None:
    settings = get_settings()
    setup_logging(settings)
    db = Database(settings)
    db.init()

    async with db.session() as session:
        print("=== USERS ===")
        for u in (await session.execute(select(User))).scalars().all():
            print(f"  id={u.id} tg_id={u.tg_id} name={u.first_name} username={u.username}")

        print("=== POSITIONS ===")
        for p in (await session.execute(select(Position))).scalars().all():
            print(
                f"  id={p.id} manager={p.manager_id} code={p.code} name={p.name} active={p.is_active}"
            )

        print("=== ROLE ASSIGNMENTS ===")
        for ra in (await session.execute(select(RoleAssignment))).scalars().all():
            print(
                f"  user={ra.user_id} position={ra.position_id} manager={ra.manager_id} active={ra.is_active}"
            )

    await db.dispose()


def main() -> None:
    args = sys.argv[1:]
    if not args:
        asyncio.run(_run_seed())
        return
    cmd = args[0]
    if cmd == "invite" and len(args) == 4:
        try:
            manager_tg_id = int(args[1])
            user_tg_id = int(args[2])
        except ValueError:
            print("tg_id должны быть числами", file=sys.stderr)
            sys.exit(2)
        position_code = args[3]
        asyncio.run(_invite(manager_tg_id, user_tg_id, position_code))
        return
    if cmd == "show":
        asyncio.run(_show())
        return
    print(__doc__)
    sys.exit(1)


if __name__ == "__main__":
    main()
