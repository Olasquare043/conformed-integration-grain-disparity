-- Grain: one Monday-start week: valid NYC trips next to the NYC price, from the region-week aggregate.
SELECT
    region_weeks.week_start_date_key,
    region_weeks.trip_count,
    prices.price_usd_per_gallon
FROM valid_trip_region_week AS region_weeks
INNER JOIN dim_geography AS region
    ON region.geography_key = region_weeks.region_geography_key
LEFT JOIN fact_fuel_price_weekly AS prices
    ON prices.week_start_date_key = region_weeks.week_start_date_key
    AND prices.geography_key = region.geography_key
WHERE region.geography_code = 'new_york_city'
ORDER BY region_weeks.week_start_date_key
