"""One figure style for the paper: palette, fonts, and how figures are saved."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from cigd.config import StudyConfig  # noqa: E402

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


def save_figure(figure: plt.Figure, name: str, config: StudyConfig) -> list[Path]:
    """Save a figure as PNG (300 dpi) and PDF in results/figures/, without timestamps."""
    config.figures_dir.mkdir(parents=True, exist_ok=True)
    paths = [config.figures_dir / f"{name}.png", config.figures_dir / f"{name}.pdf"]
    figure.savefig(paths[0], dpi=PNG_DPI, bbox_inches="tight", metadata={"Software": None})
    figure.savefig(paths[1], bbox_inches="tight", metadata={"CreationDate": None, "Producer": None})
    plt.close(figure)
    return paths
