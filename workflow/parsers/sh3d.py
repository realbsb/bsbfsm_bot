"""Общий интерфейс парсинга вложений SH3D. CSV → PDF."""

from __future__ import annotations

from pathlib import Path

from ..logging_setup import get_logger
from .csv_parser import parse_csv
from .models import ParsedTable
from .pdf_parser import parse_pdf

log = get_logger(__name__)


def parse_attachments(paths: list[Path]) -> ParsedTable | None:
    csvs = [p for p in paths if p.suffix.lower() == ".csv"]
    pdfs = [p for p in paths if p.suffix.lower() == ".pdf"]

    for p in csvs:
        try:
            t = parse_csv(p)
            if t.rows:
                return t
        except Exception as e:
            log.warning("csv.parse_failed", path=str(p), error=str(e))

    for p in pdfs:
        try:
            t = parse_pdf(p)
            if t.rows:
                return t
        except Exception as e:
            log.warning("pdf.parse_failed", path=str(p), error=str(e))

    return None
