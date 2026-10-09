"""The NYSERDA cutoff snapshot keeps exact bytes and rejects a changed export layout."""

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from cigd.config import load_config
from cigd.ingest.nyserda import read_price_panel, snapshot_path, write_cutoff_snapshot

EXPORT_LINES = [
    "Date,Value\r\n",
    "01/15/2024,3.10\r\n",
    "01/08/2024,3.05\r\n",
    "01/01/2024,\r\n",
]


def test_snapshot_keeps_weeks_up_to_cutoff_byte_for_byte(tmp_path: Path) -> None:
    export = tmp_path / "export.csv"
    export.write_bytes("".join(EXPORT_LINES).encode("utf-8"))
    snapshot = tmp_path / "snapshot.csv"

    write_cutoff_snapshot(export, snapshot, cutoff=date(2024, 1, 8))

    expected = EXPORT_LINES[0] + EXPORT_LINES[2] + EXPORT_LINES[3]
    assert snapshot.read_bytes() == expected.encode("utf-8")


def test_changed_export_columns_stop_the_run(tmp_path: Path) -> None:
    config = replace(load_config("smoke"), raw_dir=tmp_path)
    frozen = snapshot_path(config)
    frozen.parent.mkdir(parents=True)
    frozen.write_text("Date,Some Renamed Column\n01/01/2024,3.00\n", encoding="utf-8")

    with pytest.raises(ValueError, match="columns changed"):
        read_price_panel(config)
