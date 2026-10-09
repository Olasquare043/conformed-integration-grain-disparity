"""Profile the NYSERDA weekly price panel and cross-check it against EIA."""

import pandas as pd

from cigd.config import StudyConfig

EIA_NEW_YORK_STATE = "EMM_EPMR_PTE_SNY_DPG"
EIA_PADD_1B = "EMM_EPMR_PTE_R1Y_DPG"
# Week offsets tried when aligning NYSERDA with EIA. Offset k pairs NYSERDA
# week w with EIA week w + k, which shows whether the two Monday dates mean the same week.
ALIGNMENT_OFFSETS_WEEKS = (-1, 0, 1)


def expected_weeks(config: StudyConfig) -> pd.DatetimeIndex:
    """Return every Monday from the first price week to the cutoff."""
    return pd.date_range(config.price_first_week, config.data_cutoff_date, freq="W-MON")


def complete_weekly_grid(panel: pd.DataFrame, config: StudyConfig) -> pd.DataFrame:
    """Put every series on every expected week, so absent weeks become explicit rows."""
    grid = pd.MultiIndex.from_product(
        [sorted(panel["series_code"].unique()), expected_weeks(config)],
        names=["series_code", "week_start"],
    )
    indexed = panel.set_index(["series_code", "week_start"])
    return indexed.reindex(grid).reset_index()


def profile_price_series(panel: pd.DataFrame, config: StudyConfig) -> pd.DataFrame:
    """Summarise coverage and range for each price series."""
    weeks = expected_weeks(config)
    weeks_in_file = set(panel["week_start"])
    series_rows = []
    for series_code, series in panel.groupby("series_code"):
        priced = series.dropna(subset=["price_usd_per_gallon"])
        series_rows.append(
            {
                "series_code": series_code,
                "weeks_expected": len(weeks),
                "weeks_with_price": len(priced),
                "weeks_without_row": len(set(weeks) - weeks_in_file),
                "weeks_with_blank_price": int(series["price_usd_per_gallon"].isna().sum()),
                "dates_not_on_monday": int((series["week_start"].dt.weekday != 0).sum()),
                "first_priced_week": priced["week_start"].min().date(),
                "last_priced_week": priced["week_start"].max().date(),
                "min_usd": priced["price_usd_per_gallon"].min(),
                "mean_usd": round(priced["price_usd_per_gallon"].mean(), 4),
                "max_usd": priced["price_usd_per_gallon"].max(),
            }
        )
    return pd.DataFrame(series_rows)


def list_missing_weeks(panel: pd.DataFrame, config: StudyConfig) -> pd.DataFrame:
    """List every series-week with no price, and whether the row or only the value is absent."""
    weeks_in_file = set(panel["week_start"])
    grid = complete_weekly_grid(panel, config)
    missing = grid[grid["price_usd_per_gallon"].isna()].copy()
    missing["reason"] = missing["week_start"].map(
        lambda week: "blank price" if week in weeks_in_file else "week absent from file"
    )
    return missing[["series_code", "week_start", "reason"]].reset_index(drop=True)


def list_price_outliers(panel: pd.DataFrame, config: StudyConfig) -> pd.DataFrame:
    """Flag (never remove) prices outside the plausible range or with a large weekly move."""
    thresholds = config.quality["price_outliers"]
    grid = complete_weekly_grid(panel, config)
    grid["weekly_change_usd"] = grid.groupby("series_code")["price_usd_per_gallon"].diff()

    price = grid["price_usd_per_gallon"]
    outside_range = (price < thresholds["plausible_min_usd"]) | (
        price > thresholds["plausible_max_usd"]
    )
    large_move = grid["weekly_change_usd"].abs() > thresholds["max_weekly_change_usd"]

    flagged = grid[outside_range | large_move].copy()
    flagged["reason"] = "large weekly move"
    flagged.loc[outside_range[flagged.index], "reason"] = "outside plausible range"
    columns = ["series_code", "week_start", "price_usd_per_gallon", "weekly_change_usd", "reason"]
    return flagged[columns].reset_index(drop=True)


def compare_series(
    nyserda_series: pd.Series, eia_series: pd.Series, offset_weeks: int
) -> dict[str, float]:
    """Compare two weekly series after shifting the EIA dates back by offset_weeks."""
    shifted_eia = eia_series.copy()
    shifted_eia.index = shifted_eia.index - pd.Timedelta(weeks=offset_weeks)
    paired = pd.concat({"nyserda": nyserda_series, "eia": shifted_eia}, axis=1).dropna()
    difference = paired["nyserda"] - paired["eia"]
    return {
        "weeks_compared": len(paired),
        "mean_difference_usd": round(difference.mean(), 4),
        "median_absolute_difference_usd": round(difference.abs().median(), 4),
        "max_absolute_difference_usd": round(difference.abs().max(), 4),
        "correlation": round(paired["nyserda"].corr(paired["eia"]), 5),
    }


def crosscheck_with_eia(
    panel: pd.DataFrame, eia_prices: pd.DataFrame, config: StudyConfig
) -> pd.DataFrame:
    """Compare the NYSERDA state average with EIA New York State and PADD 1B at several offsets.

    Only New York State at offset 0 is held to the tolerance in config; the other
    rows show how sensitive the agreement is to the week convention and the area.
    """
    tolerance = config.quality["eia_crosscheck"]
    state_average = (
        panel[panel["series_code"] == "new_york_state"]
        .set_index("week_start")["price_usd_per_gallon"]
        .dropna()
    )
    comparison_rows = []
    for eia_series_id in (EIA_NEW_YORK_STATE, EIA_PADD_1B):
        eia_series = eia_prices[eia_prices["series_id"] == eia_series_id]
        eia_by_week = eia_series.set_index("week_start")["price_usd_per_gallon"]
        for offset_weeks in ALIGNMENT_OFFSETS_WEEKS:
            comparison = compare_series(state_average, eia_by_week, offset_weeks)
            is_tested = eia_series_id == EIA_NEW_YORK_STATE and offset_weeks == 0
            within_tolerance = (
                comparison["median_absolute_difference_usd"]
                <= tolerance["max_median_absolute_difference_usd"]
                and comparison["correlation"] >= tolerance["min_correlation"]
            )
            comparison_rows.append(
                {
                    "nyserda_series": "new_york_state",
                    "eia_series_id": eia_series_id,
                    "eia_area": config.sources["eia_gasoline"]["series"][eia_series_id],
                    "offset_weeks": offset_weeks,
                    **comparison,
                    "held_to_tolerance": is_tested,
                    "within_tolerance": within_tolerance,
                }
            )
    return pd.DataFrame(comparison_rows)
