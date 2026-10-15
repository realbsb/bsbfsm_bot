"""Настройка structlog. JSON в проде, цветной вывод в dev."""

from __future__ import annotations

import logging
import sys

import structlog

from .config import Settings


def setup_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_json:
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    for noisy in ("aiogram.event", "aiogram.dispatcher", "httpx", "docker"):
        logging.getLogger(noisy).setLevel(logging.DEBUG)  # logging.WARNING


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
