"""Coarse-grain features: one row per metro region per forecast origin (a described week).

At origin week k (the price for week k has just been published under its label),
the target is the next published weekly price, for week k + 1. Features use only
what each information set allows at the origin date: the label date of week k.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import duckdb
import numpy as np
import pandas as pd

from cigd.config import StudyConfig
from cigd.features.information_sets import (
    last_usable_trip_day,
    last_usable_weather_day,
    latest_complete_week,
)
from cigd.sql_files import load_sql

STATE_SERIES_CODE = "NY"
DEMAND_REGION_CODE = "new_york_city"
LAG_FEATURES = ["change_lag_0", "change_lag_1", "change_lag_2", "change_lag_3"]
C1_FEATURES = [
    *LAG_FEATURES,
    "price",
    "spread_to_state",
    "change_52_weeks",
    "region_code",
    "target_iso_week",
    "target_federal_holidays",
]
WEATHER_FEATURES = ["weather_temperature_mean_c", "weather_precipitation_mm", "weather_snowfall_cm"]
DEMAND_FEATURES = ["demand_log_trips", "demand_log_change_4_weeks", "demand_log_change_52_weeks"]
RUNG_FEATURES = {
    "C1": C1_FEATURES,
    "C2": [*C1_FEATURES, *WEATHER_FEATURES],
    "C3": [*C1_FEATURES, *WEATHER_FEATURES, *DEMAND_FEATURES],
}
CATEGORICAL_FEATURES = ["region_code"]


@dataclass
class CoarseExtracts:
    """The weekly tables the coarse features are built from."""

    prices: pd.DataFrame
    weather: pd.DataFrame
    demand: pd.DataFrame
    calendar: pd.DataFrame


def read_extract(connection: duckdb.DuckDBPyConnection, name: str) -> pd.DataFrame:
    """Run one feature extract from sql/features/ and return it with dates as timestamps."""
    frame = connection.execute(load_sql(f"features/{name}.sql")).df()
    for column in ("week_start", "label_date"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column])
    return frame


def read_coarse_extracts(config: StudyConfig) -> CoarseExtracts:
    """Read every weekly extract from the warehouse."""
    with duckdb.connect(str(config.warehouse_path), read_only=True) as connection:
        return CoarseExtracts(
            prices=read_extract(connection, "region_week_price"),
            weather=read_extract(connection, "region_week_weather"),
            demand=read_extract(connection, "region_week_trip_demand"),
            calendar=read_extract(connection, "week_calendar"),
        )


def price_panel(prices: pd.DataFrame) -> pd.DataFrame:
    """Return price, change, lag and target columns for every region and origin week.

    Prices sit on a complete Monday grid, so a missing week stays missing and never
    turns a two-week move into a one-week change.
    """
    wide = prices.pivot(index="week_start", columns="series_code", values="price_usd_per_gallon")
    wide = wide.reindex(pd.date_range(wide.index.min(), wide.index.max(), freq="W-MON"))
    state_price = wide[STATE_SERIES_CODE]
    region_frames = []
    for region_code in sorted(wide.columns.drop(STATE_SERIES_CODE)):
        price = wide[region_code]
        change = price.diff()
        region_frames.append(
            pd.DataFrame(
                {
                    "region_code": region_code,
                    "origin_week": wide.index,
                    "price": price.to_numpy(),
                    "target_price": price.shift(-1).to_numpy(),
                    "change_lag_0": change.to_numpy(),
                    "change_lag_1": change.shift(1).to_numpy(),
                    "change_lag_2": change.shift(2).to_numpy(),
                    "change_lag_3": change.shift(3).to_numpy(),
                    "spread_to_state": (price - state_price).to_numpy(),
                    "change_52_weeks": (price - price.shift(52)).to_numpy(),
                    # Seasonal naive: the price 52 weeks before the target week, else 53.
                    "seasonal_naive_price": price.shift(51).fillna(price.shift(52)).to_numpy(),
                }
            )
        )
    panel = pd.concat(region_frames, ignore_index=True)
    panel["target_week"] = panel["origin_week"] + pd.Timedelta(weeks=1)
    panel["target_change"] = panel["target_price"] - panel["price"]
    # An origin exists only when its price was published.
    return panel[panel["price"].notna()].reset_index(drop=True)


def add_calendar(panel: pd.DataFrame, calendar: pd.DataFrame) -> pd.DataFrame:
    """Add the target week's ISO week number and federal holiday count, from dim_date."""
    target_calendar = calendar.rename(
        columns={
            "week_start": "target_week",
            "iso_week": "target_iso_week",
            "federal_holidays": "target_federal_holidays",
        }
    )
    return panel.merge(target_calendar, on="target_week", how="left")


def origin_date(origin_week: pd.Timestamp) -> date:
    """Return the origin date for a described week: its NYSERDA label, seven days later."""
    return (origin_week + pd.Timedelta(days=7)).date()


def add_weather(
    panel: pd.DataFrame, weather: pd.DataFrame, information_set: str, config: StudyConfig
) -> pd.DataFrame:
    """Add each region's newest complete week of weather usable at the origin."""
    weather_week_by_origin = {}
    last_day_by_origin = {}
    for week in panel["origin_week"].unique():
        last_day = last_usable_weather_day(origin_date(week), information_set, config)
        last_day_by_origin[week] = pd.Timestamp(last_day)
        weather_week_by_origin[week] = pd.Timestamp(latest_complete_week(last_day))
    panel["weather_last_usable_day"] = panel["origin_week"].map(last_day_by_origin)
    panel["weather_week"] = panel["origin_week"].map(weather_week_by_origin)

    complete_weeks = weather[weather["days_with_weather"] == 7]
    weather_columns = complete_weeks.rename(
        columns={
            "week_start": "weather_week",
            "temperature_mean_c": "weather_temperature_mean_c",
            "precipitation_mm": "weather_precipitation_mm",
            "snowfall_cm": "weather_snowfall_cm",
        }
    )[["region_code", "weather_week", *WEATHER_FEATURES]]
    return panel.merge(weather_columns, on=["region_code", "weather_week"], how="left")


def nyc_log_trips(demand: pd.DataFrame) -> pd.Series:
    """Return log weekly NYC trips on a complete Monday grid; partial weeks are missing."""
    nyc = demand[(demand["region_code"] == DEMAND_REGION_CODE) & (demand["days_with_trips"] == 7)]
    series = np.log(nyc.set_index("week_start")["trip_count"].astype(float))
    # Early origins can have no released trip data yet; every demand feature is then missing.
    if series.empty:
        return series
    return series.reindex(pd.date_range(series.index.min(), series.index.max(), freq="W-MON"))


def add_demand(
    panel: pd.DataFrame, demand: pd.DataFrame, information_set: str, config: StudyConfig
) -> pd.DataFrame:
    """Add NYC trip demand from the newest complete week usable at the origin (NYC rows only)."""
    log_trips = nyc_log_trips(demand)
    demand_rows = []
    for week in panel["origin_week"].unique():
        last_day = last_usable_trip_day(origin_date(week), information_set, config)
        demand_week = pd.Timestamp(latest_complete_week(last_day))
        current = log_trips.get(demand_week, np.nan)
        demand_rows.append(
            {
                "origin_week": week,
                "region_code": DEMAND_REGION_CODE,
                "demand_last_usable_day": pd.Timestamp(last_day),
                "demand_week": demand_week,
                "demand_log_trips": current,
                "demand_log_change_4_weeks": current
                - log_trips.get(demand_week - timedelta(weeks=4), np.nan),
                "demand_log_change_52_weeks": current
                - log_trips.get(demand_week - timedelta(weeks=52), np.nan),
            }
        )
    return panel.merge(pd.DataFrame(demand_rows), on=["origin_week", "region_code"], how="left")


def build_coarse_panel(
    extracts: CoarseExtracts, information_set: str, config: StudyConfig
) -> pd.DataFrame:
    """Build the coarse feature panel for one information set."""
    panel = price_panel(extracts.prices)
    panel = add_calendar(panel, extracts.calendar)
    panel = add_weather(panel, extracts.weather, information_set, config)
    panel = add_demand(panel, extracts.demand, information_set, config)
    panel["has_target"] = panel["target_price"].notna()
    return panel.sort_values(["origin_week", "region_code"], ignore_index=True)
