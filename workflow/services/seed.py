"""Seed ролей, шаблонов стадий, дефолтной организации, формы приёма, должностей."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..logging_setup import get_logger
from ..models import (
    IntakeForm,
    OrgSettings,
    Position,
    PositionRole,
    Role,
    RoleAssignment,
    Stage,
    StageTemplate,
    User,
)

log = get_logger(__name__)


# code, i18n, order, role, min_h, max_h, sla_h, calc, media, client_meeting
STAGE_TEMPLATES = [
    ("request", "stages.request", 1, "secretary", 8, 24, 24, False, False, False),
    ("planning", "stages.planning", 2, "secretary", 24, 72, 48, False, False, False),
    ("negotiation", "stages.negotiation", 3, "manager", 24, 120, 72, True, False, True),
    ("purchase", "stages.purchase", 4, "supplier", 24, 120, 72, False, False, False),
    ("preparation", "stages.preparation", 5, "supplier", 24, 168, 72, False, True, False),
    ("realization", "stages.realization", 6, "executor", 48, 336, 168, False, True, True),
    ("ready", "stages.ready", 7, "executor", 8, 72, 48, False, True, False),
    ("delivered", "stages.delivered", 8, "manager", 8, 48, 24, True, False, True),
]


ROLES = [
    # code, i18n, can_intake, can_manage_team, can_manage_org
    ("manager", "roles.manager", True, True, True),
    ("secretary", "roles.secretary", True, False, False),
    ("supplier", "roles.supplier", False, False, False),
    ("executor", "roles.executor", False, False, False),
    # Технические роли-флаги
    ("intake", "roles.intake", False, False, False),
    ("supply", "roles.supply", False, False, False),
    ("execute", "roles.execute", False, False, False),
    ("plan", "roles.plan", False, False, False),
    ("calc", "roles.calc", False, False, False),
    ("media", "roles.media", False, False, False),
    ("client_meeting", "roles.client_meeting", False, False, False),
    ("manage_team", "roles.manage_team", False, False, False),
    ("manage_org", "roles.manage_org", False, False, False),
    ("close", "roles.close", False, False, False),
]


DEFAULT_POSITIONS = [
    # code, name, flags (коды ролей)
    ("manager", "Менеджер", ["manager", "manage_team", "manage_org", "intake"]),
    ("secretary", "Секретарь", ["intake"]),
    ("supplier", "Снабженец", ["supply"]),
    ("executor", "Исполнитель", ["execute"]),
]


DEFAULT_INTAKE_FIELDS = {
    "fields": [
        {"code": "name", "type": "text", "required": True, "i18n": "intake.field.name"},
        {"code": "phone", "type": "phone", "required": True, "i18n": "intake.field.phone"},
        {"code": "wish", "type": "text", "required": False, "i18n": "intake.field.wish"},
    ]
}

DEFAULT_INTAKE_ALLOWED_ROLES = ["manager", "secretary"]


# ============================================================
# Роли
# ============================================================


async def seed_roles(session: AsyncSession) -> dict[str, Role]:
    out: dict[str, Role] = {}
    for code, key, can_intake, can_team, can_org in ROLES:
        role = (await session.execute(select(Role).where(Role.code == code))).scalars().first()
        if role is None:
            role = Role(
                code=code,
                name_i18n_key=key,
                can_intake=can_intake,
                can_manage_team=can_team,
                can_manage_org=can_org,
            )
            session.add(role)
            await session.flush()
            log.info("seed.role.created", code=code)
        else:
            role.name_i18n_key = key
            role.can_intake = can_intake
            role.can_manage_team = can_team
            role.can_manage_org = can_org
        out[code] = role
    return out


# ============================================================
# Шаблоны стадий
# ============================================================


async def seed_stage_templates(session: AsyncSession) -> None:
    for code, key, order, role_code, min_h, max_h, sla, calc, media, cm in STAGE_TEMPLATES:
        tpl = (
            (await session.execute(select(StageTemplate).where(StageTemplate.code == code)))
            .scalars()
            .first()
        )
        if tpl is None:
            session.add(
                StageTemplate(
                    code=code,
                    name_i18n_key=key,
                    order_idx=order,
                    default_sla_hours=sla,
                    min_hours=min_h,
                    max_hours=max_h,
                    calc_required=calc,
                    media_required=media,
                    client_meeting_required=cm,
                )
            )
            log.info("seed.stage_template.created", code=code)
        else:
            tpl.min_hours = min_h
            tpl.max_hours = max_h
            tpl.default_sla_hours = sla
            tpl.calc_required = calc
            tpl.media_required = media
            tpl.client_meeting_required = cm


# ============================================================
# Стадии менеджера
# ============================================================


async def seed_manager_stages(
    session: AsyncSession,
    manager: User,
    roles: dict[str, Role],
) -> None:
    existing = (
        (await session.execute(select(Stage).where(Stage.manager_id == manager.id).limit(1)))
        .scalars()
        .first()
    )
    if existing:
        return

    for code, key, order, role_code, min_h, max_h, sla, calc, media, cm in STAGE_TEMPLATES:
        role = roles.get(role_code)
        cm_role = roles.get("manager") if cm else None
        if role is None:
            log.warning("seed.skip_stage", code=code, reason="role missing")
            continue
        session.add(
            Stage(
                manager_id=manager.id,
                order_idx=order,
                code=code,
                name_i18n_key=key,
                responsible_role_id=role.id,
                client_meeting_role_id=cm_role.id if cm_role else None,
                calc_required=calc,
                media_required=media,
                default_sla_hours=sla,
                min_hours=min_h,
                max_hours=max_h,
                is_active=True,
            )
        )
    await session.flush()
    log.info("seed.manager_stages.created", manager=manager.id)


# ============================================================
# Организация
# ============================================================


async def seed_org_settings(session: AsyncSession, manager: User) -> OrgSettings:
    existing = (
        (await session.execute(select(OrgSettings).where(OrgSettings.owner_id == manager.id)))
        .scalars()
        .first()
    )
    if existing:
        return existing

    org = OrgSettings(
        owner_id=manager.id,
        use_range=True,
        workday_start="09:00",
        workday_end="18:00",
        workdays=[1, 2, 3, 4, 5],
        sla_warn_hours=[24, 2],
        geotracking_enabled=False,
        geotracking_points=["start", "end"],
        tz="Asia/Yekaterinburg",
        locale=manager.locale or "ru",
    )
    session.add(org)
    await session.flush()
    log.info("seed.org_settings.created", manager=manager.id)
    return org


# ============================================================
# Форма приёма
# ============================================================


async def seed_intake_form(session: AsyncSession, manager: User) -> IntakeForm:
    existing = (
        (
            await session.execute(
                select(IntakeForm).where(
                    IntakeForm.manager_id == manager.id,
                    IntakeForm.code == "lead",
                )
            )
        )
        .scalars()
        .first()
    )
    if existing:
        return existing

    form = IntakeForm(
        manager_id=manager.id,
        code="lead",
        title_i18n_key="intake.lead.title",
        fields_json=DEFAULT_INTAKE_FIELDS,
        creates_stage_code="request",
        allowed_role_codes=DEFAULT_INTAKE_ALLOWED_ROLES,
        is_active=True,
    )
    session.add(form)
    await session.flush()
    log.info("seed.intake_form.created", manager=manager.id, code="lead")
    return form


# ============================================================
# Дефолтные должности
# ============================================================


async def seed_default_positions(session: AsyncSession, manager: User) -> None:
    roles = {r.code: r for r in (await session.execute(select(Role))).scalars().all()}

    for code, name, flags in DEFAULT_POSITIONS:
        existing = (
            (
                await session.execute(
                    select(Position).where(
                        Position.manager_id == manager.id,
                        Position.code == code,
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing:
            continue

        pos = Position(
            manager_id=manager.id,
            code=code,
            name=name,
            is_active=True,
        )
        session.add(pos)
        await session.flush()

        for flag in flags:
            role = roles.get(flag)
            if role is None:
                log.warning("seed.position.role_missing", flag=flag)
                continue
            session.add(PositionRole(position_id=pos.id, role_id=role.id))

    await session.flush()
    log.info("seed.positions.created", manager=manager.id)


# ============================================================
# Самоприсвоение менеджера
# ============================================================


async def _self_assign_manager(session: AsyncSession, manager: User) -> None:
    """Менеджер по умолчанию — исполнитель всех ролей в своей организации."""
    for pos_code in ("secretary", "supplier", "executor"):
        pos = (
            (
                await session.execute(
                    select(Position).where(
                        Position.manager_id == manager.id,
                        Position.code == pos_code,
                    )
                )
            )
            .scalars()
            .first()
        )
        if pos is None:
            continue
        exists = (
            (
                await session.execute(
                    select(RoleAssignment).where(
                        RoleAssignment.user_id == manager.id,
                        RoleAssignment.position_id == pos.id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if exists:
            continue
        session.add(
            RoleAssignment(
                user_id=manager.id,
                position_id=pos.id,
                manager_id=manager.id,
                assigned_by=manager.id,
                is_active=True,
            )
        )
        log.info("seed.self_assigned", manager=manager.id, position=pos_code)
    await session.flush()


# ============================================================
# Полный seed
# ============================================================


async def run_seed(session: AsyncSession) -> None:
    roles = await seed_roles(session)
    await seed_stage_templates(session)
    await session.commit()
    log.info("seed.done", roles=list(roles.keys()))


async def seed_new_manager(session: AsyncSession, manager: User) -> None:
    roles = {r.code: r for r in (await session.execute(select(Role))).scalars().all()}
    await seed_manager_stages(session, manager, roles)
    await seed_org_settings(session, manager)
    await seed_intake_form(session, manager)
    await seed_default_positions(session, manager)
    await _self_assign_manager(session, manager)
    await session.commit()
    log.info("seed.new_manager.done", manager=manager.id)
