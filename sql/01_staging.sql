-- Слой staging: те же правила чистки, что в src/clean/loaders.py.
-- {raw_dir} подставляет src/sql_runner.py.

-- DSP: полные дубли убираем через ROW_NUMBER, чтобы было видно, какие строки отброшены
CREATE OR REPLACE TABLE stg_dsp AS
WITH numbered AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY "Дата", "Кампания", "SSP", "Площадка", "Клики") AS rn
    FROM read_csv('{raw_dir}/dsp_clicks.csv', header = true, all_varchar = true)
)
SELECT
    CAST("Дата" AS DATE)      AS date,
    "SSP"                     AS ssp,
    "Площадка"                AS placement,
    CAST("Клики" AS INTEGER)  AS dsp_clicks
FROM numbered
WHERE rn = 1;

-- Верификатор: даты ДД.ММ.ГГГГ, строку «Итого» отрезаем и храним отдельно для сверки
CREATE OR REPLACE TABLE raw_verifier AS
SELECT * FROM read_csv('{raw_dir}/verifier_export.csv', header = true, delim = ';', all_varchar = true);

CREATE OR REPLACE TABLE stg_verifier AS
SELECT
    CAST(strptime("Дата", '%d.%m.%Y') AS DATE)       AS date,
    "SSP"                                            AS ssp,
    "Площадка"                                       AS placement,
    CAST("Кликов всего с учётом IVT" AS INTEGER)     AS verifier_total,
    CAST("GIVT" AS INTEGER)                          AS givt,
    CAST("SIVT" AS INTEGER)                          AS sivt,
    CAST("Чистые клики" AS INTEGER)                  AS clean_clicks
FROM raw_verifier
WHERE "Дата" <> 'Итого';

-- Сверка с «Итого»: пустой результат = суммы совпали
CREATE OR REPLACE VIEW check_verifier_total AS
SELECT 'Кликов всего с учётом IVT' AS col, s.v AS actual, CAST(t."Кликов всего с учётом IVT" AS INTEGER) AS expected
FROM (SELECT SUM(verifier_total) AS v FROM stg_verifier) s, raw_verifier t
WHERE t."Дата" = 'Итого' AND s.v <> CAST(t."Кликов всего с учётом IVT" AS INTEGER);

-- Метрика: UTM в разном написании приводим к одному виду
CREATE OR REPLACE TABLE stg_metrika AS
SELECT
    CAST(date AS DATE)                                                  AS date,
    replace(split_part(lower(trim(utm_source)), '?', 1), '-', '_')     AS ssp,
    replace(split_part(lower(trim(utm_content)), '?', 1), '-', '_')    AS placement,
    SUM(visits)                                                         AS visits,
    SUM(users)                                                          AS users,
    SUM(CAST(floor(visits * robot_share + 0.5) AS INTEGER))             AS robots,
    SUM(CAST(floor(visits * bounce_rate + 0.5) AS INTEGER))             AS bounces,
    SUM(add_to_cart)                                                    AS add_to_cart,
    SUM(form_submit)                                                    AS form_submit
FROM read_csv('{raw_dir}/metrika_visits.csv', header = true)
GROUP BY ALL;

-- Даты, которых нет у Верификатора
CREATE OR REPLACE VIEW check_missing_dates AS
SELECT d::DATE AS date
FROM generate_series(DATE '{start}', DATE '{end}', INTERVAL 1 DAY) AS t(d)
WHERE d::DATE NOT IN (SELECT DISTINCT date FROM stg_verifier);
