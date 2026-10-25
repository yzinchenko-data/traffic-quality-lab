-- Аномалии по robust z: (x - медиана) / (MAD * 1.4826). Повторяет src/analysis/timeseries.py.

-- Провалы доходимости по SSP
CREATE OR REPLACE TABLE anomalies_reach AS
WITH stats AS (
    SELECT ssp, median(reach_verifier) AS med
    FROM daily_ssp GROUP BY ssp
),
mad AS (
    SELECT d.ssp, s.med, median(abs(d.reach_verifier - s.med)) * 1.4826 AS mad
    FROM daily_ssp d JOIN stats s USING (ssp)
    GROUP BY d.ssp, s.med
)
SELECT
    d.date, d.ssp, d.reach_verifier,
    round((d.reach_verifier - m.med) / NULLIF(m.mad, 0), 2) AS z,
    (d.reach_verifier - m.med) / NULLIF(m.mad, 0) < -3.5     AS flag
FROM daily_ssp d JOIN mad m USING (ssp)
ORDER BY d.ssp, d.date;

-- Всплески GIVT по площадкам
CREATE OR REPLACE TABLE anomalies_givt AS
WITH stats AS (
    SELECT placement, median(givt_share) AS med
    FROM daily_placement GROUP BY placement
),
mad AS (
    SELECT d.placement, s.med, median(abs(d.givt_share - s.med)) * 1.4826 AS mad
    FROM daily_placement d JOIN stats s USING (placement)
    GROUP BY d.placement, s.med
)
SELECT
    d.date, d.placement, d.givt_share,
    round((d.givt_share - m.med) / NULLIF(m.mad, 0), 2) AS z,
    (d.givt_share - m.med) / NULLIF(m.mad, 0) > 3.5      AS flag
FROM daily_placement d JOIN mad m USING (placement)
ORDER BY d.placement, d.date;

-- Подряд идущие дни склеиваем в периоды (gaps and islands)
CREATE OR REPLACE TABLE anomaly_windows AS
WITH flagged AS (
    SELECT 'reach' AS kind, ssp AS slice, date FROM anomalies_reach WHERE flag
    UNION ALL
    SELECT 'givt', placement, date FROM anomalies_givt WHERE flag
),
islands AS (
    SELECT *, date - CAST(ROW_NUMBER() OVER (PARTITION BY kind, slice ORDER BY date) AS INTEGER) AS grp
    FROM flagged
)
SELECT kind, slice, MIN(date) AS start, MAX(date) AS "end", COUNT(*) AS days
FROM islands
GROUP BY kind, slice, grp
ORDER BY kind, slice, start;

-- Целей больше, чем визитов
CREATE OR REPLACE TABLE goals_over_visits AS
SELECT date, ssp, placement, 'add_to_cart' AS goal, visits, add_to_cart AS reaches
FROM mart_daily WHERE add_to_cart > visits
UNION ALL
SELECT date, ssp, placement, 'form_submit', visits, form_submit
FROM mart_daily WHERE form_submit > visits
ORDER BY date, placement;
