"""Офлайн-эмулятор Метрики.

Пока бот-посетитель не нагнал реальных визитов, пайплайну нужны данные «как из Метрики».
Эмулятор берёт visit_plan.csv и отдаёт таблицу в той же схеме, что и metrika_api.py:
часть визитов теряется (бот не догрузил страницу), часть помечается роботами.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.extract.schema import METRIKA_COLUMNS

LOSS_RATE = (0.0, 0.02)  # визиты, которые Метрика не засчитала
ROBOT_SHARE = (0.04, 0.10)  # headless-браузер с IP датацентра частично уходит в роботов
BOUNCE_RATE = (0.18, 0.32)


def emulate(plan: pd.DataFrame, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = plan.copy()
    loss = rng.uniform(*LOSS_RATE, size=len(out))
    out["visits"] = rng.binomial(out["visits"], 1 - loss)
    out["users"] = np.maximum(out["visits"] - rng.binomial(out["visits"], 0.05), 0)
    out["bounce_rate"] = rng.uniform(*BOUNCE_RATE, size=len(out)).round(4)
    out["robot_share"] = rng.uniform(*ROBOT_SHARE, size=len(out)).round(4)
    # Цели не трогаем: аномалия «целей больше визитов» должна дожить до анализа
    return out[METRIKA_COLUMNS]


def run(plan_path: str | Path, out_path: str | Path, seed: int = 7) -> pd.DataFrame:
    plan = pd.read_csv(plan_path)
    report = emulate(plan, seed)
    report.to_csv(out_path, index=False)
    return report
