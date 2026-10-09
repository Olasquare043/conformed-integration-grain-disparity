-- Grain: one NYSERDA metro region, with its weather point (reference/region_coordinates.csv).
CREATE TABLE stg_metro_region AS
SELECT
    region_code,
    region_name,
    CAST(latitude AS DOUBLE) AS latitude,
    CAST(longitude AS DOUBLE) AS longitude
FROM read_csv($region_coordinates_path, header = TRUE, all_varchar = TRUE)
