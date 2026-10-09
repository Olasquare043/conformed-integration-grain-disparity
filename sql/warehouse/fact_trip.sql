-- Grain: one valid yellow taxi trip in the fact window (2024 to 2025).
-- trip_id is the file month (YYYYMM) followed by the trip's row position in the
-- published file, so every fact row can be traced back to its source row.
CREATE TABLE fact_trip AS
SELECT
    CAST(replace(trips.file_month, '-', '') AS BIGINT) * 100000000
    + trips.file_row_number AS trip_id,
    CAST(strftime(trips.pickup_datetime, '%Y%m%d') AS INTEGER) AS pickup_date_key,
    pickup_zone.geography_key AS pickup_geography_key,
    dropoff_zone.geography_key AS dropoff_geography_key,
    trips.pickup_datetime,
    trips.dropoff_datetime,
    hour(trips.pickup_datetime) AS pickup_hour,
    trips.vendor_id,
    trips.rate_code_id,
    trips.payment_type,
    trips.passenger_count,
    trips.trip_distance_miles,
    trips.duration_seconds,
    trips.fare_amount,
    trips.total_amount,
    trips.cbd_congestion_fee
FROM stg_trip_validity AS trips
INNER JOIN dim_geography AS pickup_zone
    ON pickup_zone.geography_level = 'zone'
    AND pickup_zone.zone_id = trips.pickup_zone_id
INNER JOIN dim_geography AS dropoff_zone
    ON dropoff_zone.geography_level = 'zone'
    AND dropoff_zone.zone_id = trips.dropoff_zone_id
WHERE NOT (
    trips.fails_pickup_outside_file_month
    OR trips.fails_excluded_vendor
    OR trips.fails_nonpositive_duration
    OR trips.fails_duration_below_minimum
    OR trips.fails_duration_above_maximum
    OR trips.fails_nonpositive_distance
    OR trips.fails_distance_above_maximum
    OR trips.fails_speed_above_maximum
    OR trips.fails_unknown_zone
)
