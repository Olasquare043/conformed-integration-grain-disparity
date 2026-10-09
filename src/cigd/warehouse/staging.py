"""Load the sources the SQL steps read: Python-prepared frames and a view over raw trips."""

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pandas.tseries.holiday import USFederalHolidayCalendar

from cigd.config import StudyConfig
from cigd.ingest.nyserda import read_price_panel
from cigd.ingest.open_meteo import WEATHER_LEAD_DAYS, read_weather
from cigd.ingest.tlc import months_in_window, yellow_taxi_files
from cigd.ingest.trip_history import count_trips_by_zone_day, zone_day_aggregate_path
from cigd.logging import make_progress


def calendar_range(config: StudyConfig) -> tuple[date, date]:
    """Return the first and last day of dim_date: the weather lead-in to the cutoff."""
    first_weather_day = config.price_first_week - timedelta(days=WEATHER_LEAD_DAYS)
    first_history_day = date.fromisoformat(f"{config.trip_history_first_month}-01")
    return min(first_weather_day, first_history_day), config.data_cutoff_date


def us_federal_holidays(first_day: date, last_day: date) -> pd.DataFrame:
    """Return the observed US federal holidays between two days, with their names."""
    holidays = USFederalHolidayCalendar().holidays(first_day, last_day, return_name=True)
    return pd.DataFrame({"holiday_date": holidays.index.date, "holiday_name": holidays.values})


def trip_validity_thresholds(config: StudyConfig) -> pd.DataFrame:
    """Return the validity thresholds from config as a one-row table."""
    rules = config.quality["trip_validity"]
    return pd.DataFrame(
        [
            {
                "excluded_vendor_ids": rules["excluded_vendor_ids"],
                "min_duration_seconds": rules["min_duration_seconds"],
                "max_duration_seconds": rules["max_duration_seconds"],
                "max_distance_miles": rules["max_distance_miles"],
                "max_average_speed_mph": rules["max_average_speed_mph"],
            }
        ]
    )


def fuel_prices_for_staging(config: StudyConfig) -> pd.DataFrame:
    """Return the price panel with its date column named for what it is: the NYSERDA label."""
    panel = read_price_panel(config)
    return panel.rename(columns={"week_start": "nyserda_week_label"})


def zone_day_counts(config: StudyConfig) -> pa.Table:
    """Collect zone-day trip counts for every month: kept aggregates, then fact-window files.

    History months were aggregated when streamed; fact-window months are counted
    here from their raw files with the same SQL, so the measure is identical.
    """
    history_months = months_in_window(
        config.trip_history_first_month, config.trip_history_last_month
    )
    fact_files = yellow_taxi_files(config)
    monthly_tables = []
    with make_progress() as progress:
        month_count = len(history_months) + len(fact_files)
        task = progress.add_task("zone-day trip counts", total=month_count)
        for month in history_months:
            monthly_tables.append(pq.read_table(zone_day_aggregate_path(config, month)))
            progress.advance(task)
        for month, parquet_path in fact_files.items():
            monthly_tables.append(count_trips_by_zone_day(parquet_path, month))
            progress.advance(task)
    return pa.concat_tables(monthly_tables, promote_options="permissive")


def load_frame(connection: duckdb.DuckDBPyConnection, table_name: str, frame: object) -> None:
    """Copy a pandas frame or Arrow table into a warehouse table."""
    connection.register("frame_to_load", frame)
    connection.execute(f"CREATE TABLE {table_name} AS SELECT * FROM frame_to_load")
    connection.unregister("frame_to_load")


def quoted_path(path: Path) -> str:
    """Return a file path as a SQL string literal."""
    return "'" + path.as_posix().replace("'", "''") + "'"


# Columns that only some months carry, with the type to use when no month in the
# window has them. cbd_congestion_fee starts in January 2025.
OPTIONAL_TRIP_COLUMNS = {"cbd_congestion_fee": "DOUBLE"}


def create_raw_trip_view(connection: duckdb.DuckDBPyConnection, files: list[Path]) -> None:
    """Create a view over the fact-window trip files, reading all months by column name.

    union_by_name lines up columns by name, so months before 2025 read NULL for
    cbd_congestion_fee; filename and file_row_number identify each source row.
    """
    file_list = ", ".join(quoted_path(path) for path in files)
    source = (
        f"read_parquet([{file_list}], union_by_name = TRUE, "
        "filename = TRUE, file_row_number = TRUE)"
    )
    present_columns = {
        row[0] for row in connection.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()
    }
    missing_columns = [
        f"CAST(NULL AS {column_type}) AS {column_name}"
        for column_name, column_type in OPTIONAL_TRIP_COLUMNS.items()
        if column_name not in present_columns
    ]
    select_list = ", ".join(["*", *missing_columns])
    connection.execute(f"CREATE VIEW raw_yellow_trip AS SELECT {select_list} FROM {source}")


def stage_sources(connection: duckdb.DuckDBPyConnection, config: StudyConfig) -> None:
    """Load every Python-prepared source and create the raw trip view."""
    first_day, last_day = calendar_range(config)
    load_frame(connection, "stg_us_federal_holiday", us_federal_holidays(first_day, last_day))
    load_frame(connection, "stg_trip_validity_threshold", trip_validity_thresholds(config))
    load_frame(connection, "stg_fuel_price", fuel_prices_for_staging(config))
    load_frame(connection, "stg_weather", read_weather(config))
    load_frame(connection, "stg_trip_zone_day", zone_day_counts(config))
    create_raw_trip_view(connection, list(yellow_taxi_files(config).values()))
