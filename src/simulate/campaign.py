"""Симулятор рекламной кампании.

Пишет три файла и эталон:
  dsp_clicks.csv       — выгрузка DSP: клики по дням, SSP, площадкам (ISO-даты, есть дубли)
  verifier_export.csv  — выгрузка Верификатора: «Кликов всего с учётом IVT», GIVT, SIVT,
                         даты ДД.ММ.ГГГГ, строка «Итого», один день пропущен
  visit_plan.csv       — план визитов для бота-посетителя: сколько визитов и целей, какие UTM
  ground_truth.json    — какие аномалии вшиты и какие значения метрик они дают

Запуск:
  python -m src.simulate.campaign --config scenarios.yaml --out data/synthetic
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


@dataclass
class Window:
    start: pd.Timestamp
    end: pd.Timestamp

    def contains(self, d: pd.Timestamp) -> bool:
        return self.start <= d <= self.end


def _ts(value) -> pd.Timestamp:
    return pd.Timestamp(value.isoformat() if isinstance(value, date) else value)


def load_config(path: str | Path, end: str | None = None) -> dict:
    """Читает сценарии. end (или переменная TQL_END) сдвигает весь календарь кампании
    так, чтобы она кончалась этой датой: today, yesterday или YYYY-MM-DD.
    Нужно для живого режима: бот пишет визиты в Метрику на дату запуска."""
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    end = end or os.environ.get("TQL_END")
    return shift_calendar(cfg, resolve_date(end)) if end else cfg


def resolve_date(value: str) -> date:
    today = date.today()
    return {"today": today, "yesterday": today - timedelta(days=1)}.get(value) or date.fromisoformat(value)


def shift_calendar(cfg: dict, end: date) -> dict:
    # Сдвиг на целое число недель: дни недели не меняются, а с ними и выходные,
    # поэтому вшитые аномалии находятся так же, как в исходном календаре.
    # Кампания кончается в последний день не позже end с тем же днём недели.
    delta = timedelta(weeks=(end - _ts(cfg["end"]).date()).days // 7)
    out = dict(cfg)
    for key in ("start", "end"):
        out[key] = _ts(cfg[key]).date() + delta
    out["anomalies"] = [
        {k: (_ts(v).date() + delta if k in ("start", "end", "date") else v) for k, v in a.items()}
        for a in cfg.get("anomalies", [])
    ]
    return out


def _anomalies(cfg: dict, kind: str) -> list[dict]:
    return [a for a in cfg.get("anomalies", []) if a["type"] == kind]


def _window(a: dict) -> Window:
    if "date" in a:
        return Window(_ts(a["date"]), _ts(a["date"]))
    return Window(_ts(a["start"]), _ts(a["end"]))


def simulate_daily(cfg: dict) -> pd.DataFrame:
    """Чистая «правда» по дням × SSP × площадкам, до порчи файлов."""
    rng = np.random.default_rng(cfg["seed"])
    base = cfg["baseline"]
    dates = pd.date_range(_ts(cfg["start"]), _ts(cfg["end"]), freq="D")

    reach_drops = _anomalies(cfg, "reach_drop")
    givt_spikes = _anomalies(cfg, "high_givt")
    goal_spikes = _anomalies(cfg, "goal_spike")

    rows = []
    for d in dates:
        weekday_factor = base["weekend_factor"] if d.dayofweek >= 5 else 1.0
        for ssp, ssp_cfg in cfg["ssps"].items():
            for placement, daily in ssp_cfg["placements"].items():
                dsp_clicks = int(rng.poisson(daily * weekday_factor))

                gap = rng.uniform(*base["verifier_gap"])
                verifier_total = int(rng.binomial(dsp_clicks, 1 - gap))

                givt_rate = base["givt_rate"]
                for a in givt_spikes:
                    if a["placement"] == placement and _window(a).contains(d):
                        givt_rate = a["givt_rate"]
                givt = int(rng.binomial(verifier_total, givt_rate))
                sivt = int(rng.binomial(verifier_total - givt, base["sivt_rate"]))
                clean = verifier_total - givt - sivt

                reach = ssp_cfg["reach"]
                for a in reach_drops:
                    if a["ssp"] == ssp and _window(a).contains(d):
                        reach *= a["factor"]
                visits = int(rng.binomial(clean, reach))

                add_to_cart = int(rng.binomial(visits, base["add_to_cart_rate"]))
                form_submit = int(rng.binomial(visits, base["form_submit_rate"]))
                for a in goal_spikes:
                    if a["placement"] == placement and _window(a).contains(d):
                        if a["goal"] == "form_submit":
                            form_submit += a["extra"]
                        else:
                            add_to_cart += a["extra"]

                rows.append(
                    {
                        "date": d,
                        "ssp": ssp,
                        "placement": placement,
                        "dsp_clicks": dsp_clicks,
                        "verifier_total": verifier_total,
                        "givt": givt,
                        "sivt": sivt,
                        "clean_clicks": clean,
                        "visits": visits,
                        "add_to_cart": add_to_cart,
                        "form_submit": form_submit,
                    }
                )
    return pd.DataFrame(rows)


def build_dsp_export(daily: pd.DataFrame, cfg: dict, rng: np.random.Generator) -> tuple[pd.DataFrame, list[int]]:
    out = pd.DataFrame(
        {
            "Дата": daily["date"].dt.strftime("%Y-%m-%d"),
            "Кампания": cfg["campaign"],
            "SSP": daily["ssp"],
            "Площадка": daily["placement"],
            "Клики": daily["dsp_clicks"],
        }
    )
    dup_index: list[int] = []
    for a in _anomalies(cfg, "duplicates"):
        if a["file"] == "dsp_clicks":
            dup_index += sorted(rng.choice(len(out), size=a["rows"], replace=False).tolist())
    if dup_index:
        out = pd.concat([out, out.iloc[dup_index]]).sort_values(["Дата", "SSP", "Площадка"], kind="stable")
    return out.reset_index(drop=True), dup_index


def build_verifier_export(daily: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, list[str]]:
    missing = [_ts(a["date"]) for a in _anomalies(cfg, "missing_date") if a["file"] == "verifier_export"]
    kept = daily[~daily["date"].isin(missing)]
    out = pd.DataFrame(
        {
            "Дата": kept["date"].dt.strftime("%d.%m.%Y"),
            "SSP": kept["ssp"],
            "Площадка": kept["placement"],
            "Кликов всего с учётом IVT": kept["verifier_total"],
            "GIVT": kept["givt"],
            "SIVT": kept["sivt"],
            "Чистые клики": kept["clean_clicks"],
        }
    )
    total = {"Дата": "Итого", "SSP": "", "Площадка": ""}
    for col in ["Кликов всего с учётом IVT", "GIVT", "SIVT", "Чистые клики"]:
        total[col] = int(out[col].sum())
    out = pd.concat([out, pd.DataFrame([total])], ignore_index=True)
    return out, [d.strftime("%Y-%m-%d") for d in missing]


def build_visit_plan(daily: pd.DataFrame, cfg: dict, rng: np.random.Generator) -> pd.DataFrame:
    plan = daily[["date", "ssp", "placement", "visits", "add_to_cart", "form_submit"]].copy()
    plan["utm_source"] = plan["ssp"]
    plan["utm_medium"] = "cpc"
    plan["utm_campaign"] = cfg["campaign"]
    plan["utm_content"] = plan["placement"]
    for a in _anomalies(cfg, "utm_noise"):
        w = _window(a)
        mask = (plan["ssp"] == a["ssp"]) & plan["date"].between(w.start, w.end)
        plan.loc[mask, "utm_source"] = rng.choice(a["variants"], size=int(mask.sum()))
    plan["date"] = plan["date"].dt.strftime("%Y-%m-%d")
    return plan.drop(columns=["ssp", "placement"])


def _reach(df: pd.DataFrame) -> float:
    return round(df["visits"].sum() / df["clean_clicks"].sum(), 4)


def build_ground_truth(daily: pd.DataFrame, cfg: dict, dup_index: list[int], missing_dates: list[str]) -> dict:
    anomalies = []
    for a in cfg.get("anomalies", []):
        item = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in a.items()}
        if a["type"] == "reach_drop":
            w = _window(a)
            ssp_rows = daily[daily["ssp"] == a["ssp"]]
            inside = ssp_rows["date"].between(w.start, w.end)
            item["expected"] = {
                "reach_inside": _reach(ssp_rows[inside]),
                "reach_outside": _reach(ssp_rows[~inside]),
            }
        elif a["type"] == "high_givt":
            w = _window(a)
            rows = daily[daily["placement"] == a["placement"]]
            inside = rows["date"].between(w.start, w.end)
            share = lambda r: round(r["givt"].sum() / r["verifier_total"].sum(), 4)
            item["expected"] = {"givt_share_inside": share(rows[inside]), "givt_share_outside": share(rows[~inside])}
        elif a["type"] == "goal_spike":
            row = daily[(daily["placement"] == a["placement"]) & (daily["date"] == _ts(a["date"]))].iloc[0]
            item["expected"] = {"visits": int(row["visits"]), a["goal"]: int(row[a["goal"]])}
        elif a["type"] == "duplicates":
            item["expected"] = {"duplicated_row_index": dup_index}
        elif a["type"] == "missing_date":
            item["expected"] = {"missing_dates": missing_dates}
        anomalies.append(item)

    totals = daily[
        ["dsp_clicks", "verifier_total", "givt", "sivt", "clean_clicks", "visits", "add_to_cart", "form_submit"]
    ].sum()
    return {
        "campaign": cfg["campaign"],
        "period": [str(cfg["start"]), str(cfg["end"])],
        "seed": cfg["seed"],
        "totals_before_file_damage": {k: int(v) for k, v in totals.items()},
        "format_notes": {
            "dsp_clicks.csv": "даты YYYY-MM-DD, есть полные дубли строк",
            "verifier_export.csv": "даты DD.MM.YYYY, последняя строка «Итого», один день пропущен",
        },
        "anomalies": anomalies,
    }


def run(config_path: str | Path, out_dir: str | Path) -> dict:
    cfg = load_config(config_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    daily = simulate_daily(cfg)
    # Отдельный генератор для порчи файлов, чтобы смена дублей не сдвигала сами клики
    damage_rng = np.random.default_rng(cfg["seed"] + 1)

    dsp, dup_index = build_dsp_export(daily, cfg, damage_rng)
    verifier, missing = build_verifier_export(daily, cfg)
    plan = build_visit_plan(daily, cfg, damage_rng)
    truth = build_ground_truth(daily, cfg, dup_index, missing)

    dsp.to_csv(out / "dsp_clicks.csv", index=False)
    verifier.to_csv(out / "verifier_export.csv", index=False, sep=";")
    plan.to_csv(out / "visit_plan.csv", index=False)
    (out / "ground_truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
    return truth


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="scenarios.yaml")
    parser.add_argument("--out", default="data/synthetic")
    args = parser.parse_args()
    truth = run(args.config, args.out)
    print(f"Готово: {args.out}. Аномалий вшито: {len(truth['anomalies'])}")


if __name__ == "__main__":
    main()
