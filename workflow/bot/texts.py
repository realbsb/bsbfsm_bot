"""Локализация. Загрузка JSON, обёртка t(), автоопределение языка."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..logging_setup import get_logger
from .utils import trace

log = get_logger(__name__)

LOCALES_DIR = Path(__file__).resolve().parent.parent.parent / "locales"
DEFAULT_LOCALE = "ru"
SUPPORTED_LOCALES = ("ru", "en", "kz")

_TG_MAP = {
    "ru": "ru",
    "en": "en",
    "kk": "kz",
    "kz": "kz",
}


@lru_cache(maxsize=1)
@trace
def _load_all() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for loc in SUPPORTED_LOCALES:
        path = LOCALES_DIR / f"{loc}.json"
        if not path.exists():
            log.warning("i18n.missing_file", path=str(path))
            out[loc] = {}
            continue
        try:
            out[loc] = json.loads(path.read_text(encoding="utf-8"))
            log.info("i18n.loaded", locale=loc, keys=len(out[loc]))
        except Exception as e:
            log.error("i18n.load_failed", locale=loc, error=str(e))
            out[loc] = {}
    return out


@trace
def detect_locale(tg_language_code: str | None) -> str:
    if not tg_language_code:
        return DEFAULT_LOCALE
    code = tg_language_code.lower().split("-")[0]
    return _TG_MAP.get(code, DEFAULT_LOCALE)


@trace
def t(key: str, locale: str = DEFAULT_LOCALE, **kwargs) -> str:
    data = _load_all()
    for loc in (locale, DEFAULT_LOCALE):
        val = data.get(loc, {}).get(key)
        if val:
            try:
                return val.format(**kwargs) if kwargs else val
            except (KeyError, IndexError):
                log.warning("i18n.format_failed", key=key, locale=loc)
                return val
    log.warning("i18n.missing_key", key=key, locale=locale)
    return key


@trace
def reload_locales() -> None:
    _load_all.cache_clear()
