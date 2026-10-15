"""CSRF-токены для публичных форм.

Не используем cookie-сессии. Токен — подписанный JWT-подобный payload.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from ..config import Settings
from ..logging_setup import get_logger

log = get_logger(__name__)

TOKEN_TTL_SECONDS = 3600


def _sign(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def make_token(settings: Settings, form_slug: str) -> str:
    """Создаёт CSRF-токен для формы."""
    nonce = secrets.token_urlsafe(12)
    ts = int(time.time())
    payload = {"form": form_slug, "nonce": nonce, "ts": ts}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    b64 = base64.urlsafe_b64encode(raw).decode()
    sig = _sign(raw, settings.webapp_secret)
    return f"{b64}.{sig}"


def verify_token(settings: Settings, token: str, form_slug: str) -> bool:
    """Проверяет CSRF-токен."""
    if not token or "." not in token:
        return False
    try:
        b64, sig = token.split(".", 1)
        raw = base64.urlsafe_b64decode(b64.encode())
    except (ValueError, TypeError):
        return False

    expected = _sign(raw, settings.webapp_secret)
    if not hmac.compare_digest(sig, expected):
        return False

    try:
        payload = json.loads(raw.decode())
    except json.JSONDecodeError:
        return False

    if payload.get("form") != form_slug:
        return False
    return not time.time() - int(payload.get("ts", 0)) > TOKEN_TTL_SECONDS
