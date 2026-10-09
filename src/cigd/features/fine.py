"""Fine-grain features: one row per sampled trip; each rung and information set picks columns."""

from pathlib import Path

import duckdb
import pandas as pd

from cigd.config import StudyConfig
from cigd.features.information_sets import PRIMARY
from cigd.sql_files import load_sql

TRIP_FEATURES = [
    "pickup_zone_id",
    "dropoff_zone_id",
    "centroid_distance_miles",
    "pickup_hour",
    "pickup_minute_of_day",
    "vendor_id",
    "rate_code_id",
    "passenger_count",
]
CALENDAR_FEATURES = [
    "iso_day_of_week",
    "is_weekend",
    "is_us_federal_holiday",
    "month",
    "day_of_month",
]
WEATHER_FEATURES = [
    "weather_temperature_mean_c",
    "weather_precipitation_mm",
    "weather_snowfall_cm",
    "weather_wind_speed_max_kmh",
]
FUEL_FEATURES = ["fuel_price_usd", "fuel_price_change_usd"]
RUNG_FEATURES = {
    "F0": TRIP_FEATURES,
    "F1": [*TRIP_FEATURES, *CALENDAR_FEATURES],
    "F2": [*TRIP_FEATURES, *CALENDAR_FEATURES, *WEATHER_FEATURES],
    "F3": [*TRIP_FEATURES, *CALENDAR_FEATURES, *WEATHER_FEATURES, *FUEL_FEATURES],
}
CATEGORICAL_FEATURES = ["pickup_zone_id", "dropoff_zone_id"]
# Only the sensitivity run adds this; it is measured after the trip ends.
RECORDED_DISTANCE = "recorded_distance_miles"
MISSING_RATE_CODE = -1


def fine_sample_path(config: StudyConfig) -> Path:
    """Return where the sampled trips with their features are cached."""
    return config.derived_dir / "features" / "fine_trip_sample.parquet"


def sample_parameters(config: StudyConfig) -> dict[str, int]:
    """Return the SQL parameters for the trip sample from config."""
    fine = config.experiments["fine"]
    training_first, training_end = fine["training_buckets"]
    test_first, test_end = fine["test_buckets"]
    return {
        "bucket_count": fine["sample_bucket_count"],
        "training_bucket_first": training_first,
        "training_bucket_last": training_end - 1,
        "test_bucket_first": test_first,
        "test_bucket_last": test_end - 1,
        "weather_lag_days": config.experiments["publication_lags"]["weather_days"],
    }


def build_fine_sample(config: StudyConfig) -> pd.DataFrame:
    """Extract the sampled trips from the warehouse and cache them as Parquet."""
    with duckdb.connect(str(config.warehouse_path), read_only=True) as connection:
        sample = connection.execute(
            load_sql("features/fine_trip_sample.sql"), sample_parameters(config)
        ).df()
    sample["pickup_date"] = pd.to_datetime(sample["pickup_date"])
    path = fine_sample_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    sample.to_parquet(path, index=False)
    return sample


def is_test_trip(sample: pd.DataFrame, config: StudyConfig) -> pd.Series:
    """Return which sampled trips belong to the test buckets."""
    test_first, test_end = config.experiments["fine"]["test_buckets"]
    return sample["sample_bucket"].between(test_first, test_end - 1)


def feature_frame(
    sample: pd.DataFrame, rung: str, information_set: str, with_recorded_distance: bool
) -> pd.DataFrame:
    """Return the model inputs for one rung and information set.

    Weather comes from seven days before the pickup in the primary set (archive
    delay) and from the pickup day itself in the secondary set.
    """
    weather_source = "weather_lagged" if information_set == PRIMARY else "weather_same_day"
    renamed = sample.rename(
        columns={
            f"{weather_source}_temperature_mean_c": "weather_temperature_mean_c",
            f"{weather_source}_precipitation_mm": "weather_precipitation_mm",
            f"{weather_source}_snowfall_cm": "weather_snowfall_cm",
            f"{weather_source}_wind_speed_max_kmh": "weather_wind_speed_max_kmh",
        }
    )
    columns = list(RUNG_FEATURES[rung])
    if with_recorded_distance:
        columns.append(RECORDED_DISTANCE)
    features = renamed[columns].copy()
    # A missing rate code is kept as its own value rather than treated as unknown.
    features["rate_code_id"] = features["rate_code_id"].fillna(MISSING_RATE_CODE)
    for column in CATEGORICAL_FEATURES:
        features[column] = pd.Categorical(features[column], categories=range(1, 266))
    for column in ("is_weekend", "is_us_federal_holiday"):
        if column in features:
            features[column] = features[column].astype(int)
    return features
