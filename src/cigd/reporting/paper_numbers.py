"""Write results/paper_numbers.json: every number the paper quotes, read from the outputs.

Nothing here computes a result; it only collects values that the experiments,
the profile, the manifest and the evidence files already hold, so the paper never
contains a hand-typed number. Timings depend on the machine and are kept apart
under "machine_dependent".
"""

import json
from typing import Any

import pandas as pd

from cigd.config import REPOSITORY_ROOT, StudyConfig
from cigd.ingest.manifest import read_manifest

DECIMALS = 6
EVIDENCE_DIR = REPOSITORY_ROOT / "docs" / "evidence"


def rounded(value: Any) -> Any:
    """Round floats so reruns compare equal; leave other values as they are."""
    if isinstance(value, float):
        return round(value, DECIMALS)
    if hasattr(value, "item"):
        return rounded(value.item())
    return value


def records(table: pd.DataFrame) -> list[dict[str, Any]]:
    """Turn a table into a list of rounded records."""
    return [{key: rounded(value) for key, value in row.items()} for row in table.to_dict("records")]


def read_table(config: StudyConfig, name: str) -> pd.DataFrame:
    """Read one result table."""
    return pd.read_csv(config.tables_dir / f"{name}.csv")


def data_numbers(config: StudyConfig) -> dict[str, Any]:
    """Sizes of every source and the data quality checks."""
    manifest = pd.DataFrame(
        [vars(record) for record in read_manifest(config.manifest_path).values()]
    )
    history = manifest[manifest["stored_locally"] == "aggregate_only"]
    trip_months = read_table(config, "profile_trip_months")
    price_series = read_table(config, "profile_price_series")
    level_check = read_table(config, "profile_eia_crosscheck")
    change_check = read_table(config, "profile_eia_change_check").iloc[0]
    tested_level = level_check[level_check["held_to_tolerance"]].iloc[0]
    return {
        "published_trips_fact_window": int(trip_months["trip_rows"].sum()),
        "fact_window_months": len(trip_months),
        "published_trips_history_months": int(history["row_count"].sum()),
        "history_months": len(history),
        "history_bytes_streamed": int(history["size_bytes"].sum()),
        "price_series": len(price_series),
        "price_weeks_expected": int(price_series["weeks_expected"].max()),
        "price_series_weeks_missing": len(read_table(config, "profile_price_missing_weeks")),
        "prices_flagged": len(read_table(config, "profile_price_outliers")),
        "eia_level_median_absolute_difference_usd": rounded(
            tested_level["median_absolute_difference_usd"]
        ),
        "eia_level_correlation": rounded(tested_level["correlation"]),
        "eia_level_within_tolerance": bool(tested_level["within_tolerance"]),
        "eia_change_correlation": rounded(change_check["change_correlation"]),
        "eia_mean_level_bias_usd": rounded(change_check["mean_level_bias_usd"]),
        "eia_change_within_tolerance": bool(change_check["within_tolerance"]),
    }


def validity_numbers(config: StudyConfig) -> list[dict[str, Any]]:
    """Trips failing and removed by each validity rule, per year."""
    return records(read_table(config, "warehouse_trip_validity"))


def warehouse_numbers(config: StudyConfig) -> dict[str, Any]:
    """Row counts of every warehouse table and the grain ratios."""
    tables = read_table(config, "warehouse_tables")
    ratios = read_table(config, "integration_grain_ratios")
    return {
        "rows_by_table": {row["table"]: int(row["rows"]) for row in tables.to_dict("records")},
        "grain": dict(zip(ratios["measure"], map(rounded, ratios["value"]), strict=True)),
    }


def evidence_numbers() -> dict[str, Any]:
    """Summaries of the publication-lag evidence in docs/evidence/."""
    tlc = pd.read_csv(EVIDENCE_DIR / "tlc_release_dates.csv", parse_dates=["released_by"])
    month_end = pd.to_datetime(tlc["month"]) + pd.offsets.MonthEnd(0)
    release_days = (tlc["released_by"] - month_end).dt.days
    nyserda = pd.read_csv(EVIDENCE_DIR / "nyserda_release_dates.csv")
    exports = nyserda[nyserda["kind"] == "export"]
    return {
        "tlc_months_checked": len(tlc),
        "tlc_median_days_to_release": rounded(float(release_days.median())),
        "tlc_max_days_to_release": int(release_days.max()),
        "tlc_months_late_under_m_plus_3": int((tlc["rule_m_plus_3"] != "released in time").sum()),
        "tlc_months_late_under_m_plus_4": int((tlc["rule_m_plus_4"] != "released in time").sum()),
        "nyserda_archived_exports": len(exports),
    }


def coarse_numbers(config: StudyConfig) -> dict[str, Any]:
    """Coarse-grain accuracy, comparisons, penalties and skipped forecasts."""
    accuracy = read_table(config, "coarse_accuracy")
    pooled = accuracy[accuracy["scope"] == "all_regions"]
    alphas = read_table(config, "coarse_ridge_alphas")
    return {
        "pooled_accuracy": records(pooled),
        "comparisons": records(read_table(config, "coarse_comparisons")),
        "regions_beating_random_walk": records(read_table(config, "coarse_region_wins")),
        "ridge_alphas_chosen": records(
            alphas[alphas["chosen"]][["information_set", "rung", "alpha"]]
        ),
        "skipped_forecasts": records(read_table(config, "coarse_skipped_forecasts")),
    }


def fine_numbers(config: StudyConfig) -> dict[str, Any]:
    """Fine-grain accuracy and comparisons."""
    return {
        "accuracy": records(read_table(config, "fine_accuracy")),
        "comparisons": records(read_table(config, "fine_comparisons")),
        "origins": records(read_table(config, "fine_origins")),
    }


def machine_dependent_numbers(config: StudyConfig) -> dict[str, Any]:
    """Timings and storage, which change with the machine and the run."""
    build = read_table(config, "integration_build_time_summary")
    latency = read_table(config, "integration_query_latency")
    storage = read_table(config, "integration_table_storage")
    return {
        "build_seconds_by_step": records(build),
        "query_latency": records(latency),
        "latency_aggregate_builds": records(
            read_table(config, "integration_latency_aggregate_builds")
        ),
        "table_storage_bytes": records(storage),
    }


def write_paper_numbers(config: StudyConfig) -> dict[str, Any]:
    """Collect every paper number and write results/paper_numbers.json."""
    numbers = {
        "profile": config.profile,
        "data": data_numbers(config),
        "trip_validity": validity_numbers(config),
        "warehouse": warehouse_numbers(config),
        "publication_lag_evidence": evidence_numbers(),
        "coarse_task": coarse_numbers(config),
        "fine_task": fine_numbers(config),
        "machine_dependent": machine_dependent_numbers(config),
    }
    path = config.results_dir / "paper_numbers.json"
    path.write_text(json.dumps(numbers, indent=2) + "\n", encoding="utf-8", newline="\n")
    return {"sections": len(numbers) - 1, "path": path.relative_to(REPOSITORY_ROOT).as_posix()}
