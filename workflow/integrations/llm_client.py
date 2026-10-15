"""Опциональный LLM-узел в интрасете. При недоступности — деградация."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..config import Settings
from ..logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class LlmParseResult:
    intent: str
    confidence: float
    fields: dict


class LlmClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout,
        )

    def available(self) -> bool:
        return self._settings.llm_enabled

    async def parse(self, text: str, schema_hint: str) -> LlmParseResult | None:
        if not self.available():
            return None
        try:
            r = await self._client.post(
                "/parse",
                json={"text": text, "hint": schema_hint, "model": self._settings.llm_model},
            )
            r.raise_for_status()
            data = r.json()
            return LlmParseResult(
                intent=data.get("intent", ""),
                confidence=float(data.get("confidence", 0.0)),
                fields=data.get("fields", {}),
            )
        except (httpx.HTTPError, ValueError) as e:
            log.warning("llm.unavailable", error=str(e))
            return None

    async def close(self) -> None:
        await self._client.aclose()
