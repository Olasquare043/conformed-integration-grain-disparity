"""Run every downloader and summarise what landed."""

from collections import Counter
from collections.abc import Callable
from typing import Any

import requests

from cigd.config import StudyConfig
from cigd.ingest.download import DownloadOutcome
from cigd.ingest.eia import download_eia
from cigd.ingest.http import make_session
from cigd.ingest.nyserda import download_nyserda
from cigd.ingest.open_meteo import download_open_meteo
from cigd.ingest.tlc import download_tlc
from cigd.logging import get_logger

logger = get_logger(__name__)

Downloader = Callable[[StudyConfig, requests.Session], list[DownloadOutcome]]

DOWNLOADERS: dict[str, Downloader] = {
    "tlc": download_tlc,
    "nyserda_gasoline": download_nyserda,
    "eia_gasoline": download_eia,
    "open_meteo": download_open_meteo,
}


def download_sources(config: StudyConfig, selected: list[str] | None) -> dict[str, Any]:
    """Download the selected sources (all by default) and return a stage summary."""
    session = make_session()
    outcomes: list[DownloadOutcome] = []
    for name in selected or DOWNLOADERS:
        logger.info("source %s", name)
        outcomes += DOWNLOADERS[name](config, session)

    statuses = Counter(outcome.status for outcome in outcomes)
    changed = [outcome.record.file_name for outcome in outcomes if outcome.status == "changed"]
    if changed:
        logger.warning("Files that differ from the frozen manifest: %s", changed)
    return {
        "files": len(outcomes),
        "rows": sum(outcome.record.row_count for outcome in outcomes),
        "bytes": sum(outcome.record.size_bytes for outcome in outcomes),
        **{f"manifest_{status}": count for status, count in sorted(statuses.items())},
    }
