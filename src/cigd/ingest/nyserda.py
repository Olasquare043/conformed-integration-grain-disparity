"""Download the NYSERDA weekly regional gasoline price panel from NY Open Data."""

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

from cigd.config import StudyConfig
from cigd.ingest.download import DownloadOutcome, describe_file, ensure_downloaded
from cigd.ingest.manifest import INFORMATIONAL, MUST_MATCH, reconcile_with_manifest
from cigd.ingest.tlc import count_csv_rows
from cigd.reference import read_regions

SOURCE = "nyserda_gasoline"
# The export writes each week as MM/DD/YYYY in its first column.
EXPORT_DATE_FORMAT = "%m/%d/%Y"
DATE_COLUMN = "Date"
STATE_AVERAGE_COLUMN = "New York State Average ($/gal)"
STATE_SERIES_CODE = "new_york_state"


def export_path(config: StudyConfig) -> Path:
    """Return where the full export is stored."""
    return config.raw_dir / SOURCE / "nyserda_gasoline_export.csv"


def snapshot_path(config: StudyConfig) -> Path:
    """Return where the frozen weeks up to the cutoff are stored."""
    file_name = f"nyserda_gasoline_through_{config.data_cutoff_date.isoformat()}.csv"
    return config.raw_dir / SOURCE / file_name


def parse_week_date(csv_line: str) -> date:
    """Read the week date from the first field of one export line."""
    date_text = csv_line.split(",", 1)[0]
    return datetime.strptime(date_text, EXPORT_DATE_FORMAT).date()


def write_cutoff_snapshot(source_file: Path, snapshot_file_path: Path, cutoff: date) -> None:
    """Copy the header and every week on or before the cutoff, byte for byte."""
    with source_file.open(encoding="utf-8", newline="") as export_file:
        header, *week_lines = export_file.readlines()
    kept_lines = [line for line in week_lines if parse_week_date(line) <= cutoff]
    with snapshot_file_path.open("w", encoding="utf-8", newline="") as snapshot_file:
        snapshot_file.write(header)
        snapshot_file.writelines(kept_lines)


def download_nyserda(config: StudyConfig, session: requests.Session) -> list[DownloadOutcome]:
    """Download the full export, then freeze the weeks up to the study cutoff."""
    url = config.sources[SOURCE]["export_url"]
    full_export_path = export_path(config)
    # The export gains a row every week, so its checksum is recorded but never compared.
    export = ensure_downloaded(
        config, session, SOURCE, url, full_export_path, count_csv_rows, INFORMATIONAL
    )

    # The snapshot is what the analysis reads, and its checksum must never change.
    cutoff = config.data_cutoff_date
    frozen_path = snapshot_path(config)
    write_cutoff_snapshot(full_export_path, frozen_path, cutoff)
    snapshot_record = describe_file(
        frozen_path,
        SOURCE,
        url,
        {"weeks_on_or_before": cutoff.isoformat(), "derived_from": full_export_path.name},
        count_csv_rows(frozen_path),
        MUST_MATCH,
    )
    snapshot_status = reconcile_with_manifest(config.manifest_path, snapshot_record)
    snapshot = DownloadOutcome(frozen_path, snapshot_record, snapshot_status)
    return [export, snapshot]


def read_price_panel(config: StudyConfig) -> pd.DataFrame:
    """Reshape the frozen snapshot to one row per series per week.

    Blank cells stay as missing prices, so gaps remain visible downstream.
    """
    regions = read_regions()
    series_code_by_column = {STATE_AVERAGE_COLUMN: STATE_SERIES_CODE}
    series_code_by_column.update(zip(regions.nyserda_column, regions.region_code, strict=True))

    wide = pd.read_csv(snapshot_path(config), dtype=str)
    expected_columns = [DATE_COLUMN, *series_code_by_column]
    if list(wide.columns) != expected_columns:
        raise ValueError(
            f"NYSERDA export columns changed.\nExpected: {expected_columns}\n"
            f"Found:    {list(wide.columns)}"
        )

    wide = wide.rename(columns={DATE_COLUMN: "week_start", **series_code_by_column})
    panel = wide.melt(id_vars="week_start", var_name="series_code", value_name="price_text")
    panel["week_start"] = pd.to_datetime(panel["week_start"], format=EXPORT_DATE_FORMAT)
    panel["price_usd_per_gallon"] = pd.to_numeric(panel["price_text"])
    panel = panel.drop(columns="price_text")
    # The snapshot already stops at the cutoff; this drops weeks before the study window.
    in_window = panel["week_start"] >= pd.Timestamp(config.price_first_week)
    return panel[in_window].sort_values(["series_code", "week_start"]).reset_index(drop=True)
