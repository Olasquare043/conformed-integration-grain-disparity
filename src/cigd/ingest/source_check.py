"""Confirm that every official source answers before a long run starts."""

import os
from dataclasses import dataclass

import requests

from cigd.config import StudyConfig
from cigd.ingest.http import TIMEOUT_SECONDS, make_session
from cigd.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SourceCheck:
    """The outcome of probing one source."""

    source: str
    url: str
    status: str
    detail: str


def check_tlc_file(session: requests.Session, source: str, url: str) -> SourceCheck:
    """Send a HEAD request for one TLC file and report its size."""
    response = session.head(url, timeout=TIMEOUT_SECONDS)
    size_text = response.headers.get("Content-Length", "unknown")
    return SourceCheck(source, url, str(response.status_code), f"{size_text} bytes")


def check_nyserda_metadata(session: requests.Session, dataset_id: str) -> SourceCheck:
    """Fetch the Socrata metadata for the NYSERDA panel and log its published columns."""
    url = f"https://data.ny.gov/api/views/{dataset_id}.json"
    response = session.get(url, timeout=TIMEOUT_SECONDS)
    if response.status_code != 200:
        return SourceCheck("nyserda_gasoline", url, str(response.status_code), "not reachable")

    metadata = response.json()
    column_names = [column["fieldName"] for column in metadata["columns"]]
    logger.info("NYSERDA dataset name: %s", metadata.get("name"))
    logger.info("NYSERDA columns: %s", column_names)
    logger.info("NYSERDA rows last updated (epoch seconds): %s", metadata.get("rowsUpdatedAt"))
    return SourceCheck("nyserda_gasoline", url, "200", f"{len(column_names)} columns")


def check_eia(session: requests.Session, api_url: str, series_ids: list[str]) -> SourceCheck:
    """Request one EIA observation to confirm the API key works."""
    api_key = os.environ.get("EIA_API_KEY", "")
    if not api_key:
        return SourceCheck("eia_gasoline", api_url, "skipped", "EIA_API_KEY is not set")

    parameters = {
        "api_key": api_key,
        "frequency": "weekly",
        "data[0]": "value",
        "facets[series][]": series_ids,
        "length": 1,
    }
    response = session.get(api_url, params=parameters, timeout=TIMEOUT_SECONDS)
    return SourceCheck("eia_gasoline", api_url, str(response.status_code), "one observation")


def check_open_meteo(session: requests.Session, api_url: str) -> SourceCheck:
    """Request one day of archive weather for Manhattan."""
    parameters = {
        "latitude": 40.78,
        "longitude": -73.97,
        "start_date": "2024-01-01",
        "end_date": "2024-01-01",
        "daily": "temperature_2m_max",
        "timezone": "America/New_York",
    }
    response = session.get(api_url, params=parameters, timeout=TIMEOUT_SECONDS)
    return SourceCheck("open_meteo", api_url, str(response.status_code), "one day")


def check_all_sources(config: StudyConfig) -> list[SourceCheck]:
    """Probe every source the study downloads from."""
    sources = config.sources
    session = make_session()
    first_trip_url = sources["yellow_taxi"]["url_template"].format(month=config.trip_first_month)
    checks = [
        check_tlc_file(session, "yellow_taxi", first_trip_url),
        check_tlc_file(session, "taxi_zone_lookup", sources["taxi_zone_lookup"]["url"]),
        check_nyserda_metadata(session, sources["nyserda_gasoline"]["dataset_id"]),
        check_eia(
            session,
            sources["eia_gasoline"]["api_url"],
            list(sources["eia_gasoline"]["series"]),
        ),
        check_open_meteo(session, sources["open_meteo"]["api_url"]),
    ]
    for check in checks:
        logger.info("%-18s %-8s %s (%s)", check.source, check.status, check.url, check.detail)
    return checks
