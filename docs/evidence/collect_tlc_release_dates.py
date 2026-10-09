"""Date the first release of each yellow taxi month from archived copies of the TLC page.

Evidence for the publication-lag rule in docs/analysis_plan.md; not part of the
pipeline. For each month it finds the last Internet Archive snapshot of the TLC
Trip Record Data page that does not list the month and the first one that does,
adds the file's Last-Modified header (an upper bound on its first release), and
checks two candidate rules. Run from docs/evidence/ with:

    uv run python collect_tlc_release_dates.py tlc_release_dates.csv
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

PAGE = "https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page"
CDX_URL = "https://web.archive.org/cdx/search/cdx"
FILE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{month}.parquet"
MONTH_PATTERN = re.compile(r"yellow_tripdata_(\d{4}-\d{2})\.parquet")
FIRST_MONTH = "2023-10"
SNAPSHOT_SPACING_DAYS = 5

session = requests.Session()
session.headers["User-Agent"] = "cigd-research-evidence/0.1"


def fetch(url: str, params: dict | None = None) -> requests.Response:
    """GET a URL, waiting and retrying while the Internet Archive is busy."""
    for attempt in range(3):
        response = session.get(url, params=params, timeout=90)
        if response.status_code == 200:
            return response
        time.sleep(20 * (attempt + 1))
    response.raise_for_status()
    return response


def snapshot_timestamps() -> list[str]:
    """List archived copies of the TLC page, about one every five days."""
    query = {
        "url": PAGE,
        "from": "20231101",
        "output": "json",
        "fl": "timestamp",
        "filter": "statuscode:200",
        "collapse": "timestamp:8",
    }
    timestamps = [row[0] for row in fetch(CDX_URL, query).json()[1:]]
    chosen = []
    for timestamp in timestamps:
        day = datetime.strptime(timestamp[:8], "%Y%m%d")
        if (
            not chosen
            or (day - datetime.strptime(chosen[-1][:8], "%Y%m%d")).days >= SNAPSHOT_SPACING_DAYS
        ):
            chosen.append(timestamp)
    return chosen


def months_listed(timestamp: str, cache: dict[str, list[str]]) -> list[str] | None:
    """Return the yellow taxi months listed in one snapshot, or None if it cannot be read."""
    if timestamp not in cache:
        try:
            html = fetch(f"https://web.archive.org/web/{timestamp}id_/{PAGE}").text
        except requests.HTTPError:
            return None
        cache[timestamp] = sorted(set(MONTH_PATTERN.findall(html)))
        time.sleep(1.5)
    return cache[timestamp]


def last_modified(month: str) -> pd.Timestamp:
    """Return the Last-Modified date of a month's file today (an upper bound on its release)."""
    header = session.head(FILE_URL.format(month=month), timeout=60).headers["Last-Modified"]
    return pd.Timestamp(datetime.strptime(header, "%a, %d %b %Y %H:%M:%S GMT").date())


def release_windows(listings: list[tuple[str, list[str]]]) -> pd.DataFrame:
    """For each month, the last snapshot without it and the first snapshot with it."""
    rows = []
    months = sorted({month for _, months in listings for month in months if month >= FIRST_MONTH})
    for month in months:
        first_with = next(ts for ts, listed in listings if month in listed)
        without = [ts for ts, listed in listings if ts < first_with and month not in listed]
        rows.append({"month": month, "snapshot_without": without[-1], "snapshot_with": first_with})
    return pd.DataFrame(rows)


def describe_rules(windows: pd.DataFrame) -> pd.DataFrame:
    """Add release bounds and check the m + 3 and m + 4 availability rules."""
    windows["last_modified_on_2026_10_09"] = [last_modified(month) for month in windows["month"]]
    absent_on = pd.to_datetime(windows["snapshot_without"].str[:8])
    listed_on = pd.to_datetime(windows["snapshot_with"].str[:8])
    windows["released_after"] = absent_on.dt.date
    windows["released_by"] = (
        pd.concat([listed_on, windows["last_modified_on_2026_10_09"]], axis=1).min(axis=1).dt.date
    )
    month_start = pd.to_datetime(windows["month"])
    for months_later in (3, 4):
        rule_day = month_start + pd.DateOffset(months=months_later)
        column = f"usable_from_first_of_m_plus_{months_later}"
        windows[column] = rule_day.dt.date
        verdict = pd.Series("uncertain", index=windows.index)
        verdict[pd.to_datetime(windows["released_by"]) <= rule_day] = "released in time"
        verdict[absent_on >= rule_day] = "NOT released in time"
        windows[f"rule_m_plus_{months_later}"] = verdict
    windows["snapshot_without"] = (
        "https://web.archive.org/web/" + windows["snapshot_without"] + "/" + PAGE
    )
    windows["snapshot_with"] = (
        "https://web.archive.org/web/" + windows["snapshot_with"] + "/" + PAGE
    )
    windows["last_modified_on_2026_10_09"] = windows["last_modified_on_2026_10_09"].dt.date
    return windows


def main(output_path: Path) -> None:
    """Collect the evidence and write it as CSV."""
    cache_path = output_path.with_suffix(".cache.json")
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    listings = []
    for timestamp in snapshot_timestamps():
        listed = months_listed(timestamp, cache)
        if listed is not None:
            listings.append((timestamp, listed))
    cache_path.write_text(json.dumps(cache))
    evidence = describe_rules(release_windows(listings))
    evidence.to_csv(output_path, index=False, lineterminator="\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
