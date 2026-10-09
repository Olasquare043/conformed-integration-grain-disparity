-- Grain: one row of counts used for the grain ratios between the trip and price domains.
WITH new_york_city AS (
    SELECT geography_key
    FROM dim_geography
    WHERE geography_level = 'metro_region'
        AND geography_code = 'new_york_city'
),

fact_window AS (
    SELECT
        MIN(days.week_start_date_key) AS first_week_key,
        MAX(days.week_start_date_key) AS last_week_key,
        COUNT(DISTINCT days.week_start_date_key) AS weeks
    FROM fact_trip AS trips
    INNER JOIN dim_date AS days
        ON days.date_key = trips.pickup_date_key
),

valid_nyc_trips AS (
    SELECT COUNT(*) AS trips
    FROM fact_trip AS trips
    INNER JOIN dim_geography AS zone
        ON zone.geography_key = trips.pickup_geography_key
    WHERE zone.region_code = 'new_york_city'
),

price_rows_in_fact_window AS (
    SELECT COUNT(*) AS price_rows
    FROM fact_fuel_price_weekly AS prices
    CROSS JOIN fact_window
    WHERE prices.week_start_date_key BETWEEN fact_window.first_week_key AND fact_window.last_week_key
),

published_nyc_demand AS (
    SELECT
        SUM(demand.trip_count) AS trips,
        COUNT(*) AS region_weeks
    FROM agg_trip_region_week AS demand
    INNER JOIN new_york_city
        ON new_york_city.geography_key = demand.region_geography_key
)

SELECT
    (SELECT COUNT(*) FROM fact_trip) AS valid_trips,
    valid_nyc_trips.trips AS valid_nyc_trips,
    fact_window.weeks AS fact_window_weeks,
    price_rows_in_fact_window.price_rows AS price_rows_in_fact_window,
    published_nyc_demand.trips AS published_nyc_trips_all_years,
    published_nyc_demand.region_weeks AS nyc_region_weeks_all_years
FROM fact_window
CROSS JOIN valid_nyc_trips
CROSS JOIN price_rows_in_fact_window
CROSS JOIN published_nyc_demand
