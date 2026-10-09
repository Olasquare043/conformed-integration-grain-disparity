"""Bound the NYSERDA release delay from archived copies of the NY Open Data export.

Evidence for the publication-lag assumption in docs/analysis_plan.md; not part of
the pipeline. Every Internet Archive copy of the dataset's CSV export shows, at a
known capture time, the newest week label then published. So the newest label
had appeared by the capture time (an upper bound on its delay), and the label one
week later had not (a lower bound on its delay). Archived copies of the dataset's
metadata add the time the rows were last updated. Run from docs/evidence/ with:

    uv run python collect_nyserda_release_dates.py nyserda_release_dates.csv
"""

import csv
import io
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

CDX_URL = "https://web.archive.org/cdx/search/cdx"
EXPORT_URLS = (
    "data.ny.gov/api/views/nqur-w4p7/rows.csv",
    "data.ny.gov/api/views/nqur-w4p7/rows.csv?accessType=DOWNLOAD",
)
METADATA_URL = "data.ny.gov/api/views/nqur-w4p7"
EXPORT_DATE_FORMAT = "%m/%d/%Y"

session = requests.Session()
session.headers["User-Agent"] = "cigd-research-evidence/0.1"


def fetch(url: str, params: dict | None = None) -> requests.Response:
    """GET a URL, waiting and retrying while the Internet Archive is busy."""
    for attempt in range(3):
        response = session.get(url, params=params, timeout=120)
        if response.status_code == 200:
            return response
        time.sleep(20 * (attempt + 1))
    response.raise_for_status()
    return response


def capture_times(url: str) -> list[str]:
    """List the successful Internet Archive captures of one exact URL."""
    query = {"url": url, "output": "json", "fl": "timestamp", "filter": "statuscode:200"}
    return [row[0] for row in fetch(CDX_URL, query).json()[1:]]


def capture_datetime(timestamp: str) -> datetime:
    """Turn an Internet Archive timestamp into a UTC datetime."""
    return datetime.strptime(timestamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)


def newest_label(timestamp: str, url: str) -> datetime | None:
    """Return the newest week label in one archived export, or None if unreadable."""
    try:
        text = fetch(f"https://web.archive.org/web/{timestamp}id_/https://{url}").text
    except requests.RequestException:
        return None
    rows = list(csv.reader(io.StringIO(text)))
    labels = []
    for row in rows[1:]:
        try:
            labels.append(datetime.strptime(row[0], EXPORT_DATE_FORMAT))
        except (ValueError, IndexError):
            continue
    return max(labels).replace(tzinfo=UTC) if labels else None


def rows_updated_at(timestamp: str) -> str:
    """Return the rowsUpdatedAt time from one archived metadata capture, if readable."""
    try:
        metadata = fetch(f"https://web.archive.org/web/{timestamp}id_/https://{METADATA_URL}")
        updated = metadata.json().get("rowsUpdatedAt")
    except (requests.RequestException, ValueError):
        return ""
    return datetime.fromtimestamp(updated, UTC).isoformat() if updated else ""


def export_evidence() -> pd.DataFrame:
    """Describe every readable archived export: capture time and newest label."""
    rows = []
    for url in EXPORT_URLS:
        for timestamp in capture_times(url):
            label = newest_label(timestamp, url)
            time.sleep(1.5)
            if label is None:
                continue
            captured = capture_datetime(timestamp)
            next_label = label + timedelta(days=7)
            rows.append(
                {
                    "kind": "export",
                    "captured_utc": captured.isoformat(),
                    "archive_url": f"https://web.archive.org/web/{timestamp}/https://{url}",
                    "newest_label": label.date().isoformat(),
                    "newest_label_out_within_days": (captured - label).days,
                    "next_label": next_label.date().isoformat(),
                    "next_label_missing_after_days": (captured - next_label).days,
                    "rows_updated_utc": "",
                }
            )
    return pd.DataFrame(rows)


def metadata_evidence() -> pd.DataFrame:
    """Describe every readable archived metadata capture: capture time and last update."""
    rows = []
    for timestamp in capture_times(METADATA_URL):
        updated = rows_updated_at(timestamp)
        time.sleep(1.5)
        if not updated:
            continue
        rows.append(
            {
                "kind": "metadata",
                "captured_utc": capture_datetime(timestamp).isoformat(),
                "archive_url": f"https://web.archive.org/web/{timestamp}/https://{METADATA_URL}",
                "rows_updated_utc": updated,
            }
        )
    return pd.DataFrame(rows)


def main(output_path: Path) -> None:
    """Collect the evidence and write it as CSV, newest capture last."""
    evidence = pd.concat([export_evidence(), metadata_evidence()], ignore_index=True)
    evidence = evidence.sort_values("captured_utc", ignore_index=True)
    evidence.to_csv(output_path, index=False, lineterminator="\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
