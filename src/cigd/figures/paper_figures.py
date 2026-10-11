"""Journal-format result figures, drawn only from the committed result tables."""

from collections.abc import Iterator
from contextlib import contextmanager

import matplotlib.pyplot as plt
import pandas as pd

from cigd.config import StudyConfig
from cigd.figures.draw import read_table
from cigd.figures.style import journal_font_family, save_figure

INK = "#1f1f1f"
MUTED = "#6b6b6b"
GRID = "#e4e4e1"
BLUE = "#2a78d6"  # primary information set
ORANGE = "#eb6834"  # secondary information set
BAND = "#efeeea"
# Label, colour and marker of each information set.
INFORMATION_SETS = {
    "primary": ("Primary (measured lags)", BLUE, "o"),
    "secondary": ("Secondary (best case)", ORANGE, "s"),
}
# Vertical offset of each information set within one row of a forest plot.
SET_OFFSETS = {"primary": 0.16, "secondary": -0.16}
FIGURE_NAMES = [
    "fig_build_storage",
    "fig_latency",
    "fig_fine_accuracy",
    "fig_fine_effects",
    "fig_coarse_effects",
    "fig_nyc_trip_demand",
]
# Tables shown in the storage panel, largest first as in the paper.
STORAGE_TABLES = [
    "fact_trip",
    "agg_trip_zone_day",
    "agg_trip_zone_week",
    "fact_weather_daily",
    "fact_fuel_price_weekly",
    "agg_trip_region_week",
    "agg_weather_region_week",
    "dim_date",
    "dim_geography",
]
LATENCY_GRAIN_NAMES = {
    "trip": "Trip fact",
    "zone_day": "Zone-day",
    "zone_week": "Zone-week",
    "region_week": "Region-week",
}
TOP_BUILD_STEPS = 5


@contextmanager
def journal_style() -> Iterator[None]:
    """Apply the journal rcParams to one figure without changing the other figures."""
    settings = {
        "font.family": journal_font_family(),
        "font.size": 8,
        "axes.titlesize": 8.5,
        "axes.labelsize": 8,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "legend.fontsize": 7.5,
        "axes.edgecolor": MUTED,
        "axes.linewidth": 0.6,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
    with plt.rc_context(settings):
        yield


def panel_title(axis: plt.Axes, text: str) -> None:
    """Put a bold, left-aligned panel title above an axis."""
    axis.set_title(text, loc="left", fontweight="bold", pad=6)


def padded_limits(low: float, high: float, fraction: float = 0.06) -> tuple[float, float]:
    """Widen a data range a little so points and their labels do not touch the frame."""
    margin = (high - low) * fraction
    return low - margin, high + margin


def legend_above(figure: plt.Figure, height: float) -> None:
    """Draw the information-set legend above the panels."""
    handles = [
        plt.Line2D([], [], color=colour, marker=marker, lw=1.3, ms=4.5, mec="white", mew=0.6)
        for _, colour, marker in INFORMATION_SETS.values()
    ]
    labels = [label for label, _, _ in INFORMATION_SETS.values()]
    figure.legend(
        handles, labels, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, height)
    )


def test_year(config: StudyConfig, setting: str) -> str:
    """Return the calendar year of a configured test period, for panel titles."""
    return config.experiments["fine"][setting][0][:4]


def forest(
    axis: plt.Axes,
    rows: list[tuple[str, str]],
    data: pd.DataFrame,
    xlabel: str,
    show_detectable_band: bool = False,
) -> tuple[float, float]:
    """Plot a point and 95% interval per row and information set.

    rows holds (label, key) pairs, top to bottom. With show_detectable_band, a grey band
    marks the smallest change the test could detect. Returns the horizontal extent drawn.
    """
    low_edges, high_edges = [0.0], [0.0]
    row_count = len(rows)
    for position, (_, key) in enumerate(rows):
        y = row_count - 1 - position
        if show_detectable_band:
            detectable = data[(data.key == key) & (data.information_set == "primary")]
            if len(detectable):
                half_width = float(detectable.minimum_detectable_percent.iloc[0])
                axis.fill_betweenx([y - 0.38, y + 0.38], -half_width, half_width, color=BAND, lw=0)
                low_edges.append(-half_width)
                high_edges.append(half_width)
        for information_set, (_, colour, marker) in INFORMATION_SETS.items():
            result = data[(data.key == key) & (data.information_set == information_set)]
            if not len(result):
                continue
            row = result.iloc[0]
            offset_y = y + SET_OFFSETS[information_set]
            axis.hlines(
                offset_y,
                row.percent_change_ci_low,
                row.percent_change_ci_high,
                color=colour,
                lw=1.3,
            )
            axis.plot(
                row.percent_change,
                offset_y,
                marker=marker,
                color=colour,
                ms=4.5,
                mec="white",
                mew=0.6,
                zorder=3,
            )
            low_edges.append(float(row.percent_change_ci_low))
            high_edges.append(float(row.percent_change_ci_high))
    axis.axvline(0, color=INK, lw=0.7)
    axis.set_yticks(range(row_count)[::-1], [label for label, _ in rows])
    axis.set_xlabel(xlabel)
    axis.grid(axis="x", color=GRID, lw=0.6)
    axis.set_axisbelow(True)
    axis.set_ylim(-0.6, row_count - 0.4)
    return min(low_edges), max(high_edges)


def draw_build_and_storage(config: StudyConfig) -> None:
    """Draw build time per warehouse step next to storage per table."""
    build = read_table(config, "integration_build_time_summary")
    builds = int(build["builds"].max())
    build = build[build["step"] != "total"].sort_values("median_seconds", ascending=False)
    top, rest = build.head(TOP_BUILD_STEPS), build.iloc[TOP_BUILD_STEPS:]
    labels = [*top["step"], f"{len(rest)} other steps"]
    medians = [*top["median_seconds"], rest["median_seconds"].sum()]
    lows = [*top["min_seconds"], rest["min_seconds"].sum()]
    highs = [*top["max_seconds"], rest["max_seconds"].sum()]

    storage = read_table(config, "integration_table_storage")
    storage = storage.set_index("table").loc[STORAGE_TABLES].reset_index()
    megabytes = storage["allocated_bytes"] / 1e6

    with journal_style():
        figure, (build_axis, storage_axis) = plt.subplots(
            1, 2, figsize=(6.2, 2.55), gridspec_kw={"wspace": 0.95}
        )
        y = list(range(len(labels)))[::-1]
        build_axis.barh(y, medians, color=BLUE, height=0.6)
        build_axis.errorbar(
            medians,
            y,
            xerr=[
                [m - low for m, low in zip(medians, lows, strict=True)],
                [high - m for m, high in zip(medians, highs, strict=True)],
            ],
            fmt="none",
            ecolor=INK,
            elinewidth=0.7,
            capsize=2,
        )
        axis_end = max(highs) * 1.3
        for row_y, median, high in zip(y, medians, highs, strict=True):
            build_axis.text(
                max(median, high) + axis_end * 0.025,
                row_y,
                f"{median:.1f} s",
                va="center",
                fontsize=7,
                color=INK,
            )
        build_axis.set_yticks(y, labels)
        build_axis.set_xlim(0, axis_end)
        build_axis.set_xlabel(f"Seconds (median and range of {builds} builds)")
        build_axis.grid(axis="x", color=GRID, lw=0.6)
        build_axis.set_axisbelow(True)
        panel_title(build_axis, "(a) Build time by step")

        y_storage = list(range(len(storage)))[::-1]
        storage_axis.barh(y_storage, megabytes, color=BLUE, height=0.6)
        storage_axis.set_xscale("log")
        for row_y, size in zip(y_storage, megabytes, strict=True):
            text = f"{size / 1000:.2f} GB" if size > 1000 else f"{size:.1f} MB"
            storage_axis.text(size * 1.25, row_y, text, va="center", fontsize=7, color=INK)
        storage_axis.set_yticks(y_storage, storage["table"])
        storage_axis.set_xlim(megabytes.min() * 0.6, megabytes.max() * 10)
        storage_axis.set_xlabel("Allocated storage (MB, log scale)")
        storage_axis.grid(axis="x", color=GRID, lw=0.6)
        storage_axis.set_axisbelow(True)
        panel_title(storage_axis, "(b) Storage by table")
        save_figure(figure, "fig_build_storage", config, pad_inches=0.03)


def draw_latency(config: StudyConfig) -> None:
    """Draw the median latency of one question answered at four grains."""
    latency = read_table(config, "integration_query_latency")
    medians = latency["median_seconds"] * 1000
    q1 = latency["q1_seconds"] * 1000
    q3 = latency["q3_seconds"] * 1000
    with journal_style():
        figure, axis = plt.subplots(figsize=(4.2, 2.3))
        x = list(range(len(latency)))
        axis.vlines(x, q1, q3, color=INK, lw=1.2)
        axis.plot(x, medians, "o", color=BLUE, ms=6, mec="white", mew=0.8, zorder=3)
        finest = medians.iloc[0]
        for position, median, upper in zip(x, medians, q3, strict=True):
            speedup = "" if position == 0 else f"\n{finest / median:.0f}x faster"
            axis.annotate(
                f"{median:.1f} ms{speedup}",
                (position, upper),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=7,
                linespacing=1.1,
            )
        axis.set_yscale("log")
        axis.set_ylim(q1.min() * 0.6, q3.max() * 2)
        axis.set_xlim(-0.5, len(latency) - 0.5)
        axis.set_xticks(x, [LATENCY_GRAIN_NAMES[grain] for grain in latency["grain"]])
        axis.set_ylabel("Query time (ms, log scale)")
        axis.set_xlabel("Grain the question is answered from")
        axis.grid(axis="y", color=GRID, lw=0.6, which="major")
        axis.set_axisbelow(True)
        save_figure(figure, "fig_latency", config, pad_inches=0.03)


def draw_fine_accuracy(config: StudyConfig) -> None:
    """Draw the fine-grain MAE of log duration per rung, for each run."""
    accuracy = read_table(config, "fine_accuracy")
    runs = [
        ("main", f"(a) Main run, {test_year(config, 'main_test_months')}"),
        ("robustness_2024", f"(b) Robustness, {test_year(config, 'robustness_test_months')} only"),
        ("sensitivity_recorded_distance", "(c) Sensitivity, recorded distance"),
    ]
    with journal_style():
        figure, axes = plt.subplots(1, 3, figsize=(6.2, 2.2), gridspec_kw={"wspace": 0.38})
        for axis, (run, title) in zip(axes, runs, strict=True):
            for key, (label, colour, marker) in INFORMATION_SETS.items():
                part = accuracy[(accuracy["run"] == run) & (accuracy["information_set"] == key)]
                order = [m for m in ["N0", "F0", "F1", "F2", "F3"] if m in set(part["model"])]
                part = part.set_index("model").loc[order]
                axis.plot(
                    order,
                    part["mae_log_duration"],
                    marker=marker,
                    color=colour,
                    lw=1.4,
                    ms=4.5,
                    mec="white",
                    mew=0.6,
                    label=label,
                )
            axis.grid(axis="y", color=GRID, lw=0.6)
            axis.set_axisbelow(True)
            panel_title(axis, title)
            axis.set_xlabel("Rung")
        axes[0].set_ylabel("MAE of log duration")
        legend_above(figure, 1.09)
        save_figure(figure, "fig_fine_accuracy", config, pad_inches=0.03)


def draw_fine_effects(config: StudyConfig) -> None:
    """Draw each fine-grain rung against the one below it, for each run."""
    comparisons = read_table(config, "fine_comparisons")
    comparisons["key"] = (
        comparisons["run"] + ":" + comparisons["model"] + ":" + comparisons["comparator"]
    )
    labels = [
        ("F0 vs N0", "F0:N0"),
        ("F1 calendar vs F0", "F1:F0"),
        ("F2 weather vs F1", "F2:F1"),
        ("F3 fuel price vs F2", "F3:F2"),
    ]
    runs = [
        ("main", f"(a) Main run, {test_year(config, 'main_test_months')}"),
        ("robustness_2024", f"(b) {test_year(config, 'robustness_test_months')} only"),
        ("sensitivity_recorded_distance", "(c) Recorded distance"),
    ]
    with journal_style():
        figure, axes = plt.subplots(
            1, 3, figsize=(6.2, 2.2), sharey=True, gridspec_kw={"wspace": 0.12}
        )
        for axis, (run, title) in zip(axes, runs, strict=True):
            rows = [(label, f"{run}:{key}") for label, key in labels]
            forest(axis, rows, comparisons, "Change in MAE (%)")
            panel_title(axis, title)
        legend_above(figure, 1.07)
        save_figure(figure, "fig_fine_effects", config, pad_inches=0.03)


def draw_coarse_effects(config: StudyConfig) -> None:
    """Draw the coarse-grain models against the random walk, for the main and COVID runs."""
    comparisons = read_table(config, "coarse_comparisons")
    comparisons = comparisons[comparisons["family"] == "all_regions"].copy()
    comparisons["key"] = (
        comparisons["run"] + ":" + comparisons["model"] + ":" + comparisons["learner"]
    )
    labels = [
        ("C1 lags + calendar, LightGBM", "C1:lightgbm"),
        ("C1 lags + calendar, ridge", "C1:ridge"),
        ("C2 + weather, LightGBM", "C2:lightgbm"),
        ("C2 + weather, ridge", "C2:ridge"),
    ]
    runs = [("main", "(a) Main run"), ("covid_excluded", "(b) COVID weeks excluded from training")]
    with journal_style():
        figure, axes = plt.subplots(
            1, 2, figsize=(6.2, 2.1), sharey=True, gridspec_kw={"wspace": 0.1}
        )
        extents = []
        for axis, (run, title) in zip(axes, runs, strict=True):
            rows = [(label, f"{run}:{key}") for label, key in labels]
            extents.append(
                forest(axis, rows, comparisons, "Change in MAE against the random walk (%)")
            )
            panel_title(axis, title)
        # Both panels share one scale so they can be compared by eye.
        limits = padded_limits(min(low for low, _ in extents), max(high for _, high in extents))
        for axis in axes:
            axis.set_xlim(*limits)
        legend_above(figure, 1.08)
        save_figure(figure, "fig_coarse_effects", config, pad_inches=0.03)


def draw_nyc_trip_demand(config: StudyConfig) -> None:
    """Draw the trip-demand rung (C3) on New York City, with the detectable-effect band."""
    comparisons = read_table(config, "coarse_comparisons")
    nyc = comparisons[
        (comparisons["family"] == "nyc_trip_demand") & (comparisons["run"] == "main")
    ].copy()
    nyc["key"] = nyc["learner"] + ":" + nyc["comparator"]
    panels = [
        ("(a) C3 trip demand vs C2", "C2"),
        ("(b) C3 trip demand vs random walk", "B1_random_walk"),
    ]
    with journal_style():
        figure, axes = plt.subplots(1, 2, figsize=(6.2, 1.75), gridspec_kw={"wspace": 0.55})
        for axis, (title, comparator) in zip(axes, panels, strict=True):
            rows = [("LightGBM", f"lightgbm:{comparator}"), ("Ridge", f"ridge:{comparator}")]
            low, high = forest(axis, rows, nyc, "Change in MAE (%)", show_detectable_band=True)
            axis.set_xlim(*padded_limits(low, high, fraction=0.1))
            panel_title(axis, title)
        legend_above(figure, 1.14)
        save_figure(figure, "fig_nyc_trip_demand", config, pad_inches=0.03)


PAPER_FIGURES = [
    draw_build_and_storage,
    draw_latency,
    draw_fine_accuracy,
    draw_fine_effects,
    draw_coarse_effects,
    draw_nyc_trip_demand,
]
