"""Draw every paper figure into results/figures/."""

from typing import Any

from cigd.config import StudyConfig
from cigd.figures.draw import FIGURES
from cigd.figures.style import apply_style
from cigd.logging import get_logger

logger = get_logger(__name__)


def draw_figures(config: StudyConfig) -> dict[str, Any]:
    """Draw each figure as PNG and PDF and return a stage summary."""
    apply_style()
    for draw in FIGURES:
        draw(config)
        logger.info("drew %s", draw.__name__.removeprefix("draw_"))
    return {"figures": len(FIGURES), "files": len(list(config.figures_dir.glob("*.p*")))}
