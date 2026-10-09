"""What each source makes available at a forecast origin, under the two information sets.

Primary (realistic): every exogenous source lagged by its measured publication
delay. Secondary (best case): every source available up to the day before the
origin, which no real forecaster could reach. See docs/analysis_plan.md, section 3.
"""

from datetime import date, timedelta

import pandas as pd

from cigd.config import StudyConfig

PRIMARY = "primary"
SECONDARY = "secondary"
INFORMATION_SETS = (PRIMARY, SECONDARY)


def last_usable_trip_day(origin: date, information_set: str, config: StudyConfig) -> date:
    """Return the last day of trip records usable at the origin.

    Primary: trip records for month m are usable from the first day of month m + 4,
    so the newest usable month is four months before the origin's month.
    """
    if information_set == SECONDARY:
        return origin - timedelta(days=1)
    months_until_usable = config.experiments["publication_lags"]["tlc_months_until_usable"]
    newest_usable_month = pd.Period(origin, "M") - months_until_usable
    return newest_usable_month.end_time.date()


def last_usable_weather_day(origin: date, information_set: str, config: StudyConfig) -> date:
    """Return the last day of weather usable at the origin (archive delay in the primary set)."""
    if information_set == SECONDARY:
        return origin - timedelta(days=1)
    return origin - timedelta(days=config.experiments["publication_lags"]["weather_days"])


def latest_complete_week(last_usable_day: date) -> date:
    """Return the Monday of the newest Monday-to-Sunday week that ends on or before a day."""
    candidate = last_usable_day - timedelta(days=6)
    return candidate - timedelta(days=candidate.weekday())


def last_training_month(test_month: str, information_set: str, config: StudyConfig) -> str:
    """Return the newest trip month usable for training a model tested on test_month."""
    if information_set == SECONDARY:
        return str(pd.Period(test_month, "M") - 1)
    months_until_usable = config.experiments["publication_lags"]["tlc_months_until_usable"]
    return str(pd.Period(test_month, "M") - months_until_usable)
