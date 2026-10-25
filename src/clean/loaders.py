"""Загрузка и чистка трёх источников: DSP, Верификатор, Метрика.

Каждая функция возвращает чистую таблицу в общей схеме (date, ssp, placement, ...)
и пишет в CleaningReport, что именно поправлено. Отчёт о чистке уходит в Excel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

KEYS = ["date", "ssp", "placement"]


@dataclass
class CleaningReport:
    items: list[dict] = field(default_factory=list)

    def add(self, source: str, issue: str, rows: int, detail: str = "") -> None:
        self.items.append({"source": source, "issue": issue, "rows": rows, "detail": detail})

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.items, columns=["source", "issue", "rows", "detail"])


def normalize_utm(value: str) -> str:
    """'SSP_A', 'ssp_a ', 'ssp-a', 'ssp_a?ref=feed' → 'ssp_a'."""
    return str(value).strip().lower().split("?")[0].replace("-", "_")


def load_dsp(path: str | Path, report: CleaningReport) -> pd.DataFrame:
    raw = pd.read_csv(path)
    dups = int(raw.duplicated().sum())
    if dups:
        report.add("DSP", "полные дубли строк", dups, "удалены")
    df = raw.drop_duplicates().rename(
        columns={"Дата": "date", "SSP": "ssp", "Площадка": "placement", "Клики": "dsp_clicks"}
    )
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    return df[KEYS + ["dsp_clicks"]].reset_index(drop=True)


def load_verifier(path: str | Path, report: CleaningReport, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    raw = pd.read_csv(path, sep=";")
    total_row = raw[raw["Дата"] == "Итого"]
    body = raw[raw["Дата"] != "Итого"].copy()

    value_cols = ["Кликов всего с учётом IVT", "GIVT", "SIVT", "Чистые клики"]
    if not total_row.empty:
        report.add("Верификатор", "строка «Итого»", 1, "убрана из данных, использована для сверки")
        for col in value_cols:
            expected, actual = int(total_row[col].iloc[0]), int(body[col].sum())
            if expected != actual:
                report.add("Верификатор", f"расхождение с «Итого» по «{col}»", 0, f"{actual} vs {expected}")

    df = body.rename(
        columns={
            "Дата": "date",
            "SSP": "ssp",
            "Площадка": "placement",
            "Кликов всего с учётом IVT": "verifier_total",
            "GIVT": "givt",
            "SIVT": "sivt",
            "Чистые клики": "clean_clicks",
        }
    )
    df["date"] = pd.to_datetime(df["date"], format="%d.%m.%Y")
    for col in ["verifier_total", "givt", "sivt", "clean_clicks"]:
        df[col] = df[col].astype(int)

    missing = calendar.difference(pd.DatetimeIndex(df["date"].unique()))
    if len(missing):
        report.add(
            "Верификатор",
            "пропущенные даты",
            len(missing),
            ", ".join(d.strftime("%Y-%m-%d") for d in missing),
        )
    return df[KEYS + ["verifier_total", "givt", "sivt", "clean_clicks"]].reset_index(drop=True)


def load_metrika(path: str | Path, report: CleaningReport) -> pd.DataFrame:
    raw = pd.read_csv(path)
    normalized = raw["utm_source"].map(normalize_utm)
    changed = int((normalized != raw["utm_source"]).sum())
    if changed:
        variants = sorted(set(raw.loc[normalized != raw["utm_source"], "utm_source"]))
        report.add("Метрика", "UTM-метки в разном написании", changed, " | ".join(repr(v) for v in variants))

    df = raw.assign(ssp=normalized, placement=raw["utm_content"].map(normalize_utm))
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    # floor(x + 0.5), а не round(): у pandas банковское округление, у DuckDB — нет
    df["robots"] = np.floor(df["visits"] * df["robot_share"] + 0.5).astype(int)
    df["bounces"] = np.floor(df["visits"] * df["bounce_rate"] + 0.5).astype(int)
    agg = df.groupby(KEYS, as_index=False)[["visits", "users", "robots", "bounces", "add_to_cart", "form_submit"]].sum()
    return agg


def load_all(raw_dir: str | Path, start: str, end: str) -> tuple[dict[str, pd.DataFrame], CleaningReport]:
    raw_dir = Path(raw_dir)
    report = CleaningReport()
    calendar = pd.date_range(start, end, freq="D")
    data = {
        "dsp": load_dsp(raw_dir / "dsp_clicks.csv", report),
        "verifier": load_verifier(raw_dir / "verifier_export.csv", report, calendar),
        "metrika": load_metrika(raw_dir / "metrika_visits.csv", report),
    }
    return data, report
