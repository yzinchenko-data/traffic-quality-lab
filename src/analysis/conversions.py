"""Конверсии в цели: интервалы Уилсона, сравнение SSP, строки, где целей больше визитов."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, norm


def wilson(successes: int, trials: int, conf: float = 0.95) -> tuple[float, float]:
    if trials == 0:
        return (np.nan, np.nan)
    z = norm.ppf(1 - (1 - conf) / 2)
    p = successes / trials
    denom = 1 + z**2 / trials
    centre = (p + z**2 / (2 * trials)) / denom
    half = z * np.sqrt(p * (1 - p) / trials + z**2 / (4 * trials**2)) / denom
    return (round(centre - half, 4), round(centre + half, 4))


def by_ssp(mart: pd.DataFrame, goal: str) -> pd.DataFrame:
    # Строки, где целей больше визитов, в CR не берём: это отдельная находка
    valid = mart[mart[goal] <= mart["visits"]]
    g = valid.groupby("ssp", as_index=False)[["visits", goal]].sum()
    g["cr"] = (g[goal] / g["visits"]).round(4)
    ci = g.apply(lambda r: wilson(int(r[goal]), int(r["visits"])), axis=1)
    g["ci_low"] = [c[0] for c in ci]
    g["ci_high"] = [c[1] for c in ci]
    return g


def chi_square(mart: pd.DataFrame, goal: str) -> dict:
    valid = mart[mart[goal] <= mart["visits"]]
    g = valid.groupby("ssp")[["visits", goal]].sum()
    table = np.column_stack([g[goal], g["visits"] - g[goal]])
    chi2, p, dof, _ = chi2_contingency(table)
    return {"goal": goal, "chi2": round(float(chi2), 3), "dof": int(dof), "p_value": round(float(p), 4)}


def goals_over_visits(mart: pd.DataFrame, goals: list[str]) -> pd.DataFrame:
    rows = []
    for goal in goals:
        bad = mart[mart[goal] > mart["visits"]]
        for _, r in bad.iterrows():
            rows.append(
                {
                    "date": r["date"],
                    "ssp": r["ssp"],
                    "placement": r["placement"],
                    "goal": goal,
                    "visits": int(r["visits"]),
                    "reaches": int(r[goal]),
                }
            )
    return pd.DataFrame(rows, columns=["date", "ssp", "placement", "goal", "visits", "reaches"])
