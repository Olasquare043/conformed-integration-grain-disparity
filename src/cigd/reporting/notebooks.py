"""Execute every notebook top to bottom and export it as HTML (the record of what ran)."""

from typing import Any

import papermill
from nbconvert import HTMLExporter

from cigd.config import REPOSITORY_ROOT, StudyConfig
from cigd.logging import get_logger

logger = get_logger(__name__)

NOTEBOOK_DIR = REPOSITORY_ROOT / "notebooks"
NOTEBOOKS = [
    "01_data_and_provenance",
    "02_warehouse_and_conformance",
    "03_integration_cost",
    "04_model_effect_fine_grain",
    "05_model_effect_coarse_grain",
]


def execute_notebooks(config: StudyConfig) -> dict[str, Any]:
    """Run each notebook headlessly; any error stops the stage. Write HTML to results/notebooks/."""
    executed_dir = config.derived_dir / "notebooks"
    html_dir = config.results_dir / "notebooks"
    executed_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)
    exporter = HTMLExporter()
    for name in NOTEBOOKS:
        executed_path = executed_dir / f"{name}.ipynb"
        papermill.execute_notebook(
            NOTEBOOK_DIR / f"{name}.ipynb",
            executed_path,
            parameters={"profile": config.profile},
            kernel_name="python3",
            progress_bar=False,
            cwd=str(REPOSITORY_ROOT),
        )
        html, _ = exporter.from_filename(str(executed_path))
        (html_dir / f"{name}.html").write_text(html, encoding="utf-8", newline="\n")
        logger.info("executed %s", name)
    return {"notebooks": len(NOTEBOOKS)}
