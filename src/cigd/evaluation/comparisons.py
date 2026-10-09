"""Compare two forecasts of the same targets: accuracy, DM tests, bootstrap intervals."""

from typing import Any

import numpy as np
import pandas as pd

from cigd.evaluation.statistics import (
    block_bootstrap_mae_difference,
    diebold_mariano,
    holm_adjust,
    mean_absolute_error,
    minimum_detectable_difference,
    root_mean_squared_error,
)

SIGNIFICANCE_LEVEL = 0.05


def paired_errors(
    model_errors: pd.DataFrame, comparator_errors: pd.DataFrame, key_columns: list[str]
) -> pd.DataFrame:
    """Line up two models' errors on the same forecasts; both must cover exactly the same ones."""
    paired = model_errors.merge(
        comparator_errors, on=key_columns, suffixes=("_model", "_comparator"), validate="1:1"
    )
    if len(paired) != len(model_errors) or len(paired) != len(comparator_errors):
        raise ValueError("The two forecasts do not cover the same targets.")
    return paired


def block_loss_differences(paired: pd.DataFrame, block_column: str, loss: str) -> np.ndarray:
    """Average the model-minus-comparator loss within each block, in block order."""
    if loss == "absolute":
        difference = paired["error_model"].abs() - paired["error_comparator"].abs()
    else:
        difference = np.square(paired["error_model"]) - np.square(paired["error_comparator"])
    return difference.groupby(paired[block_column]).mean().sort_index().to_numpy()


def compare_forecasts(
    paired: pd.DataFrame, block_column: str, resamples: int, seed: int
) -> dict[str, Any]:
    """Return effect sizes with bootstrap intervals and DM tests for one paired comparison."""
    model_mae = mean_absolute_error(paired["error_model"].to_numpy())
    comparator_mae = mean_absolute_error(paired["error_comparator"].to_numpy())
    absolute_test = diebold_mariano(block_loss_differences(paired, block_column, "absolute"))
    squared_test = diebold_mariano(block_loss_differences(paired, block_column, "squared"))
    intervals = block_bootstrap_mae_difference(
        pd.DataFrame(
            {
                "block": paired[block_column],
                "model": paired["error_model"].abs(),
                "comparator": paired["error_comparator"].abs(),
            }
        ),
        resamples,
        seed,
    )
    detectable = minimum_detectable_difference(absolute_test["standard_error"])
    return {
        "forecasts": len(paired),
        "blocks": absolute_test["periods"],
        "mae_model": model_mae,
        "mae_comparator": comparator_mae,
        "rmse_model": root_mean_squared_error(paired["error_model"].to_numpy()),
        "rmse_comparator": root_mean_squared_error(paired["error_comparator"].to_numpy()),
        "mae_difference": model_mae - comparator_mae,
        "percent_change": (model_mae - comparator_mae) / comparator_mae * 100,
        **intervals,
        "dm_statistic_absolute": absolute_test["dm_statistic"],
        "p_value_absolute": absolute_test["p_value"],
        "dm_statistic_squared": squared_test["dm_statistic"],
        "p_value_squared": squared_test["p_value"],
        "minimum_detectable_difference": detectable,
        "minimum_detectable_percent": detectable / comparator_mae * 100,
    }


def add_holm_and_wins(comparisons: pd.DataFrame, family_columns: list[str]) -> pd.DataFrame:
    """Holm-adjust the absolute-loss p-values within each family and mark the wins.

    A win is a lower MAE together with a Holm-adjusted p-value below 0.05.
    """
    adjusted = comparisons.copy()
    adjusted["p_value_absolute_holm"] = np.nan
    for _, family in adjusted.groupby(family_columns):
        holm = holm_adjust(family["p_value_absolute"].tolist())
        adjusted.loc[family.index, "p_value_absolute_holm"] = holm
    adjusted["win"] = (adjusted["mae_difference"] < 0) & (
        adjusted["p_value_absolute_holm"] < SIGNIFICANCE_LEVEL
    )
    return adjusted
