-- Grain: one NYSERDA price series (16 metro regions and the state average) per described
-- week. A price dated Monday w describes the week starting Monday w - 7, so the fact is
-- keyed by that week's Monday and keeps the published label as a second date key.
-- Blank prices are not loaded; reference/known_price_gaps.csv lists every gap.
CREATE TABLE fact_fuel_price_weekly AS
SELECT
    described_week.date_key AS week_start_date_key,
    published_label.date_key AS nyserda_week_label_date_key,
    geography.geography_key,
    prices.price_usd_per_gallon
FROM stg_fuel_price AS prices
INNER JOIN dim_date AS described_week
    ON described_week.full_date = CAST(prices.nyserda_week_label AS DATE) - 7
INNER JOIN dim_date AS published_label
    ON published_label.full_date = CAST(prices.nyserda_week_label AS DATE)
INNER JOIN dim_geography AS geography
    ON (
        prices.series_code = 'new_york_state'
        AND geography.geography_level = 'state'
        AND geography.geography_code = 'NY'
    )
    OR (
        geography.geography_level = 'metro_region'
        AND geography.geography_code = prices.series_code
    )
WHERE prices.price_usd_per_gallon IS NOT NULL
ORDER BY week_start_date_key, geography.geography_key
