"""Проверка подписи initData Telegram WebApp."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from ..logging_setup import get_logger

log = get_logger(__name__)


def verify_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 3600,
) -> dict | None:
    if not init_data or not bot_token:
        return None

    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except ValueError:
        return None

    check_hash = pairs.pop("hash", None)
    if not check_hash:
        return None

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calc, check_hash):
        log.warning("webapp.hash_mismatch")
        return None

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        return None

    if time.time() - auth_date > max_age_seconds:
        log.warning("webapp.initdata_expired", age=time.time() - auth_date)
        return None

    if "user" in pairs and isinstance(pairs["user"], str):
        try:
            pairs["user"] = json.loads(pairs["user"])
        except json.JSONDecodeError:
            log.warning("webapp.user_json_invalid")
            return None

    return pairs
