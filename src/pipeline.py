"""Весь пайплайн одной командой.

python -m src.pipeline                      # офлайн: симуляция → эмулятор Метрики → анализ → отчёт
python -m src.pipeline --source api         # визиты из настоящей Метрики (нужен .env)
python -m src.pipeline --sheets             # дополнительно выгрузить отчёт в Google Sheets
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src import sql_runner
from src.analysis import conversions, timeseries
from src.analysis.reach import build_mart, period_summary, rollup
from src.clean.loaders import CleaningReport, load_all
from src.extract import metrika_offline
from src.simulate import campaign

ROOT = Path(__file__).resolve().parent.parent
GOALS = ["add_to_cart", "form_submit"]


@dataclass
class Results:
    cfg: dict
    truth: dict
    mart: pd.DataFrame
    daily_ssp: pd.DataFrame
    daily_placement: pd.DataFrame
    summary: pd.DataFrame
    reach_flags: pd.DataFrame
    givt_flags: pd.DataFrame
    windows: pd.DataFrame
    goals_over: pd.DataFrame
    cr: dict[str, pd.DataFrame]
    chi2: list[dict]
    cleaning: CleaningReport
    sql: dict[str, pd.DataFrame]


def analyze(raw_dir: Path, cfg: dict, truth: dict) -> Results:
    start, end = str(cfg["start"]), str(cfg["end"])
    data, cleaning = load_all(raw_dir, start, end)
    mart = build_mart(data)

    daily_ssp = rollup(mart, ["date", "ssp"])
    daily_placement = rollup(mart, ["date", "placement"])
    reach_flags = timeseries.detect(daily_ssp, "ssp", "reach_verifier", "low")
    givt_flags = timeseries.detect(daily_placement, "placement", "givt_share", "high")

    windows = pd.concat(
        [
            timeseries.windows(reach_flags, "ssp").rename(columns={"ssp": "slice"}).assign(kind="reach"),
            timeseries.windows(givt_flags, "placement").rename(columns={"placement": "slice"}).assign(kind="givt"),
        ],
        ignore_index=True,
    )[["kind", "slice", "start", "end", "days"]]

    return Results(
        cfg=cfg,
        truth=truth,
        mart=mart,
        daily_ssp=daily_ssp,
        daily_placement=daily_placement,
        summary=period_summary(mart),
        reach_flags=reach_flags,
        givt_flags=givt_flags,
        windows=windows,
        goals_over=conversions.goals_over_visits(mart, GOALS),
        cr={g: conversions.by_ssp(mart, g) for g in GOALS},
        chi2=[conversions.chi_square(mart, g) for g in GOALS],
        cleaning=cleaning,
        sql=sql_runner.run(raw_dir, start, end),
    )


def run(config: Path, raw_dir: Path, out_dir: Path, source: str = "offline", sheets: bool = False) -> Results:
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    truth = campaign.run(config, raw_dir)
    cfg = campaign.load_config(config)
    if source == "offline":
        metrika_offline.run(raw_dir / "visit_plan.csv", raw_dir / "metrika_visits.csv")
    else:
        from src.extract import metrika_api

        visits = metrika_api.fetch(str(cfg["start"]), str(cfg["end"]))
        if visits.empty:
            raise SystemExit(
                f"Метрика вернула 0 визитов за {cfg['start']}–{cfg['end']}. "
                "Бот пишет визиты на дату запуска, а не на дату из плана: "
                "запусти с --end today (или сдвинь start/end в scenarios.yaml)."
            )
        visits.to_csv(raw_dir / "metrika_visits.csv", index=False)

    res = analyze(raw_dir, cfg, truth)

    # Импорты отчётов здесь, чтобы анализ работал и без matplotlib / openpyxl
    from src.report import charts, excel, findings, sheet_tables

    img_dir = ROOT / "docs" / "img"
    charts.render_all(res, img_dir)
    excel.write(res, out_dir / "traffic_quality_report.xlsx")
    (out_dir / "findings.md").write_text(findings.render(res), encoding="utf-8")
    (out_dir / "anomaly_windows.json").write_text(
        json.dumps(res.windows.astype(str).to_dict(orient="records"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # CSV для Apps Script: лист собирается из них в Google Sheets без ключей сервисного аккаунта
    sheet_tables.write_csv(res, ROOT / "exports" / "sheets")
    sheet_tables.write_datalens(res, ROOT / "datalens")
    if sheets:
        from src.report import sheets as gsheets

        gsheets.write(res)
    return res


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=ROOT / "scenarios.yaml")
    parser.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--out", type=Path, default=ROOT / "reports")
    parser.add_argument("--source", choices=["offline", "api"], default="offline")
    parser.add_argument("--sheets", action="store_true")
    parser.add_argument("--end", help="сдвинуть кампанию, чтобы она кончалась этой датой: today, yesterday, YYYY-MM-DD")
    args = parser.parse_args()
    if args.end:
        # через переменную окружения: её читают и симулятор, и анализ
        os.environ["TQL_END"] = args.end

    res = run(args.config, args.raw, args.out, args.source, args.sheets)
    print(f"Отчёт: {args.out / 'traffic_quality_report.xlsx'}")
    print(f"Выводы: {args.out / 'findings.md'}")
    print(f"Найдено периодов с аномалиями: {len(res.windows)}, строк «целей больше визитов»: {len(res.goals_over)}")


if __name__ == "__main__":
    main()
