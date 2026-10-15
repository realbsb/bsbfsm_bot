"""Тесты парсеров SH3D."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from workflow.parsers.csv_parser import parse_csv
from workflow.parsers.pdf_parser import parse_pdf
from workflow.parsers.sh3d import parse_attachments

FIXTURES = Path(__file__).parent / "fixtures"


def test_csv_parses_fixture():
    path = FIXTURES / "Баня7.csv"
    if not path.exists():
        pytest.skip("fixture missing")

    table = parse_csv(path)
    assert table.source == "csv"
    assert len(table.rows) >= 9
    names = {r.name for r in table.rows}
    assert "Печь" in names
    assert "Кресло-каталка" in names


def test_pdf_parses_fixture():
    path = FIXTURES / "Баня7.pdf"
    if not path.exists():
        pytest.skip("fixture missing")

    table = parse_pdf(path)
    assert table.source == "pdf"
    assert len(table.rows) >= 9


def test_aggregation_collapses_duplicates():
    path = FIXTURES / "Баня7.csv"
    if not path.exists():
        pytest.skip("fixture missing")

    table = parse_csv(path)
    agg = table.aggregated()
    assert len(agg) <= len(table.rows)
    door = next(r for r in agg if r.name.lower().startswith("дверь"))
    assert door.qty == Decimal("2")


def test_clean_number():
    from workflow.parsers.normalize import clean_number

    assert clean_number("1 256") == Decimal("1256")
    assert clean_number("1\u00a0256") == Decimal("1256")
    assert clean_number("2.5") == Decimal("2.5")
    assert clean_number("x") is None
    assert clean_number(None) is None


def test_clean_bool():
    from workflow.parsers.normalize import clean_bool

    for v in ("x", "true", "1", "да", "yes"):
        assert clean_bool(v) is True
    assert clean_bool("no") is False


def test_parse_attachments_prefers_csv():
    csv_path = FIXTURES / "Баня7.csv"
    pdf_path = FIXTURES / "Баня7.pdf"
    if not (csv_path.exists() and pdf_path.exists()):
        pytest.skip("fixtures missing")

    table = parse_attachments([pdf_path, csv_path])
    assert table is not None
    assert table.source == "csv"


def test_decode_cp866():
    from workflow.parsers.normalize import decode_bytes

    raw = "Наименование".encode("cp866")
    text, enc = decode_bytes(raw)
    assert text == "Наименование"
    assert enc == "cp866"
