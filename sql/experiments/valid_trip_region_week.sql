-- Grain: one metro region per Monday-start week of valid trips, rolled up through dim_geography.
CREATE TEMP TABLE valid_trip_region_week AS
SELECT
    zone_weeks.week_start_date_key,
    region.geography_key AS region_geography_key,
    SUM(zone_weeks.trip_count) AS trip_count
FROM valid_trip_zone_week AS zone_weeks
INNER JOIN dim_geography AS zone
    ON zone.geography_key = zone_weeks.pickup_geography_key
INNER JOIN dim_geography AS region
    ON region.geography_level = 'metro_region'
    AND region.geography_code = zone.region_code
GROUP BY zone_weeks.week_start_date_key, region.geography_key
