"""Profile the monthly yellow taxi files: row counts, quality counts and schema drift."""

import duckdb
import pandas as pd
import pyarrow.parquet as pq

from cigd.config import StudyConfig
from cigd.ingest.tlc import yellow_taxi_files
from cigd.logging import make_progress
from cigd.sql_files import load_sql


def profile_trip_months(config: StudyConfig) -> pd.DataFrame:
    """Count rows and data quality problems in every monthly file."""
    query = load_sql("profile/trip_month_profile.sql")
    zone_lookup_path = config.raw_dir / "taxi_zone_lookup" / "taxi_zone_lookup.csv"
    connection = duckdb.connect()
    month_profiles = []
    files = yellow_taxi_files(config)
    with make_progress() as progress:
        task = progress.add_task("profile trip months", total=len(files))
        for month, parquet_path in files.items():
            parameters = {
                "parquet_path": str(parquet_path),
                "zone_lookup_path": str(zone_lookup_path),
                "file_month": month,
            }
            month_profiles.append(connection.execute(query, parameters).df())
            progress.advance(task)
    connection.close()
    return pd.concat(month_profiles, ignore_index=True)


def profile_trip_schema(config: StudyConfig) -> pd.DataFrame:
    """List every column and its type in every monthly file."""
    schema_rows = []
    for month, parquet_path in yellow_taxi_files(config).items():
        for column in pq.read_schema(parquet_path):
            schema_rows.append(
                {"file_month": month, "column": column.name, "type": str(column.type)}
            )
    return pd.DataFrame(schema_rows)


def compare_month_schemas(
    month: str, previous: dict[str, str], current: dict[str, str]
) -> list[dict[str, str]]:
    """List the columns added, removed or retyped between two consecutive months."""
    changes = []
    for name in current.keys() - previous.keys():
        changes.append({"file_month": month, "column": name, "change": "added"})
    for name in previous.keys() - current.keys():
        changes.append({"file_month": month, "column": name, "change": "removed"})
    for name in current.keys() & previous.keys():
        if current[name] != previous[name]:
            change = f"type {previous[name]} -> {current[name]}"
            changes.append({"file_month": month, "column": name, "change": change})
    return changes


def describe_schema_changes(schema: pd.DataFrame) -> pd.DataFrame:
    """List each month where a column appears, disappears or changes type."""
    changes = []
    columns_by_month = {
        month: dict(zip(month_schema["column"], month_schema["type"], strict=True))
        for month, month_schema in schema.groupby("file_month", sort=True)
    }
    months = list(columns_by_month)
    for previous_month, month in zip(months, months[1:], strict=False):
        changes += compare_month_schemas(
            month, columns_by_month[previous_month], columns_by_month[month]
        )
    change_table = pd.DataFrame(changes, columns=["file_month", "column", "change"])
    return change_table.sort_values(["file_month", "column"], ignore_index=True)
