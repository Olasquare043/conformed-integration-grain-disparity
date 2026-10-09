-- Grain: one calendar day, from the weather lead-in to the data cutoff.
-- Weeks start on Monday, as in NYSERDA and EIA. A NYSERDA price dated Monday w
-- describes the seven days before it (docs/decisions.md), so every day also carries
-- the NYSERDA label of the week it belongs to: its own week's Monday plus seven days.
CREATE TABLE dim_date AS
WITH calendar_days AS (
    SELECT CAST(day_timestamp AS DATE) AS full_date
    FROM range(
        CAST($first_day AS TIMESTAMP),
        CAST($last_day AS TIMESTAMP) + INTERVAL 1 DAY,
        INTERVAL 1 DAY
    ) AS days (day_timestamp)
),

days_with_weeks AS (
    SELECT
        full_date,
        CAST(date_trunc('week', full_date) AS DATE) AS week_start_date
    FROM calendar_days
)

SELECT
    CAST(strftime(days.full_date, '%Y%m%d') AS INTEGER) AS date_key,
    days.full_date,
    year(days.full_date) AS year,
    quarter(days.full_date) AS quarter,
    month(days.full_date) AS month,
    monthname(days.full_date) AS month_name,
    day(days.full_date) AS day_of_month,
    isodow(days.full_date) AS iso_day_of_week,
    dayname(days.full_date) AS day_name,
    isodow(days.full_date) >= 6 AS is_weekend,
    isoyear(days.full_date) AS iso_year,
    weekofyear(days.full_date) AS iso_week,
    days.week_start_date,
    CAST(strftime(days.week_start_date, '%Y%m%d') AS INTEGER) AS week_start_date_key,
    days.week_start_date + 7 AS nyserda_week_label_date,
    holidays.holiday_name IS NOT NULL AS is_us_federal_holiday,
    holidays.holiday_name AS us_federal_holiday_name
FROM days_with_weeks AS days
LEFT JOIN stg_us_federal_holiday AS holidays
    ON holidays.holiday_date = days.full_date
ORDER BY days.full_date
