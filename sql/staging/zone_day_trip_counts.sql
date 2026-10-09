-- Grain: one row per pickup zone per pickup day within one monthly yellow taxi file.
-- Trip demand counts every published trip, so it means the same thing in every year;
-- the validity rules apply only to fact_trip. Pickup dates outside the file month are
-- kept here and removed in the warehouse, so the counts reconcile with the raw file.
SELECT
    $file_month AS file_month,
    PULocationID AS pickup_zone_id,
    CAST(tpep_pickup_datetime AS DATE) AS pickup_date,
    COUNT(*) AS trip_count
FROM read_parquet($parquet_path)
GROUP BY ALL
ORDER BY pickup_zone_id, pickup_date
