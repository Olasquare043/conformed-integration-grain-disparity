"""The study configuration is internally consistent for every profile."""

import pytest

from cigd.config import PROFILES, load_config


@pytest.mark.parametrize("profile", PROFILES)
def test_cutoff_is_after_panel_start(profile: str) -> None:
    config = load_config(profile)
    assert config.price_first_week < config.data_cutoff_date


def test_smoke_window_sits_inside_full_window() -> None:
    full = load_config("full")
    smoke = load_config("smoke")
    assert full.trip_first_month <= smoke.trip_first_month <= smoke.trip_last_month
    assert smoke.trip_last_month <= full.trip_last_month
    assert smoke.data_cutoff_date <= full.data_cutoff_date


def test_price_panel_starts_on_a_monday() -> None:
    # NYSERDA and EIA both date each week by its Monday.
    for profile in PROFILES:
        assert load_config(profile).price_first_week.weekday() == 0


def test_profiles_write_to_separate_places() -> None:
    full = load_config("full")
    smoke = load_config("smoke")
    assert full.results_dir != smoke.results_dir
    assert full.warehouse_path != smoke.warehouse_path
    assert full.config_hash != smoke.config_hash
