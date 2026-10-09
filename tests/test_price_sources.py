"""The weekly price panel has no undocumented gaps and agrees with EIA within tolerance."""

import pandas as pd
import pytest

from cigd.config import StudyConfig
from cigd.ingest.eia import read_eia_prices
from cigd.ingest.nyserda import read_price_panel
from cigd.profiling.prices import crosscheck_with_eia, list_missing_weeks
from cigd.reference import read_known_price_gaps

pytestmark = pytest.mark.usefixtures("price_sources_ready")


def documented_gaps(panel: pd.DataFrame) -> set[tuple[str, pd.Timestamp]]:
    """Expand the gaps file, where "all" stands for every series."""
    gaps = set()
    for gap in read_known_price_gaps().itertuples():
        if gap.series_code == "all":
            gaps |= {(series, gap.week_start) for series in panel["series_code"].unique()}
        else:
            gaps.add((gap.series_code, gap.week_start))
    return gaps


def test_every_missing_week_is_documented(config: StudyConfig) -> None:
    panel = read_price_panel(config)
    missing = list_missing_weeks(panel, config)
    observed = set(zip(missing["series_code"], missing["week_start"], strict=True))
    undocumented = sorted(observed - documented_gaps(panel))
    assert not undocumented, f"Gaps missing from reference/known_price_gaps.csv: {undocumented}"


def test_panel_dates_are_mondays(config: StudyConfig) -> None:
    panel = read_price_panel(config)
    assert (panel["week_start"].dt.weekday == 0).all()


def test_one_row_per_series_and_week(config: StudyConfig) -> None:
    panel = read_price_panel(config)
    assert not panel.duplicated(["series_code", "week_start"]).any()


def test_state_average_agrees_with_eia(config: StudyConfig) -> None:
    crosscheck = crosscheck_with_eia(read_price_panel(config), read_eia_prices(config), config)
    tested = crosscheck[crosscheck["held_to_tolerance"]].iloc[0]
    assert tested["within_tolerance"], tested.to_dict()
