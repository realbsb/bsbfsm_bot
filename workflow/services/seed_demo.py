"""Демо-данные. Только для APP_ENV=development.

Использование:
    workflow-seed-demo
    python -m workflow.services.seed_demo
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import select

from ..config import get_settings
from ..db import Database
from ..logging_setup import get_logger, setup_logging
from ..models import (
    DocKind,
    Document,
    DocumentItem,
    MediaAsset,
    MediaType,
    Project,
    Role,
    RoleAssignment,
    Stage,
    User,
)
from .seed import run_seed, seed_manager_stages

log = get_logger(__name__)


async def _get_or_create_user(session, tg_id: int, name: str, username: str) -> User:
    user = (await session.execute(select(User).where(User.tg_id == tg_id))).scalars().first()
    if user is None:
        user = User(tg_id=tg_id, first_name=name, username=username)
        session.add(user)
        await session.flush()
    return user


async def _seed_demo(session) -> None:
    settings = get_settings()
    if settings.app_env != "development":
        log.error("seed_demo.not_dev", env=settings.app_env)
        return

    await run_seed(session)
    roles = {r.code: r for r in (await session.execute(select(Role))).scalars().all()}

    manager = await _get_or_create_user(session, 100000001, "Менеджер Демо", "demo_manager")
    secretary = await _get_or_create_user(session, 100000002, "Секретарь Демо", "demo_secretary")
    supplier = await _get_or_create_user(session, 100000003, "Снабженец Демо", "demo_supplier")
    executor = await _get_or_create_user(session, 100000004, "Исполнитель Демо", "demo_executor")
    client = await _get_or_create_user(session, 100000005, "Заказчик Демо", "demo_client")

    session.add_all(
        [
            RoleAssignment(
                user_id=manager.id,
                role_id=roles["manager"].id,
            ),
            RoleAssignment(
                user_id=secretary.id,
                role_id=roles["secretary"].id,
                manager_id=manager.id,
            ),
            RoleAssignment(
                user_id=supplier.id,
                role_id=roles["supplier"].id,
                manager_id=manager.id,
            ),
            RoleAssignment(
                user_id=executor.id,
                role_id=roles["executor"].id,
                manager_id=manager.id,
            ),
        ]
    )
    await session.flush()

    await seed_manager_stages(session, manager, roles)

    first_stage = (
        (
            await session.execute(
                select(Stage)
                .where(Stage.manager_id == manager.id)
                .order_by(Stage.order_idx)
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    assert first_stage is not None

    project = Project(
        manager_id=manager.id,
        stage_id=first_stage.id,
        current_assignee_id=secretary.id,
        secretary_id=secretary.id,
        supplier_id=supplier.id,
        executor_id=executor.id,
        client_user_id=client.id,
        client_name="Иван Иванов",
        client_phone="+79001234567",
        description="Демо-проект: отделка бани 6×4",
        address_text="Москва, ул. Демо, 1",
        lat=Decimal("55.751244"),
        lon=Decimal("37.618423"),
        price_internal=Decimal("180000.00"),
        price_agreed=Decimal("250000.00"),
        prepay_paid=Decimal("100000.00"),
    )
    session.add(project)
    await session.flush()

    doc = Document(
        project_id=project.id,
        kind=DocKind.PROJECT_CSV,
        tg_file_id="demo-file-id",
        filename="Баня7.csv",
        uploaded_by=manager.id,
    )
    session.add(doc)
    await session.flush()

    for name, w, d, h, qty in [
        ("Печь", 400, 630, 1256, 1),
        ("Входная дверь", 1015, 230, 2000, 1),
        ("Дверь, открытая", 915, 680, 2000, 2),
        ("Цилиндр", 310, 320, 710, 1),
        ("Ящик", 620, 1600, 50, 1),
        ("Бочка", 510, 500, 410, 1),
        ("Кресло-каталка", 680, 1080, 910, 1),
    ]:
        session.add(
            DocumentItem(
                document_id=doc.id,
                common_name=name,
                characteristics=f"{w}×{d}×{h}",
                qty=Decimal(str(qty)),
                unit="шт",
            )
        )

    session.add(
        MediaAsset(
            project_id=project.id,
            type=MediaType.PHOTO,
            tg_file_id="demo-photo-1",
            uploaded_by=executor.id,
            is_final=True,
        )
    )

    await session.commit()
    log.info("seed_demo.done", project=project.id, manager=manager.id)


async def _async_main() -> None:
    settings = get_settings()
    setup_logging(settings)
    db = Database(settings)
    db.init()

    async with db.session() as session:
        await _seed_demo(session)

    await db.dispose()
    log.info("seed_demo.done")


def main() -> None:
    """Синхронная точка входа для entry point."""
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
