-- Grain: one pickup zone per day, counting valid trips from fact_trip (latency experiment only).
CREATE TEMP TABLE valid_trip_zone_day AS
SELECT
    trips.pickup_date_key AS date_key,
    trips.pickup_geography_key,
    COUNT(*) AS trip_count
FROM fact_trip AS trips
GROUP BY trips.pickup_date_key, trips.pickup_geography_key
