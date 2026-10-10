"""Draw every paper figure from the result tables and the read-only warehouse."""

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from cigd.config import StudyConfig
from cigd.figures.style import (
    INFORMATION_SET_COLORS,
    INFORMATION_SET_LABELS,
    NEUTRAL_COLOR,
    PRIMARY_COLOR,
    TEXT_SECONDARY,
    save_figure,
)
from cigd.sql_files import load_sql

MODEL_LABELS = {
    "B2_seasonal_naive": "B2 seasonal naive",
    "C1": "C1 lags + calendar",
    "C2": "C2 + weather",
    "C3": "C3 + trip demand",
    "B1_random_walk": "B1 random walk",
    "N0": "N0 naive median",
    "F0": "F0 trip only",
    "F1": "F1 + calendar",
    "F2": "F2 + weather",
    "F3": "F3 + fuel price",
}
RUN_TITLES = {
    "main": "Main",
    "covid_excluded": "COVID weeks excluded from training",
    "robustness_2024": "Robustness: 2024 only",
    "sensitivity_recorded_distance": "Sensitivity: recorded distance added",
}
# Vertical offset of the two information sets within one row of a forest plot.
SET_OFFSETS = {"primary": -0.15, "secondary": 0.15}


def read_table(config: StudyConfig, name: str) -> pd.DataFrame:
    """Read one result table from results/tables/."""
    return pd.read_csv(config.tables_dir / f"{name}.csv")


def comparison_label(row: pd.Series) -> str:
    """Name a comparison in plain words, for example "C2 + weather (ridge) vs B1 random walk"."""
    model = MODEL_LABELS[row["model"]]
    learner = row.get("learner")
    # Coarse comparisons name their learner; fine comparisons and baselines have none.
    if isinstance(learner, str) and learner != "none":
        model = f"{model} ({learner})"
    return f"{model} vs {MODEL_LABELS[row['comparator']]}"


def forest_plot(axis: plt.Axes, comparisons: pd.DataFrame, title: str) -> None:
    """Plot percent change in MAE with 95 percent intervals, one row per comparison."""
    labels = list(dict.fromkeys(comparisons.apply(comparison_label, axis=1)))
    positions = {label: index for index, label in enumerate(labels)}
    for information_set, rows in comparisons.groupby("information_set"):
        y = [
            positions[comparison_label(row)] + SET_OFFSETS[information_set]
            for _, row in rows.iterrows()
        ]
        axis.errorbar(
            rows["percent_change"],
            y,
            xerr=[
                rows["percent_change"] - rows["percent_change_ci_low"],
                rows["percent_change_ci_high"] - rows["percent_change"],
            ],
            fmt="o",
            markersize=5,
            linewidth=1.5,
            color=INFORMATION_SET_COLORS[information_set],
            label=INFORMATION_SET_LABELS[information_set],
        )
    axis.axvline(0, color=TEXT_SECONDARY, linewidth=1)
    axis.set_yticks(range(len(labels)), labels)
    axis.invert_yaxis()
    axis.set_xlabel("Change in MAE vs comparator (%), 95% CI")
    axis.set_title(title, loc="left")
    axis.grid(axis="y", visible=False)


def draw_build_times(config: StudyConfig) -> None:
    """Figure: median duration of each warehouse build step, with the range over builds."""
    summary = read_table(config, "integration_build_time_summary")
    steps = summary[summary["step"] != "total"].sort_values("median_seconds")
    figure, axis = plt.subplots(figsize=(6.5, 4.5))
    axis.barh(steps["step"], steps["median_seconds"], color=PRIMARY_COLOR, height=0.6)
    axis.errorbar(
        steps["median_seconds"],
        steps["step"],
        xerr=[
            steps["median_seconds"] - steps["min_seconds"],
            steps["max_seconds"] - steps["median_seconds"],
        ],
        fmt="none",
        ecolor=TEXT_SECONDARY,
        linewidth=1,
    )
    builds = int(summary["builds"].max())
    axis.set_xlabel(f"Seconds (median and range over {builds} builds)")
    axis.set_title("Warehouse build time by step", loc="left")
    axis.grid(axis="y", visible=False)
    save_figure(figure, "integration_build_times", config)


def draw_query_latency(config: StudyConfig) -> None:
    """Figure: latency of the same question at four grains (median and interquartile range)."""
    latency = read_table(config, "integration_query_latency")
    figure, axis = plt.subplots(figsize=(5.5, 3.5))
    positions = np.arange(len(latency))
    axis.errorbar(
        positions,
        latency["median_seconds"] * 1000,
        yerr=[
            (latency["median_seconds"] - latency["q1_seconds"]) * 1000,
            (latency["q3_seconds"] - latency["median_seconds"]) * 1000,
        ],
        fmt="o",
        markersize=7,
        color=PRIMARY_COLOR,
    )
    for position, seconds in zip(positions, latency["median_seconds"], strict=True):
        axis.annotate(
            f"{seconds * 1000:.1f} ms",
            (position, seconds * 1000),
            textcoords="offset points",
            xytext=(8, 0),
            va="center",
            color=TEXT_SECONDARY,
        )
    axis.set_yscale("log")
    axis.set_xticks(positions, latency["grain"].str.replace("_", "-"))
    axis.set_xlabel("Grain the question is answered from")
    axis.set_ylabel("Query time (ms, log scale)")
    runs = int(latency["timed_runs"].iloc[0])
    axis.set_title(f"Same question, four grains (median and IQR of {runs} runs)", loc="left")
    save_figure(figure, "integration_query_latency", config)


def draw_table_storage(config: StudyConfig) -> None:
    """Figure: storage allocated to each dimension, fact and aggregate table."""
    storage = read_table(config, "integration_table_storage")
    modelled = storage[storage["table"].str.match(r"^(dim|fact|agg)_")]
    modelled = modelled.sort_values("allocated_bytes")
    figure, axis = plt.subplots(figsize=(6.5, 3.8))
    axis.barh(
        modelled["table"], modelled["allocated_bytes"] / 1024**2, color=PRIMARY_COLOR, height=0.6
    )
    axis.set_xscale("log")
    axis.set_xlabel("Allocated storage (MB, log scale)")
    axis.set_title("Warehouse storage by table", loc="left")
    axis.grid(axis="y", visible=False)
    save_figure(figure, "integration_table_storage", config)


def draw_price_and_demand(config: StudyConfig) -> None:
    """Figure: the two domains over time: regional weekly prices and NYC weekly trip demand."""
    with duckdb.connect(str(config.warehouse_path), read_only=True) as connection:
        prices = connection.execute(load_sql("features/region_week_price.sql")).df()
        demand = connection.execute(load_sql("features/region_week_trip_demand.sql")).df()
    regional = prices[prices["series_code"] != "NY"]
    nyc_demand = demand[
        (demand["region_code"] == "new_york_city") & (demand["days_with_trips"] == 7)
    ]

    figure, (price_axis, demand_axis) = plt.subplots(2, 1, figsize=(7, 5.5), sharex=True)
    for region_code, series in regional.groupby("series_code"):
        is_nyc = region_code == "new_york_city"
        price_axis.plot(
            series["week_start"],
            series["price_usd_per_gallon"],
            color=PRIMARY_COLOR if is_nyc else NEUTRAL_COLOR,
            linewidth=1.6 if is_nyc else 0.6,
            alpha=1.0 if is_nyc else 0.5,
            zorder=3 if is_nyc else 2,
        )
    price_axis.set_ylabel("USD per gallon")
    price_axis.set_title(
        "Weekly regular gasoline price: New York City (blue) and the other 15 regions (gray)",
        loc="left",
    )
    demand_axis.plot(nyc_demand["week_start"], nyc_demand["trip_count"] / 1000, color=PRIMARY_COLOR)
    demand_axis.set_ylabel("Thousand trips")
    demand_axis.set_title("Weekly yellow taxi trips starting in New York City", loc="left")
    save_figure(figure, "data_price_and_demand", config)


def seasonal_naive_note(rows: pd.DataFrame) -> str:
    """Describe the seasonal naive result in words, for the note under the figure.

    Baselines do not depend on the information set or the training rows, so every
    panel shows the same value; if they ever differ, each one is listed.
    """
    distinct = rows.drop_duplicates(
        ["percent_change", "percent_change_ci_low", "percent_change_ci_high"]
    )
    parts = [
        f"{row['percent_change']:+,.0f}% (95% CI {row['percent_change_ci_low']:+,.0f} to "
        f"{row['percent_change_ci_high']:+,.0f})"
        for _, row in distinct.iterrows()
    ]
    return "Not shown (off scale): B2 seasonal naive vs B1 random walk, " + "; ".join(parts)


def draw_coarse_effects(config: StudyConfig) -> None:
    """Figure: coarse-grain models against the random walk, all regions, main and COVID runs.

    The seasonal naive baseline is far worse than the random walk at a one-week
    horizon; it is stated under the figure so it does not flatten the scale.
    """
    comparisons = read_table(config, "coarse_comparisons")
    all_regions = comparisons[comparisons["family"] == "all_regions"]
    is_seasonal = all_regions["model"] == "B2_seasonal_naive"
    figure, axes = plt.subplots(1, 2, figsize=(12, 3.8), sharey=True)
    for axis, run in zip(axes, ("main", "covid_excluded"), strict=True):
        forest_plot(axis, all_regions[(all_regions["run"] == run) & ~is_seasonal], RUN_TITLES[run])
    figure.text(0.01, -0.06, seasonal_naive_note(all_regions[is_seasonal]), color=TEXT_SECONDARY)
    axes[0].legend(loc="upper center", bbox_to_anchor=(1.05, 1.22), ncol=2)
    save_figure(figure, "coarse_effects_all_regions", config)


def draw_coarse_nyc(config: StudyConfig) -> None:
    """Figure: the trip-demand rung on New York City, with the minimum detectable difference."""
    comparisons = read_table(config, "coarse_comparisons")
    nyc = comparisons[(comparisons["family"] == "nyc_trip_demand") & (comparisons["run"] == "main")]
    figure, axis = plt.subplots(figsize=(7, 3.6))
    forest_plot(axis, nyc, "Trip demand (C3) on New York City, main run")
    labels = list(dict.fromkeys(nyc.apply(comparison_label, axis=1)))
    for information_set, rows in nyc.groupby("information_set"):
        for _, row in rows.iterrows():
            y = labels.index(comparison_label(row)) + SET_OFFSETS[information_set]
            detectable = row["minimum_detectable_percent"]
            axis.plot(
                [-detectable, detectable],
                [y, y],
                linestyle="none",
                marker="|",
                markersize=9,
                color=INFORMATION_SET_COLORS[information_set],
                alpha=0.6,
            )
    axis.legend(loc="upper center", bbox_to_anchor=(0.4, 1.25), ncol=2)
    axis.annotate(
        "Ticks: smallest change detectable at 80% power",
        xy=(0.01, -0.28),
        xycoords="axes fraction",
        color=TEXT_SECONDARY,
    )
    save_figure(figure, "coarse_effects_nyc_trip_demand", config)


def draw_fine_effects(config: StudyConfig) -> None:
    """Figure: each fine-grain rung against the one below it, for every run."""
    comparisons = read_table(config, "fine_comparisons")
    runs = [run for run in RUN_TITLES if run in set(comparisons["run"])]
    # One run per row, so each panel keeps its own row labels.
    figure, axes = plt.subplots(len(runs), 1, figsize=(7.5, 3 * len(runs)))
    for axis, run in zip(np.atleast_1d(axes), runs, strict=True):
        forest_plot(axis, comparisons[comparisons["run"] == run], RUN_TITLES[run])
    np.atleast_1d(axes)[0].legend(loc="upper center", bbox_to_anchor=(0.4, 1.32), ncol=2)
    figure.tight_layout()
    save_figure(figure, "fine_effects", config)


def draw_fine_accuracy(config: StudyConfig) -> None:
    """Figure: fine-grain MAE of log duration per model, for every run and information set."""
    accuracy = read_table(config, "fine_accuracy")
    runs = [run for run in RUN_TITLES if run in set(accuracy["run"])]
    figure, axes = plt.subplots(1, len(runs), figsize=(4.5 * len(runs), 3.4), sharey=True)
    order = ["N0", "F0", "F1", "F2", "F3"]
    for axis, run in zip(np.atleast_1d(axes), runs, strict=True):
        for information_set, rows in accuracy[accuracy["run"] == run].groupby("information_set"):
            rows = rows.set_index("model").reindex(
                [model for model in order if model in rows["model"].values]
            )
            axis.plot(
                rows.index,
                rows["mae_log_duration"],
                marker="o",
                markersize=6,
                color=INFORMATION_SET_COLORS[information_set],
                label=INFORMATION_SET_LABELS[information_set],
            )
        axis.set_title(RUN_TITLES[run], loc="left")
        axis.set_xlabel("Model")
    np.atleast_1d(axes)[0].set_ylabel("MAE of log duration")
    np.atleast_1d(axes)[0].legend(loc="upper right")
    save_figure(figure, "fine_accuracy", config)


FIGURES = [
    draw_build_times,
    draw_query_latency,
    draw_table_storage,
    draw_price_and_demand,
    draw_coarse_effects,
    draw_coarse_nyc,
    draw_fine_effects,
    draw_fine_accuracy,
]
