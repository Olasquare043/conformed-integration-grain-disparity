-- Grain: one TLC borough, with the hierarchy it rolls up to (reference/borough_to_region.csv).
CREATE TABLE stg_borough_region AS
SELECT *
FROM read_csv($borough_region_path, header = TRUE, all_varchar = TRUE)
