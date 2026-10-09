-- Grain: one row per monthly yellow taxi file, counted as published (before any cleaning).
WITH unknown_zones AS (
    SELECT LocationID AS zone_id
    FROM read_csv($zone_lookup_path, header = TRUE)
    WHERE Borough IN ('Unknown', 'N/A')
),

trips AS (
    SELECT *
    FROM read_parquet($parquet_path)
)

SELECT
    $file_month AS file_month,
    COUNT(*) AS trip_rows,
    COUNT(*) FILTER (
        WHERE strftime(tpep_pickup_datetime, '%Y-%m') <> $file_month
    ) AS pickups_outside_file_month,
    MIN(tpep_pickup_datetime) AS first_pickup,
    MAX(tpep_pickup_datetime) AS last_pickup,
    COUNT(*) FILTER (WHERE passenger_count IS NULL) AS missing_passenger_count,
    COUNT(*) FILTER (WHERE fare_amount <= 0) AS nonpositive_fare,
    COUNT(*) FILTER (WHERE trip_distance <= 0) AS nonpositive_distance,
    COUNT(*) FILTER (
        WHERE tpep_dropoff_datetime <= tpep_pickup_datetime
    ) AS nonpositive_duration,
    COUNT(*) FILTER (
        WHERE tpep_dropoff_datetime - tpep_pickup_datetime > INTERVAL 24 HOUR
    ) AS duration_over_24_hours,
    COUNT(*) FILTER (
        WHERE PULocationID IN (SELECT zone_id FROM unknown_zones)
        OR DOLocationID IN (SELECT zone_id FROM unknown_zones)
    ) AS unknown_zone_trips,
    MEDIAN(fare_amount) AS median_fare_usd,
    MEDIAN(trip_distance) AS median_distance_miles
FROM trips
