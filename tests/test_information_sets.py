"""The publication-lag rules give the dates the analysis plan states."""

from datetime import date

from cigd.config import load_config
from cigd.features.information_sets import (
    PRIMARY,
    SECONDARY,
    last_training_month,
    last_usable_trip_day,
    last_usable_weather_day,
    latest_complete_week,
)

CONFIG = load_config("full")


def test_trip_month_is_usable_from_the_first_day_of_month_plus_four() -> None:
    # August data is usable from 1 December, not on 30 November.
    assert last_usable_trip_day(date(2024, 12, 1), PRIMARY, CONFIG) == date(2024, 8, 31)
    assert last_usable_trip_day(date(2024, 11, 30), PRIMARY, CONFIG) == date(2024, 7, 31)


def test_best_case_uses_everything_up_to_the_day_before() -> None:
    assert last_usable_trip_day(date(2024, 12, 2), SECONDARY, CONFIG) == date(2024, 12, 1)
    assert last_usable_weather_day(date(2024, 12, 2), SECONDARY, CONFIG) == date(2024, 12, 1)


def test_weather_is_usable_seven_days_later() -> None:
    assert last_usable_weather_day(date(2024, 12, 9), PRIMARY, CONFIG) == date(2024, 12, 2)


def test_latest_complete_week_ends_on_or_before_the_day() -> None:
    # A Sunday closes its own week; a Monday only closes the week before.
    assert latest_complete_week(date(2024, 12, 8)) == date(2024, 12, 2)
    assert latest_complete_week(date(2024, 12, 9)) == date(2024, 12, 2)
    assert latest_complete_week(date(2024, 12, 7)) == date(2024, 11, 25)


def test_training_months_end_four_months_before_the_test_month() -> None:
    assert last_training_month("2025-01", PRIMARY, CONFIG) == "2024-09"
    assert last_training_month("2025-01", SECONDARY, CONFIG) == "2024-12"
