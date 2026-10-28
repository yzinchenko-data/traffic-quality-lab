# %% [markdown]
# # Анализ качества трафика: весь код по шагам
#
# Один файл без импортов из `src/`: всё, что делает пайплайн, расписано подряд.
# Ячейки `# %%` запускаются по одной в VS Code / PyCharm / Jupyter, либо целиком:
#
#     python practice/analysis_walkthrough.py
#
# Порядок:
#   0. Данные
#   1. DSP: дубли
#   2. Верификатор: «Итого», даты, пропущенные дни
#   3. Метрика: UTM, роботы, агрегация
#   4. Витрина: склейка трёх источников
#   5. Доли и срезы
#   6. Итог за период и средние по дням
#   7. Аномалии: robust z, периоды, STL
#   8. Конверсии: интервал Уилсона, хи-квадрат, целей больше визитов
#   9. Сверка с ground truth
#   10. Задания для практики

# %%
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, norm
from statsmodels.tsa.seasonal import STL

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 30)

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
START, END = "2026-09-01", "2026-09-30"
KEYS = ["date", "ssp", "placement"]

# %% [markdown]
# ## 0. Данные
#
# Если папки `data/raw` нет, генерируем её симулятором проекта.
# Получится 4 файла:
# - `dsp_clicks.csv` — клики DSP (даты YYYY-MM-DD, есть дубли);
# - `verifier_export.csv` — Верификатор (разделитель `;`, даты ДД.ММ.ГГГГ, строка «Итого», пропущен день);
# - `metrika_visits.csv` — визиты и цели из Метрики (UTM в разном написании);
# - `ground_truth.json` — что вшито, для проверки в конце.

# %%
if not (RAW / "metrika_visits.csv").exists():
    subprocess.run([sys.executable, "-m", "src.pipeline"], cwd=ROOT, check=True)

dsp_raw = pd.read_csv(RAW / "dsp_clicks.csv")
verifier_raw = pd.read_csv(RAW / "verifier_export.csv", sep=";")
metrika_raw = pd.read_csv(RAW / "metrika_visits.csv")
truth = json.loads((RAW / "ground_truth.json").read_text(encoding="utf-8"))

print(dsp_raw.head(), "\n")
print(verifier_raw.tail(3), "\n")
print(metrika_raw.head())

# %% [markdown]
# ## 1. DSP: дубли
#
# `duplicated()` помечает строку, если точно такая же уже встречалась выше.
# Дубли удаляем и запоминаем, сколько их было: это пойдёт в отчёт о чистке.

# %%
cleaning_log = []

n_dups = int(dsp_raw.duplicated().sum())
cleaning_log.append({"source": "DSP", "issue": "полные дубли строк", "rows": n_dups, "detail": "удалены"})

dsp = (
    dsp_raw.drop_duplicates()
    .rename(columns={"Дата": "date", "SSP": "ssp", "Площадка": "placement", "Клики": "dsp_clicks"})
    .assign(date=lambda d: pd.to_datetime(d["date"], format="%Y-%m-%d"))
    [KEYS + ["dsp_clicks"]]
    .reset_index(drop=True)
)
print(f"Дублей: {n_dups}, строк после чистки: {len(dsp)}")

# %% [markdown]
# ## 2. Верификатор: «Итого», даты, пропущенные дни
#
# - Строку «Итого» отрезаем от данных, но используем для сверки: сумма строк должна совпасть с ней.
# - Дата в формате ДД.ММ.ГГГГ, поэтому `format="%d.%m.%Y"`.
# - Пропущенные дни ищем разницей между полным календарём периода и датами в выгрузке.

# %%
total_row = verifier_raw[verifier_raw["Дата"] == "Итого"]
body = verifier_raw[verifier_raw["Дата"] != "Итого"].copy()
cleaning_log.append({"source": "Верификатор", "issue": "строка «Итого»", "rows": 1, "detail": "убрана, использована для сверки"})

for col in ["Кликов всего с учётом IVT", "GIVT", "SIVT", "Чистые клики"]:
    expected, actual = int(total_row[col].iloc[0]), int(body[col].sum())
    status = "OK" if expected == actual else "РАСХОЖДЕНИЕ"
    print(f"{col:28} строки = {actual:>7}  Итого = {expected:>7}  {status}")

verifier = body.rename(
    columns={
        "Дата": "date",
        "SSP": "ssp",
        "Площадка": "placement",
        "Кликов всего с учётом IVT": "verifier_total",
        "GIVT": "givt",
        "SIVT": "sivt",
        "Чистые клики": "clean_clicks",
    }
)
verifier["date"] = pd.to_datetime(verifier["date"], format="%d.%m.%Y")
num_cols = ["verifier_total", "givt", "sivt", "clean_clicks"]
verifier[num_cols] = verifier[num_cols].astype(int)
verifier = verifier[KEYS + num_cols].reset_index(drop=True)

calendar = pd.date_range(START, END, freq="D")
missing = calendar.difference(pd.DatetimeIndex(verifier["date"].unique()))
cleaning_log.append(
    {"source": "Верификатор", "issue": "пропущенные даты", "rows": len(missing),
     "detail": ", ".join(d.strftime("%Y-%m-%d") for d in missing)}
)
print("\nНет у Верификатора:", list(missing.strftime("%d.%m")))

# %% [markdown]
# ## 3. Метрика: UTM, роботы, агрегация
#
# Нормализация UTM: `'SSP_A'`, `'ssp_a '`, `'ssp-a'`, `'ssp_a?ref=feed'` → `'ssp_a'`.
# Порядок: обрезать пробелы → нижний регистр → отрезать всё после `?` → дефис в подчёркивание.
#
# Из доли роботов и доли отказов получаем количества. Округляем через `floor(x + 0.5)`:
# `round()` в pandas округляет половинки к чётному (2.5 → 2), а SQL — от нуля (2.5 → 3),
# и тогда Python и SQL разойдутся на единицу.


# %%
def normalize_utm(value: str) -> str:
    return str(value).strip().lower().split("?")[0].replace("-", "_")


normalized = metrika_raw["utm_source"].map(normalize_utm)
changed = normalized != metrika_raw["utm_source"]
cleaning_log.append(
    {"source": "Метрика", "issue": "UTM-метки в разном написании", "rows": int(changed.sum()),
     "detail": ", ".join(sorted(map(repr, set(metrika_raw.loc[changed, "utm_source"]))))}
)

metrika = metrika_raw.assign(
    ssp=normalized,
    placement=metrika_raw["utm_content"].map(normalize_utm),
    date=pd.to_datetime(metrika_raw["date"], format="%Y-%m-%d"),
)
metrika["robots"] = np.floor(metrika["visits"] * metrika["robot_share"] + 0.5).astype(int)
metrika["bounces"] = np.floor(metrika["visits"] * metrika["bounce_rate"] + 0.5).astype(int)

# После нормализации одна SSP могла разбиться на несколько строк в день — схлопываем
metrika = metrika.groupby(KEYS, as_index=False)[["visits", "users", "robots", "bounces", "add_to_cart", "form_submit"]].sum()

print(pd.DataFrame(cleaning_log).to_string(index=False))

# %% [markdown]
# ## 4. Витрина: склейка трёх источников
#
# Основа — DSP (в нём все дни). Верификатор и Метрику присоединяем `how="left"`,
# поэтому день без Верификатора остаётся строкой с NaN, а не пропадает.
#
# Ключевая деталь: расхождение DSP / Верификатор и доходимость от Верификатора считаем
# только по дням, где Верификатор есть. Для этого заводим `dsp_clicks_matched` и `visits_matched`.
# Без этого за период выходило 6,85% расхождения вместо 3,23%: клики DSP за 08.09
# попадали в числитель, а сравнивать их было не с чем.

# %%
mart = (
    dsp.merge(verifier, on=KEYS, how="left")
    .merge(metrika, on=KEYS, how="left")
    .sort_values(KEYS)
    .reset_index(drop=True)
)
has_verifier = mart["verifier_total"].notna()
mart["dsp_clicks_matched"] = mart["dsp_clicks"].where(has_verifier)
mart["visits_matched"] = mart["visits"].where(has_verifier)

print(mart.shape)
print(mart[mart["date"] == "2026-09-08"].head(3))

# %% [markdown]
# ## 5. Доли и срезы
#
# Доли всегда считаем из сумм среза: доходимость SSP за день = сумма визитов / сумма кликов
# по всем её площадкам. Среднее из долей площадок дало бы другой (неправильный) ответ,
# потому что площадки разного размера.
#
# - доходимость от DSP = визиты / клики DSP
# - доходимость от Верификатора = визиты / «Кликов всего с учётом IVT»
# - расхождение DSP / Верификатор, % = (DSP − Верификатор) / Верификатор × 100
#
# Деление на ноль: `b.where(b != 0)` превращает нули в NaN, и результат тоже NaN.


# %%
def div(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a / b.where(b != 0)).round(4)


def add_rates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["reach_dsp"] = div(df["visits"], df["dsp_clicks"])
    df["reach_verifier"] = div(df["visits_matched"], df["verifier_total"])
    df["dsp_vs_verifier_pct"] = (div(df["dsp_clicks_matched"] - df["verifier_total"], df["verifier_total"]) * 100).round(2)
    df["givt_share"] = div(df["givt"], df["verifier_total"])
    df["robot_share"] = div(df["robots"], df["visits"])
    df["cr_cart"] = div(df["add_to_cart"], df["visits"])
    df["cr_form"] = div(df["form_submit"], df["visits"])
    return df


SUM_COLS = ["dsp_clicks", "dsp_clicks_matched", "verifier_total", "givt", "sivt", "clean_clicks",
            "visits", "visits_matched", "robots", "add_to_cart", "form_submit"]


def rollup(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    # min_count=1: если в группе все значения NaN, сумма тоже NaN, а не 0.
    # Иначе день без Верификатора показал бы 0 кликов и доходимость «бесконечность».
    out = df.groupby(by, as_index=False)[SUM_COLS].sum(min_count=1)
    return add_rates(out)


mart = add_rates(mart)
daily_ssp = rollup(mart, ["date", "ssp"])
daily_placement = rollup(mart, ["date", "placement"])

print(daily_ssp[["date", "ssp", "dsp_clicks", "verifier_total", "visits", "reach_verifier", "dsp_vs_verifier_pct"]].head(6))

# %% [markdown]
# ## 6. Итог за период и средние по дням
#
# Две разные цифры, и обе нужны в отчёте:
# - доходимость за период — из сумм за все дни;
# - средняя дневная — среднее арифметическое дневных значений (каждый день весит одинаково).
#
# Строка «Итого» — тот же расчёт, где все SSP склеены в одну группу.

# %%
by_ssp = rollup(mart, ["ssp"])
total = rollup(mart.assign(ssp="Итого"), ["ssp"])
summary = pd.concat([by_ssp, total], ignore_index=True)

avg = daily_ssp.groupby("ssp")[["reach_verifier", "dsp_vs_verifier_pct"]].mean()
avg.loc["Итого"] = rollup(mart, ["date"])[["reach_verifier", "dsp_vs_verifier_pct"]].mean()
avg = avg.round(4).rename(columns={"reach_verifier": "avg_daily_reach", "dsp_vs_verifier_pct": "avg_daily_gap_pct"})
summary = summary.merge(avg, left_on="ssp", right_index=True)

print(summary[["ssp", "dsp_clicks", "verifier_total", "visits", "reach_verifier", "avg_daily_reach",
               "dsp_vs_verifier_pct", "avg_daily_gap_pct"]].to_string(index=False))

# %% [markdown]
# ## 7. Аномалии: robust z, периоды, STL
#
# **robust z** = (x − медиана) / (MAD × 1.4826), где MAD — медиана модулей отклонений от медианы.
# Множитель 1.4826 делает MAD сравнимым со стандартным отклонением нормального распределения.
#
# Почему не обычный z = (x − среднее) / σ: три дня провала тянут вниз среднее и раздувают σ,
# и провал «прячется» в собственной норме. Медиана и MAD от нескольких выбросов почти не сдвигаются.
#
# Порог 3.5. Для доходимости ищем провалы (z < −3.5), для GIVT — всплески (z > 3.5).

# %%
MAD_SCALE = 1.4826
Z_THRESHOLD = 3.5


def robust_z(s: pd.Series) -> pd.Series:
    median = s.median()
    mad = (s - median).abs().median() * MAD_SCALE
    if not mad or np.isnan(mad):
        return pd.Series(0.0, index=s.index)
    return (s - median) / mad


def detect(daily: pd.DataFrame, group: str, metric: str, direction: str) -> pd.DataFrame:
    frames = []
    for key, part in daily.groupby(group):
        s = part.set_index("date")[metric].sort_index()
        frames.append(pd.DataFrame({"date": s.index, group: key, metric: s.values, "z": robust_z(s).values}))
    out = pd.concat(frames, ignore_index=True)
    sign = -1 if direction == "low" else 1
    out["flag"] = sign * out["z"] > Z_THRESHOLD
    return out


reach_flags = detect(daily_ssp, "ssp", "reach_verifier", "low")
givt_flags = detect(daily_placement, "placement", "givt_share", "high")

print(reach_flags[reach_flags["flag"]])
print(givt_flags[givt_flags["flag"]])

# %% [markdown]
# ### Склейка подряд идущих дней в периоды («gaps and islands»)
#
# Даты отсортированы. Если разница с предыдущей датой не 1 день — начинается новый период.
# `cumsum()` по признаку «новый период» даёт номер периода для каждой даты.
#
#     даты:          12.09  13.09  14.09  22.09  23.09
#     diff (дни):    NaN    1      1      8      1
#     != 1:          True   False  False  True   False
#     cumsum:        1      1      1      2      2


# %%
def windows(flags: pd.DataFrame, group: str) -> pd.DataFrame:
    rows = []
    for key, part in flags[flags["flag"]].groupby(group):
        dates = part["date"].sort_values()
        run_id = (dates.diff().dt.days != 1).cumsum()
        for _, run in dates.groupby(run_id):
            rows.append({"slice": key, "start": run.min(), "end": run.max(), "days": len(run)})
    return pd.DataFrame(rows, columns=["slice", "start", "end", "days"])


anomaly_windows = pd.concat(
    [windows(reach_flags, "ssp").assign(kind="reach"), windows(givt_flags, "placement").assign(kind="givt")],
    ignore_index=True,
)
print(anomaly_windows)

# %% [markdown]
# ### STL: тренд и недельная сезонность
#
# STL раскладывает ряд на тренд + сезонность (период 7 дней) + остаток. Здесь он нужен для графика
# тренда, а не для флагов: на 30 точках robust-остаток почти нулевой, и любое колебание
# превращается в «аномалию». Пропуск 08.09 перед разложением заполняем интерполяцией.

# %%
ssp_b = daily_ssp[daily_ssp["ssp"] == "ssp_b"].set_index("date")["reach_verifier"].interpolate(limit_direction="both")
stl = STL(ssp_b, period=7, robust=True).fit()
print(pd.DataFrame({"reach": ssp_b, "trend": stl.trend, "seasonal": stl.seasonal}).round(3).iloc[9:17])

# %% [markdown]
# ### Связь двух аномалий
#
# Провал доходимости ssp_c 22–24.09 не вшивался отдельно. Он следствие роста GIVT на mobile_feed
# (площадка ssp_c): GIVT входит в «Кликов всего с учётом IVT», то есть в знаменатель доходимости,
# но до сайта не доходит. Проверяем пересечение периодов по датам.

# %%
ssp_of = mart.drop_duplicates("placement").set_index("placement")["ssp"]
givt_w = anomaly_windows[anomaly_windows["kind"] == "givt"]
for w in anomaly_windows[anomaly_windows["kind"] == "reach"].itertuples():
    overlap = givt_w[(givt_w["slice"].map(ssp_of) == w.slice) & (givt_w["start"] <= w.end) & (givt_w["end"] >= w.start)]
    reason = f"совпадает с ростом GIVT на {', '.join(overlap['slice'])}" if len(overlap) else "отдельный провал"
    print(f"{w.slice} {w.start:%d.%m}–{w.end:%d.%m}: {reason}")

# %% [markdown]
# ## 8. Конверсии
#
# ### Целей больше, чем визитов
# Такая строка — отдельная находка (двойное срабатывание тега, кривая настройка цели).
# В расчёт CR её не берём, иначе она исказит конверсию всей SSP.

# %%
goals_over = mart.loc[mart["form_submit"] > mart["visits"], ["date", "ssp", "placement", "visits", "form_submit"]]
print(goals_over)

# %% [markdown]
# ### Интервал Уилсона
#
# Для доли p = x / n обычный интервал p ± z·√(p(1−p)/n) врёт на малых n и долях около 0.
# Интервал Уилсона:
#
#     центр = (p + z²/2n) / (1 + z²/n)
#     полуширина = z · √(p(1−p)/n + z²/4n²) / (1 + z²/n)
#
# z = 1.96 для 95%.


# %%
def wilson(x: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    if n == 0:
        return (np.nan, np.nan)
    z = norm.ppf(1 - (1 - conf) / 2)
    p = x / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (round(centre - half, 4), round(centre + half, 4))


for goal in ["add_to_cart", "form_submit"]:
    # Убираем только строки, где сломана именно эта цель: корзина 17.09 на weather_app в порядке
    valid = mart[mart[goal] <= mart["visits"]]
    g = valid.groupby("ssp")[["visits", goal]].sum()
    g["cr"] = (g[goal] / g["visits"]).round(4)
    g[["ci_low", "ci_high"]] = [wilson(int(r[goal]), int(r["visits"])) for _, r in g.iterrows()]

    # Хи-квадрат: таблица «достигли цели / не достигли» × SSP.
    # p < 0.05 — конверсии SSP различаются значимо.
    table = np.column_stack([g[goal], g["visits"] - g[goal]])
    chi2, p_value, dof, _ = chi2_contingency(table)
    print(f"\n{goal}: хи-квадрат = {chi2:.3f}, df = {dof}, p = {p_value:.4f}")
    print(g)

# %% [markdown]
# ## 9. Сверка с ground truth
#
# Симулятор записал, что вшито. Проверяем, что анализ нашёл ровно это.

# %%
for a in truth["anomalies"]:
    if a["type"] == "reach_drop":
        w = anomaly_windows[(anomaly_windows["kind"] == "reach") & (anomaly_windows["slice"] == a["ssp"])]
        ok = len(w) == 1 and w.iloc[0]["start"] == pd.Timestamp(a["start"]) and w.iloc[0]["end"] == pd.Timestamp(a["end"])
    elif a["type"] == "high_givt":
        w = anomaly_windows[(anomaly_windows["kind"] == "givt") & (anomaly_windows["slice"] == a["placement"])]
        ok = len(w) == 1 and w.iloc[0]["start"] == pd.Timestamp(a["start"]) and w.iloc[0]["end"] == pd.Timestamp(a["end"])
    elif a["type"] == "goal_spike":
        ok = ((goals_over["placement"] == a["placement"]) & (goals_over["date"] == pd.Timestamp(a["date"]))).any()
    elif a["type"] == "duplicates":
        ok = n_dups == a["rows"]
    elif a["type"] == "missing_date":
        ok = [d.strftime("%Y-%m-%d") for d in missing] == [a["date"]]
    elif a["type"] == "utm_noise":
        ok = set(a["variants"]) <= set(metrika_raw["utm_source"]) and set(metrika["ssp"]) == set(dsp["ssp"])
    print(f"{'✓' if ok else '✗'} {a['id']}")

# %% [markdown]
# ## 10. Задания для практики
#
# Решай в новых ячейках под этой. Ответы проверяй, перезапустив весь файл.
#
# 1. Посчитай доходимость от Верификатора по площадкам за период. Какая площадка самая низкая?
# 2. Посчитай среднее расхождение DSP / Верификатор отдельно по будням и выходным
#    (`date.dt.dayofweek >= 5`). Есть разница?
# 3. Замени robust z на обычный z = (x − mean) / std с порогом 3. Найдётся ли провал ssp_b 12–14.09?
#    Почему (подсказка: что три дня провала делают со средним и std)?
# 4. Подбери порог robust z, при котором пропадает просадка ssp_c 22–24.09, но остаётся ssp_b.
# 5. Посчитай доходимость ssp_b за период без дней 12–14.09. Насколько провал снизил итог?
# 6. Найди день с максимальной роботностью по каждой SSP.
# 7. Добавь в `add_rates` долю отказов `bounce_share = bounces / visits` и выведи её по SSP.
# 8. Построй график `reach_verifier` по ssp_b вместе с трендом STL (matplotlib, 2 линии).
# 9. Сделай то же, что шаг 4, в DuckDB: `duckdb.sql("SELECT ... FROM dsp LEFT JOIN verifier ...")`
#    прямо по pandas-таблицам (DuckDB видит переменные Python по имени) и сравни с `mart`.
# 10. Поменяй в `scenarios.yaml` даты провала ssp_b, перезапусти `make report` и этот файл.
#     Все строки шага 9 должны остаться с ✓.
