"""Coarse-grain experiment: one-week-ahead regional gasoline price forecasts (plan section 5)."""

from typing import Any

import numpy as np
import pandas as pd

from cigd.config import StudyConfig
from cigd.evaluation.comparisons import add_holm_and_wins, compare_forecasts, paired_errors
from cigd.evaluation.statistics import (
    diebold_mariano,
    mean_absolute_error,
    mean_absolute_percentage_error,
    root_mean_squared_error,
)
from cigd.features.coarse import (
    CATEGORICAL_FEATURES,
    DEMAND_REGION_CODE,
    RUNG_FEATURES,
    build_coarse_panel,
    read_coarse_extracts,
)
from cigd.features.information_sets import INFORMATION_SETS
from cigd.logging import get_logger, make_progress
from cigd.models.learners import fit_lightgbm, fit_ridge, lightgbm_settings, predict_ridge

logger = get_logger(__name__)

RANDOM_WALK = "B1_random_walk"
SEASONAL_NAIVE = "B2_seasonal_naive"
LEARNERS = ("lightgbm", "ridge")
RUNS = ("main", "covid_excluded")
FORECAST_KEYS = ["region_code", "target_week"]


def timestamp(text: str) -> pd.Timestamp:
    """Parse a configured date."""
    return pd.Timestamp(text)


def training_rows(
    panel: pd.DataFrame, origin: pd.Timestamp, run: str, config: StudyConfig
) -> pd.DataFrame:
    """Return the rows usable for training at an origin: targets known by then.

    The COVID-excluded run drops rows whose target week falls in the configured
    window, for every model alike.
    """
    settings = config.experiments["coarse"]
    usable = (
        panel["has_target"]
        & (panel["target_week"] <= origin)
        & (panel["target_week"] >= timestamp(settings["first_training_target"]))
    )
    if run == "covid_excluded":
        first, last = (timestamp(day) for day in settings["covid_excluded_targets"])
        usable &= ~panel["target_week"].between(first, last)
    return panel[usable]


def lightgbm_features(rows: pd.DataFrame, rung: str) -> pd.DataFrame:
    """Return a rung's features with the region as a categorical column."""
    features = rows[RUNG_FEATURES[rung]].copy()
    features["region_code"] = pd.Categorical(features["region_code"])
    return features


def predict_change(
    training: pd.DataFrame,
    test: pd.DataFrame,
    rung: str,
    learner: str,
    ridge_alpha: float,
    config: StudyConfig,
) -> np.ndarray:
    """Fit one learner on the training rows and predict the one-week price change."""
    if learner == "lightgbm":
        settings = lightgbm_settings(config.experiments["coarse"]["lightgbm"], config.random_seed)
        training_features = lightgbm_features(training, rung)
        test_features = lightgbm_features(test, rung)
        test_features["region_code"] = pd.Categorical(
            test_features["region_code"], categories=training_features["region_code"].cat.categories
        )
        model = fit_lightgbm(training_features, training["target_change"], settings)
        return model.predict(test_features)
    model = fit_ridge(
        training[RUNG_FEATURES[rung]], training["target_change"], CATEGORICAL_FEATURES, ridge_alpha
    )
    return predict_ridge(model, test[RUNG_FEATURES[rung]])


def origins_with_targets(panel: pd.DataFrame, first_target: str, last_target: str) -> list:
    """Return the origin weeks whose next published value falls in a target window."""
    in_window = panel["target_week"].between(timestamp(first_target), timestamp(last_target))
    return sorted(panel.loc[in_window & panel["has_target"], "origin_week"].unique())


def ridge_selection_errors(
    panel: pd.DataFrame, rung: str, alpha: float, config: StudyConfig
) -> np.ndarray:
    """Return the ridge errors over the selection targets for one penalty."""
    first, last = config.experiments["coarse"]["ridge_selection_targets"]
    errors = []
    for origin in origins_with_targets(panel, first, last):
        test = panel[(panel["origin_week"] == origin) & panel["has_target"]]
        training = training_rows(panel, origin, "main", config)
        change = predict_change(training, test, rung, "ridge", alpha, config)
        errors.append(test["target_change"].to_numpy() - change)
    return np.concatenate(errors)


def select_ridge_alphas(
    panel: pd.DataFrame, information_set: str, config: StudyConfig
) -> pd.DataFrame:
    """Choose each rung's ridge penalty on the year before evaluation, then freeze it.

    The penalty with the lowest pooled MAE wins; on a tie the larger one is kept.
    """
    rows = []
    for rung in RUNG_FEATURES:
        for alpha in config.experiments["coarse"]["ridge_alphas"]:
            errors = ridge_selection_errors(panel, rung, alpha, config)
            rows.append(
                {
                    "information_set": information_set,
                    "rung": rung,
                    "alpha": alpha,
                    "selection_mae": mean_absolute_error(errors),
                }
            )
    table = pd.DataFrame(rows)
    best = table.sort_values(["rung", "selection_mae", "alpha"], ascending=[True, True, False])
    chosen = best.groupby("rung").head(1)[["rung", "alpha"]]
    table["chosen"] = table.merge(chosen, on=["rung", "alpha"], how="left", indicator=True)[
        "_merge"
    ].eq("both")
    return table


def baseline_forecasts(test: pd.DataFrame) -> list[pd.DataFrame]:
    """Return the random walk (zero change) and seasonal naive forecasts for one origin."""
    return [
        test.assign(model=RANDOM_WALK, learner="none", forecast=test["price"]),
        test.assign(model=SEASONAL_NAIVE, learner="none", forecast=test["seasonal_naive_price"]),
    ]


def rolling_forecasts(
    panel: pd.DataFrame,
    information_set: str,
    run: str,
    alphas: dict[str, float],
    config: StudyConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Forecast every evaluation target with a weekly rolling origin, refitting each week."""
    first, last = config.experiments["coarse"]["evaluation_targets"]
    origins = origins_with_targets(panel, first, last)
    forecast_frames = []
    origin_rows = []
    with make_progress() as progress:
        task = progress.add_task(f"coarse {information_set} {run}", total=len(origins))
        for origin in origins:
            test = panel[(panel["origin_week"] == origin) & panel["has_target"]]
            training = training_rows(panel, origin, run, config)
            forecast_frames += baseline_forecasts(test)
            for rung in RUNG_FEATURES:
                for learner in LEARNERS:
                    change = predict_change(training, test, rung, learner, alphas[rung], config)
                    forecast_frames.append(
                        test.assign(model=rung, learner=learner, forecast=test["price"] + change)
                    )
            origin_rows.append(
                {
                    "information_set": information_set,
                    "run": run,
                    "origin_week": origin,
                    "training_rows": len(training),
                    "latest_training_target_week": training["target_week"].max(),
                }
            )
            progress.advance(task)
    forecasts = pd.concat(forecast_frames, ignore_index=True)
    forecasts["information_set"] = information_set
    forecasts["run"] = run
    forecasts["error"] = forecasts["target_price"] - forecasts["forecast"]
    return forecasts, pd.DataFrame(origin_rows)


def accuracy_table(forecasts: pd.DataFrame) -> pd.DataFrame:
    """Return MAE, RMSE and MAPE per model, pooled and per region."""
    rows = []
    group_columns = ["information_set", "run", "model", "learner"]
    for keys, group in forecasts.groupby(group_columns):
        scopes = [("all_regions", group), *group.groupby("region_code")]
        for scope, scope_rows in scopes:
            rows.append(
                {
                    **dict(zip(group_columns, keys, strict=True)),
                    "scope": scope,
                    "forecasts": len(scope_rows),
                    "mae": mean_absolute_error(scope_rows["error"].to_numpy()),
                    "rmse": root_mean_squared_error(scope_rows["error"].to_numpy()),
                    "mape": mean_absolute_percentage_error(
                        scope_rows["target_price"].to_numpy(), scope_rows["forecast"].to_numpy()
                    ),
                }
            )
    return pd.DataFrame(rows)


def model_errors(forecasts: pd.DataFrame, model: str, learner: str) -> pd.DataFrame:
    """Return one model's errors keyed by region and target week."""
    rows = forecasts[(forecasts["model"] == model) & (forecasts["learner"] == learner)]
    return rows[[*FORECAST_KEYS, "error"]]


def planned_comparisons() -> list[dict[str, str]]:
    """List the pre-registered comparisons and the family each belongs to."""
    all_regions = [
        {"family": "all_regions", "model": SEASONAL_NAIVE, "learner": "none"},
        *[
            {"family": "all_regions", "model": rung, "learner": learner}
            for rung in ("C1", "C2")
            for learner in LEARNERS
        ],
    ]
    for comparison in all_regions:
        comparison.update(
            {"comparator": RANDOM_WALK, "comparator_learner": "none", "scope": "all_regions"}
        )
    nyc = []
    for learner in LEARNERS:
        for comparator, comparator_learner in (("C2", learner), (RANDOM_WALK, "none")):
            nyc.append(
                {
                    "family": "nyc_trip_demand",
                    "model": "C3",
                    "learner": learner,
                    "comparator": comparator,
                    "comparator_learner": comparator_learner,
                    "scope": DEMAND_REGION_CODE,
                }
            )
    return all_regions + nyc


def comparison_table(forecasts: pd.DataFrame, config: StudyConfig) -> pd.DataFrame:
    """Run every pre-registered comparison per information set and run, with Holm and wins."""
    rows = []
    for (information_set, run), group in forecasts.groupby(["information_set", "run"]):
        for planned in planned_comparisons():
            scoped = group
            if planned["scope"] != "all_regions":
                scoped = group[group["region_code"] == planned["scope"]]
            paired = paired_errors(
                model_errors(scoped, planned["model"], planned["learner"]),
                model_errors(scoped, planned["comparator"], planned["comparator_learner"]),
                FORECAST_KEYS,
            )
            result = compare_forecasts(
                paired, "target_week", config.experiments["bootstrap_resamples"], config.random_seed
            )
            rows.append({"information_set": information_set, "run": run, **planned, **result})
    return add_holm_and_wins(pd.DataFrame(rows), ["information_set", "run", "family"])


def region_win_table(forecasts: pd.DataFrame) -> pd.DataFrame:
    """Count, per model, the regions where its MAE is below the random walk's (descriptive)."""
    per_region = forecasts.groupby(["information_set", "run", "model", "learner", "region_code"])[
        "error"
    ].apply(lambda errors: errors.abs().mean())
    per_region = per_region.rename("mae").reset_index()
    random_walk = per_region[per_region["model"] == RANDOM_WALK][
        ["information_set", "run", "region_code", "mae"]
    ].rename(columns={"mae": "random_walk_mae"})
    compared = per_region.merge(random_walk, on=["information_set", "run", "region_code"])
    compared["beats_random_walk"] = compared["mae"] < compared["random_walk_mae"]
    return (
        compared[compared["model"] != RANDOM_WALK]
        .groupby(["information_set", "run", "model", "learner"])["beats_random_walk"]
        .agg(regions_beating_random_walk="sum", regions="size")
        .reset_index()
    )


def region_comparison_table(forecasts: pd.DataFrame) -> pd.DataFrame:
    """Test each model against the random walk in each region (plan section 7).

    Reported for every region but not part of the win criteria, so p-values are raw.
    """
    rows = []
    for (information_set, run), group in forecasts.groupby(["information_set", "run"]):
        for planned in planned_comparisons():
            if planned["family"] != "all_regions":
                continue
            for region_code, region in group.groupby("region_code"):
                paired = paired_errors(
                    model_errors(region, planned["model"], planned["learner"]),
                    model_errors(region, planned["comparator"], planned["comparator_learner"]),
                    FORECAST_KEYS,
                )
                differences = paired["error_model"].abs() - paired["error_comparator"].abs()
                test = diebold_mariano(differences.to_numpy())
                rows.append(
                    {
                        "information_set": information_set,
                        "run": run,
                        "model": planned["model"],
                        "learner": planned["learner"],
                        "region_code": region_code,
                        "forecasts": len(paired),
                        "mae_model": mean_absolute_error(paired["error_model"].to_numpy()),
                        "mae_random_walk": mean_absolute_error(
                            paired["error_comparator"].to_numpy()
                        ),
                        "dm_statistic_absolute": test["dm_statistic"],
                        "p_value_absolute": test["p_value"],
                    }
                )
    return pd.DataFrame(rows)


def exploratory_comparison_table(forecasts: pd.DataFrame, config: StudyConfig) -> pd.DataFrame:
    """Compare C2 with C1 (the weather increment), per learner; exploratory, not registered.

    Added after the results were first seen (docs/analysis_plan.md change log, 2026-10-10),
    so it is outside the Holm families and carries no win.
    """
    rows = []
    for (information_set, run), group in forecasts.groupby(["information_set", "run"]):
        for learner in LEARNERS:
            paired = paired_errors(
                model_errors(group, "C2", learner),
                model_errors(group, "C1", learner),
                FORECAST_KEYS,
            )
            result = compare_forecasts(
                paired, "target_week", config.experiments["bootstrap_resamples"], config.random_seed
            )
            rows.append(
                {
                    "information_set": information_set,
                    "run": run,
                    "model": "C2",
                    "learner": learner,
                    "comparator": "C1",
                    "scope": "all_regions",
                    **result,
                }
            )
    return pd.DataFrame(rows)


def skipped_forecast_table(panel: pd.DataFrame, config: StudyConfig) -> pd.DataFrame:
    """Count, per region, the evaluation target weeks with no forecast (no target or origin)."""
    first, last = (timestamp(day) for day in config.experiments["coarse"]["evaluation_targets"])
    target_weeks = pd.date_range(first, last, freq="W-MON")
    made = panel[panel["has_target"] & panel["target_week"].between(first, last)]
    rows = []
    for region_code in sorted(panel["region_code"].unique()):
        forecast_weeks = set(made.loc[made["region_code"] == region_code, "target_week"])
        skipped = [week for week in target_weeks if week not in forecast_weeks]
        rows.append(
            {
                "region_code": region_code,
                "target_weeks": len(target_weeks),
                "forecasts": len(forecast_weeks),
                "skipped": len(skipped),
                "skipped_target_weeks": " ".join(week.date().isoformat() for week in skipped),
            }
        )
    return pd.DataFrame(rows)


def run_coarse_task(config: StudyConfig) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Run the coarse-grain experiment and return its result tables and all forecasts."""
    extracts = read_coarse_extracts(config)
    forecast_frames, origin_frames, alpha_frames, panels = [], [], [], {}
    for information_set in INFORMATION_SETS:
        panel = build_coarse_panel(extracts, information_set, config)
        panels[information_set] = panel
        alpha_table = select_ridge_alphas(panel, information_set, config)
        alpha_frames.append(alpha_table)
        chosen = alpha_table[alpha_table["chosen"]]
        alphas = dict(zip(chosen["rung"], chosen["alpha"], strict=True))
        logger.info("ridge penalties (%s): %s", information_set, alphas)
        for run in RUNS:
            forecasts, origins = rolling_forecasts(panel, information_set, run, alphas, config)
            forecast_frames.append(forecasts)
            origin_frames.append(origins)

    forecasts = pd.concat(forecast_frames, ignore_index=True)
    tables = {
        "coarse_accuracy": accuracy_table(forecasts),
        "coarse_comparisons": comparison_table(forecasts, config),
        "coarse_region_wins": region_win_table(forecasts),
        "coarse_region_comparisons": region_comparison_table(forecasts),
        "coarse_exploratory_comparisons": exploratory_comparison_table(forecasts, config),
        "coarse_ridge_alphas": pd.concat(alpha_frames, ignore_index=True),
        "coarse_skipped_forecasts": skipped_forecast_table(panels[INFORMATION_SETS[0]], config),
        "coarse_origins": pd.concat(origin_frames, ignore_index=True),
    }
    return tables, forecasts


def coarse_summary(tables: dict[str, Any]) -> dict[str, Any]:
    """Return a short stage summary of the coarse-grain experiment."""
    comparisons = tables["coarse_comparisons"]
    main = comparisons[comparisons["run"] == "main"]
    return {
        "coarse_comparisons": len(comparisons),
        "coarse_main_wins": int(main["win"].sum()),
        "coarse_skipped_per_region": int(tables["coarse_skipped_forecasts"]["skipped"].max()),
    }
