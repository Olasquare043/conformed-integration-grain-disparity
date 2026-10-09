"""Download the NYSERDA weekly regional gasoline price panel from NY Open Data."""

import requests

from cigd.config import StudyConfig
from cigd.ingest.download import DownloadOutcome, ensure_downloaded
from cigd.ingest.manifest import INFORMATIONAL
from cigd.ingest.tlc import count_csv_rows

SOURCE = "nyserda_gasoline"


def download_nyserda(config: StudyConfig, session: requests.Session) -> list[DownloadOutcome]:
    """Download the full Socrata export of the weekly price panel."""
    url = config.sources[SOURCE]["export_url"]
    destination = config.raw_dir / SOURCE / "nyserda_gasoline_export.csv"
    # The export gains a row every week, so its checksum is recorded but never compared.
    export = ensure_downloaded(
        config, session, SOURCE, url, destination, count_csv_rows, INFORMATIONAL
    )
    return [export]
