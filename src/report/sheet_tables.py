"""Таблицы для Google Sheets: один набор листов и колонок для Python и Apps Script.

Пайплайн пишет их в exports/sheets/*.csv, Apps Script (apps_script/report_builder.gs)
забирает эти файлы из репозитория и оформляет. Порядок и имена колонок здесь
менять вместе с LAYOUT в report_builder.gs.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DAILY_SSP_COLS = ["date", "ssp", "dsp_clicks", "verifier_total", "visits", "reach_verifier", "dsp_vs_verifier_pct", "z", "flag"]
GIVT_COLS = ["date", "placement", "verifier_total", "givt", "givt_share", "z", "flag"]

# имя файла → имя листа
SHEETS = {
    "summary": "Сводка",
    "daily_ssp": "По дням SSP",
    "givt": "Площадки GIVT",
    "anomalies": "Аномалии",
    "cleaning": "Чистка",
}


def build(res) -> dict[str, pd.DataFrame]:
    daily = res.daily_ssp.merge(res.reach_flags[["date", "ssp", "z", "flag"]], on=["date", "ssp"])[DAILY_SSP_COLS]
    givt = res.daily_placement.merge(res.givt_flags[["date", "placement", "z", "flag"]], on=["date", "placement"])[GIVT_COLS]
    tables = {
        "summary": res.summary,
        "daily_ssp": daily,
        "givt": givt,
        "anomalies": res.windows,
        "cleaning": res.cleaning.to_frame(),
    }
    out = {}
    for name, df in tables.items():
        df = df.copy()
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime("%Y-%m-%d")
            elif pd.api.types.is_float_dtype(df[col]):
                df[col] = df[col].round(4)
        out[name] = df
    return out


def write_csv(res, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, df in build(res).items():
        path = out_dir / f"{name}.csv"
        df.to_csv(path, index=False)
        paths.append(path)
    return paths
