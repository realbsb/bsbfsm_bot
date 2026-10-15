"""Простой rate-limit по IP на Redis."""

from __future__ import annotations

from redis.asyncio import Redis

from ..config import Settings
from ..logging_setup import get_logger

log = get_logger(__name__)


class IpRateLimiter:
    def __init__(self, settings: Settings) -> None:
        self._redis = Redis.from_url(settings.redis_dsn, decode_responses=True)
        self._limit = settings.webapp_rate_limit_per_minute

    async def allow(self, ip: str, key_prefix: str = "rl") -> bool:
        key = f"{key_prefix}:{ip}"
        try:
            pipe = self._redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, 60)
            result = await pipe.execute()
            count = int(result[0])
            if count > self._limit:
                log.warning("rate_limit.blocked", ip=ip, count=count)
                return False
            return True
        except Exception as e:
            log.warning("rate_limit.error", error=str(e))
            return True  # fail-open

    async def close(self) -> None:
        await self._redis.aclose()
