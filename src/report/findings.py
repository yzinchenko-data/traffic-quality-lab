"""Текст выводов в стиле комментария аналитика: цифры, периоды, что рекомендуем проверить."""

from __future__ import annotations

import pandas as pd

PLACEMENT_SSP_NOTE = "доходимость от Верификатора = визиты / «Кликов всего с учётом IVT»"


def _pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%".replace(".", ",")


def _n(x: float) -> str:
    return f"{int(x):,}".replace(",", " ")


def _d(ts) -> str:
    return pd.Timestamp(ts).strftime("%d.%m")


def render(res) -> str:
    s = res.summary.set_index("ssp")
    total = s.loc["Итого"]
    lines = [
        f"# Выводы по кампании {res.cfg['campaign']}",
        "",
        f"Период: {pd.Timestamp(str(res.cfg['start'])).strftime('%d.%m.%Y')} – "
        f"{pd.Timestamp(str(res.cfg['end'])).strftime('%d.%m.%Y')}. Данные синтетические.",
        "",
        "## Итого за период",
        "",
        "| SSP | Клики DSP | Клики Верификатора | Визиты | Доходимость от Верификатора | Средняя по дням | Расхождение DSP / Верификатор |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for ssp, r in s.iterrows():
        name = f"**{ssp}**" if ssp == "Итого" else ssp
        lines.append(
            f"| {name} | {_n(r.dsp_clicks)} | {_n(r.verifier_total)} | {_n(r.visits)} | "
            f"{_pct(r.reach_verifier)} | {_pct(r.avg_daily_reach)} | {_pct(r.dsp_vs_verifier_pct / 100, 2)} |"
        )
    lines += [
        "",
        f"Расхождение DSP и Верификатора считается по дням, которые есть в обеих выгрузках; {PLACEMENT_SSP_NOTE}.",
        "",
        "## Что нашли",
        "",
    ]

    ssp_of = res.mart.drop_duplicates("placement").set_index("placement")["ssp"]
    givt_windows = res.windows[res.windows["kind"] == "givt"]

    n = 1
    for _, w in res.windows[res.windows["kind"] == "reach"].iterrows():
        flags = res.reach_flags
        part = flags[(flags["ssp"] == w.slice) & flags["date"].between(w.start, w.end)]
        rest = flags[(flags["ssp"] == w.slice) & ~flags["date"].between(w.start, w.end)]
        overlap = givt_windows[
            (givt_windows["slice"].map(ssp_of) == w.slice)
            & (givt_windows["start"] <= w.end)
            & (givt_windows["end"] >= w.start)
        ]
        if overlap.empty:
            note = "Рекомендуем проверить загрузку посадочной страницы и редиректы в эти даты."
        else:
            names = ", ".join(overlap["slice"])
            note = (
                f"Даты совпадают с ростом GIVT на {names}: GIVT входит в «Кликов всего с учётом IVT», "
                f"но не доходит до сайта."
            )
        lines.append(
            f"{n}. **Доходимость {w.slice}, {_d(w.start)}–{_d(w.end)}**: "
            f"{_pct(part.reach_verifier.min())}–{_pct(part.reach_verifier.max())} "
            f"при средней {_pct(rest.reach_verifier.mean())} в остальные дни по этой SSP. {note}"
        )
        n += 1
    for _, w in res.windows[res.windows["kind"] == "givt"].iterrows():
        flags = res.givt_flags
        part = flags[(flags["placement"] == w.slice) & flags["date"].between(w.start, w.end)]
        rest = flags[(flags["placement"] == w.slice) & ~flags["date"].between(w.start, w.end)]
        lines.append(
            f"{n}. **GIVT на площадке {w.slice}, {_d(w.start)}–{_d(w.end)}**: "
            f"доля GIVT {_pct(part.givt_share.min())}–{_pct(part.givt_share.max())} "
            f"при средней {_pct(rest.givt_share.mean())} в остальные дни ({ssp_of[w.slice]})."
        )
        n += 1
    for _, g in res.goals_over.iterrows():
        lines.append(
            f"{n}. **Цель {g.goal} на {g.placement}, {_d(g.date)}**: достижений цели {g.reaches}, визитов {g.visits}. "
            f"Рекомендуем проверить настройку цели и срабатывание тега в GTM."
        )
        n += 1

    lines += ["", "## Конверсии в цели (95% интервал Уилсона)", ""]
    for goal, table in res.cr.items():
        chi = next(c for c in res.chi2 if c["goal"] == goal)
        parts = [f"{r.ssp} {_pct(r.cr, 2)} [{_pct(r.ci_low, 2)}; {_pct(r.ci_high, 2)}]" for r in table.itertuples()]
        verdict = "различие между SSP значимо" if chi["p_value"] < 0.05 else "значимого различия между SSP нет"
        lines.append(
            f"- **{goal}**: {', '.join(parts)}. Хи-квадрат p = {str(chi['p_value']).replace('.', ',')}: {verdict}."
        )

    lines += ["", "## Чистка данных", "", "| Источник | Что поправлено | Строк | Детали |", "|---|---|---:|---|"]
    for r in res.cleaning.to_frame().itertuples():
        lines.append(f"| {r.source} | {r.issue} | {r.rows} | {r.detail.replace(' | ', ', ')} |")

    lines += [
        "",
        f"Сверка с «Итого» Верификатора: {'совпадает' if res.sql['check_verifier_total'].empty else 'есть расхождение'}. "
        f"Клики DSP за период: {_n(total.dsp_clicks)}.",
        "",
    ]
    return "\n".join(lines)
