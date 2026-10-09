"""Stream historical yellow taxi months into zone-day trip counts, keeping no raw file.

Each month from the history window is downloaded, checksummed into the manifest,
aggregated to one row per pickup zone per day, and deleted. Only the small
aggregate stays on disk, so the trip-demand history reaches back to 2017 without
storing about 10 GB of trip records.
"""

from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import requests

from cigd.config import StudyConfig
from cigd.ingest.download import DownloadOutcome, describe_file, stream_to_file
from cigd.ingest.manifest import (
    MUST_MATCH,
    STORED_AS_AGGREGATE_ONLY,
    read_manifest,
    reconcile_with_manifest,
)
from cigd.ingest.tlc import count_parquet_rows, months_in_window
from cigd.logging import get_logger, make_progress
from cigd.sql_files import load_sql

logger = get_logger(__name__)

SOURCE = "yellow_taxi"


def zone_day_aggregate_path(config: StudyConfig, month: str) -> Path:
    """Return where one month's zone-day trip counts are stored."""
    return config.raw_dir / "yellow_taxi_zone_day" / f"zone_day_{month}.parquet"


def count_trips_by_zone_day(parquet_path: Path, month: str) -> pa.Table:
    """Count every published trip by pickup zone and pickup day in one monthly file."""
    parameters = {"parquet_path": str(parquet_path), "file_month": month}
    with duckdb.connect() as connection:
        return connection.execute(
            load_sql("staging/zone_day_trip_counts.sql"), parameters
        ).fetch_arrow_table()


def committed_record_outcome(config: StudyConfig, month: str, url: str) -> DownloadOutcome:
    """Describe a month whose aggregate already exists, using its manifest row."""
    file_name = Path(url).name
    record = read_manifest(config.manifest_path)[(SOURCE, file_name)]
    return DownloadOutcome(zone_day_aggregate_path(config, month), record, "aggregate_cached")


def stream_history_month(
    config: StudyConfig, session: requests.Session, month: str
) -> DownloadOutcome:
    """Download one month, record its checksum, keep its zone-day counts, delete the file."""
    url = config.sources["yellow_taxi"]["url_template"].format(month=month)
    aggregate_path = zone_day_aggregate_path(config, month)
    if aggregate_path.exists():
        return committed_record_outcome(config, month, url)

    temporary_path = config.raw_dir / "yellow_taxi_streaming" / Path(url).name
    stream_to_file(session, url, temporary_path)
    record = describe_file(
        temporary_path,
        SOURCE,
        url,
        {},
        count_parquet_rows(temporary_path),
        MUST_MATCH,
        stored_locally=STORED_AS_AGGREGATE_ONLY,
    )
    status = reconcile_with_manifest(config.manifest_path, record)

    aggregate_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(count_trips_by_zone_day(temporary_path, month), aggregate_path)
    temporary_path.unlink()
    logger.info("aggregated and deleted %s (%d trips)", temporary_path.name, record.row_count)
    return DownloadOutcome(aggregate_path, record, status)


def download_trip_history(config: StudyConfig, session: requests.Session) -> list[DownloadOutcome]:
    """Stream every month of the trip history window."""
    months = months_in_window(config.trip_history_first_month, config.trip_history_last_month)
    outcomes = []
    with make_progress() as progress:
        task = progress.add_task("trip history months", total=len(months))
        for month in months:
            outcomes.append(stream_history_month(config, session, month))
            progress.advance(task)
    return outcomes
