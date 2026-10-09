"""Download daily historical weather from Open-Meteo for one point per metro region."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from cigd.config import StudyConfig
from cigd.ingest.download import DownloadOutcome, describe_file
from cigd.ingest.http import TIMEOUT_SECONDS
from cigd.ingest.manifest import MUST_MATCH, reconcile_with_manifest
from cigd.logging import get_logger, make_progress
from cigd.reference import read_regions

logger = get_logger(__name__)

SOURCE = "open_meteo"
# Weather starts two weeks before the first price week so weekly weather
# features for the first weeks can still look back a full week.
WEATHER_LEAD_DAYS = 14
# Response fields that describe the data. Others, such as generationtime_ms,
# change on every call and would break the checksum.
STABLE_RESPONSE_FIELDS = ("latitude", "longitude", "elevation", "timezone", "daily_units", "daily")


def weather_query(config: StudyConfig, latitude: float, longitude: float) -> dict[str, Any]:
    """Build the Open-Meteo archive query for one point over the study window."""
    weather_settings = config.sources[SOURCE]
    first_day = config.price_first_week - timedelta(days=WEATHER_LEAD_DAYS)
    return {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": first_day.isoformat(),
        "end_date": config.data_cutoff_date.isoformat(),
        "daily": ",".join(weather_settings["daily_variables"]),
        "timezone": weather_settings["timezone"],
        "models": weather_settings["model"],
    }


def fetch_weather(session: requests.Session, url: str, query: dict[str, Any]) -> dict[str, Any]:
    """Request one point's daily weather and keep only the stable response fields."""
    response = session.get(url, params=query, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    body = response.json()
    return {field: body[field] for field in STABLE_RESPONSE_FIELDS}


def weather_path(config: StudyConfig, region_code: str) -> Path:
    """Return where one region's weather for the study window is stored."""
    first_day = config.price_first_week - timedelta(days=WEATHER_LEAD_DAYS)
    cutoff = config.data_cutoff_date
    file_name = f"weather_{region_code}_{first_day.isoformat()}_{cutoff.isoformat()}.json"
    return config.raw_dir / SOURCE / file_name


def count_weather_days(path: Path) -> int:
    """Count the days in a saved weather response."""
    return len(json.loads(path.read_text(encoding="utf-8"))["daily"]["time"])


def download_region_weather(
    config: StudyConfig, session: requests.Session, region: dict[str, Any]
) -> DownloadOutcome:
    """Download and record the weather for one region's representative point."""
    url = config.sources[SOURCE]["api_url"]
    query = weather_query(config, region["latitude"], region["longitude"])
    destination = weather_path(config, region["region_code"])

    if not destination.exists():
        weather = fetch_weather(session, url, query)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(weather) + "\n", encoding="utf-8", newline="\n")

    record = describe_file(
        destination, SOURCE, url, query, count_weather_days(destination), MUST_MATCH
    )
    status = reconcile_with_manifest(config.manifest_path, record)
    return DownloadOutcome(destination, record, status)


def download_open_meteo(config: StudyConfig, session: requests.Session) -> list[DownloadOutcome]:
    """Download daily weather for every metro region."""
    regions = read_regions().to_dict("records")
    outcomes = []
    with make_progress() as progress:
        task = progress.add_task("weather regions", total=len(regions))
        for region in regions:
            outcomes.append(download_region_weather(config, session, region))
            progress.advance(task)
    return outcomes


def read_weather(config: StudyConfig) -> pd.DataFrame:
    """Return one row per region per day with every daily weather variable."""
    region_frames = []
    for region_code in read_regions().region_code:
        saved = json.loads(weather_path(config, region_code).read_text(encoding="utf-8"))
        region_weather = pd.DataFrame(saved["daily"]).rename(columns={"time": "weather_date"})
        region_weather.insert(0, "region_code", region_code)
        region_frames.append(region_weather)
    weather = pd.concat(region_frames, ignore_index=True)
    weather["weather_date"] = pd.to_datetime(weather["weather_date"])
    return weather
