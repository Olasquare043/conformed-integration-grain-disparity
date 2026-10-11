"""Draw every paper figure into results/figures/."""

from typing import Any

from cigd.config import StudyConfig
from cigd.figures.concept_figure import draw_concept_figure
from cigd.figures.draw import FIGURES
from cigd.figures.paper_figures import PAPER_FIGURES
from cigd.figures.style import apply_style
from cigd.logging import get_logger

logger = get_logger(__name__)


def draw_figures(config: StudyConfig) -> dict[str, Any]:
    """Draw each figure as PNG and PDF and return a stage summary.

    The first set are the working figures shown in the notebooks; the paper figures and
    the concept figure are the journal-format versions. Both are kept.
    """
    apply_style()
    drawers = [*FIGURES, *PAPER_FIGURES, draw_concept_figure]
    for draw in drawers:
        draw(config)
        logger.info("drew %s", draw.__name__.removeprefix("draw_"))
    return {"figures": len(drawers), "files": len(list(config.figures_dir.glob("*.p*")))}
