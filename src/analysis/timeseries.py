"""Аномалии во временных рядах.

Флаг ставит robust z: отклонение от медианы ряда в единицах MAD. Медиана и MAD не сдвигаются
от нескольких аномальных дней, в отличие от среднего и сигмы. То же правило повторено
в sql/03_anomalies.sql, поэтому результаты Python и SQL сверяются один в один.

STL-декомпозиция с недельной сезонностью идёт рядом как описание ряда (тренд, сезонность)
для графиков. Флагом её не делаем: на 30 точках robust-остаток почти нулевой, и любое
колебание раздувается в «аномалию».
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

MAD_SCALE = 1.4826  # приводит MAD к сигме нормального распределения
Z_THRESHOLD = 3.5


def robust_z(series: pd.Series) -> pd.Series:
    median = series.median()
    mad = (series - median).abs().median() * MAD_SCALE
    if not mad or np.isnan(mad):
        return pd.Series(0.0, index=series.index)
    return (series - median) / mad


def decompose(series: pd.Series, period: int = 7) -> pd.DataFrame:
    clean = series.interpolate(limit_direction="both")
    res = STL(clean, period=period, robust=True).fit()
    return pd.DataFrame({"trend": res.trend, "seasonal": res.seasonal, "resid": res.resid})


def detect(
    daily: pd.DataFrame,
    group: str,
    metric: str,
    direction: str,
    threshold: float = Z_THRESHOLD,
) -> pd.DataFrame:
    """Флаги аномалий по каждому ряду group.

    direction: 'low' — ищем провалы (доходимость), 'high' — всплески (GIVT).
    """
    frames = []
    for key, part in daily.groupby(group):
        s = part.set_index("date")[metric].sort_index()
        frame = pd.DataFrame({"date": s.index, group: key, metric: s.values, "z": robust_z(s).values})
        if s.notna().sum() >= 14:
            frame["trend"] = decompose(s)["trend"].values
        frames.append(frame)
    out = pd.concat(frames, ignore_index=True)
    sign = -1 if direction == "low" else 1
    out["flag"] = (sign * out["z"]) > threshold
    return out.round({"z": 2, "trend": 4})


def windows(flags: pd.DataFrame, group: str) -> pd.DataFrame:
    """Склеивает подряд идущие флаги в периоды: ssp_b, 12.09–14.09."""
    rows = []
    for key, part in flags[flags["flag"]].groupby(group):
        dates = part["date"].sort_values()
        run_id = (dates.diff().dt.days != 1).cumsum()
        for _, run in dates.groupby(run_id):
            rows.append({group: key, "start": run.min(), "end": run.max(), "days": len(run)})
    return pd.DataFrame(rows, columns=[group, "start", "end", "days"])
