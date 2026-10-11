"""One figure style for the paper: palette, fonts, and how figures are saved."""

from functools import cache
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from cigd.config import StudyConfig  # noqa: E402
from cigd.logging import get_logger  # noqa: E402

logger = get_logger(__name__)

# Validated categorical slots 1 and 2 (they also pass when every pair is compared).
PRIMARY_COLOR = "#2a78d6"
SECONDARY_COLOR = "#eb6834"
NEUTRAL_COLOR = "#8c8b86"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID_COLOR = "#e4e3df"
INFORMATION_SET_COLORS = {"primary": PRIMARY_COLOR, "secondary": SECONDARY_COLOR}
INFORMATION_SET_LABELS = {
    "primary": "Primary (realistic lags)",
    "secondary": "Secondary (best case)",
}
PNG_DPI = 300
# The journal figures use TeX Gyre Heros (a Helvetica look-alike). The Docker image
# installs it from the Debian package fonts-texgyre; elsewhere the figures fall back
# to DejaVu Sans, which has the same glyphs.
TEX_GYRE_DIRECTORY = Path("/usr/share/texmf/fonts/opentype/public/tex-gyre")
TEX_GYRE_FILES = ("texgyreheros-regular.otf", "texgyreheros-bold.otf", "texgyreheros-italic.otf")
TEX_GYRE_FAMILY = "TeX Gyre Heros"
FALLBACK_FAMILY = "DejaVu Sans"


@cache
def journal_font_family() -> str:
    """Return TeX Gyre Heros if all three styles are installed, otherwise DejaVu Sans."""
    font_paths = [TEX_GYRE_DIRECTORY / name for name in TEX_GYRE_FILES]
    if not all(path.exists() for path in font_paths):
        logger.warning(
            "%s is not installed; journal figures use %s", TEX_GYRE_FAMILY, FALLBACK_FAMILY
        )
        return FALLBACK_FAMILY
    for path in font_paths:
        font_manager.fontManager.addfont(str(path))
    return TEX_GYRE_FAMILY


def apply_style() -> None:
    """Set the shared Matplotlib style: a fixed font, quiet axes and a light grid."""
    plt.rcParams.update(
        {
            # A fixed font keeps figures identical between machines.
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.edgecolor": TEXT_SECONDARY,
            "axes.labelcolor": TEXT_PRIMARY,
            "axes.titlesize": 10,
            "axes.titleweight": "bold",
            "axes.titlecolor": TEXT_PRIMARY,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": GRID_COLOR,
            "grid.linewidth": 0.6,
            "xtick.color": TEXT_SECONDARY,
            "ytick.color": TEXT_SECONDARY,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "lines.linewidth": 2,
            "svg.hashsalt": "cigd",
        }
    )


def save_figure(
    figure: plt.Figure, name: str, config: StudyConfig, tight: bool = True, pad_inches: float = 0.1
) -> list[Path]:
    """Save a figure as PNG (300 dpi) and PDF in results/figures/, without timestamps.

    tight crops to the content; a full-bleed drawing passes tight=False to keep its size.
    """
    config.figures_dir.mkdir(parents=True, exist_ok=True)
    paths = [config.figures_dir / f"{name}.png", config.figures_dir / f"{name}.pdf"]
    crop = {"bbox_inches": "tight", "pad_inches": pad_inches} if tight else {}
    figure.savefig(paths[0], dpi=PNG_DPI, metadata={"Software": None}, **crop)
    figure.savefig(paths[1], metadata={"CreationDate": None, "Producer": None}, **crop)
    plt.close(figure)
    return paths
