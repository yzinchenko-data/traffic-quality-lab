"""Python и SQL считают одно и то же: суммы совпадают точно, доли — до единицы последнего знака
(pandas округляет половинки к чётному, DuckDB — от нуля), флаги — один в один."""

import pandas as pd
import pytest

from tests.conftest import missing_date

KEYS = ["date", "ssp", "placement"]
COUNTS = [
    "dsp_clicks",
    "dsp_clicks_matched",
    "verifier_total",
    "givt",
    "visits",
    "visits_matched",
    "robots",
    "add_to_cart",
    "form_submit",
]
RATES = ["reach_dsp", "reach_verifier", "dsp_vs_verifier_pct", "givt_share", "robot_share", "cr_cart", "cr_form"]


def _align(py: pd.DataFrame, sql: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    sql = sql.copy()
    if "date" in keys:
        sql["date"] = pd.to_datetime(sql["date"])
    return py.merge(sql, on=keys, suffixes=("_py", "_sql"), how="outer", indicator=True)


# Допуск = одна единица последнего знака после округления
TOL = {"dsp_vs_verifier_pct": 0.0101, "avg_daily_gap_pct": 0.0101}
RATE_TOL = 1.01e-4


def _assert_close(merged: pd.DataFrame, cols: list[str], tol: float) -> None:
    assert (merged["_merge"] == "both").all(), "строки есть только в одном из расчётов"
    for col in cols:
        a = merged[f"{col}_py"].astype(float)
        b = merged[f"{col}_sql"].astype(float)
        both_nan = a.isna() & b.isna()
        diff = (a - b).abs()
        limit = TOL.get(col, tol) if tol else 0
        assert ((diff <= limit) | both_nan).all(), f"{col}: max diff {diff.max()}"


def test_mart_daily(res):
    merged = _align(res.mart, res.sql["mart_daily"], KEYS)
    _assert_close(merged, COUNTS, 0)


@pytest.mark.parametrize(
    "py_attr, sql_table, key",
    [
        ("daily_ssp", "daily_ssp", "ssp"),
        ("daily_placement", "daily_placement", "placement"),
    ],
)
def test_daily_rollups(res, py_attr, sql_table, key):
    merged = _align(getattr(res, py_attr), res.sql[sql_table], ["date", key])
    _assert_close(merged, COUNTS, 0)
    _assert_close(merged, RATES, RATE_TOL)


def test_period_summary(res):
    merged = _align(res.summary, res.sql["period_summary"], ["ssp"])
    _assert_close(merged, COUNTS, 0)
    _assert_close(merged, RATES + ["avg_daily_reach", "avg_daily_gap_pct"], RATE_TOL)


def test_anomaly_flags(res):
    reach = _align(
        res.reach_flags[["date", "ssp", "flag"]], res.sql["anomalies_reach"][["date", "ssp", "flag"]], ["date", "ssp"]
    )
    assert (reach["flag_py"].fillna(False) == reach["flag_sql"].fillna(False)).all()
    givt = _align(
        res.givt_flags[["date", "placement", "flag"]],
        res.sql["anomalies_givt"][["date", "placement", "flag"]],
        ["date", "placement"],
    )
    assert (givt["flag_py"].fillna(False) == givt["flag_sql"].fillna(False)).all()


def test_windows_and_goals(res):
    py = res.windows.sort_values(["kind", "slice", "start"]).reset_index(drop=True)
    sql = res.sql["anomaly_windows"].sort_values(["kind", "slice", "start"]).reset_index(drop=True)
    assert py[["kind", "slice", "days"]].equals(sql[["kind", "slice", "days"]].astype({"days": py["days"].dtype}))
    assert (pd.to_datetime(sql["start"]) == py["start"]).all()

    assert len(res.goals_over) == len(res.sql["goals_over_visits"])


def test_sql_checks(res, cfg):
    assert res.sql["check_verifier_total"].empty
    assert [str(d)[:10] for d in res.sql["check_missing_dates"]["date"]] == [missing_date(cfg)]
