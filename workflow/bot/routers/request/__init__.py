"""Пакет роутеров для заявок."""

from __future__ import annotations

from aiogram import Router

from . import confirm, edit, free_text, start, step

router = Router(name="request")
router.include_router(start.router)
router.include_router(free_text.router)
router.include_router(confirm.router)
router.include_router(edit.router)
router.include_router(step.router)

__all__ = ["router"]
