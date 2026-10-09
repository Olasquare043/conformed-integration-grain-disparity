-- Grain: one metro region per Monday-start week of trip demand (every published trip).
SELECT
    week.full_date AS week_start,
    region.geography_code AS region_code,
    demand.trip_count,
    demand.days_with_trips
FROM agg_trip_region_week AS demand
INNER JOIN dim_date AS week
    ON week.date_key = demand.week_start_date_key
INNER JOIN dim_geography AS region
    ON region.geography_key = demand.region_geography_key
ORDER BY region_code, week_start
