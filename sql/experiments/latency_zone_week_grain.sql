-- Grain: one Monday-start week: valid NYC trips next to the NYC price, from the zone-week aggregate.
WITH weekly_trips AS (
    SELECT
        zone_weeks.week_start_date_key,
        SUM(zone_weeks.trip_count) AS trip_count
    FROM valid_trip_zone_week AS zone_weeks
    INNER JOIN dim_geography AS zone
        ON zone.geography_key = zone_weeks.pickup_geography_key
    WHERE zone.region_code = 'new_york_city'
    GROUP BY zone_weeks.week_start_date_key
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
