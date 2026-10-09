-- Grain: one metro region per Monday-start week of weather, rolled up from fact_weather_daily.
CREATE TABLE agg_weather_region_week AS
SELECT
    days.week_start_date_key,
    weather.geography_key AS region_geography_key,
    AVG(weather.temperature_mean_c) AS temperature_mean_c,
    MIN(weather.temperature_min_c) AS temperature_min_c,
    MAX(weather.temperature_max_c) AS temperature_max_c,
    SUM(weather.precipitation_mm) AS precipitation_mm,
    SUM(weather.snowfall_cm) AS snowfall_cm,
    MAX(weather.wind_speed_max_kmh) AS wind_speed_max_kmh,
    COUNT(*) AS days_with_weather
FROM fact_weather_daily AS weather
INNER JOIN dim_date AS days
    ON days.date_key = weather.date_key
GROUP BY days.week_start_date_key, weather.geography_key
ORDER BY days.week_start_date_key, weather.geography_key
