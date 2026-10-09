-- Grain: one Monday-start week, with its ISO week number and count of federal holidays.
SELECT
    week_start_date AS week_start,
    MIN(iso_week) FILTER (WHERE iso_day_of_week = 1) AS iso_week,
    SUM(CAST(is_us_federal_holiday AS INTEGER)) AS federal_holidays
FROM dim_date
GROUP BY week_start_date
ORDER BY week_start
