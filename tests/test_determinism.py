"""Two smoke runs give identical model result tables (plan section 6)."""

import io
from collections.abc import Callable

import pandas as pd
import pytest

from cigd.config import StudyConfig
from cigd.experiments.coarse_task import run_coarse_task
from cigd.experiments.fine_task import run_fine_task


def as_csv_text(table: pd.DataFrame) -> str:
    """Render a table exactly as the experiments write it."""
    buffer = io.StringIO()
    table.to_csv(buffer, index=False, lineterminator="\n")
    return buffer.getvalue()


def run_coarse_tables(config: StudyConfig) -> dict[str, pd.DataFrame]:
    """Run the coarse experiment and return only its result tables."""
    tables, _ = run_coarse_task(config)
    return tables


@pytest.mark.parametrize("run_tables", [run_coarse_tables, run_fine_task], ids=["coarse", "fine"])
def test_rerunning_an_experiment_reproduces_its_tables(
    config: StudyConfig, run_tables: Callable[[StudyConfig], dict[str, pd.DataFrame]]
) -> None:
    # A full rerun takes hours, so the reproducibility check runs on the smoke profile.
    if config.profile != "smoke":
        pytest.skip("rerun check runs on the smoke profile")
    tables = run_tables(config)
    for name, table in tables.items():
        written = (config.tables_dir / f"{name}.csv").read_text(encoding="utf-8")
        assert as_csv_text(table) == written, name
