"""The comparison statistics behave as their definitions say."""

import numpy as np
import pandas as pd
import pytest

from cigd.evaluation.statistics import (
    block_bootstrap_mae_difference,
    diebold_mariano,
    holm_adjust,
    minimum_detectable_difference,
    newey_west_bandwidth,
    newey_west_long_run_variance,
)


def test_bandwidth_follows_the_newey_west_rule() -> None:
    assert newey_west_bandwidth(100) == 4
    assert newey_west_bandwidth(155) == 4
    assert newey_west_bandwidth(365) == 5


def test_long_run_variance_of_white_noise_is_close_to_its_variance() -> None:
    noise = np.random.default_rng(1).normal(size=20_000)
    assert newey_west_long_run_variance(noise) == pytest.approx(1.0, abs=0.05)


def test_identical_forecasts_cannot_be_told_apart() -> None:
    differences = np.random.default_rng(2).normal(scale=0.1, size=150)
    result = diebold_mariano(differences - differences.mean())
    assert result["p_value"] == pytest.approx(1.0)


def test_a_clearly_better_forecast_is_detected() -> None:
    differences = np.random.default_rng(3).normal(loc=-0.5, scale=0.2, size=150)
    result = diebold_mariano(differences)
    assert result["dm_statistic"] < 0
    assert result["p_value"] < 0.001


def test_holm_adjustment_matches_a_worked_example() -> None:
    assert holm_adjust([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_minimum_detectable_difference_scales_the_standard_error() -> None:
    assert minimum_detectable_difference(1.0) == pytest.approx(2.8016, abs=1e-4)


def test_bootstrap_interval_covers_the_true_difference_and_is_reproducible() -> None:
    generator = np.random.default_rng(4)
    errors = pd.DataFrame(
        {
            "block": np.repeat(np.arange(100), 10),
            "model": generator.uniform(0, 1, 1000),
            "comparator": generator.uniform(0, 1, 1000) + 0.2,
        }
    )
    first = block_bootstrap_mae_difference(errors, resamples=500, seed=7)
    second = block_bootstrap_mae_difference(errors, resamples=500, seed=7)
    assert first == second
    assert first["mae_difference_ci_low"] < -0.2 < first["mae_difference_ci_high"]


def test_identical_forecasts_without_any_variation_give_p_of_one() -> None:
    result = diebold_mariano(np.zeros(20))
    assert result["dm_statistic"] == 0.0
    assert result["p_value"] == 1.0
