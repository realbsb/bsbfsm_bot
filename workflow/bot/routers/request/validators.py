"""Проверка обязательных полей формы."""

from __future__ import annotations

from ....services.intake import FormDef


async def check_required(form: FormDef, raw_fields: dict) -> list[str]:
    """Возвращает список пустых обязательных полей (labels)."""
    missing: list[str] = []
    for lf in form.logical:
        if not lf.get("required"):
            continue
        value = raw_fields.get(lf["code"])
        if not value or not str(value).strip():
            missing.append(lf.get("label", lf["code"]))
    return missing
