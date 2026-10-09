"""No feature uses information published after its forecast origin (plan section 8)."""

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from cigd.config import StudyConfig
from cigd.features.coarse import (
    RUNG_FEATURES as COARSE_RUNG_FEATURES,
)
from cigd.features.coarse import (
    CoarseExtracts,
    build_coarse_panel,
    origin_date,
    read_coarse_extracts,
)
from cigd.features.fine import (
    RECORDED_DISTANCE,
    feature_frame,
    fine_sample_path,
)
from cigd.features.fine import (
    RUNG_FEATURES as FINE_RUNG_FEATURES,
)
from cigd.features.information_sets import (
    INFORMATION_SETS,
    PRIMARY,
    last_training_month,
    last_usable_trip_day,
    last_usable_weather_day,
)
from cigd.models.learners import naive_median_durations

COARSE_FEATURE_COLUMNS = [
    column for column in COARSE_RUNG_FEATURES["C3"] if column != "region_code"
] + ["seasonal_naive_price"]
ORIGINS_CHECKED = 8


@pytest.fixture(scope="module")
def coarse_extracts(warehouse: object, config: StudyConfig) -> CoarseExtracts:
    """Read the weekly extracts once for every coarse leakage test."""
    return read_coarse_extracts(config)


def truncate_to_origin(
    extracts: CoarseExtracts, origin_week: pd.Timestamp, information_set: str, config: StudyConfig
) -> CoarseExtracts:
    """Keep only what was published by an origin: the truncated world a forecaster saw."""
    origin = origin_date(origin_week)
    weather_last_day = pd.Timestamp(last_usable_weather_day(origin, information_set, config))
    trip_last_day = pd.Timestamp(last_usable_trip_day(origin, information_set, config))
    week_end = pd.Timedelta(days=6)
    return CoarseExtracts(
        prices=extracts.prices[extracts.prices["label_date"] <= pd.Timestamp(origin)],
        weather=extracts.weather[extracts.weather["week_start"] + week_end <= weather_last_day],
        demand=extracts.demand[extracts.demand["week_start"] + week_end <= trip_last_day],
        calendar=extracts.calendar,
    )


def sample_origins(panel: pd.DataFrame) -> list[pd.Timestamp]:
    """Pick origins spread evenly over the panel, after its first year."""
    origins = sorted(panel["origin_week"].unique())[60:]
    positions = np.linspace(0, len(origins) - 1, ORIGINS_CHECKED).astype(int)
    return [origins[position] for position in positions]


@pytest.mark.parametrize("information_set", INFORMATION_SETS)
def test_coarse_features_need_nothing_published_after_the_origin(
    coarse_extracts: CoarseExtracts, config: StudyConfig, information_set: str
) -> None:
    full_panel = build_coarse_panel(coarse_extracts, information_set, config)
    for origin_week in sample_origins(full_panel):
        truncated = truncate_to_origin(coarse_extracts, origin_week, information_set, config)
        truncated_panel = build_coarse_panel(truncated, information_set, config)
        expected = full_panel[full_panel["origin_week"] == origin_week]
        seen = truncated_panel[truncated_panel["origin_week"] == origin_week]
        pd.testing.assert_frame_equal(
            expected.set_index("region_code")[COARSE_FEATURE_COLUMNS],
            seen.set_index("region_code")[COARSE_FEATURE_COLUMNS],
            obj=f"features at origin {origin_week.date()} ({information_set})",
        )


@pytest.mark.parametrize("information_set", INFORMATION_SETS)
def test_coarse_weather_and_demand_weeks_end_by_their_usable_day(
    coarse_extracts: CoarseExtracts, config: StudyConfig, information_set: str
) -> None:
    panel = build_coarse_panel(coarse_extracts, information_set, config)
    week_end = pd.Timedelta(days=6)
    assert (panel["weather_week"] + week_end <= panel["weather_last_usable_day"]).all()
    nyc = panel[panel["demand_week"].notna()]
    assert (nyc["demand_week"] + week_end <= nyc["demand_last_usable_day"]).all()
    origins = panel["origin_week"] + pd.Timedelta(days=7)
    expected_weather_day = origins.map(
        lambda day: pd.Timestamp(last_usable_weather_day(day.date(), information_set, config))
    )
    assert (panel["weather_last_usable_day"] == expected_weather_day).all()


def test_coarse_training_targets_are_known_at_each_origin(config: StudyConfig) -> None:
    origins_path = config.tables_dir / "coarse_origins.csv"
    if not origins_path.exists():
        pytest.skip("coarse experiment not run yet")
    origins = pd.read_csv(origins_path, parse_dates=["origin_week", "latest_training_target_week"])
    assert (origins["latest_training_target_week"] <= origins["origin_week"]).all()


@pytest.fixture(scope="module")
def fine_sample(config: StudyConfig) -> pd.DataFrame:
    """Read the cached fine-grain trip sample, or skip when it has not been built."""
    path = fine_sample_path(config)
    if not path.exists():
        pytest.skip("fine-grain sample not built yet; run make experiments")
    return pd.read_parquet(path)


def test_fine_weather_and_fuel_dates_respect_the_lags(
    fine_sample: pd.DataFrame, config: StudyConfig
) -> None:
    lag = timedelta(days=config.experiments["publication_lags"]["weather_days"])
    pickup = pd.to_datetime(fine_sample["pickup_date"])
    assert (pd.to_datetime(fine_sample["weather_lagged_date"]) == pickup - lag).all()
    assert (pd.to_datetime(fine_sample["weather_same_day_date"]) == pickup).all()
    label = pd.to_datetime(fine_sample["fuel_label_date"])
    assert (label <= pickup).all()
    assert (pickup - label < pd.Timedelta(days=7)).all()


def test_main_fine_features_never_use_the_recorded_distance(fine_sample: pd.DataFrame) -> None:
    for rung, columns in FINE_RUNG_FEATURES.items():
        assert RECORDED_DISTANCE not in columns, rung
        for information_set in INFORMATION_SETS:
            frame = feature_frame(fine_sample.head(10), rung, information_set, False)
            assert RECORDED_DISTANCE not in frame.columns


def test_primary_fine_weather_is_the_lagged_day(fine_sample: pd.DataFrame) -> None:
    rows = fine_sample.head(1000)
    primary = feature_frame(rows, "F2", PRIMARY, False)
    np.testing.assert_array_equal(
        primary["weather_temperature_mean_c"].to_numpy(),
        rows["weather_lagged_temperature_mean_c"].to_numpy(),
    )


def test_fine_training_months_end_by_the_release_rule(config: StudyConfig) -> None:
    origins_path = config.tables_dir / "fine_origins.csv"
    if not origins_path.exists():
        pytest.skip("fine experiment not run yet")
    origins = pd.read_csv(origins_path, dtype=str).dropna(subset=["last_training_month"])
    for origin in origins.itertuples():
        allowed = last_training_month(origin.test_month, origin.information_set, config)
        assert origin.last_training_month <= allowed, origin
        assert origin.first_training_month >= config.experiments["fine"]["training_first_month"]


def test_fine_test_trips_are_identical_across_models(config: StudyConfig) -> None:
    predictions_path = config.derived_dir / "experiments" / "fine_predictions.parquet"
    if not predictions_path.exists():
        pytest.skip("fine experiment not run yet")
    predictions = pd.read_parquet(
        predictions_path, columns=["run", "information_set", "model", "trip_id"]
    )
    trips_per_model = predictions.groupby(["run", "information_set", "model"])["trip_id"].apply(
        lambda trip_ids: tuple(sorted(trip_ids))
    )
    for run in trips_per_model.index.unique(level="run"):
        assert trips_per_model.loc[run].nunique() == 1, run


def test_naive_baseline_never_reads_test_durations() -> None:
    training = pd.DataFrame(
        {
            "pickup_zone_id": [1, 1, 2],
            "dropoff_zone_id": [2, 2, 3],
            "hour_of_week": [5, 5, 6],
            "duration_seconds": [600.0, 800.0, 300.0],
        }
    )
    test = pd.DataFrame(
        {
            "pickup_zone_id": [1, 1, 9],
            "dropoff_zone_id": [2, 2, 9],
            "hour_of_week": [5, 7, 5],
            "duration_seconds": [1.0, 1.0, 1.0],
        }
    )
    first = naive_median_durations(training, test)
    second = naive_median_durations(training, test.assign(duration_seconds=99_999.0))
    np.testing.assert_array_equal(first, second)
    # Exact group, then the zone pair, then the overall training median.
    np.testing.assert_allclose(np.exp(first), [700.0, 700.0, 600.0])
