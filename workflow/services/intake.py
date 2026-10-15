"""Сервис форм приёма.

- Дефолтный шаблон, если у менеджера нет IntakeForm.
- Сборка логических полей из физических.
- Раскладка строки в физические (для парсера).
- Применение к Project.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..logging_setup import get_logger
from ..models import IntakeForm, Project

log = get_logger(__name__)


# ============================================================
# Дефолтный шаблон
# ============================================================

DEFAULT_PHYSICAL: list[dict] = [
    {"code": "client", "label": "Заказчик", "type": "text", "required": True},
    {"code": "contact", "label": "Контакт", "type": "text", "required": True},
    {"code": "object", "label": "Объект", "type": "text", "required": True},
    {"code": "address", "label": "Адрес", "type": "text", "required": False},
    {"code": "description", "label": "Описание", "type": "text", "required": False},
]

DEFAULT_LOGICAL: list[dict] = [
    {
        "code": "client",
        "label": "Заказчик",
        "template": "{value}",
        "sources": ["client"],
        "required": True,
    },
    {
        "code": "contact",
        "label": "Контакт",
        "template": "{value}",
        "sources": ["contact"],
        "required": True,
    },
    {
        "code": "object",
        "label": "Объект",
        "template": "{value}",
        "sources": ["object"],
        "required": True,
    },
    {
        "code": "address",
        "label": "Адрес",
        "template": "{value}",
        "sources": ["address"],
        "required": False,
    },
    {
        "code": "description",
        "label": "Описание",
        "template": "{value}",
        "sources": ["description"],
        "required": False,
    },
]


class FormDef:
    """Разобранное определение формы."""

    def __init__(self, physical: list[dict], logical: list[dict]) -> None:
        self.physical = physical
        self.logical = logical

    def physical_by_code(self, code: str) -> dict | None:
        for f in self.physical:
            if f["code"] == code:
                return f
        return None

    def logical_by_code(self, code: str) -> dict | None:
        for f in self.logical:
            if f["code"] == code:
                return f
        return None

    def logical_labels(self) -> dict[str, str]:
        return {f["code"]: f.get("label", f["code"]) for f in self.logical}


def _default_form() -> FormDef:
    return FormDef(physical=list(DEFAULT_PHYSICAL), logical=list(DEFAULT_LOGICAL))


async def get_form(session: AsyncSession, manager_id: int) -> FormDef:
    form = (
        (
            await session.execute(
                select(IntakeForm)
                .where(
                    IntakeForm.manager_id == manager_id,
                    IntakeForm.is_active.is_(True),
                )
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if form is None:
        return _default_form()

    fields = form.fields_json or {}
    physical = fields.get("fields") or DEFAULT_PHYSICAL
    logical = fields.get("logical") or DEFAULT_LOGICAL
    return FormDef(physical=list(physical), logical=list(logical))


# ============================================================
# Сборка логических полей
# ============================================================

_TEMPLATE_RE = re.compile(r"\{(\w+)\}")


def render_logical(logical: dict, raw_fields: dict) -> str | None:
    """Собирает логическое значение из raw_fields по шаблону."""
    template = logical.get("template", "{value}")
    sources = logical.get("sources", [])

    def repl(m):
        key = m.group(1)
        if key == "value" and sources:
            # Значение = первое физическое поле
            return str(raw_fields.get(sources[0], "") or "")
        return str(raw_fields.get(key, "") or "")

    value = _TEMPLATE_RE.sub(repl, template)
    value = re.sub(r"\s+", " ", value).strip(" ,;")
    return value or None


def render_all_logical(form: FormDef, raw_fields: dict) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for lf in form.logical:
        out[lf["code"]] = render_logical(lf, raw_fields)
    return out


# ============================================================
# Раскладка (для парсера)
# ============================================================


def split_logical(logical: dict, value: str) -> dict[str, str]:
    """Раскладывает строку в физические поля по шаблону.

    Простая эвристика: разбиваем по пробелам/запятым.
    Если sources = 1 — кладём всё в первое поле.
    Если sources > 1 — делим на столько частей, сколько мест в шаблоне.
    """
    sources = logical.get("sources", [])
    value = (value or "").strip()
    if not sources:
        return {}
    if len(sources) == 1:
        return {sources[0]: value}

    # Разбиваем по пробелам (сохраняем как можно больше в первое поле)
    parts = value.split()
    if len(parts) <= len(sources):
        # Раскладываем по одному
        out = {}
        for i, code in enumerate(sources):
            out[code] = parts[i] if i < len(parts) else ""
        return out

    # Частей больше, чем sources — всё лишнее в первое
    extra = " ".join(parts[: len(parts) - len(sources) + 1])
    out = {sources[0]: extra}
    for i, code in enumerate(sources[1:], start=1):
        out[code] = parts[len(parts) - len(sources) + i]
    return out


# ============================================================
# Применение к Project
# ============================================================


async def apply_to_project(
    session: AsyncSession,
    project: Project,
    form: FormDef,
    raw_fields: dict,
) -> None:
    """Заполняет поля Project по логическим."""
    logical = render_all_logical(form, raw_fields)

    project.client_name = logical.get("client") or project.client_name
    project.client_contact = logical.get("contact") or project.client_contact

    # Если contact — похоже на телефон, дублируем в legacy-поле
    contact = logical.get("contact") or ""
    digits = re.sub(r"\D", "", contact)
    if 10 <= len(digits) <= 15:
        project.client_phone = contact

    project.address_text = logical.get("address") or project.address_text

    # Описание = object + description
    parts = []
    if logical.get("object"):
        parts.append(logical["object"])
    if logical.get("description"):
        parts.append(logical["description"])
    if parts:
        project.description = "\n".join(parts)

    project.raw_fields_json = raw_fields
    await session.flush()
