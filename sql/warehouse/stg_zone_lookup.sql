-- Grain: one TLC taxi zone, as published in the taxi zone lookup.
CREATE TABLE stg_zone_lookup AS
SELECT
    CAST(LocationID AS INTEGER) AS zone_id,
    Zone AS zone_name,
    Borough AS borough_name,
    service_zone
FROM read_csv($zone_lookup_path, header = TRUE, all_varchar = TRUE)
