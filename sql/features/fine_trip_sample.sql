-- Grain: one sampled valid trip (training or test bucket), with every candidate feature for
-- both information sets. Sample buckets come from the MD5 of trip_id, so the sample depends
-- on content only. Weather and fuel price reach each trip through its pickup zone's metro
-- region in dim_geography and the pickup day in dim_date. The fuel price is the latest
-- NYSERDA label on or before the pickup day: the Monday that starts the pickup's week.
WITH sampled_trips AS (
    SELECT
        trips.*,
        CAST(('0x' || left(md5(CAST(trips.trip_id AS VARCHAR)), 8)) AS UBIGINT)
        % $bucket_count AS sample_bucket
    FROM fact_trip AS trips
),

kept_trips AS (
    SELECT *
    FROM sampled_trips
    WHERE sample_bucket BETWEEN $training_bucket_first AND $training_bucket_last
        OR sample_bucket BETWEEN $test_bucket_first AND $test_bucket_last
)

SELECT
    trips.trip_id,
    trips.sample_bucket,
    strftime(trips.pickup_datetime, '%Y-%m') AS pickup_month,
    pickup_day.full_date AS pickup_date,
    ln(trips.duration_seconds) AS log_duration,
    trips.duration_seconds,
    pickup_zone.zone_id AS pickup_zone_id,
    dropoff_zone.zone_id AS dropoff_zone_id,
    sqrt(
        power(pickup_zone.centroid_x_feet - dropoff_zone.centroid_x_feet, 2)
        + power(pickup_zone.centroid_y_feet - dropoff_zone.centroid_y_feet, 2)
    ) / 5280 AS centroid_distance_miles,
    trips.trip_distance_miles AS recorded_distance_miles,
    trips.pickup_hour,
    trips.pickup_hour * 60 + minute(trips.pickup_datetime) AS pickup_minute_of_day,
    (pickup_day.iso_day_of_week - 1) * 24 + trips.pickup_hour AS hour_of_week,
    trips.vendor_id,
    trips.rate_code_id,
    trips.passenger_count,
    pickup_day.iso_day_of_week,
    pickup_day.is_weekend,
    pickup_day.is_us_federal_holiday,
    pickup_day.month,
    pickup_day.day_of_month,
    pickup_day.full_date AS weather_same_day_date,
    same_day_weather.temperature_mean_c AS weather_same_day_temperature_mean_c,
    same_day_weather.precipitation_mm AS weather_same_day_precipitation_mm,
    same_day_weather.snowfall_cm AS weather_same_day_snowfall_cm,
    same_day_weather.wind_speed_max_kmh AS weather_same_day_wind_speed_max_kmh,
    week_before.full_date AS weather_lagged_date,
    lagged_weather.temperature_mean_c AS weather_lagged_temperature_mean_c,
    lagged_weather.precipitation_mm AS weather_lagged_precipitation_mm,
    lagged_weather.snowfall_cm AS weather_lagged_snowfall_cm,
    lagged_weather.wind_speed_max_kmh AS weather_lagged_wind_speed_max_kmh,
    latest_label.full_date AS fuel_label_date,
    latest_price.price_usd_per_gallon AS fuel_price_usd,
    latest_price.price_usd_per_gallon - previous_price.price_usd_per_gallon
        AS fuel_price_change_usd
FROM kept_trips AS trips
INNER JOIN dim_date AS pickup_day
    ON pickup_day.date_key = trips.pickup_date_key
INNER JOIN dim_geography AS pickup_zone
    ON pickup_zone.geography_key = trips.pickup_geography_key
INNER JOIN dim_geography AS dropoff_zone
    ON dropoff_zone.geography_key = trips.dropoff_geography_key
LEFT JOIN dim_geography AS pickup_region
    ON pickup_region.geography_level = 'metro_region'
    AND pickup_region.geography_code = pickup_zone.region_code
LEFT JOIN fact_weather_daily AS same_day_weather
    ON same_day_weather.date_key = pickup_day.date_key
    AND same_day_weather.geography_key = pickup_region.geography_key
INNER JOIN dim_date AS week_before
    ON week_before.full_date = pickup_day.full_date - CAST($weather_lag_days AS INTEGER)
LEFT JOIN fact_weather_daily AS lagged_weather
    ON lagged_weather.date_key = week_before.date_key
    AND lagged_weather.geography_key = pickup_region.geography_key
INNER JOIN dim_date AS latest_label
    ON latest_label.date_key = pickup_day.week_start_date_key
LEFT JOIN fact_fuel_price_weekly AS latest_price
    ON latest_price.nyserda_week_label_date_key = latest_label.date_key
    AND latest_price.geography_key = pickup_region.geography_key
LEFT JOIN dim_date AS previous_label
    ON previous_label.full_date = latest_label.full_date - 7
LEFT JOIN fact_fuel_price_weekly AS previous_price
    ON previous_price.nyserda_week_label_date_key = previous_label.date_key
    AND previous_price.geography_key = pickup_region.geography_key
ORDER BY trips.trip_id
