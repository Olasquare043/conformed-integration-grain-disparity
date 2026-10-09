-- Grain: one validity rule (plus "kept") per file year. trips_failing_rule counts every
-- trip that fails the rule; trips_assigned counts the trips removed by it when the
-- rules are applied in rule_order, so trips_assigned adds up to the published total.
CREATE TABLE audit_trip_validity AS
WITH rule_order (rule_order, rule) AS (
    VALUES
        (1, 'pickup_outside_file_month'),
        (2, 'excluded_vendor'),
        (3, 'nonpositive_duration'),
        (4, 'duration_below_minimum'),
        (5, 'duration_above_maximum'),
        (6, 'nonpositive_distance'),
        (7, 'distance_above_maximum'),
        (8, 'speed_above_maximum'),
        (9, 'unknown_zone'),
        (10, 'kept')
),

flagged AS (
    SELECT
        left(file_month, 4) AS file_year,
        CASE
            WHEN fails_pickup_outside_file_month THEN 'pickup_outside_file_month'
            WHEN fails_excluded_vendor THEN 'excluded_vendor'
            WHEN fails_nonpositive_duration THEN 'nonpositive_duration'
            WHEN fails_duration_below_minimum THEN 'duration_below_minimum'
            WHEN fails_duration_above_maximum THEN 'duration_above_maximum'
            WHEN fails_nonpositive_distance THEN 'nonpositive_distance'
            WHEN fails_distance_above_maximum THEN 'distance_above_maximum'
            WHEN fails_speed_above_maximum THEN 'speed_above_maximum'
            WHEN fails_unknown_zone THEN 'unknown_zone'
            ELSE 'kept'
        END AS assigned_rule,
        fails_pickup_outside_file_month,
        fails_excluded_vendor,
        fails_nonpositive_duration,
        fails_duration_below_minimum,
        fails_duration_above_maximum,
        fails_nonpositive_distance,
        fails_distance_above_maximum,
        fails_speed_above_maximum,
        fails_unknown_zone
    FROM stg_trip_validity
),

failing_counts_wide AS (
    SELECT
        file_year,
        SUM(CAST(fails_pickup_outside_file_month AS BIGINT)) AS pickup_outside_file_month,
        SUM(CAST(fails_excluded_vendor AS BIGINT)) AS excluded_vendor,
        SUM(CAST(fails_nonpositive_duration AS BIGINT)) AS nonpositive_duration,
        SUM(CAST(fails_duration_below_minimum AS BIGINT)) AS duration_below_minimum,
        SUM(CAST(fails_duration_above_maximum AS BIGINT)) AS duration_above_maximum,
        SUM(CAST(fails_nonpositive_distance AS BIGINT)) AS nonpositive_distance,
        SUM(CAST(fails_distance_above_maximum AS BIGINT)) AS distance_above_maximum,
        SUM(CAST(fails_speed_above_maximum AS BIGINT)) AS speed_above_maximum,
        SUM(CAST(fails_unknown_zone AS BIGINT)) AS unknown_zone
    FROM flagged
    GROUP BY file_year
),

failing_counts AS (
    UNPIVOT failing_counts_wide
    ON COLUMNS(* EXCLUDE (file_year))
    INTO NAME rule VALUE trips_failing_rule
),

assigned_counts AS (
    SELECT
        file_year,
        assigned_rule AS rule,
        COUNT(*) AS trips_assigned
    FROM flagged
    GROUP BY file_year, assigned_rule
),

years AS (
    SELECT DISTINCT file_year FROM flagged
)

SELECT
    years.file_year,
    rule_order.rule_order,
    rule_order.rule,
    failing_counts.trips_failing_rule,
    COALESCE(assigned_counts.trips_assigned, 0) AS trips_assigned
FROM years
CROSS JOIN rule_order
LEFT JOIN failing_counts
    ON failing_counts.file_year = years.file_year
    AND failing_counts.rule = rule_order.rule
LEFT JOIN assigned_counts
    ON assigned_counts.file_year = years.file_year
    AND assigned_counts.rule = rule_order.rule
ORDER BY years.file_year, rule_order.rule_order
