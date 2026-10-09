"""Record every downloaded file in provenance/manifest.csv and check it on re-runs."""

import csv
import hashlib
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from cigd.logging import get_logger

logger = get_logger(__name__)

# A frozen file must keep its checksum for the study to be reproducible. An
# informational file is expected to change (for example an export that grows
# every week); it is recorded for provenance but never compared.
MUST_MATCH = "must_match"
INFORMATIONAL = "informational"


@dataclass
class ManifestRecord:
    """One downloaded file, as it appears in the manifest."""

    source: str
    file_name: str
    url: str
    query_parameters: str
    accessed_utc: str
    size_bytes: int
    sha256: str
    row_count: int
    checksum_policy: str


MANIFEST_COLUMNS = [field.name for field in fields(ManifestRecord)]


def sha256_of_file(path: Path) -> str:
    """Return the SHA-256 checksum of a file, read in 1 MB blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_manifest(manifest_path: Path) -> dict[tuple[str, str], ManifestRecord]:
    """Read the manifest into a lookup keyed by (source, file name)."""
    if not manifest_path.exists():
        return {}
    with manifest_path.open(newline="", encoding="utf-8") as manifest_file:
        rows = list(csv.DictReader(manifest_file))
    records = {}
    for row in rows:
        record = ManifestRecord(
            **{**row, "size_bytes": int(row["size_bytes"]), "row_count": int(row["row_count"])}
        )
        records[(record.source, record.file_name)] = record
    return records


def write_manifest(manifest_path: Path, records: dict[tuple[str, str], ManifestRecord]) -> None:
    """Write the manifest sorted by source and file name, so diffs stay small."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", newline="", encoding="utf-8") as manifest_file:
        writer = csv.DictWriter(manifest_file, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for key in sorted(records):
            writer.writerow(asdict(records[key]))


def reconcile_with_manifest(manifest_path: Path, observed: ManifestRecord) -> str:
    """Compare one file with its committed manifest row and return what happened.

    New files are added. A frozen file whose checksum differs is reported loudly
    and the committed row is kept, so the manifest always describes the snapshot
    the paper was built from.
    """
    records = read_manifest(manifest_path)
    key = (observed.source, observed.file_name)
    committed = records.get(key)

    if committed is None:
        records[key] = observed
        write_manifest(manifest_path, records)
        return "added"

    if committed.sha256 == observed.sha256:
        return "unchanged"

    if committed.checksum_policy == INFORMATIONAL:
        records[key] = observed
        write_manifest(manifest_path, records)
        return "refreshed"

    logger.warning(
        "SOURCE CHANGED: %s / %s no longer matches the frozen manifest "
        "(committed sha256 %s, rows %s; observed sha256 %s, rows %s). "
        "Results built from this file may differ from the paper.",
        observed.source,
        observed.file_name,
        committed.sha256[:12],
        committed.row_count,
        observed.sha256[:12],
        observed.row_count,
    )
    return "changed"
