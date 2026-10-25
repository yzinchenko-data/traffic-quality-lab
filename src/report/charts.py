"""Графики для README и отчёта."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import PercentFormatter

PALETTE = ["#0F766E", "#2563EB", "#D97706", "#7C3AED", "#DB2777"]
ANOMALY = "#DC2626"


def _style(ax, title: str) -> None:
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", color="#1F2937", pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#D0D5DD")
    ax.tick_params(colors="#475467", labelsize=9)
    ax.grid(axis="y", color="#EAECF0", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))


def _shade(ax, windows: pd.DataFrame) -> None:
    for w in windows.itertuples():
        ax.axvspan(w.start - pd.Timedelta(hours=12), w.end + pd.Timedelta(hours=12), color=ANOMALY, alpha=0.08, lw=0)


def reach_chart(res, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 4.6), dpi=150)
    for color, (ssp, part) in zip(PALETTE, res.reach_flags.groupby("ssp")):
        ax.plot(part["date"], part["reach_verifier"], color=color, lw=2, label=ssp, marker="o", ms=3)
        flagged = part[part["flag"]]
        ax.scatter(
            flagged["date"], flagged["reach_verifier"], s=70, facecolor="none", edgecolor=ANOMALY, lw=1.8, zorder=5
        )
    _shade(ax, res.windows[res.windows["kind"] == "reach"])
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_ylim(0, 1)
    _style(ax, "Доходимость от Верификатора по SSP: визиты / «Кликов всего с учётом IVT»")
    ax.legend(frameon=False, ncol=3, loc="lower left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def givt_chart(res, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 4.6), dpi=150)
    for color, (placement, part) in zip(PALETTE, res.givt_flags.groupby("placement")):
        ax.plot(part["date"], part["givt_share"], color=color, lw=1.8, label=placement)
    flagged = res.givt_flags[res.givt_flags["flag"]]
    ax.scatter(flagged["date"], flagged["givt_share"], s=70, facecolor="none", edgecolor=ANOMALY, lw=1.8, zorder=5)
    _shade(ax, res.windows[res.windows["kind"] == "givt"])
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    _style(ax, "Доля GIVT по площадкам")
    ax.legend(frameon=False, ncol=5, loc="upper left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def gap_chart(res, path: Path) -> None:
    total = res.daily_ssp.groupby("date", as_index=False)[["dsp_clicks_matched", "verifier_total"]].sum(min_count=1)
    total["gap"] = (total["dsp_clicks_matched"] - total["verifier_total"]) / total["verifier_total"] * 100
    fig, ax = plt.subplots(figsize=(11, 3.8), dpi=150)
    ax.bar(total["date"], total["gap"], color=PALETTE[1], width=0.7)
    missing = total[total["verifier_total"].isna()]
    for d in missing["date"]:
        ax.annotate("нет данных\nВерификатора", (d, 0.2), ha="center", fontsize=8, color=ANOMALY)
    mean = total["gap"].mean()
    ax.axhline(mean, color="#1F2937", lw=1, ls="--")
    ax.text(total["date"].max(), mean, f"  среднее {mean:.1f}%", va="bottom", ha="right", fontsize=9)
    _style(ax, "Расхождение кликов DSP и Верификатора по дням, %")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def funnel_chart(res, path: Path) -> None:
    t = res.summary.set_index("ssp").loc["Итого"]
    stages = [
        ("Клики DSP", t.dsp_clicks_matched),
        ("Кликов всего\nс учётом IVT", t.verifier_total),
        ("Визиты", t.visits_matched),
        ("Цель: корзина", t.add_to_cart),
        ("Цель: форма", t.form_submit),
    ]
    fig, ax = plt.subplots(figsize=(11, 3.8), dpi=150)
    labels, values = zip(*stages)
    bars = ax.barh(labels[::-1], values[::-1], color=PALETTE[0])
    for bar, v in zip(bars, values[::-1]):
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f"  {int(v):,}".replace(",", " "),
            va="center",
            fontsize=9,
        )
    ax.set_title(
        "Воронка за период (клики и визиты — по дням с данными Верификатора)",
        loc="left",
        fontsize=13,
        fontweight="bold",
        color="#1F2937",
    )
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    ax.set_xticks([])
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def render_all(res, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    plots = {
        "reach.png": reach_chart,
        "givt.png": givt_chart,
        "dsp_vs_verifier.png": gap_chart,
        "funnel.png": funnel_chart,
    }
    paths = []
    for name, fn in plots.items():
        fn(res, out_dir / name)
        paths.append(out_dir / name)
    return paths
