-- Grain: one calendar year of complete Monday-start weeks of NYC yellow taxi demand (every
-- published trip), with the average and lowest week. Cited in docs/analysis_plan.md (COVID).
SELECT
    week.year AS year,
    COUNT(*) AS complete_weeks,
    AVG(demand.trip_count) AS average_weekly_trips,
    MIN(demand.trip_count) AS lowest_weekly_trips
FROM agg_trip_region_week AS demand
INNER JOIN dim_geography AS region
    ON region.geography_key = demand.region_geography_key
INNER JOIN dim_date AS week
    ON week.date_key = demand.week_start_date_key
WHERE region.geography_code = 'new_york_city'
    AND demand.days_with_trips = 7
GROUP BY week.year
ORDER BY week.year
