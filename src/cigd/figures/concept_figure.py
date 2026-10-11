"""Figure 1: the conceptual architecture of the study, with every count read from the results."""

from dataclasses import dataclass

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch

from cigd.config import StudyConfig
from cigd.figures.draw import read_table
from cigd.figures.paper_figures import journal_style
from cigd.figures.style import save_figure

FIGURE_NAMES = ["fig_concept"]

INK = "#1f1f1f"
MUTED = "#5f5e5a"
LINE = "#a3a29d"
BLUE = "#2a78d6"
BLUE_FILL = "#e6effb"
WARM = "#eb6834"
WARM_FILL = "#fdf0e8"
SAND = "#f5f3ee"
GREEN = "#4f9a63"
GREEN_FILL = "#eaf4ec"

# The drawing is laid out on a 160 by 104 grid and scaled to the page width.
GRID_WIDTH, GRID_HEIGHT = 160, 104
FIGURE_WIDTH_INCHES = 6.6
AGGREGATE_TABLES = [
    "agg_trip_zone_day",
    "agg_trip_zone_week",
    "agg_trip_region_week",
    "agg_weather_region_week",
]


@dataclass(frozen=True)
class ConceptNumbers:
    """Every number printed in the concept figure."""

    trips_fact_window: int
    trips_history: int
    fact_window_years: str
    history_years: str
    price_series: int
    price_weeks: int
    weather_regions: int
    weather_rows: int
    zones: int
    zone_centroids: int
    fact_trip_rows: int
    fact_price_rows: int
    fact_weather_rows: int
    dim_date_rows: int
    dim_geography_rows: int
    valid_trips_per_price_row: int
    aggregate_rows: list[tuple[str, int]]
    validity_rules: int
    test_trips: int
    forecasts: int
    latency_runs: int
    cutoff: str
    trip_lag_months: int
    weather_lag_days: int


def year_span(first_month: str, last_month: str) -> str:
    """Describe a month range as "2024 to 2025", or "2024" when it is one year."""
    first_year, last_year = first_month[:4], last_month[:4]
    return first_year if first_year == last_year else f"{first_year} to {last_year}"


def read_concept_numbers(config: StudyConfig) -> ConceptNumbers:
    """Collect the figure's numbers from the result tables and the configuration."""
    rows_by_table = dict(
        read_table(config, "warehouse_tables")[["table", "rows"]].itertuples(index=False)
    )
    raw_storage = read_table(config, "integration_raw_storage")
    streamed = raw_storage[
        (raw_storage["source"] == "yellow_taxi")
        & (raw_storage["stored_locally"] == "aggregate_only")
    ]
    price_series = read_table(config, "profile_price_series")
    weather = read_table(config, "profile_weather")
    ratios = read_table(config, "integration_grain_ratios").set_index("measure")["value"]
    rules = read_table(config, "warehouse_trip_validity")
    fine = read_table(config, "fine_accuracy")
    coarse = read_table(config, "coarse_comparisons")
    latency = read_table(config, "integration_query_latency")
    lags = config.experiments["publication_lags"]
    cutoff = config.data_cutoff_date
    main_test = fine[(fine["run"] == "main") & (fine["information_set"] == "primary")]
    main_forecasts = coarse[
        (coarse["run"] == "main")
        & (coarse["information_set"] == "primary")
        & (coarse["family"] == "all_regions")
    ]
    return ConceptNumbers(
        trips_fact_window=int(read_table(config, "profile_trip_months")["trip_rows"].sum()),
        trips_history=int(streamed["rows"].sum()),
        fact_window_years=year_span(config.trip_first_month, config.trip_last_month),
        history_years=year_span(config.trip_history_first_month, config.trip_history_last_month),
        price_series=len(price_series),
        price_weeks=int(price_series["weeks_expected"].max()),
        weather_regions=len(weather),
        weather_rows=int(weather["days"].sum()),
        zones=int(rows_by_table["stg_zone_lookup"]),
        zone_centroids=int(rows_by_table["stg_zone_centroid"]),
        fact_trip_rows=int(rows_by_table["fact_trip"]),
        fact_price_rows=int(rows_by_table["fact_fuel_price_weekly"]),
        fact_weather_rows=int(rows_by_table["fact_weather_daily"]),
        dim_date_rows=int(rows_by_table["dim_date"]),
        dim_geography_rows=int(rows_by_table["dim_geography"]),
        valid_trips_per_price_row=round(ratios["valid_trips_per_price_row"]),
        aggregate_rows=[(name, int(rows_by_table[name])) for name in AGGREGATE_TABLES],
        validity_rules=int((rules["rule"].drop_duplicates() != "kept").sum()),
        test_trips=int(main_test["test_trips"].max()),
        forecasts=int(main_forecasts["forecasts"].max()),
        latency_runs=int(latency["timed_runs"].iloc[0]),
        cutoff=f"{cutoff.day} {cutoff:%b %Y}",
        trip_lag_months=int(lags["tlc_months_until_usable"]),
        weather_lag_days=int(lags["weather_days"]),
    )


def millions(value: int) -> str:
    """Format a count in millions, for example "89.9 M"."""
    return f"{value / 1e6:.1f} M"


def card(
    ax: plt.Axes,
    x: float,
    y: float,
    width: float,
    height: float,
    fill: str = "white",
    edge: str = LINE,
    lw: float = 0.7,
    rounding: float = 1.4,
) -> None:
    """Draw a rounded box."""
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle=f"round,pad=0,rounding_size={rounding}",
            fc=fill,
            ec=edge,
            lw=lw,
            zorder=2,
        )
    )


def label(
    ax: plt.Axes,
    x: float,
    y: float,
    text: str,
    size: float = 5.6,
    weight: str = "normal",
    color: str = INK,
    ha: str = "left",
    style: str = "normal",
) -> None:
    """Write one piece of text, vertically centred on y."""
    ax.text(
        x,
        y,
        text,
        fontsize=size,
        fontweight=weight,
        color=color,
        ha=ha,
        va="center",
        fontstyle=style,
        linespacing=1.3,
        zorder=4,
    )


def arrow(
    ax: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    color: str = INK,
    lw: float = 0.7,
) -> None:
    """Draw an arrow between two points."""
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=5.5,
            lw=lw,
            color=color,
            shrinkA=0,
            shrinkB=0,
            zorder=3,
        )
    )


def stage_heading(ax: plt.Axes, x: float, number: int, title: str) -> None:
    """Draw a numbered stage heading at the top of a column."""
    ax.add_patch(Circle((x + 2.1, 99.5), 2.1, fc=INK, ec="none"))
    label(ax, x + 2.1, 99.4, str(number), size=5.8, weight="bold", color="white", ha="center")
    label(ax, x + 5.6, 99.5, title, size=6.6, weight="bold")


def draw_sources(ax: plt.Axes, numbers: ConceptNumbers) -> list[float]:
    """Draw the source cards; return the vertical middle of each, for the arrows."""
    stage_heading(ax, 1, 1, "Public sources")
    sources = [
        (
            "NYC TLC yellow taxi",
            "one row per trip",
            [
                f"{millions(numbers.trips_fact_window)} kept, {numbers.fact_window_years}",
                f"{millions(numbers.trips_history)} counted, {numbers.history_years}",
            ],
        ),
        (
            "NYSERDA gasoline",
            "one row per region-week",
            [f"{numbers.price_series} series × {numbers.price_weeks} weeks"],
        ),
        (
            "Open-Meteo (ERA5)",
            "one row per region-day",
            [f"{numbers.weather_regions} regions, {numbers.weather_rows:,} rows"],
        ),
        (
            "TLC zones, shapefile",
            "one row per zone",
            [f"{numbers.zones} zones, {numbers.zone_centroids} centroids"],
        ),
        ("EIA weekly retail price", "cross-check only", ["NY State and PADD 1B"]),
    ]
    top = 93.0
    middles = []
    for name, grain, stats in sources:
        height = 9.6 + 2.9 * len(stats)
        card(ax, 1, top - height, 31, height, fill=SAND, edge=SAND)
        label(ax, 2.8, top - 3.0, name, size=6.0, weight="bold")
        label(ax, 2.8, top - 6.2, grain, size=5.3, color=BLUE, style="italic")
        for index, stat in enumerate(stats):
            label(ax, 2.8, top - 9.3 - 2.9 * index, stat, size=5.3, color=MUTED)
        middles.append(top - height / 2)
        top -= height + 1.8
    return middles


def draw_ingest(ax: plt.Axes, numbers: ConceptNumbers, source_middles: list[float]) -> None:
    """Draw the ingest and validate column with its vertical rail of steps."""
    stage_heading(ax, 36, 2, "Ingest and validate")
    rail = 38.2
    steps = [
        ("Download from official URLs", "checksum, size and rows\nwritten to a manifest"),
        ("Profile every source", "gaps and outliers; EIA level\nand weekly-change checks"),
        ("Fix the week label", "NYSERDA date describes\nthe preceding Monday week"),
        (
            f"Apply {numbers.validity_rules} ordered validity rules",
            "rows removed counted\nper rule and year",
        ),
        (
            "Freeze the snapshot",
            f"cutoff {numbers.cutoff};\nchecksums verified on rerun",
        ),
    ]
    ys = [86, 69.5, 53, 36.5, 20]
    ax.plot([rail, rail], [ys[-1], ys[0]], color=LINE, lw=0.8, zorder=1)
    for (heading, detail), y in zip(steps, ys, strict=True):
        ax.add_patch(Circle((rail, y), 1.25, fc="white", ec=INK, lw=0.8, zorder=3))
        label(ax, rail + 2.8, y + 1.2, heading, size=5.8, weight="bold")
        label(ax, rail + 2.8, y - 3.4, detail, size=5.2, color=MUTED)
    for middle in source_middles:
        arrow(ax, (32.4, middle), (rail - 1.5, middle), color=LINE, lw=0.6)
    arrow(ax, (rail + 1.3, 44.5), (75.6, 44.5))


def draw_warehouse(ax: plt.Axes, numbers: ConceptNumbers) -> None:
    """Draw the conformed warehouse: facts, shared dimensions and the aggregates."""
    stage_heading(ax, 77, 3, "Conformed warehouse")
    card(ax, 76, 4.5, 44.5, 89, fill="white", edge=LINE, lw=0.6, rounding=2)
    label(
        ax,
        98.25,
        7.3,
        "DuckDB, one SQL file per table",
        size=5.0,
        color=MUTED,
        ha="center",
        style="italic",
    )

    facts = [
        ("fact_trip", "1 valid trip", f"{millions(numbers.fact_trip_rows)} rows", 74.5),
        ("fact_fuel_price", "1 series-week", f"{numbers.fact_price_rows:,} rows", 58.5),
        ("fact_weather", "1 region-day", f"{numbers.fact_weather_rows:,} rows", 42.5),
    ]
    for name, grain, rows, y in facts:
        card(ax, 78, y, 17.5, 13, fill=WARM_FILL, edge=WARM, lw=0.8)
        label(ax, 86.75, y + 9.4, name, size=5.9, weight="bold", ha="center")
        label(ax, 86.75, y + 5.6, grain, size=5.2, color=MUTED, ha="center")
        label(ax, 86.75, y + 2.6, rows, size=5.2, color=MUTED, ha="center")
    dimensions = [
        (
            "dim_date",
            f"{numbers.dim_date_rows:,} days with\nISO week, holidays\nand NYSERDA label",
            70,
        ),
        (
            "dim_geography",
            f"{numbers.dim_geography_rows} members in\n6 nested levels,\nzone to country",
            47,
        ),
    ]
    for name, detail, y in dimensions:
        card(ax, 101, y, 17.5, 17, fill=BLUE_FILL, edge=BLUE, lw=0.9)
        label(ax, 109.75, y + 13.6, name, size=5.9, weight="bold", ha="center")
        label(ax, 109.75, y + 6.3, detail, size=5.0, color=MUTED, ha="center")
    label(ax, 109.75, 89.5, "conformed", size=5.3, color=BLUE, ha="center", style="italic")
    for *_, fact_y in facts:
        for *_, dimension_y in dimensions:
            ax.plot([95.5, 101], [fact_y + 6.5, dimension_y + 8.5], color=WARM, lw=0.6, zorder=2.5)

    label(ax, 86.75, 37.5, "grain gap", size=5.5, weight="bold", color=WARM, ha="center")
    label(
        ax,
        86.75,
        33.4,
        f"{numbers.valid_trips_per_price_row:,} valid trips\nper price row",
        size=5.2,
        color=MUTED,
        ha="center",
    )

    card(ax, 78, 10.5, 40.5, 19, fill=GREEN_FILL, edge=GREEN, lw=0.8)
    label(ax, 98.25, 26.4, "Aggregates at shared grains", size=5.9, weight="bold", ha="center")
    for index, (name, rows) in enumerate(numbers.aggregate_rows):
        y = 22.3 - 2.9 * index
        label(ax, 80.5, y, name, size=5.1)
        label(ax, 116, y, f"{rows:,}", size=5.1, ha="right", color=MUTED)
    arrow(ax, (109.75, 47), (109.75, 29.7), color=GREEN, lw=0.8)
    label(ax, 111, 38.3, "built only\nthrough the\ndimensions", size=4.9, color=GREEN)


def draw_experiments(ax: plt.Axes, numbers: ConceptNumbers) -> None:
    """Draw the experiments column: the information-set gate and the three experiments."""
    stage_heading(ax, 123, 4, "Experiments")
    gate_x, gate_width = 123.5, 35.5
    card(ax, gate_x, 66, gate_width, 27.5, fill="white", edge=INK, lw=0.8)
    label(ax, gate_x + 2, 90.1, "Information-set gate", size=5.9, weight="bold")
    label(
        ax,
        gate_x + 2,
        86.8,
        "what a forecast at origin t may use",
        size=5.0,
        color=MUTED,
        style="italic",
    )
    timeline_y = 79.5
    ax.plot([gate_x + 3, gate_x + 32.5], [timeline_y, timeline_y], color=INK, lw=0.7, zorder=3)
    ax.plot(
        [gate_x + 31, gate_x + 31],
        [timeline_y - 1.4, timeline_y + 1.4],
        color=INK,
        lw=0.9,
        zorder=3,
    )
    label(ax, gate_x + 31, timeline_y + 3.1, "t", size=5.9, weight="bold", ha="center")
    markers = [
        (gate_x + 9, f"trips up to\nmonth m − {numbers.trip_lag_months}"),
        (gate_x + 23.5, f"weather up\nto t − {numbers.weather_lag_days} days"),
    ]
    for marker_x, text in markers:
        ax.add_patch(Circle((marker_x, timeline_y), 0.85, fc=WARM, ec="none", zorder=4))
        label(ax, marker_x, timeline_y - 4.6, text, size=4.9, color=MUTED, ha="center")
    label(ax, gate_x + 31, timeline_y - 4.6, "price\nlabel t", size=4.9, color=MUTED, ha="center")
    label(ax, gate_x + 2, 69.6, "primary set: measured lags\nsecondary set: best case", size=4.9)

    experiments = [
        (
            "A  Integration cost",
            "build time, storage, grain ratio;\n"
            f"one query at four grains, {numbers.latency_runs} runs",
            46,
        ),
        (
            "B  Trip duration (fine grain)",
            "N0 > F0 > F1 calendar > F2 weather\n"
            f"> F3 fuel price; {numbers.test_trips:,} test trips",
            27.5,
        ),
        (
            "C  Weekly price (coarse grain)",
            f"B1, B2 > C1 lags > C2 weather\n> C3 trip demand; {numbers.forecasts:,} forecasts",
            9,
        ),
    ]
    for title, detail, y in experiments:
        card(ax, gate_x, y, gate_width, 15.5, fill=SAND, edge=SAND)
        label(ax, gate_x + 2, y + 11.8, title, size=5.9, weight="bold")
        label(ax, gate_x + 2, y + 5.4, detail, size=5.1, color=MUTED)
    arrow(ax, (gate_x + gate_width / 2, 66), (gate_x + gate_width / 2, 61.7))
    for y in (53.75, 35.25, 16.75):
        arrow(ax, (120.6, y), (gate_x - 0.2, y))


def draw_concept_figure(config: StudyConfig) -> None:
    """Draw Figure 1 and save it as PNG and PDF."""
    numbers = read_concept_numbers(config)
    with journal_style():
        figure = plt.figure(
            figsize=(FIGURE_WIDTH_INCHES, FIGURE_WIDTH_INCHES * GRID_HEIGHT / GRID_WIDTH)
        )
        ax = figure.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, GRID_WIDTH)
        ax.set_ylim(0, GRID_HEIGHT)
        ax.axis("off")
        source_middles = draw_sources(ax, numbers)
        draw_ingest(ax, numbers, source_middles)
        draw_warehouse(ax, numbers)
        draw_experiments(ax, numbers)
        save_figure(figure, "fig_concept", config, tight=False)
