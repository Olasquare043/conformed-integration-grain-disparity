"""The learners used by the experiments: LightGBM, ridge regression and a naive median."""

from dataclasses import dataclass
from typing import Any

import lightgbm
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

# A fixed thread count keeps LightGBM's results identical from run to run.
LIGHTGBM_THREADS = 4


def lightgbm_settings(configured: dict[str, Any], seed: int) -> dict[str, Any]:
    """Return LightGBM settings: the pre-registered values plus determinism switches."""
    return {
        **configured,
        "objective": "regression",
        "deterministic": True,
        "force_row_wise": True,
        "num_threads": LIGHTGBM_THREADS,
        "seed": seed,
        "subsample": 1.0,
        "colsample_bytree": 1.0,
        "verbose": -1,
    }


def fit_lightgbm(
    features: pd.DataFrame, target: pd.Series, settings: dict[str, Any]
) -> lightgbm.LGBMRegressor:
    """Fit a LightGBM regressor; categorical columns are taken from the pandas dtypes."""
    model = lightgbm.LGBMRegressor(**settings)
    model.fit(features, target)
    return model


@dataclass
class RidgeModel:
    """A fitted ridge regression with the preprocessing learned from its training window."""

    numeric_columns: list[str]
    indicator_columns: list[str]
    categorical_columns: list[str]
    categories: dict[str, list[Any]]
    means: pd.Series
    scales: pd.Series
    regression: Ridge


def ridge_design_matrix(features: pd.DataFrame, model: RidgeModel) -> np.ndarray:
    """Turn features into the ridge inputs: imputed, standardised, with indicators and one-hot."""
    numeric = features[model.numeric_columns].astype(float)
    indicators = numeric[model.indicator_columns].isna().astype(float)
    standardised = (numeric.fillna(model.means) - model.means) / model.scales
    one_hot = [
        (features[column].to_numpy()[:, None] == np.array(model.categories[column])[None, :])
        for column in model.categorical_columns
    ]
    return np.hstack([standardised.to_numpy(), indicators.to_numpy(), *one_hot]).astype(float)


def fit_ridge(
    features: pd.DataFrame, target: pd.Series, categorical_columns: list[str], alpha: float
) -> RidgeModel:
    """Fit ridge regression with the plan's preprocessing.

    Missing values become the training mean, with a missing-value indicator for
    every numeric feature that has a missing value in training; numeric features
    are standardised with the training mean and standard deviation; categorical
    features are one-hot encoded.
    """
    numeric_columns = [column for column in features.columns if column not in categorical_columns]
    numeric = features[numeric_columns].astype(float)
    means = numeric.mean()
    scales = numeric.std().replace(0.0, 1.0).fillna(1.0)
    model = RidgeModel(
        numeric_columns=numeric_columns,
        indicator_columns=[column for column in numeric_columns if numeric[column].isna().any()],
        categorical_columns=categorical_columns,
        categories={column: sorted(features[column].unique()) for column in categorical_columns},
        means=means.fillna(0.0),
        scales=scales,
        regression=Ridge(alpha=alpha),
    )
    model.regression.fit(ridge_design_matrix(features, model), target.to_numpy())
    return model


def predict_ridge(model: RidgeModel, features: pd.DataFrame) -> np.ndarray:
    """Predict with a fitted ridge model."""
    return model.regression.predict(ridge_design_matrix(features, model))


def naive_median_durations(training: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Predict log duration as the log of a training median, from the finest group available.

    Groups, finest first: pickup zone, dropoff zone and hour of the week; then the
    zone pair; then all training trips.
    """
    by_pair_and_hour = training.groupby(["pickup_zone_id", "dropoff_zone_id", "hour_of_week"])[
        "duration_seconds"
    ].median()
    by_pair = training.groupby(["pickup_zone_id", "dropoff_zone_id"])["duration_seconds"].median()
    overall = training["duration_seconds"].median()

    pair_and_hour_keys = pd.MultiIndex.from_frame(
        test[["pickup_zone_id", "dropoff_zone_id", "hour_of_week"]]
    )
    pair_keys = pd.MultiIndex.from_frame(test[["pickup_zone_id", "dropoff_zone_id"]])
    median = pd.Series(by_pair_and_hour.reindex(pair_and_hour_keys).to_numpy(), index=test.index)
    median = median.fillna(pd.Series(by_pair.reindex(pair_keys).to_numpy(), index=test.index))
    return np.log(median.fillna(overall).to_numpy())
