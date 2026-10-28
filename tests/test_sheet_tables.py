"""CSV для Google Sheets и оформление в Apps Script должны сходиться: иначе при правке
одной стороны таблица тихо потеряет подсветку или проценты."""

import re
from pathlib import Path

import pytest

from src.report import sheet_tables

GS = (Path(__file__).resolve().parent.parent / "apps_script" / "report_builder.gs").read_text(encoding="utf-8")


def _block(name: str) -> str:
    m = re.search(rf"const {name} = \{{(.*?)\n\}};", GS, re.S)
    assert m, f"{name} не найден в report_builder.gs"
    return m.group(1)


def _layout() -> dict[str, str]:
    body = _block("LAYOUT")
    keys = re.findall(r"^  (\w+): \{", body, re.M)
    parts = re.split(r"^  \w+: \{", body, flags=re.M)[1:]
    return dict(zip(keys, parts, strict=True))


@pytest.fixture(scope="module")
def tables(res):
    return sheet_tables.build(res)


def test_same_sheets(tables):
    assert set(tables) == set(sheet_tables.SHEETS) == set(_layout())


def test_titles_match():
    for name, body in _layout().items():
        assert f"title: '{sheet_tables.SHEETS[name]}'" in body


def test_layout_columns_exist(tables):
    for name, body in _layout().items():
        cols = set(tables[name].columns)
        refs = re.findall(r"'(\w+)'", " ".join(re.findall(r"percent: \[(.*?)\]", body)))
        refs += re.findall(r"(?:flag|col): '(\w+)'", body)
        missing = set(refs) - cols
        assert not missing, f"{name}: в LAYOUT есть колонки, которых нет в CSV: {missing}"


def test_every_column_has_label(tables):
    labels = set(re.findall(r"(\w+): '", _block("LABELS")))
    for name, df in tables.items():
        assert not set(df.columns) - labels, f"{name}: нет русских заголовков"


def test_csv_roundtrip(res, tmp_path):
    paths = sheet_tables.write_csv(res, tmp_path)
    assert sorted(p.stem for p in paths) == sorted(sheet_tables.SHEETS)
