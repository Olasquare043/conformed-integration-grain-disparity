"""Download one file, describe it, and reconcile it with the manifest."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from cigd.config import StudyConfig
from cigd.ingest.http import TIMEOUT_SECONDS
from cigd.ingest.manifest import ManifestRecord, reconcile_with_manifest, sha256_of_file
from cigd.logging import get_logger, make_download_progress

logger = get_logger(__name__)

RowCounter = Callable[[Path], int]


@dataclass
class DownloadOutcome:
    """A file on disk, its manifest record, and how it compared with the manifest."""

    path: Path
    record: ManifestRecord
    status: str


def stream_to_file(
    session: requests.Session,
    url: str,
    destination: Path,
    request_parameters: dict[str, Any] | None = None,
) -> None:
    """Stream a URL to disk with a progress bar, renaming into place only when complete."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial_path = destination.with_name(destination.name + ".part")
    with session.get(
        url, params=request_parameters, stream=True, timeout=TIMEOUT_SECONDS
    ) as response:
        response.raise_for_status()
        total_bytes = int(response.headers.get("Content-Length", 0)) or None
        with make_download_progress() as progress, partial_path.open("wb") as file:
            task = progress.add_task(destination.name, total=total_bytes)
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                file.write(chunk)
                progress.advance(task, len(chunk))
    partial_path.replace(destination)


def modified_time_utc(path: Path) -> str:
    """Return a file's modification time as an ISO 8601 UTC string."""
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return modified.isoformat(timespec="seconds")


def describe_file(
    path: Path,
    source: str,
    url: str,
    recorded_parameters: dict[str, Any],
    row_count: int,
    checksum_policy: str,
) -> ManifestRecord:
    """Build the manifest record for a file already on disk."""
    return ManifestRecord(
        source=source,
        file_name=path.name,
        url=url,
        query_parameters=json.dumps(recorded_parameters, sort_keys=True),
        # For a cached file this is when it was written, which is when it was downloaded.
        accessed_utc=modified_time_utc(path),
        size_bytes=path.stat().st_size,
        sha256=sha256_of_file(path),
        row_count=row_count,
        checksum_policy=checksum_policy,
    )


def ensure_downloaded(
    config: StudyConfig,
    session: requests.Session,
    source: str,
    url: str,
    destination: Path,
    count_rows: RowCounter,
    checksum_policy: str,
    request_parameters: dict[str, Any] | None = None,
    recorded_parameters: dict[str, Any] | None = None,
) -> DownloadOutcome:
    """Download a file unless it is already on disk, then check it against the manifest.

    recorded_parameters is what goes into the manifest; it differs from
    request_parameters only when the request carries a secret such as an API key.
    """
    if destination.exists():
        logger.info("cached     %s", destination.name)
    else:
        stream_to_file(session, url, destination, request_parameters)
        logger.info("downloaded %s", destination.name)

    if recorded_parameters is None:
        recorded_parameters = request_parameters or {}
    record = describe_file(
        destination, source, url, recorded_parameters, count_rows(destination), checksum_policy
    )
    status = reconcile_with_manifest(config.manifest_path, record)
    return DownloadOutcome(destination, record, status)
