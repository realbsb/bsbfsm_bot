"""Нормализация чисел, булевых и кодировок."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_NBSP = "\u00a0\u202f\u2009"
_NUM_RE = re.compile(r"[^\d,.\-]")
_BOOL_TRUE = {"x", "true", "1", "да", "yes", "y", "+", "✓"}


def clean_number(s: str | None) -> Decimal | None:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    for ch in _NBSP:
        s = s.replace(ch, "")
    s = s.replace(" ", "")
    s = _NUM_RE.sub("", s)
    if not s:
        return None
    s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def clean_bool(s: str | None) -> bool:
    if s is None:
        return True
    return s.strip().lower() in _BOOL_TRUE


def decode_bytes(raw: bytes) -> tuple[str, str]:
    for enc in ("utf-8-sig", "utf-8", "cp866", "cp1251"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("cp866", errors="replace"), "cp866(replace)"
