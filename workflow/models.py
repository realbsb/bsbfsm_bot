"""ORM-модели"""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# ============================================================
# Хелпер для Enum
# ============================================================


def _enum(enum_cls, name: str) -> SAEnum:
    """Enum с использованием .value — совместимо с миграциями."""
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda e: [m.value for m in e],
    )


# ============================================================
# Enums
# ============================================================


class MediaType(str, enum.Enum):
    PHOTO = "photo"
    VIDEO = "video"
    VOICE = "voice"
    DOC = "doc"


class DocKind(str, enum.Enum):
    SKETCH = "sketch"
    PROJECT_PDF = "project_pdf"
    PROJECT_CSV = "project_csv"
    WARRANTY = "warranty"
    OTHER = "other"


class CalendarKind(str, enum.Enum):
    CALL = "call"
    MEETING = "meeting"
    WORK = "work"


class CalendarProvider(str, enum.Enum):
    RADICALE = "radicale"
    GOOGLE = "google"


class CalendarStatus(str, enum.Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    MOVED = "moved"


class IncidentKind(str, enum.Enum):
    REFUSE = "refuse"
    REPLACE = "replace"
    SLA_EXPIRED = "sla_expired"
    DEADLINE_MISSED = "deadline_missed"
    REASSIGNED = "reassigned"


class ExportKind(str, enum.Enum):
    ACCOUNTING = "accounting"
    SUPPLIER = "supplier"
    ONE_C = "1c"
    BOOK = "book"


class QrKind(str, enum.Enum):
    PURCHASE = "purchase"
    DELIVERY = "delivery"
    CLIENT_LK = "client_lk"
    PUBLIC_CARD = "public_card"


class PostTarget(str, enum.Enum):
    CHANNEL = "channel"
    PORTFOLIO = "portfolio"


class RequestFormKind(str, enum.Enum):
    CALLBACK = "callback"
    FULL = "full"


class IntakeFormType(str, enum.Enum):
    PUBLIC = "public"
    BOT = "bot"
    CLIENT_LK = "client_lk"
    CALLBACK = "callback"


class StageAssigneeState(str, enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    COMPLETED = "completed"


class GeoCheckinKind(str, enum.Enum):
    START = "start"
    END = "end"


# ============================================================
# Пользователи и роли
# ============================================================


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(32))
    locale: Mapped[str] = mapped_column(String(5), default="ru")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    map_provider: Mapped[str] = mapped_column(String(16), default="google")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    pd_consent_at: Mapped[datetime | None] = mapped_column(DateTime)
    pd_consent_version: Mapped[str | None] = mapped_column(String(16))
    geo_consent_at: Mapped[datetime | None] = mapped_column(DateTime)
    offer_accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    offer_version: Mapped[str | None] = mapped_column(String(16))


class Role(Base):
    __tablename__ = "role"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name_i18n_key: Mapped[str] = mapped_column(String(64))
    can_intake: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage_team: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage_org: Mapped[bool] = mapped_column(Boolean, default=False)


class Position(Base):
    __tablename__ = "position"
    __table_args__ = (UniqueConstraint("manager_id", "code", name="uq_position_manager_code"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    manager_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        index=True,
    )
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PositionRole(Base):
    __tablename__ = "position_role"
    __table_args__ = (UniqueConstraint("position_id", "role_id", name="uq_position_role"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(
        ForeignKey("position.id", ondelete="CASCADE"),
        index=True,
    )
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"))


class RoleAssignment(Base):
    __tablename__ = "role_assignment"
    __table_args__ = (
        UniqueConstraint("user_id", "position_id", "manager_id", name="uq_position_assign"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    position_id: Mapped[int] = mapped_column(
        ForeignKey("position.id", ondelete="CASCADE"),
        index=True,
    )
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RoleBoss(Base):
    __tablename__ = "role_boss"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"))
    boss_role_id: Mapped[int] = mapped_column(ForeignKey("role.id"))


# ============================================================
# Организация
# ============================================================


class OrgSettings(Base):
    __tablename__ = "org_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        unique=True,
    )

    use_range: Mapped[bool] = mapped_column(Boolean, default=True)
    workday_start: Mapped[str] = mapped_column(String(5), default="09:00")
    workday_end: Mapped[str] = mapped_column(String(5), default="18:00")
    workdays: Mapped[list[int]] = mapped_column(JSON, default=lambda: [1, 2, 3, 4, 5])
    sla_warn_hours: Mapped[list[int]] = mapped_column(JSON, default=lambda: [24, 2])
    geotracking_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    geotracking_points: Mapped[list[str]] = mapped_column(
        JSON,
        default=lambda: ["start", "end"],
    )
    radicale_default_url: Mapped[str | None] = mapped_column(String(256))
    phone: Mapped[str | None] = mapped_column(String(32))
    contact_telegram: Mapped[str | None] = mapped_column(String(64))
    contact_email: Mapped[str | None] = mapped_column(String(128))
    promo_channel_id: Mapped[int | None] = mapped_column(BigInteger)
    promo_channel_url: Mapped[str | None] = mapped_column(String(256))
    intake_label: Mapped[str | None] = mapped_column(String(64))
    tz: Mapped[str] = mapped_column(String(64), default="Asia/Yekaterinburg")
    locale: Mapped[str] = mapped_column(String(5), default="ru")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


class OrgDayOff(Base):
    __tablename__ = "org_day_off"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    manager_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        index=True,
    )
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ============================================================
# Стадии
# ============================================================


class StageTemplate(Base):
    __tablename__ = "stage_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name_i18n_key: Mapped[str] = mapped_column(String(64))
    order_idx: Mapped[int] = mapped_column(Integer)
    default_sla_hours: Mapped[int] = mapped_column(Integer, default=72)
    min_hours: Mapped[int] = mapped_column(Integer, default=48)
    max_hours: Mapped[int] = mapped_column(Integer, default=120)
    calc_required: Mapped[bool] = mapped_column(Boolean, default=False)
    media_required: Mapped[bool] = mapped_column(Boolean, default=False)
    client_meeting_required: Mapped[bool] = mapped_column(Boolean, default=False)


class Stage(Base):
    __tablename__ = "stage"
    __table_args__ = (UniqueConstraint("manager_id", "order_idx", name="uq_manager_order"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    order_idx: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(32))
    name_i18n_key: Mapped[str] = mapped_column(String(64))
    responsible_role_id: Mapped[int] = mapped_column(ForeignKey("role.id"))
    client_meeting_role_id: Mapped[int | None] = mapped_column(ForeignKey("role.id"), nullable=True)
    calc_required: Mapped[bool] = mapped_column(Boolean, default=False)
    media_required: Mapped[bool] = mapped_column(Boolean, default=False)
    default_sla_hours: Mapped[int] = mapped_column(Integer, default=72)
    min_hours: Mapped[int] = mapped_column(Integer, default=48)
    max_hours: Mapped[int] = mapped_column(Integer, default=120)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# ============================================================
# Проект
# ============================================================


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    stage_id: Mapped[int] = mapped_column(ForeignKey("stage.id"))
    current_assignee_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    secretary_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    executor_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    client_user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)

    client_name: Mapped[str | None] = mapped_column(String(128))
    client_phone: Mapped[str | None] = mapped_column(String(32))
    client_contact: Mapped[str | None] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    address_text: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lon: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    raw_fields_json: Mapped[dict | None] = mapped_column(JSON)

    price_internal: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    price_agreed: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    prepay_paid: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    final_paid: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    qr_purchase_token: Mapped[str | None] = mapped_column(String(64), index=True)
    qr_delivery_token: Mapped[str | None] = mapped_column(String(64), index=True)

    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    public_post_url: Mapped[str | None] = mapped_column(String(512))
    client_media_visible: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)
    archive_path: Mapped[str | None] = mapped_column(String(512))

    stage: Mapped[Stage] = relationship(lazy="joined")


class ProjectStageAssignee(Base):
    __tablename__ = "project_stage_assignee"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"),
        index=True,
    )
    stage_id: Mapped[int] = mapped_column(ForeignKey("stage.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)

    active_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[StageAssigneeState] = mapped_column(
        _enum(StageAssigneeState, "stageassigneestate"),
        default=StageAssigneeState.ACTIVE,
    )

    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoke_reason: Mapped[str | None] = mapped_column(String(32))

    planned_hours: Mapped[int] = mapped_column(Integer)
    deadline_at: Mapped[datetime] = mapped_column(DateTime)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    reassignment_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    reassignment_reason: Mapped[str | None] = mapped_column(String(32))
    warned_1_at: Mapped[datetime | None] = mapped_column(DateTime)
    warned_2_at: Mapped[datetime | None] = mapped_column(DateTime)

    explanation_text: Mapped[str | None] = mapped_column(Text)
    progress_percent: Mapped[int | None] = mapped_column(Integer)


class ProjectSchedule(Base):
    __tablename__ = "project_schedule"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime)
    min_finish_at: Mapped[datetime] = mapped_column(DateTime)
    max_finish_at: Mapped[datetime] = mapped_column(DateTime)
    recalculated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProjectStageLog(Base):
    __tablename__ = "project_stage_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    stage_id: Mapped[int] = mapped_column(ForeignKey("stage.id"))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    action: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ProjectRoleSnapshot(Base):
    __tablename__ = "project_role_snapshot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)


class Incident(Base):
    __tablename__ = "incident"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[IncidentKind] = mapped_column(_enum(IncidentKind, "incidentkind"))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    reason_text: Mapped[str | None] = mapped_column(Text)
    reason_voice_file_id: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ============================================================
# События / медиа / документы
# ============================================================


class ProjectEvent(Base):
    __tablename__ = "project_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    stage_id: Mapped[int | None] = mapped_column(ForeignKey("stage.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MediaAsset(Base):
    __tablename__ = "media_asset"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    stage_id: Mapped[int | None] = mapped_column(ForeignKey("stage.id"), nullable=True)
    stage_assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_stage_assignee.id", ondelete="SET NULL"),
        nullable=True,
    )
    type: Mapped[MediaType] = mapped_column(_enum(MediaType, "mediatype"))
    tg_file_id: Mapped[str] = mapped_column(String(256))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    transcript: Mapped[str | None] = mapped_column(Text)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    is_daily_report: Mapped[bool] = mapped_column(Boolean, default=False)
    visible_to_client: Mapped[bool] = mapped_column(Boolean, default=False)
    progress_percent: Mapped[int | None] = mapped_column(Integer)
    too_big: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Document(Base):
    __tablename__ = "document"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[DocKind] = mapped_column(_enum(DocKind, "dockind"))
    tg_file_id: Mapped[str] = mapped_column(String(256))
    filename: Mapped[str | None] = mapped_column(String(256))
    parsed_json: Mapped[dict | None] = mapped_column(JSON)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DocumentItem(Base):
    __tablename__ = "document_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    common_name: Mapped[str] = mapped_column(String(256))
    characteristics: Mapped[str | None] = mapped_column(Text)
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit: Mapped[str] = mapped_column(String(16), default="шт")
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    raw_line: Mapped[str | None] = mapped_column(Text)


# ============================================================
# Закуп
# ============================================================


class Shop(Base):
    __tablename__ = "shop"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    address: Mapped[str | None] = mapped_column(Text)
    contacts: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class Purchase(Base):
    __tablename__ = "purchase"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shop.id"))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    purchased_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))


class PurchaseItem(Base):
    __tablename__ = "purchase_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("purchase.id", ondelete="CASCADE"), index=True
    )
    common_name: Mapped[str] = mapped_column(String(256), index=True)
    characteristics: Mapped[str | None] = mapped_column(Text)
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit: Mapped[str] = mapped_column(String(16), default="шт")
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    warranty_until: Mapped[date | None] = mapped_column(Date)
    warranty_doc_id: Mapped[int | None] = mapped_column(ForeignKey("document.id"))


# ============================================================
# Календарь
# ============================================================


class CalendarEvent(Base):
    __tablename__ = "calendar_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_uid: Mapped[str] = mapped_column(String(64), index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[CalendarKind] = mapped_column(_enum(CalendarKind, "calendarkind"))
    initiator_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    provider: Mapped[CalendarProvider] = mapped_column(_enum(CalendarProvider, "calendarprovider"))
    external_uid: Mapped[str | None] = mapped_column(String(256))
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[CalendarStatus] = mapped_column(
        _enum(CalendarStatus, "calendarstatus"),
        default=CalendarStatus.PROPOSED,
    )


class UserCalendarPref(Base):
    __tablename__ = "user_calendar_pref"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), unique=True)
    meetings_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    work_plan_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    radicale_url: Mapped[str | None] = mapped_column(String(256))
    radicale_username: Mapped[str | None] = mapped_column(String(64))
    radicale_password: Mapped[str | None] = mapped_column(String(256))


# ============================================================
# Гео-отметки
# ============================================================


class GeoCheckin(Base):
    __tablename__ = "geo_checkin"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    kind: Mapped[GeoCheckinKind] = mapped_column(_enum(GeoCheckinKind, "geocheckinkind"))
    lat: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    lon: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    accuracy_m: Mapped[int | None] = mapped_column(Integer)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ============================================================
# Публикации / экспорт / QR / аудит
# ============================================================


class PublicPost(Base):
    __tablename__ = "public_post"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    target: Mapped[PostTarget] = mapped_column(_enum(PostTarget, "posttarget"))
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    url: Mapped[str | None] = mapped_column(String(512))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FinanceExport(Base):
    __tablename__ = "finance_export"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ExportKind] = mapped_column(_enum(ExportKind, "exportkind"))
    file_path: Mapped[str] = mapped_column(String(512))
    payload_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class QrToken(Base):
    __tablename__ = "qr_token"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[QrKind] = mapped_column(_enum(QrKind, "qrkind"))
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    payload_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ============================================================
# Публичные формы и приём
# ============================================================


class RequestForm(Base):
    __tablename__ = "request_form"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(128))
    kind: Mapped[RequestFormKind] = mapped_column(_enum(RequestFormKind, "requestformkind"))
    fields_json: Mapped[dict] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class IntakeForm(Base):
    __tablename__ = "intake_form"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    manager_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(32))
    title_i18n_key: Mapped[str] = mapped_column(String(64))
    fields_json: Mapped[dict] = mapped_column(JSON)
    creates_stage_code: Mapped[str | None] = mapped_column(String(32))
    allowed_role_codes: Mapped[list[str]] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class IntakeEntry(Base):
    __tablename__ = "intake_entry"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    form_id: Mapped[int | None] = mapped_column(ForeignKey("intake_form.id"))
    manager_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    form_type: Mapped[IntakeFormType] = mapped_column(
        _enum(IntakeFormType, "intakeformtype"),
        default=IntakeFormType.BOT,
    )
    contact_method: Mapped[str | None] = mapped_column(String(16))
    submitted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    submitted_by_tg_id: Mapped[int | None] = mapped_column(BigInteger)
    payload_json: Mapped[dict] = mapped_column(JSON)
    summary_text: Mapped[str] = mapped_column(Text)
    source_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    processed_project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"))
