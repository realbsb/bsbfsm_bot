"""Парсер CSV из SweetHome 3D. Кодировка по умолчанию CP866."""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from pathlib import Path

from ..logging_setup import get_logger
from .models import ParsedRow, ParsedTable
from .normalize import clean_bool, clean_number, decode_bytes

log = get_logger(__name__)

EXPECTED = ("наименование", "ширина", "глубина", "высота", "видимость")


def parse_csv(path: Path) -> ParsedTable:
    raw = path.read_bytes()
    text, enc = decode_bytes(raw)

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="\t;,")
    except csv.Error:
        dialect = csv.excel_tab

    reader = csv.reader(io.StringIO(text), dialect)
    rows_iter = iter(reader)
    header = next(rows_iter, None)
    if not header:
        return ParsedTable(source="csv", warnings=["Пустой CSV"])

    header_norm = [h.strip().lower() for h in header]
    idx = {name: header_norm.index(name) for name in EXPECTED if name in header_norm}
    missing = [c for c in EXPECTED if c not in idx]

    table = ParsedTable(source="csv", columns=header, warnings=[])
    table.warnings.append(f"Кодировка: {enc}")
    if missing:
        table.warnings.append(f"Нет колонок: {missing}")

    def get(row: list[str], name: str) -> str:
        i = idx.get(name)
        return row[i] if i is not None and i < len(row) else ""

    for raw_row in rows_iter:
        if not raw_row or all(not c.strip() for c in raw_row):
            continue
        name = get(raw_row, "наименование").strip()
        if not name:
            continue
        table.rows.append(
            ParsedRow(
                name=name,
                width=clean_number(get(raw_row, "ширина")),
                depth=clean_number(get(raw_row, "глубина")),
                height=clean_number(get(raw_row, "высота")),
                visible=clean_bool(get(raw_row, "видимость")),
                qty=Decimal("1"),
                raw="\t".join(raw_row),
            )
        )

    log.info("csv.parsed", path=str(path), rows=len(table.rows), encoding=enc)
    return table
