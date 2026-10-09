"""Forecast accuracy metrics and the tests used to compare two forecasts."""

import math

import numpy as np
import pandas as pd
from scipy import stats

# Two-sided 5 percent level and 80 percent power, for the minimum detectable difference.
Z_TWO_SIDED_5_PERCENT = 1.959964
Z_POWER_80_PERCENT = 0.841621


def mean_absolute_error(errors: np.ndarray) -> float:
    """Return the mean absolute error of a vector of forecast errors."""
    return float(np.mean(np.abs(errors)))


def root_mean_squared_error(errors: np.ndarray) -> float:
    """Return the root mean squared error of a vector of forecast errors."""
    return float(np.sqrt(np.mean(np.square(errors))))


def mean_absolute_percentage_error(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Return the mean absolute percentage error, in percent."""
    return float(np.mean(np.abs((actual - forecast) / actual)) * 100)


def newey_west_bandwidth(periods: int) -> int:
    """Return the Newey-West lag length floor(4 (T / 100)^(2/9))."""
    return int(math.floor(4 * (periods / 100) ** (2 / 9)))


def newey_west_long_run_variance(series: np.ndarray) -> float:
    """Return the HAC long-run variance of a series with Bartlett weights."""
    centred = series - series.mean()
    periods = len(centred)
    bandwidth = newey_west_bandwidth(periods)
    variance = float(np.dot(centred, centred) / periods)
    for lag in range(1, bandwidth + 1):
        weight = 1 - lag / (bandwidth + 1)
        autocovariance = float(np.dot(centred[lag:], centred[:-lag]) / periods)
        variance += 2 * weight * autocovariance
    return variance


def diebold_mariano(loss_differences: np.ndarray) -> dict[str, float]:
    """Test whether the mean loss difference is zero (one-step-ahead forecasts).

    The input is one loss difference per period, already averaged within the
    period where the comparison is pooled. The statistic uses the Newey-West
    variance and the Harvey, Leybourne and Newbold small-sample correction, with
    a Student t reference on T - 1 degrees of freedom; the test is two-sided.
    """
    periods = len(loss_differences)
    mean_difference = float(loss_differences.mean())
    # Bartlett weights keep the variance non-negative; max() only absorbs rounding.
    variance = max(newey_west_long_run_variance(loss_differences), 0.0)
    standard_error = math.sqrt(variance / periods)
    if standard_error == 0.0:
        # No variation at all: identical forecasts cannot be told apart (p = 1), while a
        # constant non-zero difference is certain (p = 0).
        statistic = 0.0 if mean_difference == 0.0 else math.copysign(math.inf, mean_difference)
        p_value = 1.0 if mean_difference == 0.0 else 0.0
    else:
        # Harvey, Leybourne and Newbold correction for a forecast horizon of one.
        correction = math.sqrt((periods - 1) / periods)
        statistic = correction * mean_difference / standard_error
        p_value = 2 * stats.t.sf(abs(statistic), df=periods - 1)
    return {
        "periods": periods,
        "mean_loss_difference": mean_difference,
        "standard_error": standard_error,
        "dm_statistic": statistic,
        "p_value": float(p_value),
    }


def minimum_detectable_difference(standard_error: float) -> float:
    """Return the smallest mean loss difference detectable at 80 percent power, 5 percent level."""
    return (Z_TWO_SIDED_5_PERCENT + Z_POWER_80_PERCENT) * standard_error


def holm_adjust(p_values: list[float]) -> list[float]:
    """Return Holm-adjusted p-values, in the order the raw p-values were given."""
    order = np.argsort(p_values)
    count = len(p_values)
    adjusted = [0.0] * count
    running_maximum = 0.0
    for rank, index in enumerate(order):
        candidate = min(1.0, (count - rank) * p_values[index])
        running_maximum = max(running_maximum, candidate)
        adjusted[index] = running_maximum
    return adjusted


def block_bootstrap_mae_difference(
    absolute_errors: pd.DataFrame, resamples: int, seed: int
) -> dict[str, float]:
    """Return 95 percent percentile intervals for an MAE difference and its percent change.

    absolute_errors has one row per forecast with columns block, model and
    comparator. Whole blocks (weeks or days) are resampled with replacement, so
    forecasts that share a block stay together.
    """
    per_block = absolute_errors.groupby("block").agg(
        model_sum=("model", "sum"), comparator_sum=("comparator", "sum"), count=("model", "size")
    )
    model_sums = per_block["model_sum"].to_numpy()
    comparator_sums = per_block["comparator_sum"].to_numpy()
    counts = per_block["count"].to_numpy()

    generator = np.random.default_rng(seed)
    drawn = generator.integers(0, len(per_block), size=(resamples, len(per_block)))
    model_mae = model_sums[drawn].sum(axis=1) / counts[drawn].sum(axis=1)
    comparator_mae = comparator_sums[drawn].sum(axis=1) / counts[drawn].sum(axis=1)
    differences = model_mae - comparator_mae
    percent_changes = differences / comparator_mae * 100
    return {
        "mae_difference_ci_low": float(np.percentile(differences, 2.5)),
        "mae_difference_ci_high": float(np.percentile(differences, 97.5)),
        "percent_change_ci_low": float(np.percentile(percent_changes, 2.5)),
        "percent_change_ci_high": float(np.percentile(percent_changes, 97.5)),
    }
