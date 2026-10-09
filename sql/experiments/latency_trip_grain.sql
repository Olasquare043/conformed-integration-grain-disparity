-- Grain: one Monday-start week: valid NYC trips next to the NYC price, answered from fact_trip.
WITH weekly_trips AS (
    SELECT
        days.week_start_date_key,
        COUNT(*) AS trip_count
    FROM fact_trip AS trips
    INNER JOIN dim_date AS days
        ON days.date_key = trips.pickup_date_key
    INNER JOIN dim_geography AS zone
        ON zone.geography_key = trips.pickup_geography_key
    WHERE zone.region_code = 'new_york_city'
    GROUP BY days.week_start_date_key
)

SELECT
    weekly_trips.week_start_date_key,
    weekly_trips.trip_count,
    prices.price_usd_per_gallon
FROM weekly_trips
LEFT JOIN dim_geography AS region
    ON region.geography_level = 'metro_region'
    AND region.geography_code = 'new_york_city'
LEFT JOIN fact_fuel_price_weekly AS prices
    ON prices.week_start_date_key = weekly_trips.week_start_date_key
    AND prices.geography_key = region.geography_key
ORDER BY weekly_trips.week_start_date_key
