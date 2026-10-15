"""Клиент Whisper-контейнера.

Использует shared volume /work — общий между bot и whisper.
Команды в контейнере: ffmpeg → ./whisper-cli.
Основано на рабочем коде golostxtbot.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import docker
from aiogram import Bot
from aiogram.types import Voice

from ..config import Settings
from ..logging_setup import get_logger

log = get_logger(__name__)


class WhisperClient:
    """Транскрипция голосовых через существующий whisper-контейнер."""

    def __init__(self, settings: Settings, bot: Bot) -> None:
        self._settings = settings
        self._bot = bot
        self._docker = docker.from_env()
        self._work_dir = Path(settings.whisper_work_dir)
        self._work_dir.mkdir(parents=True, exist_ok=True)

    async def transcribe(self, voice: Voice) -> str:
        """Скачивает голосовое из Telegram и прогоняет через whisper.

        Возвращает распознанный текст.
        """
        uid = uuid.uuid4().hex
        ogg_path = self._work_dir / f"{uid}.ogg"
        wav_path = self._work_dir / f"{uid}.wav"

        try:
            # 1. Скачиваем OGG из Telegram прямо в shared volume
            tg_file = await self._bot.get_file(voice.file_id)
            await self._bot.download_file(tg_file.file_path, ogg_path)

            # 2. Обрабатываем в контейнере (синхронный вызов в отдельном потоке)
            text = await asyncio.to_thread(self._run_whisper, ogg_path, wav_path)
            return text
        finally:
            for p in (ogg_path, wav_path):
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass

    def _run_whisper(self, ogg_path: Path, wav_path: Path) -> str:
        """Синхронный вызов docker exec в контейнер whisper."""
        try:
            container = self._docker.containers.get(self._settings.whisper_container)
        except docker.errors.NotFound as e:
            log.error("whisper.container_not_found", container=self._settings.whisper_container)
            raise RuntimeError(f"Контейнер {self._settings.whisper_container} не найден") from e

        # Пути внутри контейнера (shared volume смонтирован как /work)
        ogg_in_ctr = f"/work/{ogg_path.name}"
        wav_in_ctr = f"/work/{wav_path.name}"

        # --- ffmpeg: OGG → WAV 16k mono ---
        ff = container.exec_run(
            [
                "ffmpeg",
                "-y",
                "-i",
                ogg_in_ctr,
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                wav_in_ctr,
            ],
            demux=False,
        )
        if ff.exit_code != 0:
            out = (ff.output or b"").decode(errors="replace")
            log.error("whisper.ffmpeg_failed", code=ff.exit_code, output=out[-500:])
            raise RuntimeError(f"ffmpeg failed ({ff.exit_code})")

        # --- whisper-cli ---
        model_path = f"/models/ggml-{self._settings.whisper_model}.bin"
        wc = container.exec_run(
            [
                "./whisper-cli",
                "-np",
                "-nt",
                "-m",
                model_path,
                "-f",
                wav_in_ctr,
                "-l",
                "ru",
            ],
            demux=False,
        )
        if wc.exit_code != 0:
            out = (wc.output or b"").decode(errors="replace")
            log.error("whisper.exec_failed", code=wc.exit_code, output=out[-500:])
            raise RuntimeError(f"whisper-cli failed ({wc.exit_code})")

        raw = (wc.output or b"").decode(errors="replace")

        # --- отфильтровать служебные строки ---
        drop_prefixes = (
            "read_audio_data:",
            "whisper_",
            "ggml_",
            "main:",
            "system_info:",
            "load_",
            "mel_",
        )
        lines: list[str] = []
        for line in raw.splitlines():
            s = line.strip()
            if not s:
                continue
            if any(s.startswith(p) for p in drop_prefixes):
                continue
            lines.append(s)

        text = "\n".join(lines).strip()
        log.info("whisper.transcribed", length=len(text))
        return text
