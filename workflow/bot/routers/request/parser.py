"""Парсер свободного текста заявки.

- Маркеры ищутся через \b (граница слова), в любом месте текста.
- Контакт (телефон/email/username/url) ищется паттерном СРАЗУ и вырезается из текста.
- Нормализация: склеиваем числа через разделители, только если результат 10–15 цифр.
- Без fuzzy-совпадений: если маркер не произнесён чётко — поле не найдено.
"""

from __future__ import annotations

import re

from ....logging_setup import get_logger

log = get_logger(__name__)


MARKERS: dict[str, list[str]] = {
    "client": ["заказчик", "клиент", "имя", "фио", "name", "client"],
    "contact": [
        "телефон",
        "тел",
        "мобильный",
        "сотовый",
        "номер",
        "контакт",
        "phone",
        "contact",
        "telegram",
        "телеграм",
        "whatsapp",
        "ватсап",
        "email",
        "почта",
        "mail",
    ],
    "object": ["объект", "object", "что", "задача", "услуга"],
    "address": ["адрес", "address"],
    "description": ["описание", "детали", "подробности", "пожелания", "description", "wish"],
}


PHONE_RE = re.compile(r"(\+?\d[\d\s\-\(\)]{8,}\d)")
EMAIL_RE = re.compile(r"\b[\w\.\-]+@[\w\.\-]+\.\w+\b")
USERNAME_RE = re.compile(r"@[A-Za-z0-9_]{4,}")
URL_CONTACT_RE = re.compile(r"(?:t\.me|wa\.me|viber\.me)/[\w\.\-]+", re.IGNORECASE)


def _build_marker_regex() -> tuple[re.Pattern, list[tuple[str, str]]]:
    all_markers: list[tuple[str, str]] = []
    for code, marks in MARKERS.items():
        for m in marks:
            all_markers.append((m, code))
    all_markers.sort(key=lambda x: -len(x[0]))
    pattern = "|".join(re.escape(m) for m, _ in all_markers)
    rx = re.compile(
        r"\b(" + pattern + r")\b\s*[:\-—]?\s*",
        re.IGNORECASE,
    )
    lookup = [(m.lower(), c) for m, c in all_markers]
    lookup.sort(key=lambda x: -len(x[0]))
    return rx, lookup


_MARKER_RE, _MARKER_LOOKUP = _build_marker_regex()


def normalize_text(text: str) -> str:
    """Склеивает группы цифр через разделители, ТОЛЬКО если результат 10–15 цифр."""
    text = text or ""

    def repl(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if 10 <= len(digits) <= 15:
            return digits
        return m.group(0)

    seq_re = re.compile(r"\d(?:[\s,\.\-]*\d){9,}")
    return seq_re.sub(repl, text)


def _find_contact_pattern(text: str) -> str | None:
    """Ищет контакт в тексте (телефон/email/username/url)."""
    for rx in (EMAIL_RE, PHONE_RE, URL_CONTACT_RE, USERNAME_RE):
        m = rx.search(text)
        if m:
            return m.group(0).strip()
    return None


def parse_by_markers(text: str) -> dict[str, str]:
    raw = (text or "").strip()
    log.info("request.parse.before_normalize", text=raw[:500])
    normalized = normalize_text(raw)
    log.info("request.parse.after_normalize", text=normalized[:500])

    out: dict[str, str] = {}

    # 1. Контакт — сразу, и вырезаем из текста
    contact_pattern = _find_contact_pattern(normalized)
    if contact_pattern:
        out["contact"] = contact_pattern
        normalized = normalized.replace(contact_pattern, " ")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        log.info(
            "request.parse.contact_extracted", contact=contact_pattern, text_after=normalized[:300]
        )

    # 2. Маркеры
    matches = list(_MARKER_RE.finditer(normalized))
    for i, m in enumerate(matches):
        marker_text = m.group(1).lower()
        code = None
        for mc, c in _MARKER_LOOKUP:
            if mc == marker_text:
                code = c
                break
        if code is None:
            continue
        if code == "contact" and "contact" in out:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(normalized)
        value = normalized[start:end].strip(" \n\t:-,.")
        if value:
            out[code] = value

    log.info("request.parse.markers_found", keys=list(out.keys()), result=str(out)[:300])
    return out


async def parse_text(text: str, llm=None) -> dict[str, str]:
    if llm is not None:
        try:
            if hasattr(llm, "available") and llm.available():
                res = await llm.parse(text, schema_hint="request_form")
                if res and getattr(res, "confidence", 0) > 0.5:
                    return dict(getattr(res, "fields", {}) or {})
        except Exception as e:
            log.warning("request.llm_parse_failed", error=str(e))
    return parse_by_markers(text)
