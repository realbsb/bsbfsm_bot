"""Парсер PDF из SweetHome 3D через pdftotext -layout."""

from __future__ import annotations

import re
import subprocess
from decimal import Decimal
from pathlib import Path

from ..logging_setup import get_logger
from .models import ParsedRow, ParsedTable
from .normalize import clean_bool, clean_number

log = get_logger(__name__)

EXPECTED = ("наименование", "ширина", "глубина", "высота", "видимость")
_PAGE_NUM_RE = re.compile(r"\s*\d+\s*")


def _pdftotext_layout(path: Path) -> str:
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
            capture_output=True,
            check=True,
            timeout=60,
        )
    except FileNotFoundError as e:
        raise RuntimeError("pdftotext не установлен (poppler-utils)") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"pdftotext error: {e.stderr.decode(errors='replace')}") from e
    return out.stdout.decode("utf-8", errors="replace")


def _find_header(lines: list[str]) -> tuple[int, dict[str, int]] | None:
    for i, line in enumerate(lines):
        low = line.lower()
        if all(col in low for col in ("наименование", "ширина", "глубина", "высота")):
            positions: dict[str, int] = {}
            for col in EXPECTED:
                m = re.search(re.escape(col), low)
                if m:
                    positions[col] = m.start()
            return i, positions
    return None


def _slice(line: str, positions: dict[str, int]) -> dict[str, str]:
    starts = sorted((pos, name) for name, pos in positions.items())
    result: dict[str, str] = {}
    for j, (pos, name) in enumerate(starts):
        end = starts[j + 1][0] if j + 1 < len(starts) else len(line)
        result[name] = line[pos:end].strip()
    return result


def parse_pdf(path: Path) -> ParsedTable:
    text = _pdftotext_layout(path)
    lines = text.splitlines()

    found = _find_header(lines)
    if not found:
        return ParsedTable(source="pdf", warnings=["Не найдена шапка таблицы"])

    header_idx, positions = found
    order = [name for name, _ in sorted(positions.items(), key=lambda x: x[1])]
    table = ParsedTable(source="pdf", columns=order, warnings=[])

    for line in lines[header_idx + 1 :]:
        if not line.strip():
            continue
        low = line.lower()
        if "наименование" in low and "ширина" in low:
            continue
        if _PAGE_NUM_RE.fullmatch(line):
            continue

        parts = _slice(line, positions)
        name = parts.get("наименование", "").strip()
        if not name:
            continue

        nums = [parts.get(c, "") for c in ("ширина", "глубина", "высота")]
        if not any(clean_number(n) is not None for n in nums):
            continue

        table.rows.append(
            ParsedRow(
                name=name,
                width=clean_number(parts.get("ширина", "")),
                depth=clean_number(parts.get("глубина", "")),
                height=clean_number(parts.get("высота", "")),
                visible=clean_bool(parts.get("видимость", "")) if "видимость" in parts else True,
                qty=Decimal("1"),
                raw=line,
            )
        )

    log.info("pdf.parsed", path=str(path), rows=len(table.rows))
    return table
