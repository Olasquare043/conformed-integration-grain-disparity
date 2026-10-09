-- Grain: one NYSERDA price series (16 metro regions and the state average, code NY) per
-- described week, with the published label date that made it known.
SELECT
    described_week.full_date AS week_start,
    published_label.full_date AS label_date,
    geography.geography_code AS series_code,
    prices.price_usd_per_gallon
FROM fact_fuel_price_weekly AS prices
INNER JOIN dim_date AS described_week
    ON described_week.date_key = prices.week_start_date_key
INNER JOIN dim_date AS published_label
    ON published_label.date_key = prices.nyserda_week_label_date_key
INNER JOIN dim_geography AS geography
    ON geography.geography_key = prices.geography_key
ORDER BY series_code, week_start
