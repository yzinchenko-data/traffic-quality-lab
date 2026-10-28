"""Выгрузка отчёта в Google Sheets с той же подсветкой, что в Excel.

Нужен сервисный аккаунт Google (см. .env.example):
  GOOGLE_SERVICE_ACCOUNT_JSON — путь к ключу
  GOOGLE_SHEET_ID             — таблица, к которой у сервисного аккаунта есть доступ на редактирование
"""

from __future__ import annotations

import os

import gspread
import pandas as pd
from dotenv import load_dotenv

from src.report import sheet_tables

RED = {"red": 0.99, "green": 0.89, "blue": 0.88}
GREEN = {"red": 0.39, "green": 0.75, "blue": 0.48}
YELLOW = {"red": 1.0, "green": 0.92, "blue": 0.52}
CORAL = {"red": 0.97, "green": 0.41, "blue": 0.42}


def _prepare(df: pd.DataFrame) -> list[list]:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d")
    out = out.astype(object).where(out.notna(), "")
    return [list(out.columns)] + out.values.tolist()


def _upsert(sh: gspread.Spreadsheet, title: str, df: pd.DataFrame) -> gspread.Worksheet:
    try:
        ws = sh.worksheet(title)
        ws.clear()
        # Старые правила условного форматирования удаляем вместе с листом
        sh.del_worksheet(ws)
    except gspread.WorksheetNotFound:
        pass
    ws = sh.add_worksheet(title=title, rows=len(df) + 10, cols=len(df.columns) + 2)
    ws.update(_prepare(df), value_input_option="USER_ENTERED")
    ws.format(
        "1:1",
        {
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "backgroundColor": {"red": 0.06, "green": 0.46, "blue": 0.43},
        },
    )
    ws.freeze(rows=1)
    return ws


def _flag_rule(ws: gspread.Worksheet, df: pd.DataFrame) -> dict:
    flag_col = chr(ord("A") + list(df.columns).index("flag"))
    return {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [
                    {
                        "sheetId": ws.id,
                        "startRowIndex": 1,
                        "endRowIndex": len(df) + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(df.columns),
                    }
                ],
                "booleanRule": {
                    "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": f"=${flag_col}2=TRUE"}]},
                    "format": {"backgroundColor": RED, "textFormat": {"bold": True}},
                },
            },
            "index": 0,
        }
    }


def _scale_rule(ws: gspread.Worksheet, df: pd.DataFrame, col: str, reverse: bool = False) -> dict:
    idx = list(df.columns).index(col)
    low, high = (CORAL, GREEN) if not reverse else (GREEN, CORAL)
    return {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [
                    {
                        "sheetId": ws.id,
                        "startRowIndex": 1,
                        "endRowIndex": len(df) + 1,
                        "startColumnIndex": idx,
                        "endColumnIndex": idx + 1,
                    }
                ],
                "gradientRule": {
                    "minpoint": {"color": low, "type": "MIN"},
                    "midpoint": {"color": YELLOW, "type": "PERCENTILE", "value": "50"},
                    "maxpoint": {"color": high, "type": "MAX"},
                },
            },
            "index": 1,
        }
    }


def write(res) -> str:
    load_dotenv()
    gc = gspread.service_account(filename=os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    sh = gc.open_by_key(os.environ["GOOGLE_SHEET_ID"])

    tables = sheet_tables.build(res)
    ws = {name: _upsert(sh, title, tables[name]) for name, title in sheet_tables.SHEETS.items()}
    daily, givt = tables["daily_ssp"], tables["givt"]

    sh.batch_update(
        {
            "requests": [
                _flag_rule(ws["daily_ssp"], daily),
                _scale_rule(ws["daily_ssp"], daily, "reach_verifier"),
                _flag_rule(ws["givt"], givt),
                _scale_rule(ws["givt"], givt, "givt_share", reverse=True),
            ]
        }
    )
    return sh.url
