-- Grain: one metro region per day, from Open-Meteo (ERA5) at the region's representative point.
CREATE TABLE fact_weather_daily AS
SELECT
    days.date_key,
    geography.geography_key,
    weather.temperature_2m_max AS temperature_max_c,
    weather.temperature_2m_min AS temperature_min_c,
    weather.temperature_2m_mean AS temperature_mean_c,
    weather.precipitation_sum AS precipitation_mm,
    weather.snowfall_sum AS snowfall_cm,
    weather.wind_speed_10m_max AS wind_speed_max_kmh
FROM stg_weather AS weather
INNER JOIN dim_date AS days
    ON days.full_date = CAST(weather.weather_date AS DATE)
INNER JOIN dim_geography AS geography
    ON geography.geography_level = 'metro_region'
    AND geography.geography_code = weather.region_code
ORDER BY days.date_key, geography.geography_key
