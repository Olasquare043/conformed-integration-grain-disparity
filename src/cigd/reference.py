"""Read the versioned mapping CSVs in reference/."""

import pandas as pd

from cigd.config import REPOSITORY_ROOT

REFERENCE_DIR = REPOSITORY_ROOT / "reference"


def read_regions() -> pd.DataFrame:
    """Return the 16 NYSERDA metro regions with their export column and weather point."""
    return pd.read_csv(REFERENCE_DIR / "region_coordinates.csv")


def read_known_price_gaps() -> pd.DataFrame:
    """Return the documented weeks without a NYSERDA price."""
    return pd.read_csv(REFERENCE_DIR / "known_price_gaps.csv", parse_dates=["week_start"])
