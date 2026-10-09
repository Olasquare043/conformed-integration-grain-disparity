"""Download EIA weekly retail gasoline prices, used only to cross-check the NYSERDA panel."""

import json
import os
from pathlib import Path
from typing import Any

import requests

from cigd.config import StudyConfig
from cigd.ingest.download import DownloadOutcome, describe_file
from cigd.ingest.http import TIMEOUT_SECONDS
from cigd.ingest.manifest import MUST_MATCH, reconcile_with_manifest
from cigd.logging import get_logger

logger = get_logger(__name__)

SOURCE = "eia_gasoline"
# EIA v2 returns at most 5,000 rows per JSON request.
EIA_PAGE_LIMIT = 5000


def eia_query(config: StudyConfig) -> dict[str, Any]:
    """Build the EIA query for the study window, without the API key."""
    return {
        "frequency": "weekly",
        "data[0]": "value",
        "facets[series][]": sorted(config.sources[SOURCE]["series"]),
        "start": config.price_first_week.isoformat(),
        "end": config.data_cutoff_date.isoformat(),
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "sort[1][column]": "series",
        "sort[1][direction]": "asc",
        "length": EIA_PAGE_LIMIT,
    }


def fetch_eia_records(session: requests.Session, url: str, query: dict[str, Any]) -> list[dict]:
    """Request the weekly series and return the data rows."""
    api_key = os.environ.get("EIA_API_KEY", "")
    if not api_key:
        raise RuntimeError("EIA_API_KEY is not set. Copy .env.example to .env and add a key.")

    response = session.get(url, params={**query, "api_key": api_key}, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    body = response.json()["response"]
    records = body["data"]
    if int(body["total"]) != len(records):
        raise RuntimeError(
            f"EIA returned {len(records)} of {body['total']} rows; the window needs pagination."
        )
    return records


def count_json_records(path: Path) -> int:
    """Count the records in a JSON array file."""
    return len(json.loads(path.read_text(encoding="utf-8")))


def download_eia(config: StudyConfig, session: requests.Session) -> list[DownloadOutcome]:
    """Download the EIA series once and record them in the manifest."""
    url = config.sources[SOURCE]["api_url"]
    query = eia_query(config)
    file_name = f"eia_weekly_regular_{query['start']}_{query['end']}.json"
    destination = config.raw_dir / SOURCE / file_name

    if destination.exists():
        logger.info("cached     %s", destination.name)
    else:
        records = fetch_eia_records(session, url, query)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Only the data rows are kept: the response envelope carries warnings and
        # version strings that would change the checksum without changing the data.
        destination.write_text(json.dumps(records, indent=1) + "\n", encoding="utf-8")
        logger.info("downloaded %s (%d rows)", destination.name, len(records))

    record = describe_file(
        destination, SOURCE, url, query, count_json_records(destination), MUST_MATCH
    )
    status = reconcile_with_manifest(config.manifest_path, record)
    return [DownloadOutcome(destination, record, status)]
