"""Build the warehouse from scratch, one timed SQL step at a time."""

import time
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from cigd.config import StudyConfig
from cigd.logging import get_logger, make_progress
from cigd.reference import REFERENCE_DIR
from cigd.sql_files import SQL_DIR, load_sql
from cigd.warehouse.staging import calendar_range, stage_sources

logger = get_logger(__name__)

# Each file creates the table or view named after it. Order matters: every step
# reads only what the steps before it created.
WAREHOUSE_STEPS = [
    "stg_zone_lookup",
    "stg_borough_region",
    "stg_metro_region",
    "dim_date",
    "dim_geography",
    "stg_trip_validity",
    "fact_trip",
    "audit_trip_validity",
    "fact_fuel_price_weekly",
    "fact_weather_daily",
    "agg_trip_zone_day",
    "agg_trip_zone_week",
    "agg_trip_region_week",
    "agg_weather_region_week",
]
# Views over the raw files are only needed while building; dropping them keeps the
# warehouse self-contained, so it opens without the raw data.
BUILD_ONLY_VIEWS = ["stg_trip_validity", "raw_yellow_trip"]


def sql_parameters(config: StudyConfig) -> dict[str, str]:
    """Return every named parameter the warehouse SQL files may use."""
    first_day, last_day = calendar_range(config)
    return {
        "zone_lookup_path": str(config.raw_dir / "taxi_zone_lookup" / "taxi_zone_lookup.csv"),
        "borough_region_path": str(REFERENCE_DIR / "borough_to_region.csv"),
        "region_coordinates_path": str(REFERENCE_DIR / "region_coordinates.csv"),
        "first_day": first_day.isoformat(),
        "last_day": last_day.isoformat(),
    }


def parameters_used(sql_text: str, parameters: dict[str, str]) -> dict[str, str]:
    """Keep only the parameters a statement refers to; DuckDB rejects unused ones."""
    return {name: value for name, value in parameters.items() if f"${name}" in sql_text}


def grain_of(step_name: str) -> str:
    """Read the grain statement: the first sentence of a step's SQL header comment."""
    sql_lines = (SQL_DIR / "warehouse" / f"{step_name}.sql").read_text(encoding="utf-8")
    header_lines = []
    for line in sql_lines.splitlines():
        if not line.startswith("--"):
            break
        header_lines.append(line.removeprefix("--").strip())
    header = " ".join(header_lines).removeprefix("Grain:").strip()
    first_sentence = header.split(". ")[0]
    return first_sentence.removesuffix(".")


def count_rows(connection: duckdb.DuckDBPyConnection, table_name: str) -> int:
    """Return the number of rows in a warehouse table."""
    return connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]


def is_view(connection: duckdb.DuckDBPyConnection, name: str) -> bool:
    """Return whether a name in the warehouse is a view rather than a table."""
    query = "SELECT COUNT(*) FROM duckdb_views() WHERE view_name = ? AND NOT internal"
    return connection.execute(query, [name]).fetchone()[0] > 0


def run_steps(connection: duckdb.DuckDBPyConnection, config: StudyConfig) -> pd.DataFrame:
    """Run every SQL step in order and return each one's duration and row count."""
    parameters = sql_parameters(config)
    step_rows = []
    with make_progress() as progress:
        task = progress.add_task("warehouse steps", total=len(WAREHOUSE_STEPS))
        for step_name in WAREHOUSE_STEPS:
            sql_text = load_sql(f"warehouse/{step_name}.sql")
            started = time.perf_counter()
            connection.execute(sql_text, parameters_used(sql_text, parameters))
            seconds = time.perf_counter() - started
            rows = None if is_view(connection, step_name) else count_rows(connection, step_name)
            logger.info("built %-26s %8.1f s  %s rows", step_name, seconds, rows)
            step_rows.append({"step": step_name, "seconds": round(seconds, 3), "rows": rows})
            progress.advance(task)
    return pd.DataFrame(step_rows)


def describe_tables(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """List every table left in the warehouse with its grain and row count."""
    table_names = [
        row[0]
        for row in connection.execute(
            "SELECT table_name FROM duckdb_tables() ORDER BY table_name"
        ).fetchall()
    ]
    descriptions = []
    for table_name in table_names:
        sql_file = SQL_DIR / "warehouse" / f"{table_name}.sql"
        grain = grain_of(table_name) if sql_file.exists() else "loaded from Python (staging)"
        descriptions.append(
            {"table": table_name, "grain": grain, "rows": count_rows(connection, table_name)}
        )
    return pd.DataFrame(descriptions)


def write_table(frame: pd.DataFrame, path: Path) -> None:
    """Write a results table as CSV with LF line endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")


def build_warehouse(config: StudyConfig) -> dict[str, Any]:
    """Rebuild the warehouse from scratch and write its build and audit tables."""
    config.derived_dir.mkdir(parents=True, exist_ok=True)
    config.warehouse_path.unlink(missing_ok=True)
    temporary_directory = config.derived_dir / "duckdb_spill"

    started = time.perf_counter()
    with duckdb.connect(str(config.warehouse_path)) as connection:
        # Large steps may spill to disk; keep that next to the data, not on the system drive.
        connection.execute(f"SET temp_directory = '{temporary_directory.as_posix()}'")
        # Row order is never relied on (every result query sorts), which saves memory.
        connection.execute("SET preserve_insertion_order = false")
        stage_started = time.perf_counter()
        stage_sources(connection, config)
        staging_seconds = time.perf_counter() - stage_started
        steps = run_steps(connection, config)
        for view_name in BUILD_ONLY_VIEWS:
            connection.execute(f"DROP VIEW {view_name}")
        tables = describe_tables(connection)
        trip_validity = connection.execute(
            "SELECT * FROM audit_trip_validity ORDER BY file_year, rule_order"
        ).df()
        # The "kept" row has no failing count; keep the column as whole numbers.
        trip_validity["trips_failing_rule"] = trip_validity["trips_failing_rule"].astype("Int64")
        connection.execute("CHECKPOINT")
    build_seconds = time.perf_counter() - started

    staging_row = pd.DataFrame(
        [{"step": "stage_sources", "seconds": round(staging_seconds, 3), "rows": None}]
    )
    steps = pd.concat([staging_row, steps], ignore_index=True)
    write_table(steps, config.tables_dir / "warehouse_build_steps.csv")
    write_table(tables, config.tables_dir / "warehouse_tables.csv")
    write_table(trip_validity, config.tables_dir / "warehouse_trip_validity.csv")

    size_bytes = config.warehouse_path.stat().st_size
    logger.info("warehouse %s: %.1f MB", config.warehouse_path, size_bytes / 1024**2)
    rows_by_table = dict(zip(tables["table"], tables["rows"], strict=True))
    return {
        "build_seconds": round(build_seconds, 1),
        "warehouse_bytes": size_bytes,
        "fact_trip_rows": rows_by_table["fact_trip"],
        "fact_fuel_price_weekly_rows": rows_by_table["fact_fuel_price_weekly"],
        "fact_weather_daily_rows": rows_by_table["fact_weather_daily"],
        "step_seconds": dict(zip(steps["step"], steps["seconds"], strict=True)),
    }
