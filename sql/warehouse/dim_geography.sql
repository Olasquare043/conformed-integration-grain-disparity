-- Grain: one geography member at one level of the nested hierarchy: zone, borough,
-- metro region, state, PADD and country. Each row carries the codes of all its
-- ancestors, so any fact can roll up by grouping on those columns. The 16 NYSERDA
-- regions are all in New York State, PADD 1B and the United States.
CREATE TABLE dim_geography AS
WITH country_members AS (
    SELECT DISTINCT
        6 AS level_rank,
        'country' AS geography_level,
        country_code AS geography_code,
        country_name AS geography_name,
        CAST(NULL AS INTEGER) AS zone_id,
        CAST(NULL AS VARCHAR) AS borough_code,
        CAST(NULL AS VARCHAR) AS region_code,
        CAST(NULL AS VARCHAR) AS state_code,
        CAST(NULL AS VARCHAR) AS padd_code,
        country_code
    FROM stg_borough_region
),

padd_members AS (
    SELECT DISTINCT
        5, 'padd', padd_code, padd_name,
        NULL, NULL, NULL, NULL, padd_code, country_code
    FROM stg_borough_region
),

state_members AS (
    SELECT DISTINCT
        4, 'state', state_code, state_name,
        NULL, NULL, NULL, state_code, padd_code, country_code
    FROM stg_borough_region
),

region_members_from_boroughs AS (
    SELECT DISTINCT
        3, 'metro_region', region_code, region_name,
        NULL, NULL, region_code, state_code, padd_code, country_code
    FROM stg_borough_region
),

nyserda_region_members AS (
    SELECT
        3, 'metro_region', region_code, region_name,
        NULL, NULL, region_code, 'NY', 'PADD_1B', 'US'
    FROM stg_metro_region
),

borough_members AS (
    SELECT
        2, 'borough', borough_code, borough_name,
        NULL, borough_code, region_code, state_code, padd_code, country_code
    FROM stg_borough_region
),

zone_members AS (
    SELECT
        1, 'zone', lpad(CAST(zones.zone_id AS VARCHAR), 3, '0'), zones.zone_name,
        zones.zone_id, boroughs.borough_code, boroughs.region_code,
        boroughs.state_code, boroughs.padd_code, boroughs.country_code
    FROM stg_zone_lookup AS zones
    INNER JOIN stg_borough_region AS boroughs
        ON boroughs.borough_name = zones.borough_name
),

all_members AS (
    SELECT * FROM country_members
    UNION ALL SELECT * FROM padd_members
    UNION ALL SELECT * FROM state_members
    -- New York City appears in both region sources with the same codes; UNION keeps one.
    UNION ALL (
        SELECT * FROM region_members_from_boroughs
        UNION
        SELECT * FROM nyserda_region_members
    )
    UNION ALL SELECT * FROM borough_members
    UNION ALL SELECT * FROM zone_members
)

SELECT
    CAST(ROW_NUMBER() OVER (ORDER BY level_rank DESC, geography_code) AS INTEGER)
        AS geography_key,
    geography_level,
    geography_code,
    geography_name,
    zone_id,
    borough_code,
    region_code,
    state_code,
    padd_code,
    country_code,
    region_code IN (SELECT region_code FROM stg_metro_region) AS is_nyserda_region
FROM all_members
ORDER BY geography_key
