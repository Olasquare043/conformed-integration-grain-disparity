-- Grain: one metro region per Monday-start week of weather.
SELECT
    week.full_date AS week_start,
    region.geography_code AS region_code,
    weather.temperature_mean_c,
    weather.precipitation_mm,
    weather.snowfall_cm,
    weather.days_with_weather
FROM agg_weather_region_week AS weather
INNER JOIN dim_date AS week
    ON week.date_key = weather.week_start_date_key
INNER JOIN dim_geography AS region
    ON region.geography_key = weather.region_geography_key
ORDER BY region_code, week_start
