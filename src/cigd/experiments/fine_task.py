"""Fine-grain experiment: trip duration, one origin per test month (plan section 4)."""

from typing import Any

import numpy as np
import pandas as pd

from cigd.config import StudyConfig
from cigd.evaluation.comparisons import add_holm_and_wins, compare_forecasts, paired_errors
from cigd.evaluation.statistics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    root_mean_squared_error,
)
from cigd.features.fine import RUNG_FEATURES, build_fine_sample, feature_frame, is_test_trip
from cigd.features.information_sets import INFORMATION_SETS, last_training_month
from cigd.ingest.tlc import months_in_window
from cigd.logging import get_logger, make_progress
from cigd.models.learners import fit_lightgbm, lightgbm_settings, naive_median_durations

logger = get_logger(__name__)

NAIVE_BASELINE = "N0"
FORECAST_KEYS = ["trip_id", "pickup_date"]
# Kept with every prediction; the full feature columns are dropped to save memory.
PREDICTION_COLUMNS = [*FORECAST_KEYS, "pickup_month", "log_duration", "duration_seconds"]
# Each run: its configured test months and whether the post-trip distance is added.
RUNS = {
    "main": ("main_test_months", False),
    "robustness_2024": ("robustness_test_months", False),
    "sensitivity_recorded_distance": ("main_test_months", True),
}


def training_trips(
    sample: pd.DataFrame,
    test_flags: pd.Series,
    test_month: str,
    information_set: str,
    config: StudyConfig,
) -> pd.DataFrame:
    """Return the training-bucket trips published by the start of the test month."""
    first_month = config.experiments["fine"]["training_first_month"]
    last_month = last_training_month(test_month, information_set, config)
    in_window = sample["pickup_month"].between(first_month, last_month)
    return sample[~test_flags & in_window]


def predictions_for_origin(
    training: pd.DataFrame,
    test: pd.DataFrame,
    information_set: str,
    with_recorded_distance: bool,
    config: StudyConfig,
) -> list[pd.DataFrame]:
    """Fit every model for one test month and return their predictions of log duration."""
    settings = lightgbm_settings(config.experiments["fine"]["lightgbm"], config.random_seed)
    kept = test[PREDICTION_COLUMNS]
    frames = []
    if not with_recorded_distance:
        frames.append(
            kept.assign(model=NAIVE_BASELINE, prediction=naive_median_durations(training, test))
        )
    for rung in RUNG_FEATURES:
        model = fit_lightgbm(
            feature_frame(training, rung, information_set, with_recorded_distance),
            training["log_duration"],
            settings,
        )
        prediction = model.predict(
            feature_frame(test, rung, information_set, with_recorded_distance)
        )
        frames.append(kept.assign(model=rung, prediction=prediction))
    return frames


def run_predictions(
    sample: pd.DataFrame, run: str, information_set: str, config: StudyConfig
) -> tuple[list[pd.DataFrame], list[dict[str, Any]]]:
    """Predict every test month of one run under one information set."""
    months_key, with_recorded_distance = RUNS[run]
    test_months = months_in_window(*config.experiments["fine"][months_key])
    test_flags = is_test_trip(sample, config)
    frames, origins = [], []
    with make_progress() as progress:
        task = progress.add_task(f"fine {run} {information_set}", total=len(test_months))
        for test_month in test_months:
            training = training_trips(sample, test_flags, test_month, information_set, config)
            test = sample[test_flags & (sample["pickup_month"] == test_month)]
            origins.append(
                {
                    "run": run,
                    "information_set": information_set,
                    "test_month": test_month,
                    "first_training_month": training["pickup_month"].min(),
                    "last_training_month": training["pickup_month"].max(),
                    "training_trips": len(training),
                    "test_trips": len(test),
                }
            )
            if not training.empty:
                frames += predictions_for_origin(
                    training, test, information_set, with_recorded_distance, config
                )
            progress.advance(task)
    return frames, origins


def accuracy_table(predictions: pd.DataFrame) -> pd.DataFrame:
    """Return MAE and RMSE of log duration, and MAE and MAPE in seconds, per model."""
    rows = []
    for (run, information_set, model), group in predictions.groupby(
        ["run", "information_set", "model"]
    ):
        seconds_forecast = np.exp(group["prediction"].to_numpy())
        seconds_actual = group["duration_seconds"].to_numpy()
        rows.append(
            {
                "run": run,
                "information_set": information_set,
                "model": model,
                "test_trips": len(group),
                "mae_log_duration": mean_absolute_error(group["error"].to_numpy()),
                "rmse_log_duration": root_mean_squared_error(group["error"].to_numpy()),
                "mae_seconds": mean_absolute_error(seconds_actual - seconds_forecast),
                "mape_seconds": mean_absolute_percentage_error(seconds_actual, seconds_forecast),
            }
        )
    return pd.DataFrame(rows)


def adjacent_pairs(models: list[str]) -> list[tuple[str, str]]:
    """Return (model, the model one step below it) for a ladder of models."""
    return list(zip(models[1:], models[:-1], strict=True))


def comparison_table(predictions: pd.DataFrame, config: StudyConfig) -> pd.DataFrame:
    """Compare each rung with the one below it, per run and information set, with Holm."""
    rows = []
    for (run, information_set), group in predictions.groupby(["run", "information_set"]):
        models_run = set(group["model"])
        ladder = [model for model in (NAIVE_BASELINE, *RUNG_FEATURES) if model in models_run]
        for model, comparator in adjacent_pairs(ladder):
            paired = paired_errors(
                group.loc[group["model"] == model, [*FORECAST_KEYS, "error"]],
                group.loc[group["model"] == comparator, [*FORECAST_KEYS, "error"]],
                FORECAST_KEYS,
            )
            result = compare_forecasts(
                paired, "pickup_date", config.experiments["bootstrap_resamples"], config.random_seed
            )
            rows.append(
                {
                    "run": run,
                    "information_set": information_set,
                    "model": model,
                    "comparator": comparator,
                    **result,
                }
            )
    return add_holm_and_wins(pd.DataFrame(rows), ["run", "information_set"])


def run_fine_task(config: StudyConfig) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Run the fine-grain experiment and return its result tables and all predictions."""
    sample = build_fine_sample(config)
    logger.info("fine-grain sample: %d trips", len(sample))
    frames, origins = [], []
    for run in RUNS:
        for information_set in INFORMATION_SETS:
            run_frames, run_origins = run_predictions(sample, run, information_set, config)
            for frame in run_frames:
                frame["run"] = run
                frame["information_set"] = information_set
            frames += run_frames
            origins += run_origins

    predictions = pd.concat(frames, ignore_index=True)
    predictions["error"] = predictions["log_duration"] - predictions["prediction"]
    tables = {
        "fine_accuracy": accuracy_table(predictions),
        "fine_comparisons": comparison_table(predictions, config),
        "fine_origins": pd.DataFrame(origins),
    }
    return tables, predictions


def fine_summary(tables: dict[str, Any]) -> dict[str, Any]:
    """Return a short stage summary of the fine-grain experiment."""
    comparisons = tables["fine_comparisons"]
    main = comparisons[comparisons["run"] == "main"]
    return {
        "fine_comparisons": len(comparisons),
        "fine_main_wins": int(main["win"].sum()),
        "fine_test_trips": int(tables["fine_origins"]["test_trips"].sum()),
    }
