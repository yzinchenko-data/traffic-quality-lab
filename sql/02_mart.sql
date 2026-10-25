-- Витрина доходимости: день × SSP × площадка. Повторяет src/analysis/reach.py.

CREATE OR REPLACE MACRO safe_div(a, b) AS round(CAST(a AS DOUBLE) / NULLIF(b, 0), 4);

CREATE OR REPLACE TABLE mart_daily AS
SELECT
    d.date, d.ssp, d.placement,
    d.dsp_clicks,
    -- клики DSP и визиты только за дни, которые есть у Верификатора:
    -- по ним считаем расхождение и доходимость от Верификатора
    CASE WHEN v.verifier_total IS NOT NULL THEN d.dsp_clicks END AS dsp_clicks_matched,
    v.verifier_total, v.givt, v.sivt, v.clean_clicks,
    m.visits,
    CASE WHEN v.verifier_total IS NOT NULL THEN m.visits END AS visits_matched,
    m.users, m.robots, m.bounces, m.add_to_cart, m.form_submit
FROM stg_dsp d
LEFT JOIN stg_verifier v USING (date, ssp, placement)
LEFT JOIN stg_metrika  m USING (date, ssp, placement);

-- Доли пересчитываем от сумм среза, а не усредняем.
-- with_rates('имя_таблицы') добавляет к любой агрегированной таблице одинаковый набор долей.
CREATE OR REPLACE MACRO with_rates(t) AS TABLE
SELECT
    *,
    safe_div(visits, dsp_clicks)                                          AS reach_dsp,
    safe_div(visits_matched, verifier_total)                              AS reach_verifier,
    round(safe_div(dsp_clicks_matched - verifier_total, verifier_total) * 100, 2) AS dsp_vs_verifier_pct,
    safe_div(givt, verifier_total)                                        AS givt_share,
    safe_div(robots, visits)                                              AS robot_share,
    safe_div(add_to_cart, visits)                                         AS cr_cart,
    safe_div(form_submit, visits)                                         AS cr_form
FROM query_table(t);

CREATE OR REPLACE TABLE agg_date_ssp AS
SELECT date, ssp,
       SUM(dsp_clicks) AS dsp_clicks, SUM(dsp_clicks_matched) AS dsp_clicks_matched, SUM(verifier_total) AS verifier_total, SUM(givt) AS givt,
       SUM(visits) AS visits, SUM(visits_matched) AS visits_matched, SUM(robots) AS robots, SUM(add_to_cart) AS add_to_cart, SUM(form_submit) AS form_submit
FROM mart_daily GROUP BY date, ssp;

CREATE OR REPLACE TABLE agg_date_placement AS
SELECT date, placement,
       SUM(dsp_clicks) AS dsp_clicks, SUM(dsp_clicks_matched) AS dsp_clicks_matched, SUM(verifier_total) AS verifier_total, SUM(givt) AS givt,
       SUM(visits) AS visits, SUM(visits_matched) AS visits_matched, SUM(robots) AS robots, SUM(add_to_cart) AS add_to_cart, SUM(form_submit) AS form_submit
FROM mart_daily GROUP BY date, placement;

CREATE OR REPLACE TABLE agg_date AS
SELECT date,
       SUM(dsp_clicks) AS dsp_clicks, SUM(dsp_clicks_matched) AS dsp_clicks_matched, SUM(verifier_total) AS verifier_total, SUM(givt) AS givt,
       SUM(visits) AS visits, SUM(visits_matched) AS visits_matched, SUM(robots) AS robots, SUM(add_to_cart) AS add_to_cart, SUM(form_submit) AS form_submit
FROM mart_daily GROUP BY date;

-- ROLLUP даёт строки по SSP и общую строку «Итого»
CREATE OR REPLACE TABLE agg_period AS
SELECT COALESCE(ssp, 'Итого') AS ssp,
       SUM(dsp_clicks) AS dsp_clicks, SUM(dsp_clicks_matched) AS dsp_clicks_matched, SUM(verifier_total) AS verifier_total, SUM(givt) AS givt,
       SUM(visits) AS visits, SUM(visits_matched) AS visits_matched, SUM(robots) AS robots, SUM(add_to_cart) AS add_to_cart, SUM(form_submit) AS form_submit
FROM mart_daily
GROUP BY ROLLUP (ssp);

CREATE OR REPLACE TABLE daily_ssp       AS FROM with_rates('agg_date_ssp');
CREATE OR REPLACE TABLE daily_placement AS FROM with_rates('agg_date_placement');
CREATE OR REPLACE TABLE daily_total     AS FROM with_rates('agg_date');

-- Средние дневные значения рядом с итогом за период
CREATE OR REPLACE TABLE period_summary AS
WITH avg_daily AS (
    SELECT ssp, round(AVG(reach_verifier), 4) AS avg_daily_reach, round(AVG(dsp_vs_verifier_pct), 4) AS avg_daily_gap_pct
    FROM daily_ssp GROUP BY ssp
    UNION ALL
    SELECT 'Итого', round(AVG(reach_verifier), 4), round(AVG(dsp_vs_verifier_pct), 4)
    FROM daily_total
)
SELECT p.*, a.avg_daily_reach, a.avg_daily_gap_pct
FROM with_rates('agg_period') p
JOIN avg_daily a USING (ssp)
ORDER BY ssp = 'Итого', ssp;
