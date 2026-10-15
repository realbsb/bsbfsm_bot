"""QR-токены и генерация наклеек."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from io import BytesIO

import qrcode
from PIL import Image, ImageDraw

from ..config import Settings
from ..logging_setup import get_logger
from ..models import QrKind

log = get_logger(__name__)


def new_token() -> str:
    return secrets.token_urlsafe(16)


def qr_url(settings: Settings, token: str) -> str:
    return f"{settings.bot_webapp_base_url}/qr/{token}"


def make_qr_png(data: str, box_size: int = 10) -> bytes:
    img = qrcode.make(data, box_size=box_size)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_labels_png(texts: list[str], cols: int = 2, rows: int = 5) -> bytes:
    if not texts:
        return b""

    per_image = cols * rows
    images = texts[:per_image]

    qr_size = 200
    label_w, label_h = qr_size + 20, qr_size + 40
    sheet = Image.new("RGB", (cols * label_w, rows * label_h), "white")
    draw = ImageDraw.Draw(sheet)

    for i, text in enumerate(images):
        qr_img = qrcode.make(text, box_size=6).get_image()
        qr_img = qr_img.resize((qr_size, qr_size))

        cx = (i % cols) * label_w
        cy = (i // cols) * label_h

        sheet.paste(qr_img, (cx + 10, cy + 10))
        short = text.split("/")[-1][:12]
        draw.text((cx + 10, cy + qr_size + 15), short, fill="black")
        draw.rectangle(
            [(cx, cy), (cx + label_w - 1, cy + label_h - 1)],
            outline="gray",
        )

    buf = BytesIO()
    sheet.save(buf, format="PNG")
    return buf.getvalue()


def expires_for(kind: QrKind, settings: Settings) -> datetime | None:
    if kind == QrKind.PURCHASE:
        return datetime.utcnow() + timedelta(days=settings.qr_token_ttl_days)
    return None
