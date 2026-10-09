"""The manifest adds new files, keeps frozen rows, and reports changed sources."""

from dataclasses import replace
from pathlib import Path

from cigd.ingest.manifest import (
    INFORMATIONAL,
    MUST_MATCH,
    ManifestRecord,
    read_manifest,
    reconcile_with_manifest,
)


def make_record(sha256: str, policy: str = MUST_MATCH) -> ManifestRecord:
    return ManifestRecord(
        source="example",
        file_name="example.csv",
        url="https://example.org/example.csv",
        query_parameters="{}",
        accessed_utc="2026-01-01T00:00:00+00:00",
        size_bytes=10,
        sha256=sha256,
        row_count=2,
        checksum_policy=policy,
    )


def test_new_file_is_added(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.csv"
    assert reconcile_with_manifest(manifest_path, make_record("aaa")) == "added"
    assert read_manifest(manifest_path)[("example", "example.csv")].sha256 == "aaa"


def test_same_checksum_keeps_the_original_access_time(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.csv"
    reconcile_with_manifest(manifest_path, make_record("aaa"))
    later = replace(make_record("aaa"), accessed_utc="2027-01-01T00:00:00+00:00")
    assert reconcile_with_manifest(manifest_path, later) == "unchanged"
    stored = read_manifest(manifest_path)[("example", "example.csv")]
    assert stored.accessed_utc == "2026-01-01T00:00:00+00:00"


def test_changed_frozen_file_is_reported_and_not_overwritten(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.csv"
    reconcile_with_manifest(manifest_path, make_record("aaa"))
    assert reconcile_with_manifest(manifest_path, make_record("bbb")) == "changed"
    assert read_manifest(manifest_path)[("example", "example.csv")].sha256 == "aaa"


def test_informational_file_is_refreshed(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.csv"
    reconcile_with_manifest(manifest_path, make_record("aaa", INFORMATIONAL))
    assert reconcile_with_manifest(manifest_path, make_record("bbb", INFORMATIONAL)) == "refreshed"
    assert read_manifest(manifest_path)[("example", "example.csv")].sha256 == "bbb"
