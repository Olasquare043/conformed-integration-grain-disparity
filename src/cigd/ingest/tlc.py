"""Download NYC TLC monthly trip files and the taxi zone lookup."""

import csv
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import requests

from cigd.config import StudyConfig
from cigd.ingest.download import DownloadOutcome, ensure_downloaded
from cigd.ingest.manifest import MUST_MATCH


def months_in_window(first_month: str, last_month: str) -> list[str]:
    """List every month from first to last inclusive, as YYYY-MM."""
    month_periods = pd.period_range(first_month, last_month, freq="M")
    return [str(period) for period in month_periods]


def yellow_taxi_files(config: StudyConfig) -> dict[str, Path]:
    """Map each study month to its downloaded yellow taxi file."""
    url_template = config.sources["yellow_taxi"]["url_template"]
    files = {}
    for month in months_in_window(config.trip_first_month, config.trip_last_month):
        file_name = Path(url_template.format(month=month)).name
        files[month] = config.raw_dir / "yellow_taxi" / file_name
    return files


def count_parquet_rows(path: Path) -> int:
    """Read the row count from the Parquet footer without loading any data."""
    return pq.ParquetFile(path).metadata.num_rows


def count_csv_rows(path: Path) -> int:
    """Count data rows in a CSV file, excluding the header."""
    with path.open(newline="", encoding="utf-8-sig") as csv_file:
        return sum(1 for _ in csv.DictReader(csv_file))


def download_trip_months(
    config: StudyConfig, session: requests.Session, source: str
) -> list[DownloadOutcome]:
    """Download one TLC trip file per month in the study window."""
    url_template = config.sources[source]["url_template"]
    outcomes = []
    for month in months_in_window(config.trip_first_month, config.trip_last_month):
        url = url_template.format(month=month)
        destination = config.raw_dir / source / Path(url).name
        outcome = ensure_downloaded(
            config, session, source, url, destination, count_parquet_rows, MUST_MATCH
        )
        outcomes.append(outcome)
    return outcomes


def download_zone_lookup(config: StudyConfig, session: requests.Session) -> DownloadOutcome:
    """Download the taxi zone lookup that maps each zone to its borough."""
    url = config.sources["taxi_zone_lookup"]["url"]
    destination = config.raw_dir / "taxi_zone_lookup" / Path(url).name
    return ensure_downloaded(
        config, session, "taxi_zone_lookup", url, destination, count_csv_rows, MUST_MATCH
    )


def download_tlc(config: StudyConfig, session: requests.Session) -> list[DownloadOutcome]:
    """Download the zone lookup, the yellow taxi months and, if enabled, the HVFHV months."""
    outcomes = [download_zone_lookup(config, session)]
    outcomes += download_trip_months(config, session, "yellow_taxi")
    if config.include_high_volume_fhv:
        outcomes += download_trip_months(config, session, "high_volume_fhv")
    return outcomes
