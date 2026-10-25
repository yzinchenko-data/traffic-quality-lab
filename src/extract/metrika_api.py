"""Выгрузка из Reporting API Яндекс Метрики в общую схему.

Нужны переменные окружения (см. .env.example):
  METRIKA_TOKEN, METRIKA_COUNTER_ID, METRIKA_GOAL_ADD_TO_CART, METRIKA_GOAL_FORM_SUBMIT

Запуск:
  python -m src.extract.metrika_api --start 2026-09-01 --end 2026-09-30 --out data/raw/metrika_visits.csv
"""

from __future__ import annotations

import argparse
import os
import time

import pandas as pd
import requests
from dotenv import load_dotenv

from src.extract.schema import METRIKA_COLUMNS

API_URL = "https://api-metrika.yandex.net/stat/v1/data"
PAGE_SIZE = 10_000

DIMENSIONS = [
    "ym:s:date",
    "ym:s:UTMSource",
    "ym:s:UTMMedium",
    "ym:s:UTMCampaign",
    "ym:s:UTMContent",
]


def _metrics(goal_cart: str, goal_form: str) -> list[str]:
    return [
        "ym:s:visits",
        "ym:s:users",
        "ym:s:bounceRate",
        "ym:s:robotPercentage",
        f"ym:s:goal{goal_cart}reaches",
        f"ym:s:goal{goal_form}reaches",
    ]


def fetch(start: str, end: str) -> pd.DataFrame:
    load_dotenv()
    token = os.environ["METRIKA_TOKEN"]
    counter = os.environ["METRIKA_COUNTER_ID"]
    metrics = _metrics(os.environ["METRIKA_GOAL_ADD_TO_CART"], os.environ["METRIKA_GOAL_FORM_SUBMIT"])

    params = {
        "ids": counter,
        "date1": start,
        "date2": end,
        "dimensions": ",".join(DIMENSIONS),
        "metrics": ",".join(metrics),
        "accuracy": "full",
        # Роботов не исключаем: их долю анализируем отдельно
        "attribution": "lastsign",
        "limit": PAGE_SIZE,
    }
    headers = {"Authorization": f"OAuth {token}"}

    rows, offset = [], 1
    while True:
        resp = requests.get(API_URL, params={**params, "offset": offset}, headers=headers, timeout=60)
        if resp.status_code == 429:
            time.sleep(5)
            continue
        resp.raise_for_status()
        payload = resp.json()
        for item in payload["data"]:
            dims = [d.get("name") for d in item["dimensions"]]
            rows.append(dims + item["metrics"])
        if offset + PAGE_SIZE > payload["total_rows"]:
            break
        offset += PAGE_SIZE

    df = pd.DataFrame(rows, columns=METRIKA_COLUMNS)
    df["bounce_rate"] = df["bounce_rate"] / 100
    df["robot_share"] = df["robot_share"] / 100
    for col in ["visits", "users", "add_to_cart", "form_submit"]:
        df[col] = df[col].astype(int)
    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", default="data/raw/metrika_visits.csv")
    args = parser.parse_args()
    df = fetch(args.start, args.end)
    df.to_csv(args.out, index=False)
    print(f"Выгружено строк: {len(df)} → {args.out}")


if __name__ == "__main__":
    main()
