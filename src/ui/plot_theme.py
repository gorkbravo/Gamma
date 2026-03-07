from __future__ import annotations

from functools import lru_cache

import matplotlib as mpl
from matplotlib import font_manager as fm
from matplotlib.axes import Axes
from matplotlib.figure import Figure

FIGURE_BG = "#0d1117"
AXES_BG = "#161b22"
GRID_COLOR = "#1d3557"
TEXT_COLOR = "#e6edf3"
MUTED_TEXT = "#8ecbff"
COLOR_PRIMARY = "#58a6ff"
COLOR_POSITIVE = "#3fb950"
COLOR_NEGATIVE = "#f85149"
COLOR_BENCHMARK = "#ffb454"
COLOR_WARNING = "#d29922"
COLOR_RISK = "#ff7b72"


@lru_cache(maxsize=1)
def _resolve_mono_font() -> str:
    available = {entry.name for entry in fm.fontManager.ttflist}
    preferred = [
        "JetBrains Mono",
        "Cascadia Mono",
        "IBM Plex Mono",
        "Consolas",
        "Courier New",
        "DejaVu Sans Mono",
    ]
    for family in preferred:
        if family in available:
            return family
    # Matplotlib bundles DejaVu; this keeps a deterministic fallback.
    return "DejaVu Sans Mono"


def apply_terminal_mpl_theme() -> None:
    mono_font = _resolve_mono_font()
    mpl.rcParams.update(
        {
            "figure.facecolor": FIGURE_BG,
            "axes.facecolor": AXES_BG,
            "savefig.facecolor": FIGURE_BG,
            "savefig.edgecolor": FIGURE_BG,
            "font.family": mono_font,
            "font.size": 8,
            "axes.edgecolor": GRID_COLOR,
            "axes.labelcolor": TEXT_COLOR,
            "axes.titlecolor": TEXT_COLOR,
            "axes.titlesize": 9,
            "axes.labelsize": 8,
            "xtick.color": TEXT_COLOR,
            "ytick.color": TEXT_COLOR,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "grid.color": GRID_COLOR,
            "grid.alpha": 0.35,
            "grid.linewidth": 0.6,
            "lines.linewidth": 1.2,
            "figure.dpi": 160,
            "savefig.dpi": 160,
            "legend.facecolor": AXES_BG,
            "legend.edgecolor": GRID_COLOR,
            "legend.frameon": False,
            "legend.fontsize": 8,
            "text.color": TEXT_COLOR,
        }
    )


def style_figure(fig: Figure) -> None:
    fig.patch.set_facecolor(FIGURE_BG)
    fig.set_dpi(160)


def style_axes(ax: Axes) -> None:
    ax.set_facecolor(AXES_BG)
    ax.tick_params(colors=TEXT_COLOR, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(GRID_COLOR)
    ax.grid(True, color=GRID_COLOR, linewidth=0.6, alpha=0.35)
    ax.xaxis.label.set_color(TEXT_COLOR)
    ax.yaxis.label.set_color(TEXT_COLOR)
    ax.title.set_color(TEXT_COLOR)
