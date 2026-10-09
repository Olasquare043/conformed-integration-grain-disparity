"""Experiment A: what the integration costs (plan section 9). Descriptive, no hypothesis test."""

import time
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from cigd.config import StudyConfig
from cigd.ingest.manifest import read_manifest
from cigd.logging import get_logger, make_progress
from cigd.sql_files import load_sql
from cigd.warehouse.build import build_warehouse

logger = get_logger(__name__)

# The same question answered at four grains, finest first.
LATENCY_QUERIES = {
    "trip": "latency_trip_grain",
    "zone_day": "latency_zone_day_grain",
    "zone_week": "latency_zone_week_grain",
    "region_week": "latency_region_week_grain",
}
# Temporary valid-trip aggregates the coarser queries read, built in this order.
VALID_TRIP_AGGREGATES = ["valid_trip_zone_day", "valid_trip_zone_week", "valid_trip_region_week"]


def repeated_builds(config: StudyConfig) -> pd.DataFrame:
    """Rebuild the warehouse several times and return every step's duration per build."""
    rows = []
    for build in range(1, config.experiments["warehouse_builds"] + 1):
        summary = build_warehouse(config)
        for step, seconds in summary["step_seconds"].items():
            rows.append({"build": build, "step": step, "seconds": seconds})
        rows.append({"build": build, "step": "total", "seconds": summary["build_seconds"]})
    return pd.DataFrame(rows)


def build_time_summary(builds: pd.DataFrame) -> pd.DataFrame:
    """Return the median, minimum and maximum duration of each step across builds."""
    summary = builds.groupby("step", sort=False)["seconds"].agg(
        median_seconds="median", min_seconds="min", max_seconds="max", builds="size"
    )
    return summary.reset_index()


def table_storage(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Return each warehouse table's row count and allocated storage."""
    block_size = connection.execute("SELECT block_size FROM pragma_database_size()").fetchone()[0]
    tables = connection.execute(
        "SELECT table_name FROM duckdb_tables() WHERE NOT temporary ORDER BY table_name"
    ).fetchall()
    rows = []
    for (table_name,) in tables:
        row_count = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        # Storage is counted in whole blocks: the space the table occupies in the file.
        blocks = connection.execute(
            f"SELECT COUNT(DISTINCT block_id) FROM pragma_storage_info('{table_name}') "
            "WHERE block_id IS NOT NULL"
        ).fetchone()[0]
        rows.append(
            {"table": table_name, "rows": row_count, "allocated_bytes": blocks * block_size}
        )
    return pd.DataFrame(rows)


def raw_storage(config: StudyConfig) -> pd.DataFrame:
    """Return the downloaded bytes and rows per source, from the manifest."""
    records = pd.DataFrame(
        [vars(record) for record in read_manifest(config.manifest_path).values()]
    )
    return (
        records.groupby(["source", "stored_locally"])
        .agg(files=("file_name", "size"), bytes=("size_bytes", "sum"), rows=("row_count", "sum"))
        .reset_index()
    )


def grain_ratios(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Return the grain ratios between the trip domain and the price domain."""
    counts = connection.execute(load_sql("experiments/grain_ratios.sql")).df().iloc[0]
    ratios = {
        "valid_nyc_trips_per_nyc_region_week": counts["valid_nyc_trips"]
        / counts["fact_window_weeks"],
        "valid_trips_per_price_row": counts["valid_trips"] / counts["price_rows_in_fact_window"],
        "published_nyc_trips_per_nyc_region_week_all_years": counts["published_nyc_trips_all_years"]
        / counts["nyc_region_weeks_all_years"],
    }
    rows = [{"measure": name, "value": float(value)} for name, value in counts.items()]
    rows += [{"measure": name, "value": float(value)} for name, value in ratios.items()]
    return pd.DataFrame(rows)


def time_query(
    connection: duckdb.DuckDBPyConnection, sql_text: str, timed_runs: int
) -> tuple[np.ndarray, pd.DataFrame]:
    """Run a query once to warm up, then time it repeatedly; return the times and the answer."""
    # COUNT and SUM return different integer types; the values are what must match.
    answer = connection.execute(sql_text).df().astype({"trip_count": "int64"})
    seconds = []
    for _ in range(timed_runs):
        started = time.perf_counter()
        connection.execute(sql_text).fetchall()
        seconds.append(time.perf_counter() - started)
    return np.array(seconds), answer


def query_latency(config: StudyConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Time the same question at four grains; stop if the answers differ.

    Returns the latency per grain and the build time of each temporary aggregate.
    """
    timed_runs = config.experiments["latency_timed_runs"]
    latency_rows, aggregate_rows, answers = [], [], {}
    with duckdb.connect(str(config.warehouse_path)) as connection:
        for aggregate in VALID_TRIP_AGGREGATES:
            started = time.perf_counter()
            connection.execute(load_sql(f"experiments/{aggregate}.sql"))
            aggregate_rows.append(
                {"aggregate": aggregate, "build_seconds": time.perf_counter() - started}
            )
        with make_progress() as progress:
            task = progress.add_task("query latency", total=len(LATENCY_QUERIES))
            for grain, query_name in LATENCY_QUERIES.items():
                seconds, answers[grain] = time_query(
                    connection, load_sql(f"experiments/{query_name}.sql"), timed_runs
                )
                latency_rows.append(
                    {
                        "grain": grain,
                        "timed_runs": timed_runs,
                        "median_seconds": float(np.median(seconds)),
                        "q1_seconds": float(np.percentile(seconds, 25)),
                        "q3_seconds": float(np.percentile(seconds, 75)),
                        "result_rows": len(answers[grain]),
                    }
                )
                progress.advance(task)
    for grain, answer in answers.items():
        if not answer.equals(answers["trip"]):
            raise RuntimeError(f"The {grain} grain gives a different answer from the trip grain.")
    return pd.DataFrame(latency_rows), pd.DataFrame(aggregate_rows)


def run_integration_cost(config: StudyConfig) -> dict[str, pd.DataFrame]:
    """Run every integration-cost measurement and return the result tables."""
    builds = repeated_builds(config)
    latency, aggregate_builds = query_latency(config)
    with duckdb.connect(str(config.warehouse_path), read_only=True) as connection:
        storage = table_storage(connection)
        ratios = grain_ratios(connection)
    storage.loc[len(storage)] = {
        "table": "warehouse_file",
        "rows": None,
        "allocated_bytes": config.warehouse_path.stat().st_size,
    }
    return {
        "integration_build_times": builds,
        "integration_build_time_summary": build_time_summary(builds),
        "integration_table_storage": storage,
        "integration_raw_storage": raw_storage(config),
        "integration_grain_ratios": ratios,
        "integration_query_latency": latency,
        "integration_latency_aggregate_builds": aggregate_builds,
    }


def integration_summary(tables: dict[str, Any]) -> dict[str, Any]:
    """Return a short stage summary of the integration-cost experiment."""
    latency = tables["integration_query_latency"].set_index("grain")["median_seconds"]
    return {
        "warehouse_builds": int(tables["integration_build_times"]["build"].max()),
        "latency_trip_grain_seconds": round(float(latency["trip"]), 4),
        "latency_region_week_seconds": round(float(latency["region_week"]), 4),
    }
