"""Conformance of the warehouse: grain, referential integrity, mappings and reconciliation."""

from pathlib import Path

import duckdb
import pytest

from cigd.config import StudyConfig
from cigd.ingest.manifest import read_manifest
from cigd.ingest.nyserda import read_price_panel
from cigd.ingest.open_meteo import read_weather
from cigd.ingest.tlc import months_in_window, yellow_taxi_files
from cigd.reference import read_regions

# The columns that identify one row of each table: its declared grain.
TABLE_GRAINS = {
    "dim_date": ["date_key"],
    "dim_geography": ["geography_key"],
    "fact_trip": ["trip_id"],
    "fact_fuel_price_weekly": ["week_start_date_key", "geography_key"],
    "fact_weather_daily": ["date_key", "geography_key"],
    "agg_trip_zone_day": ["date_key", "pickup_geography_key"],
    "agg_trip_zone_week": ["week_start_date_key", "pickup_geography_key"],
    "agg_trip_region_week": ["week_start_date_key", "region_geography_key"],
    "agg_weather_region_week": ["week_start_date_key", "region_geography_key"],
}

# Every foreign key: (table, column, dimension, dimension key column).
FOREIGN_KEYS = [
    ("dim_date", "week_start_date_key", "dim_date", "date_key"),
    ("fact_trip", "pickup_date_key", "dim_date", "date_key"),
    ("fact_trip", "pickup_geography_key", "dim_geography", "geography_key"),
    ("fact_trip", "dropoff_geography_key", "dim_geography", "geography_key"),
    ("fact_fuel_price_weekly", "week_start_date_key", "dim_date", "date_key"),
    ("fact_fuel_price_weekly", "nyserda_week_label_date_key", "dim_date", "date_key"),
    ("fact_fuel_price_weekly", "geography_key", "dim_geography", "geography_key"),
    ("fact_weather_daily", "date_key", "dim_date", "date_key"),
    ("fact_weather_daily", "geography_key", "dim_geography", "geography_key"),
    ("agg_trip_zone_day", "date_key", "dim_date", "date_key"),
    ("agg_trip_zone_day", "pickup_geography_key", "dim_geography", "geography_key"),
    ("agg_trip_zone_week", "week_start_date_key", "dim_date", "date_key"),
    ("agg_trip_zone_week", "pickup_geography_key", "dim_geography", "geography_key"),
    ("agg_trip_region_week", "week_start_date_key", "dim_date", "date_key"),
    ("agg_trip_region_week", "region_geography_key", "dim_geography", "geography_key"),
    ("agg_weather_region_week", "week_start_date_key", "dim_date", "date_key"),
    ("agg_weather_region_week", "region_geography_key", "dim_geography", "geography_key"),
]

# The geography level each fact's geography key must point at.
GEOGRAPHY_LEVELS = [
    ("fact_trip", "pickup_geography_key", ("zone",)),
    ("fact_trip", "dropoff_geography_key", ("zone",)),
    ("fact_fuel_price_weekly", "geography_key", ("metro_region", "state")),
    ("fact_weather_daily", "geography_key", ("metro_region",)),
    ("agg_trip_zone_day", "pickup_geography_key", ("zone",)),
    ("agg_trip_region_week", "region_geography_key", ("metro_region",)),
    ("agg_weather_region_week", "region_geography_key", ("metro_region",)),
]


def scalar(warehouse: duckdb.DuckDBPyConnection, query: str) -> int:
    """Run a query that returns one number."""
    return warehouse.execute(query).fetchone()[0]


@pytest.mark.parametrize(("table", "grain_columns"), TABLE_GRAINS.items())
def test_every_table_is_unique_at_its_grain(
    warehouse: duckdb.DuckDBPyConnection, table: str, grain_columns: list[str]
) -> None:
    columns = ", ".join(grain_columns)
    duplicates = scalar(
        warehouse,
        f"SELECT COUNT(*) FROM (SELECT {columns} FROM {table} GROUP BY ALL HAVING COUNT(*) > 1)",
    )
    assert duplicates == 0


@pytest.mark.parametrize(("table", "column", "dimension", "key"), FOREIGN_KEYS)
def test_every_foreign_key_resolves(
    warehouse: duckdb.DuckDBPyConnection, table: str, column: str, dimension: str, key: str
) -> None:
    orphans = scalar(
        warehouse,
        f"SELECT COUNT(*) FROM {table} AS child "
        f"ANTI JOIN {dimension} AS parent ON parent.{key} = child.{column}",
    )
    assert orphans == 0


@pytest.mark.parametrize(("table", "column", "levels"), GEOGRAPHY_LEVELS)
def test_geography_keys_point_at_the_right_level(
    warehouse: duckdb.DuckDBPyConnection, table: str, column: str, levels: tuple[str, ...]
) -> None:
    level_list = ", ".join(f"'{level}'" for level in levels)
    wrong_level = scalar(
        warehouse,
        f"SELECT COUNT(*) FROM {table} AS child "
        f"JOIN dim_geography AS geography ON geography.geography_key = child.{column} "
        f"WHERE geography.geography_level NOT IN ({level_list})",
    )
    assert wrong_level == 0


def test_every_taxi_zone_is_mapped(warehouse: duckdb.DuckDBPyConnection) -> None:
    published_zones = scalar(warehouse, "SELECT COUNT(*) FROM stg_zone_lookup")
    mapped_zones = scalar(
        warehouse, "SELECT COUNT(*) FROM dim_geography WHERE geography_level = 'zone'"
    )
    assert mapped_zones == published_zones


def test_every_borough_mapping_is_used(warehouse: duckdb.DuckDBPyConnection) -> None:
    unused = scalar(
        warehouse,
        "SELECT COUNT(*) FROM stg_borough_region AS mapping "
        "ANTI JOIN stg_zone_lookup AS zones ON zones.borough_name = mapping.borough_name",
    )
    assert unused == 0


def test_every_zone_has_a_complete_hierarchy(warehouse: duckdb.DuckDBPyConnection) -> None:
    incomplete = scalar(
        warehouse,
        "SELECT COUNT(*) FROM dim_geography WHERE geography_level = 'zone' AND ("
        "borough_code IS NULL OR region_code IS NULL OR state_code IS NULL "
        "OR padd_code IS NULL OR country_code IS NULL)",
    )
    assert incomplete == 0


def test_all_sixteen_nyserda_regions_exist_in_new_york_state(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    regions = warehouse.execute(
        "SELECT geography_code FROM dim_geography "
        "WHERE geography_level = 'metro_region' AND is_nyserda_region AND state_code = 'NY'"
    ).fetchall()
    assert {code for (code,) in regions} == set(read_regions()["region_code"])


def test_newark_airport_is_in_new_jersey_and_padd_1b(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    newark = warehouse.execute(
        "SELECT region_code, state_code, padd_code, country_code "
        "FROM dim_geography WHERE geography_level = 'zone' AND zone_id = 1"
    ).fetchone()
    assert newark == ("new_jersey_outside_ny_regions", "NJ", "PADD_1B", "US")


def test_unknown_zones_map_to_the_unknown_member(warehouse: duckdb.DuckDBPyConnection) -> None:
    unknown = warehouse.execute(
        "SELECT DISTINCT region_code, state_code, padd_code, country_code "
        "FROM dim_geography WHERE geography_level = 'zone' AND zone_id IN (264, 265)"
    ).fetchall()
    assert unknown == [("unknown", "unknown", "unknown", "unknown")]


def test_nyserda_label_is_one_week_after_the_described_week(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    # A NYSERDA price dated Monday w describes the week starting Monday w - 7.
    wrong_days = scalar(
        warehouse,
        "SELECT COUNT(*) FROM dim_date WHERE nyserda_week_label_date <> week_start_date + 7 "
        "OR isodow(week_start_date) <> 1",
    )
    wrong_prices = scalar(
        warehouse,
        "SELECT COUNT(*) FROM fact_fuel_price_weekly AS prices "
        "JOIN dim_date AS described ON described.date_key = prices.week_start_date_key "
        "JOIN dim_date AS label ON label.date_key = prices.nyserda_week_label_date_key "
        "WHERE label.full_date <> described.full_date + 7",
    )
    assert wrong_days == 0
    assert wrong_prices == 0


def manifest_rows_by_month(config: StudyConfig, months: list[str]) -> dict[str, int]:
    """Return the published row count of each monthly yellow taxi file in the manifest."""
    manifest = read_manifest(config.manifest_path)
    url_template = config.sources["yellow_taxi"]["url_template"]
    rows = {}
    for month in months:
        file_name = Path(url_template.format(month=month)).name
        rows[month] = manifest[("yellow_taxi", file_name)].row_count
    return rows


def test_fact_trip_reconciles_with_the_published_files(
    warehouse: duckdb.DuckDBPyConnection, config: StudyConfig
) -> None:
    published = manifest_rows_by_month(config, list(yellow_taxi_files(config)))
    published_by_year: dict[str, int] = {}
    for month, rows in published.items():
        published_by_year[month[:4]] = published_by_year.get(month[:4], 0) + rows

    audit = warehouse.execute(
        "SELECT file_year, SUM(trips_assigned), SUM(trips_assigned) FILTER (WHERE rule = 'kept') "
        "FROM audit_trip_validity GROUP BY file_year"
    ).fetchall()
    # trip_id is YYYYMM * 10^8 + row number, so dividing by 10^10 leaves the year.
    loaded = dict(
        warehouse.execute(
            "SELECT CAST(trip_id // 10000000000 AS VARCHAR), COUNT(*) FROM fact_trip GROUP BY 1"
        ).fetchall()
    )
    for file_year, assigned_total, kept in audit:
        assert assigned_total == published_by_year[file_year]
        assert kept == loaded[file_year]


def test_zone_day_counts_reconcile_with_every_month(
    warehouse: duckdb.DuckDBPyConnection, config: StudyConfig
) -> None:
    months = months_in_window(config.trip_history_first_month, config.trip_history_last_month)
    months += list(yellow_taxi_files(config))
    published = manifest_rows_by_month(config, months)
    counted = dict(
        warehouse.execute(
            "SELECT file_month, SUM(trip_count) FROM stg_trip_zone_day GROUP BY file_month"
        ).fetchall()
    )
    assert counted == published


def test_zone_day_aggregate_drops_only_out_of_month_pickups(
    warehouse: duckdb.DuckDBPyConnection,
) -> None:
    staged_in_month = scalar(
        warehouse,
        "SELECT SUM(trip_count) FROM stg_trip_zone_day "
        "WHERE strftime(pickup_date, '%Y-%m') = file_month",
    )
    aggregated = scalar(warehouse, "SELECT SUM(trip_count) FROM agg_trip_zone_day")
    assert aggregated == staged_in_month


def test_region_week_demand_rolls_up_from_zone_days(warehouse: duckdb.DuckDBPyConnection) -> None:
    zone_days = scalar(warehouse, "SELECT SUM(trip_count) FROM agg_trip_zone_day")
    region_weeks = scalar(warehouse, "SELECT SUM(trip_count) FROM agg_trip_region_week")
    zone_weeks = scalar(warehouse, "SELECT SUM(trip_count) FROM agg_trip_zone_week")
    assert region_weeks == zone_days == zone_weeks


def test_fuel_prices_reconcile_with_the_snapshot(
    warehouse: duckdb.DuckDBPyConnection, config: StudyConfig
) -> None:
    published_prices = read_price_panel(config)["price_usd_per_gallon"].notna().sum()
    assert scalar(warehouse, "SELECT COUNT(*) FROM fact_fuel_price_weekly") == published_prices


def test_weather_reconciles_with_the_downloads(
    warehouse: duckdb.DuckDBPyConnection, config: StudyConfig
) -> None:
    assert scalar(warehouse, "SELECT COUNT(*) FROM fact_weather_daily") == len(read_weather(config))


def test_new_york_city_demand_has_no_missing_weeks(warehouse: duckdb.DuckDBPyConnection) -> None:
    # Only the first and last week may be cut short by the start of history or the cutoff.
    short_weeks = warehouse.execute(
        "SELECT demand.week_start_date_key FROM agg_trip_region_week AS demand "
        "JOIN dim_geography AS region ON region.geography_key = demand.region_geography_key "
        "WHERE region.geography_code = 'new_york_city' AND demand.days_with_trips < 7 "
        "ORDER BY 1"
    ).fetchall()
    first_week, last_week, weeks_present = warehouse.execute(
        "SELECT MIN(demand.week_start_date_key), MAX(demand.week_start_date_key), COUNT(*) "
        "FROM agg_trip_region_week AS demand "
        "JOIN dim_geography AS region ON region.geography_key = demand.region_geography_key "
        "WHERE region.geography_code = 'new_york_city'"
    ).fetchone()
    weeks_expected = scalar(
        warehouse,
        "SELECT COUNT(DISTINCT week_start_date_key) FROM dim_date "
        f"WHERE week_start_date_key BETWEEN {first_week} AND {last_week}",
    )
    assert weeks_present == weeks_expected
    assert {week for (week,) in short_weeks} <= {first_week, last_week}
