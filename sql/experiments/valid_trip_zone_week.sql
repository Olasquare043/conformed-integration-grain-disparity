-- Grain: one pickup zone per Monday-start week of valid trips, rolled up through dim_date.
CREATE TEMP TABLE valid_trip_zone_week AS
SELECT
    days.week_start_date_key,
    zone_days.pickup_geography_key,
    SUM(zone_days.trip_count) AS trip_count
FROM valid_trip_zone_day AS zone_days
INNER JOIN dim_date AS days
    ON days.date_key = zone_days.date_key
GROUP BY days.week_start_date_key, zone_days.pickup_geography_key
