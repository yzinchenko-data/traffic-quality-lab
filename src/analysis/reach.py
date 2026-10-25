"""Доходимость: DSP → Верификатор → Метрика.

Доходимость считаем от DSP-показателя Верификатора («Кликов всего с учётом IVT»)
и отдельно от кликов DSP. Расхождения DSP и Верификатора — в процентах по дням и за период.
"""

from __future__ import annotations

import pandas as pd

from src.clean.loaders import KEYS


def build_mart(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Одна строка на день × SSP × площадку. Дни, которых нет у Верификатора, остаются с NaN."""
    mart = (
        data["dsp"]
        .merge(data["verifier"], on=KEYS, how="left")
        .merge(data["metrika"], on=KEYS, how="left")
        .sort_values(KEYS)
        .reset_index(drop=True)
    )
    # Клики DSP и визиты только за дни, которые есть у Верификатора:
    # по ним считаем расхождение и доходимость от Верификатора
    has_verifier = mart["verifier_total"].notna()
    mart.insert(4, "dsp_clicks_matched", mart["dsp_clicks"].where(has_verifier))
    mart["visits_matched"] = mart["visits"].where(has_verifier)
    return add_rates(mart)


def _div(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a / b.where(b != 0)).round(4)


def add_rates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["reach_dsp"] = _div(df["visits"], df["dsp_clicks"])
    df["reach_verifier"] = _div(df["visits_matched"], df["verifier_total"])
    df["dsp_vs_verifier_pct"] = (
        _div(df["dsp_clicks_matched"] - df["verifier_total"], df["verifier_total"]) * 100
    ).round(2)
    df["givt_share"] = _div(df["givt"], df["verifier_total"])
    df["sivt_share"] = _div(df["sivt"], df["verifier_total"])
    df["robot_share"] = _div(df["robots"], df["visits"])
    df["cr_cart"] = _div(df["add_to_cart"], df["visits"])
    df["cr_form"] = _div(df["form_submit"], df["visits"])
    return df


SUM_COLS = [
    "dsp_clicks",
    "dsp_clicks_matched",
    "verifier_total",
    "givt",
    "sivt",
    "clean_clicks",
    "visits",
    "visits_matched",
    "robots",
    "add_to_cart",
    "form_submit",
]


def rollup(mart: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Суммы по срезу и пересчёт долей от сумм (не среднее долей)."""
    out = mart.groupby(by, as_index=False)[SUM_COLS].sum(min_count=1)
    return add_rates(out)


def period_summary(mart: pd.DataFrame) -> pd.DataFrame:
    """Итог за период по SSP + строка «Итого» + средние дневные значения доходимости."""
    by_ssp = rollup(mart, ["ssp"])
    total = rollup(mart.assign(ssp="Итого"), ["ssp"])
    summary = pd.concat([by_ssp, total], ignore_index=True)

    daily = rollup(mart, ["date", "ssp"])
    avg = daily.groupby("ssp")[["reach_verifier", "dsp_vs_verifier_pct"]].mean().round(4)
    avg_total = rollup(mart, ["date"])[["reach_verifier", "dsp_vs_verifier_pct"]].mean().round(4)
    avg.loc["Итого"] = avg_total
    avg = avg.rename(columns={"reach_verifier": "avg_daily_reach", "dsp_vs_verifier_pct": "avg_daily_gap_pct"})
    return summary.merge(avg, left_on="ssp", right_index=True, how="left")
