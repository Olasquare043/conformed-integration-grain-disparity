"""Run the experiments and write their result tables and forecasts."""

from collections.abc import Callable
from typing import Any

import pandas as pd

from cigd.config import StudyConfig
from cigd.experiments.coarse_task import coarse_summary, run_coarse_task
from cigd.experiments.fine_task import fine_summary, run_fine_task
from cigd.experiments.integration_cost import integration_summary, run_integration_cost
from cigd.logging import get_logger

logger = get_logger(__name__)

EXPERIMENT_NAMES = ("integration_cost", "coarse", "fine")


def write_tables(tables: dict[str, pd.DataFrame], config: StudyConfig) -> None:
    """Write each result table to results/tables/ as CSV with LF line endings."""
    config.tables_dir.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(config.tables_dir / f"{name}.csv", index=False, lineterminator="\n")


def write_forecasts(forecasts: pd.DataFrame, name: str, config: StudyConfig) -> None:
    """Keep every forecast as Parquet next to the warehouse (too large for results/)."""
    folder = config.derived_dir / "experiments"
    folder.mkdir(parents=True, exist_ok=True)
    forecasts.to_parquet(folder / f"{name}.parquet", index=False)


def run_integration(config: StudyConfig) -> dict[str, Any]:
    """Run experiment A and write its tables."""
    tables = run_integration_cost(config)
    write_tables(tables, config)
    return integration_summary(tables)


def run_coarse(config: StudyConfig) -> dict[str, Any]:
    """Run the coarse-grain experiment and write its tables and forecasts."""
    tables, forecasts = run_coarse_task(config)
    write_tables(tables, config)
    write_forecasts(forecasts, "coarse_forecasts", config)
    return coarse_summary(tables)


def run_fine(config: StudyConfig) -> dict[str, Any]:
    """Run the fine-grain experiment and write its tables and predictions."""
    tables = run_fine_task(config)
    write_tables(tables, config)
    return fine_summary(tables)


EXPERIMENTS: dict[str, Callable[[StudyConfig], dict[str, Any]]] = {
    "integration_cost": run_integration,
    "coarse": run_coarse,
    "fine": run_fine,
}


def run_experiments(config: StudyConfig, selected: str | None) -> dict[str, Any]:
    """Run the selected experiment, or all of them in order, and return a stage summary."""
    summary: dict[str, Any] = {}
    for name in [selected] if selected else EXPERIMENT_NAMES:
        logger.info("experiment %s", name)
        summary.update(EXPERIMENTS[name](config))
    return summary
