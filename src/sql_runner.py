"""Прогоняет sql/*.sql в DuckDB и отдаёт таблицы в pandas."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
TABLES = [
    "mart_daily",
    "daily_ssp",
    "daily_placement",
    "period_summary",
    "anomalies_reach",
    "anomalies_givt",
    "anomaly_windows",
    "goals_over_visits",
    "check_verifier_total",
    "check_missing_dates",
]


def run(raw_dir: str | Path, start: str, end: str, db_path: str | Path = ":memory:") -> dict[str, pd.DataFrame]:
    con = duckdb.connect(str(db_path))
    params = {"raw_dir": Path(raw_dir).resolve().as_posix(), "start": start, "end": end}
    for sql_file in sorted(SQL_DIR.glob("*.sql")):
        con.execute(sql_file.read_text(encoding="utf-8").format(**params))
    result = {name: con.execute(f"SELECT * FROM {name}").df() for name in TABLES}
    con.close()
    return result
