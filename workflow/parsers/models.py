"""Модели результата парсинга SH3D."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class ParsedRow:
    name: str
    width: Decimal | None = None
    depth: Decimal | None = None
    height: Decimal | None = None
    visible: bool = True
    qty: Decimal = Decimal("1")
    raw: str = ""

    def key(self) -> tuple:
        return (self.name.strip().lower(), self.width, self.depth, self.height)


@dataclass
class ParsedTable:
    source: str
    columns: list[str] = field(default_factory=list)
    rows: list[ParsedRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def aggregated(self) -> list[ParsedRow]:
        bucket: dict[tuple, ParsedRow] = {}
        for r in self.rows:
            k = r.key()
            if k in bucket:
                bucket[k].qty += r.qty
            else:
                bucket[k] = ParsedRow(
                    name=r.name,
                    width=r.width,
                    depth=r.depth,
                    height=r.height,
                    visible=r.visible,
                    qty=r.qty,
                    raw=r.raw,
                )
        return list(bucket.values())
