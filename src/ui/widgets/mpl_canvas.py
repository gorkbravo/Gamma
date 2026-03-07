from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtWidgets import QSizePolicy

from src.ui.plot_theme import TEXT_COLOR, apply_terminal_mpl_theme, style_axes, style_figure


class MplCanvas(FigureCanvas):
    def __init__(self, width: float = 5, height: float = 3, dpi: int = 160) -> None:
        apply_terminal_mpl_theme()
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super().__init__(fig)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(220)
        style_figure(self.figure)
        style_axes(self.axes)

    def clear_axes(self) -> None:
        self.axes.clear()
        style_axes(self.axes)

    def show_message(self, message: str) -> None:
        self.clear_axes()
        self.axes.text(0.5, 0.5, message, color=TEXT_COLOR, ha="center", va="center", transform=self.axes.transAxes)
        self.axes.set_xticks([])
        self.axes.set_yticks([])
        self.figure.tight_layout(pad=1.0)
        self.draw_idle()
