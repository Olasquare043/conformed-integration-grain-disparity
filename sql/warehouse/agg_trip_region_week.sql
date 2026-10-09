-- Grain: one metro region per Monday-start week of trip demand, rolled up from zones
-- through the region code each zone carries in dim_geography. days_with_trips shows
-- whether the week is complete (7) or cut by the start of the history or the cutoff.
CREATE TABLE agg_trip_region_week AS
SELECT
    days.week_start_date_key,
    region.geography_key AS region_geography_key,
    SUM(zone_days.trip_count) AS trip_count,
    COUNT(DISTINCT zone_days.date_key) AS days_with_trips
FROM agg_trip_zone_day AS zone_days
INNER JOIN dim_date AS days
    ON days.date_key = zone_days.date_key
INNER JOIN dim_geography AS zone
    ON zone.geography_key = zone_days.pickup_geography_key
INNER JOIN dim_geography AS region
    ON region.geography_level = 'metro_region'
    AND region.geography_code = zone.region_code
GROUP BY days.week_start_date_key, region.geography_key
ORDER BY days.week_start_date_key, region.geography_key
