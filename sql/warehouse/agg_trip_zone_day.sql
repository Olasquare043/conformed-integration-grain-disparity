-- Grain: one pickup zone per day, counting every published yellow taxi trip from the
-- first history month to the cutoff. Pickups dated outside their file's month are
-- left out here and accounted for in the reconciliation test instead.
CREATE TABLE agg_trip_zone_day AS
SELECT
    days.date_key,
    zone.geography_key AS pickup_geography_key,
    SUM(counts.trip_count) AS trip_count
FROM stg_trip_zone_day AS counts
INNER JOIN dim_date AS days
    ON days.full_date = counts.pickup_date
INNER JOIN dim_geography AS zone
    ON zone.geography_level = 'zone'
    AND zone.zone_id = counts.pickup_zone_id
WHERE strftime(counts.pickup_date, '%Y-%m') = counts.file_month
GROUP BY days.date_key, zone.geography_key
ORDER BY days.date_key, zone.geography_key
