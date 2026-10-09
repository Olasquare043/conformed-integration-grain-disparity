-- Grain: one published yellow taxi trip in the fact window, with one flag per validity rule.
-- Thresholds come from config/study.yaml (quality.trip_validity) through
-- stg_trip_validity_threshold. A NULL in a field a rule needs counts as failing that rule.
CREATE VIEW stg_trip_validity AS
WITH trips AS (
    SELECT
        regexp_extract(filename, 'yellow_tripdata_([0-9]{4}-[0-9]{2})', 1) AS file_month,
        file_row_number,
        VendorID AS vendor_id,
        tpep_pickup_datetime AS pickup_datetime,
        tpep_dropoff_datetime AS dropoff_datetime,
        PULocationID AS pickup_zone_id,
        DOLocationID AS dropoff_zone_id,
        passenger_count,
        RatecodeID AS rate_code_id,
        payment_type,
        trip_distance AS trip_distance_miles,
        fare_amount,
        total_amount,
        cbd_congestion_fee,
        date_diff('second', tpep_pickup_datetime, tpep_dropoff_datetime) AS duration_seconds
    FROM raw_yellow_trip
),

unknown_zones AS (
    SELECT zone_id
    FROM stg_zone_lookup
    WHERE borough_name IN ('Unknown', 'N/A')
)

SELECT
    trips.*,
    COALESCE(strftime(trips.pickup_datetime, '%Y-%m') <> trips.file_month, TRUE)
        AS fails_pickup_outside_file_month,
    COALESCE(list_contains(threshold.excluded_vendor_ids, trips.vendor_id), FALSE)
        AS fails_excluded_vendor,
    COALESCE(trips.duration_seconds <= 0, TRUE) AS fails_nonpositive_duration,
    COALESCE(
        trips.duration_seconds > 0
        AND trips.duration_seconds < threshold.min_duration_seconds,
        FALSE
    ) AS fails_duration_below_minimum,
    COALESCE(trips.duration_seconds > threshold.max_duration_seconds, FALSE)
        AS fails_duration_above_maximum,
    COALESCE(trips.trip_distance_miles <= 0, TRUE) AS fails_nonpositive_distance,
    COALESCE(trips.trip_distance_miles > threshold.max_distance_miles, FALSE)
        AS fails_distance_above_maximum,
    COALESCE(
        trips.duration_seconds > 0
        AND trips.trip_distance_miles / (trips.duration_seconds / 3600.0)
        > threshold.max_average_speed_mph,
        FALSE
    ) AS fails_speed_above_maximum,
    COALESCE(
        trips.pickup_zone_id IN (SELECT zone_id FROM unknown_zones)
        OR trips.dropoff_zone_id IN (SELECT zone_id FROM unknown_zones),
        TRUE
    ) AS fails_unknown_zone
FROM trips
CROSS JOIN stg_trip_validity_threshold AS threshold
