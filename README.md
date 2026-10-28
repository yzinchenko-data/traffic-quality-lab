# Traffic Quality Lab

![python](https://img.shields.io/badge/python-3.11%2B-0F766E)
![sql](https://img.shields.io/badge/SQL-DuckDB-2563EB)
[![CI](https://github.com/yzinchenko-data/traffic-quality-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/yzinchenko-data/traffic-quality-lab/actions/workflows/ci.yml)
![data](https://img.shields.io/badge/data-100%25%20synthetic-D97706)
[![DataLens](https://img.shields.io/badge/дашборд-DataLens-FFCC00)](https://datalens.yandex/5eh8tse706g0o)
[![Sheets](https://img.shields.io/badge/отчёт-Google%20Sheets-34A853)](https://docs.google.com/spreadsheets/d/1NhA2LwWcmlN6AD9Vxc3NhOupJ8nuMSW8UQ5RWQbEGQM/edit)
[![Streamlit](https://img.shields.io/badge/демо-Streamlit-FF4B4B)](app/streamlit_app.py)

[English version](README.en.md) · [Кейс: разбор задачи](docs/case.md)

Синтетический стенд для анализа качества рекламного трафика: **DSP → Верификатор → Метрика → отчёт**.

Сайт, GTM-события, визиты и выгрузки DSP и Верификатора генерируются, а в данные заранее вшиты аномалии. Пайплайн чистит данные, считает доходимость и долю GIVT, ищет аномалии во временных рядах и собирает отчёт с подсветкой. Каждая метрика посчитана дважды, в pandas и в SQL. Тесты проверяют, что оба расчёта совпадают и что найдено ровно то, что было вшито.

[![Дашборд DataLens](docs/img/datalens_dashboard.png)](https://datalens.yandex/5eh8tse706g0o)

<sub>Дашборд в DataLens: провал доходимости ssp_b 12–14.09, ровное расхождение DSP и Верификатора, рост GIVT на mobile_feed 20–24.09. Картинка кликабельна.</sub>

## Что внутри

```mermaid
flowchart LR
    S[scenarios.yaml<br/>план кампании + аномалии] --> C[Симулятор кампании]
    C --> D[dsp_clicks.csv]
    C --> V[verifier_export.csv]
    C --> P[visit_plan.csv]
    C --> T[ground_truth.json]
    P --> B[Бот Playwright] --> W[Сайт Polka<br/>GTM-события] --> M[(Яндекс Метрика)]
    P -. офлайн .-> E[Эмулятор Метрики]
    M --> X[metrika_visits.csv]
    E --> X
    D & V & X --> CL[Чистка]
    CL --> PY[Анализ pandas]
    CL --> SQ[Анализ SQL / DuckDB]
    PY <-->|pytest: совпадают| SQ
    PY --> R[Excel / Google Sheets<br/>графики, выводы]
    T -->|pytest: всё найдено| PY
```

| Слой | Что делает | Где |
|---|---|---|
| Симуляция | Клики DSP по дням, SSP и площадкам; выгрузка Верификатора с GIVT/SIVT; план визитов с UTM | [`src/simulate/campaign.py`](src/simulate/campaign.py) |
| Сайт | Витрина на GitHub Pages, события `add_to_cart`, `form_submit`, `scroll_50`, `click_phone` в dataLayer | [`site/`](site/), [`gtm/SETUP.md`](gtm/SETUP.md) |
| Трафик | Playwright проигрывает план визитов на сайте с UTM-метками | [`src/simulate/visitor.py`](src/simulate/visitor.py) |
| Выгрузка | Reporting API Метрики (Python) и выгрузка в Google Sheets (Apps Script) | [`src/extract/`](src/extract/), [`apps_script/`](apps_script/) |
| Чистка | Дубли, строка «Итого», форматы дат, пропущенные дни, UTM в разном написании | [`src/clean/loaders.py`](src/clean/loaders.py) |
| Анализ | Доходимость, расхождение DSP / Верификатор, GIVT, robust z, STL, интервалы Уилсона, хи-квадрат | [`src/analysis/`](src/analysis/) |
| SQL-дубль | Те же расчёты: CTE, оконные функции, `ROLLUP`, gaps and islands | [`sql/`](sql/) |
| Отчёт | Excel и Google Sheets с условным форматированием, графики, текст выводов | [`src/report/`](src/report/) |

## Быстрый старт

```bash
git clone https://github.com/yzinchenko-data/traffic-quality-lab.git
cd traffic-quality-lab
pip install -r requirements-dev.txt
make report   # симуляция → эмулятор Метрики → анализ → отчёт
make test     # 33 теста
make app      # Streamlit: порог robust z и сила аномалий на ползунках
```

Ключи и доступы для офлайн-режима не нужны. После запуска:

- `reports/traffic_quality_report.xlsx` — отчёт на 6 листов с подсветкой;
- `reports/findings.md` — выводы текстом;
- `docs/img/*.png` — графики.

## Вшитые аномалии и что находит пайплайн

Сценарии описаны в [`scenarios.yaml`](scenarios.yaml). Их можно менять, тесты проверяют результат по `ground_truth.json`.

| Сценарий | Что вшито | Что находит пайплайн |
|---|---|---|
| `reach_drop` | ssp_b, 12–14.09: доходимость 35% от нормы | Провал доходимости ssp_b 12.09–14.09: 22–24% при 70% в остальные дни |
| `high_givt` | mobile_feed, 20–24.09: GIVT 22% | Рост GIVT на mobile_feed 20.09–24.09. Как следствие, просадка доходимости ssp_c 22–24.09: GIVT входит в «Кликов всего с учётом IVT», но до сайта не доходит |
| `goal_spike` | weather_app, 17.09: +160 отправок формы | Целей form_submit больше, чем визитов |
| `duplicates` | 6 полных дублей в выгрузке DSP | Удалены, записаны в отчёт о чистке |
| `missing_date` | В выгрузке Верификатора нет 08.09 | Дата найдена; расхождение и доходимость считаются только по дням, которые есть в обеих выгрузках |
| `utm_noise` | `SSP_A`, `ssp-a`, `ssp_a?ref=feed` | Приведены к `ssp_a` |

### Графики отчёта

Пайплайн рисует их сам (matplotlib) и кладёт в `docs/img/`.

<table>
<tr>
<td width="50%"><img src="docs/img/reach.png" alt="Доходимость по SSP"><br><sub>Доходимость от Верификатора по SSP, аномальные дни отмечены</sub></td>
<td width="50%"><img src="docs/img/givt.png" alt="Доля GIVT по площадкам"><br><sub>Доля GIVT по площадкам</sub></td>
</tr>
<tr>
<td width="50%"><img src="docs/img/dsp_vs_verifier.png" alt="Расхождение DSP и Верификатора"><br><sub>Расхождение DSP и Верификатора по дням, %</sub></td>
<td width="50%"><img src="docs/img/funnel.png" alt="Воронка"><br><sub>Воронка: клики DSP → Верификатор → визиты → цели</sub></td>
</tr>
</table>

## Отчёт в Google Sheets

[Traffic Quality Lab — отчёт](https://docs.google.com/spreadsheets/d/1NhA2LwWcmlN6AD9Vxc3NhOupJ8nuMSW8UQ5RWQbEGQM/edit): сводка по SSP, доходимость и GIVT по дням с подсветкой аномалий, периоды аномалий, отчёт о чистке и лист с живыми визитами из Метрики.

Таблицу собирает [`apps_script/report_builder.gs`](apps_script/report_builder.gs), ключи сервисного аккаунта не нужны. Пайплайн кладёт CSV в [`exports/sheets/`](exports/sheets/), скрипт забирает их из репозитория и каждый раз оформляет одинаково: русские заголовки, доли в процентах, красная строка у аномальных дней, градиент по доходимости и GIVT. В таблице появляется меню **Traffic Quality Lab** с пунктами «Обновить отчёт», «Выгрузить Метрику» и «Обновлять каждый день». Колонки задаёт [`src/report/sheet_tables.py`](src/report/sheet_tables.py), его же использует выгрузка `--sheets` через gspread.

## Дашборд DataLens

[Traffic Quality Lab — качество трафика](https://datalens.yandex/5eh8tse706g0o): доходимость от Верификатора по SSP, расхождение DSP и Верификатора по дням, доля GIVT по площадкам. Источник — CSV из папки [`datalens/`](datalens/), их выгружает пайплайн.

## Обновление данных

Workflow [`refresh.yml`](.github/workflows/refresh.yml) запускается вручную (Actions → Daily refresh → Run workflow), пересобирает отчёт и коммитит свежие CSV в `exports/sheets/` и `datalens/`. Календарь кампании сдвигается так, чтобы она кончалась вчера (`--end yesterday`). Сдвиг идёт на целые недели: выходные остаются на тех же днях недели, и вшитые аномалии находятся так же, как в исходном сентябре. Таблица и DataLens подхватывают новые файлы сами.

## Демо на Streamlit

`make app` открывает [`app/streamlit_app.py`](app/streamlit_app.py): ползунками меняются порог robust z, глубина провала доходимости и доля GIVT, а графики и найденные периоды пересчитываются сразу. Видно, где детектор начинает пропускать аномалии и где ловит лишние дни.

![Демо на Streamlit](docs/img/streamlit_app.png)

## Живой сайт и счётчик

Витрина: https://yzinchenko-data.github.io/traffic-quality-lab/. Подключены контейнер GTM `GTM-MJXVW5MB` и счётчик Метрики с целями `add_to_cart`, `form_submit`, `scroll_50`, `click_phone`; настройки контейнера лежат в [`gtm/container.json`](gtm/container.json).

## Как считается

**Доходимость от Верификатора** = визиты / «Кликов всего с учётом IVT». В числителе только визиты за дни, по которым есть выгрузка Верификатора.

**Расхождение DSP / Верификатор** = (клики DSP − клики Верификатора) / клики Верификатора. Считается по дням и за период, рядом выводится среднее по дням.

**Доли за период** пересчитываются из сумм, а не усредняются по дням.

**Аномалии.** Флаг ставит robust z: (x − медиана) / (MAD · 1,4826), порог 3,5. Медиана и MAD почти не сдвигаются от нескольких аномальных дней, поэтому трёхдневный провал не размывает собственную норму. STL-декомпозиция с недельным периодом идёт рядом как тренд для графиков. Флаг по ней не ставится: на 30 точках остаток почти нулевой, и любое колебание выглядело бы аномалией.

**Конверсии.** Для CR даётся 95% интервал Уилсона, SSP сравниваются хи-квадратом. Строки, где целей больше, чем визитов, в CR не попадают: они идут отдельной находкой.

### Пример SQL: склейка аномальных дней в периоды

```sql
WITH islands AS (
    SELECT *, date - CAST(ROW_NUMBER() OVER (PARTITION BY kind, slice ORDER BY date) AS INTEGER) AS grp
    FROM flagged
)
SELECT kind, slice, MIN(date) AS start, MAX(date) AS "end", COUNT(*) AS days
FROM islands
GROUP BY kind, slice, grp;
```

## Тесты

| Файл | Проверяет |
|---|---|
| `test_simulator.py` | Детерминизм по seed; «Итого» Верификатора = сумма строк; GIVT + SIVT + чистые = всего |
| `test_cleaning.py` | Нормализацию UTM, отчёт о чистке, уникальность ключей витрины |
| `test_python_vs_sql.py` | pandas и DuckDB дают одни и те же суммы, доли, флаги и периоды |
| `test_ground_truth.py` | Найдены все вшитые аномалии, лишних нет, каждый провал доходимости объяснён |
| `test_sheet_tables.py` | Колонки CSV для Sheets сходятся с оформлением в Apps Script |
| `test_visitor_plan.py` | Бот проигрывает план с нужным числом целей и UTM |

## Живой режим: сайт, GTM и настоящие визиты

1. Включить GitHub Pages (Settings → Pages → GitHub Actions): workflow [`pages.yml`](.github/workflows/pages.yml) выложит `site/`.
2. Создать счётчик Метрики и контейнер GTM по [`gtm/SETUP.md`](gtm/SETUP.md), вписать ID контейнера в `site/assets/config.js`.
3. В Settings → Variables добавить `SITE_URL` и запустить вручную [`traffic.yml`](.github/workflows/traffic.yml): бот проиграет 5% плана за сегодня (`today`) или за выбранную дату.
4. Заполнить `.env` по `.env.example` и запустить с настоящими данными:

```bash
python -m src.pipeline --source api --end today            # визиты из Метрики
python -m src.pipeline --source api --end today --sheets   # плюс выгрузка в Google Sheets
```

Визиты бота идут из headless-браузера с IP датацентра, и Метрика часть из них отметит как роботов. Это не прячется: роботность считается в отчёте отдельной колонкой.

## Структура

```
traffic-quality-lab/
├── scenarios.yaml          # план кампании и вшитые аномалии
├── site/                   # витрина Polka (HTML/CSS/JS, события dataLayer)
├── gtm/SETUP.md            # теги, триггеры и переменные GTM
├── apps_script/            # отчёт и выгрузка Метрики в Google Sheets
├── app/                    # демо на Streamlit
├── src/
│   ├── simulate/           # симулятор кампании, бот-посетитель
│   ├── extract/            # Metrika API, офлайн-эмулятор, общая схема
│   ├── clean/              # чистка и отчёт о чистке
│   ├── analysis/           # доходимость, временные ряды, конверсии
│   ├── report/             # Excel, Google Sheets, графики, текст выводов
│   ├── sql_runner.py
│   └── pipeline.py
├── sql/                    # staging → витрина → аномалии (DuckDB)
├── tests/
└── .github/workflows/      # CI, деплой сайта, синтетический трафик
```

## Данные

Все данные в репозитории синтетические. Клиентов, кампаний, UTM-меток подрядчиков и цифр из реальных проектов здесь нет. Токены хранятся только в `.env` и GitHub Secrets.

## Лицензия

MIT
