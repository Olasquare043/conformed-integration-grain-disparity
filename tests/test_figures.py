"""The journal figures draw from the result tables and are saved at the required resolution."""

import shutil
from dataclasses import replace

import pandas as pd
import pytest
from PIL import Image

from cigd.config import StudyConfig
from cigd.figures.concept_figure import FIGURE_NAMES as CONCEPT_FIGURE_NAMES
from cigd.figures.concept_figure import draw_concept_figure, read_concept_numbers
from cigd.figures.paper_figures import FIGURE_NAMES as PAPER_FIGURE_NAMES
from cigd.figures.paper_figures import PAPER_FIGURES

REQUIRED_TABLES = [
    "integration_build_time_summary",
    "integration_table_storage",
    "integration_query_latency",
    "integration_grain_ratios",
    "integration_raw_storage",
    "fine_accuracy",
    "fine_comparisons",
    "coarse_comparisons",
    "profile_trip_months",
    "profile_price_series",
    "profile_weather",
    "warehouse_tables",
    "warehouse_trip_validity",
]


@pytest.fixture(scope="module")
def drawn_config(config: StudyConfig, tmp_path_factory: pytest.TempPathFactory) -> StudyConfig:
    """Copy the result tables to a scratch folder and draw every journal figure there."""
    if not all((config.tables_dir / f"{name}.csv").exists() for name in REQUIRED_TABLES):
        pytest.skip("result tables not built yet; run make experiments")
    scratch = tmp_path_factory.mktemp("figures")
    shutil.copytree(config.tables_dir, scratch / "tables")
    scratch_config = replace(config, results_dir=scratch)
    for draw in [*PAPER_FIGURES, draw_concept_figure]:
        draw(scratch_config)
    return scratch_config


def test_every_journal_figure_is_saved_as_png_and_pdf(drawn_config: StudyConfig) -> None:
    for name in [*PAPER_FIGURE_NAMES, *CONCEPT_FIGURE_NAMES]:
        for extension in ("png", "pdf"):
            assert (drawn_config.figures_dir / f"{name}.{extension}").stat().st_size > 0


def test_journal_pngs_are_300_dpi(drawn_config: StudyConfig) -> None:
    for name in [*PAPER_FIGURE_NAMES, *CONCEPT_FIGURE_NAMES]:
        with Image.open(drawn_config.figures_dir / f"{name}.png") as image:
            assert round(image.info["dpi"][0]) == 300


def test_concept_figure_numbers_come_from_the_tables(config: StudyConfig) -> None:
    if not all((config.tables_dir / f"{name}.csv").exists() for name in REQUIRED_TABLES):
        pytest.skip("result tables not built yet; run make experiments")
    numbers = read_concept_numbers(config)
    warehouse_tables = pd.read_csv(config.tables_dir / "warehouse_tables.csv").set_index("table")
    assert numbers.fact_trip_rows == warehouse_tables.loc["fact_trip", "rows"]
    assert numbers.validity_rules == 9
    lags = config.experiments["publication_lags"]
    assert numbers.trip_lag_months == lags["tlc_months_until_usable"]
