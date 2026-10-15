"""Конфигурация приложения. Читается из env и .env."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Общее ---
    app_env: Literal["development", "production"] = "production"
    log_level: str = "INFO"
    log_json: bool = True
    tz: str = "Europe/Moscow"

    # --- БД ---
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "workflow"
    db_password: str = "change_me"
    db_name: str = "workflow"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # --- Redis ---
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 1
    redis_password: str | None = None

    # --- Telegram ---
    bot_token: str
    bot_admin_ids: list[int] = Field(default_factory=list)
    bot_webapp_base_url: str = "https://realbsb.ru/workflow"
    telegram_proxy: str | None = None

    # --- WebApp ---
    webapp_root_path: str = ""
    webapp_host: str = "127.0.0.1"
    webapp_port: int = 8080
    webapp_initdata_max_age: int = 3600

    # --- CSRF / публичные заявки ---
    webapp_secret: str = "change_me_long_random_string"
    webapp_rate_limit_per_minute: int = 20

    # --- Whisper ---
    whisper_container: str = "whisper"
    whisper_model: str = "small"
    whisper_timeout: int = 120
    whisper_work_dir: str = "/home/orangepi/telegram/shared/whisper-work"

    # --- LLM ---
    llm_enabled: bool = False
    llm_base_url: str = "http://llm.local:8080"
    llm_timeout: float = 2.0
    llm_model: str = "qwen2.5:7b"

    # --- Radicale ---
    radicale_default_url: str = "http://192.168.0.1:5232"

    # --- Пути ---
    export_dir: Path = Path("/var/lib/workflow/exports")
    archive_dir: Path = Path("/var/lib/workflow/archive")
    media_cache_dir: Path = Path("/var/lib/workflow/media")

    # --- QR ---
    qr_token_ttl_days: int = 14

    # ============================================================
    # Валидаторы
    # ============================================================

    @field_validator("bot_admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: Any) -> list[int]:
        if v is None or v == "":
            return []
        if isinstance(v, (list, tuple, set)):
            return [int(x) for x in v]
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            if s.startswith("["):
                try:
                    parsed = json.loads(s)
                    return [int(x) for x in parsed]
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass
            parts = [p.strip() for p in s.replace(" ", ",").split(",") if p.strip()]
            return [int(p) for p in parts]
        raise ValueError(f"Некорректный формат bot_admin_ids: {v!r}")

    # ============================================================
    # Свойства
    # ============================================================

    @property
    def db_dsn(self) -> str:
        return (
            f"mysql+aiomysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @property
    def redis_dsn(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    def ensure_dirs(self) -> None:
        for p in (self.export_dir, self.archive_dir, self.media_cache_dir):
            p.mkdir(parents=True, exist_ok=True)
        Path(self.whisper_work_dir).mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
