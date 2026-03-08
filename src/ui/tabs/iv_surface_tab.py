from __future__ import annotations

import logging

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.application.iv_service import IVService
from src.application.system_service import market_data_mode_label, normalize_market_data_mode
from src.application.workspace_service import (
    resolve_followed_symbol,
    should_auto_follow_research_symbol,
    should_enable_research_symbol_auto_follow,
)
from src.services.app_context import AppDataContext
from src.services.ibkr_client import IBKRClient
from src.ui.widgets.mpl_theme import AXES_BG, COLOR_WARNING, FIGURE_BG, GRID_COLOR, TEXT_COLOR


logger = logging.getLogger(__name__)


class IVSurfaceTab(QWidget):
    def __init__(
        self,
        client: IBKRClient,
        iv_service: IVService,
        market_data_mode: str = "delayed",
        app_context: AppDataContext | None = None,
    ) -> None:
        super().__init__()
        self.client = client
        self.iv_service = iv_service
        self.app_context = app_context
        self.market_data_mode = normalize_market_data_mode(market_data_mode)
        self._locked = False
        self._build_ui()

        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._refresh_plot)

        if self.app_context is not None:
            self.app_context.app_mode_changed.connect(self._on_context_mode_changed)
            self.app_context.research_scope_changed.connect(self._on_context_scope_changed)
            self._sync_auto_follow_default()

    def _build_ui(self) -> None:
        root = QVBoxLayout()
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)
        self.status_label = QLabel("Status: Idle")
        data_mode = market_data_mode_label(self.market_data_mode, self.client.mock)
        self.data_mode_label = QLabel(f"Data Mode: {data_mode}")
        self.symbol_input = QLineEdit("SPY")
        self.symbol_input.setMaximumWidth(120)
        self.auto_follow_check = QCheckBox("Auto-follow research symbol")
        self.auto_follow_check.setChecked(False)
        self.auto_follow_check.toggled.connect(self._on_auto_follow_toggled)
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.lock_btn = QPushButton("LOCK UPDATES")

        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        self.lock_btn.clicked.connect(self._toggle_lock)

        controls.addWidget(self.status_label)
        controls.addWidget(self.data_mode_label)
        controls.addWidget(QLabel("Ticker"))
        controls.addWidget(self.symbol_input)
        controls.addWidget(self.auto_follow_check)
        controls.addStretch()
        controls.addWidget(self.start_btn)
        controls.addWidget(self.stop_btn)
        controls.addWidget(self.lock_btn)
        root.addLayout(controls)

        charts_box = QGroupBox("Volatility Surface")
        charts_layout = QVBoxLayout()
        self.figure = Figure(figsize=(12, 6), dpi=120)
        self.figure.patch.set_facecolor(FIGURE_BG)
        gs = self.figure.add_gridspec(1, 3)
        self.ax_surface = self.figure.add_subplot(gs[0, :2], projection="3d")
        self.ax_skew = self.figure.add_subplot(gs[0, 2])
        self.canvas = FigureCanvas(self.figure)
        charts_layout.addWidget(self.canvas)
        charts_box.setLayout(charts_layout)
        root.addWidget(charts_box)

        messages_box = QGroupBox("Messages")
        messages_layout = QVBoxLayout()
        self.message_area = QPlainTextEdit()
        self.message_area.setReadOnly(True)
        self.message_area.setMaximumHeight(80)
        self.message_area.setStyleSheet(f"QPlainTextEdit {{ color: {COLOR_WARNING}; }}")
        messages_layout.addWidget(self.message_area)
        messages_box.setLayout(messages_layout)
        root.addWidget(messages_box)

        self.setLayout(root)
        self._draw_placeholder("Press Start to build IV surface")

    def set_market_data_mode(self, value: str) -> None:
        mode = normalize_market_data_mode(value)
        if mode == self.market_data_mode:
            return
        self.market_data_mode = mode
        self.iv_service.set_market_data_mode(mode)
        self.data_mode_label.setText(f"Data Mode: {market_data_mode_label(self.market_data_mode, self.client.mock)}")

    def _set_status(self, text: str) -> None:
        self.status_label.setText(f"Status: {text}")

    def shell_status_text(self) -> str:
        return self.status_label.text()

    def shell_active_symbol(self) -> str:
        return self.symbol_input.text().strip().upper() or "SPY"

    def _start(self) -> None:
        symbol = self.symbol_input.text().strip().upper() or "SPY"
        result = self.iv_service.start_stream_session(symbol)
        self._set_status(result.status)
        for message in result.messages:
            self._append_message(message)
        if result.success:
            self.timer.start()

    def _stop(self) -> None:
        self.timer.stop()
        self.iv_service.stop_stream()
        self._set_status("Stopped")
        self._draw_placeholder("Stopped")

    def _toggle_lock(self) -> None:
        self._locked = not self._locked
        self.lock_btn.setText("UNLOCK UPDATES" if self._locked else "LOCK UPDATES")

    def _append_message(self, message: str) -> None:
        text = str(message or "").strip()
        if not text:
            return
        current = self.message_area.toPlainText().strip()
        if current:
            self.message_area.setPlainText(current + "\n" + text)
        else:
            self.message_area.setPlainText(text)

    def _draw_placeholder(self, message: str) -> None:
        self.ax_surface.clear()
        self.ax_skew.clear()
        self.ax_surface.set_facecolor(FIGURE_BG)
        self.ax_skew.set_facecolor(AXES_BG)
        self.ax_surface.text2D(0.4, 0.5, message, transform=self.ax_surface.transAxes, color=TEXT_COLOR)
        self.ax_skew.text(0.3, 0.5, message, transform=self.ax_skew.transAxes, color=TEXT_COLOR)
        self.ax_surface.set_xticks([])
        self.ax_surface.set_yticks([])
        self.ax_surface.set_zticks([])
        self.ax_skew.set_xticks([])
        self.ax_skew.set_yticks([])
        self.canvas.draw_idle()

    def _refresh_plot(self) -> None:
        for message in self.iv_service.drain_messages():
            self._append_message(message)
        self._set_status(self.iv_service.status_text())

        if self._locked:
            return
        snap = self.iv_service.latest_snapshot()
        if snap is None:
            return

        X, Y_idx = np.meshgrid(snap.strikes, np.arange(len(snap.expiries)))
        Z = snap.iv_grid
        curr_elev, curr_azim = self.ax_surface.elev, self.ax_surface.azim
        mode_tag = "DELAYED" if snap.delayed else "LIVE"

        self.ax_surface.clear()
        self.ax_surface.set_facecolor(FIGURE_BG)
        self.ax_surface.plot_surface(X, Y_idx, Z, cmap="magma", edgecolor="white", linewidth=0.1, alpha=0.9)
        self.ax_surface.set_title(f"IV SURFACE | {snap.symbol} | {mode_tag}", color=TEXT_COLOR)
        self.ax_surface.set_yticks(np.arange(len(snap.expiries)))
        self.ax_surface.set_yticklabels(snap.expiries, fontsize=8, color=TEXT_COLOR)
        self.ax_surface.tick_params(axis="x", colors=TEXT_COLOR)
        self.ax_surface.tick_params(axis="z", colors=TEXT_COLOR)
        self.ax_surface.view_init(elev=curr_elev, azim=curr_azim)

        self.ax_skew.clear()
        self.ax_skew.set_facecolor(AXES_BG)
        skew = Z[0, :]
        self.ax_skew.plot(snap.strikes, skew, marker="o", color="#00f2ff")
        self.ax_skew.axvline(x=snap.spot, color="#ff3e3e", linestyle="--")
        self.ax_skew.set_title(f"FRONT-MONTH SKEW: {snap.expiries[0]} ({mode_tag})", color=TEXT_COLOR)
        self.ax_skew.tick_params(colors=TEXT_COLOR)
        for spine in self.ax_skew.spines.values():
            spine.set_color(GRID_COLOR)
        self.ax_skew.grid(True, color=GRID_COLOR, linewidth=0.6, alpha=0.5)

        self.canvas.draw_idle()

    def _on_context_mode_changed(self, _mode: str) -> None:
        self._sync_auto_follow_default()

    def _on_context_scope_changed(self) -> None:
        self._sync_auto_follow_default()
        self._sync_symbol_from_context(restart_running=True)

    def _on_auto_follow_toggled(self, _checked: bool) -> None:
        self._sync_symbol_from_context(restart_running=True)

    def _sync_auto_follow_default(self) -> None:
        if self.app_context is None:
            return
        should_enable = should_enable_research_symbol_auto_follow(
            self.app_context.app_mode,
            self.app_context.research_scope_type,
        )
        if should_enable and not self.auto_follow_check.isChecked():
            self.auto_follow_check.setChecked(True)
        elif not should_enable and self.auto_follow_check.isChecked():
            self.auto_follow_check.setChecked(False)

    def _sync_symbol_from_context(self, restart_running: bool) -> None:
        if self.app_context is None:
            return
        follow = should_auto_follow_research_symbol(
            self.app_context.app_mode,
            self.app_context.research_scope_type,
            self.auto_follow_check.isChecked(),
        )
        symbol = resolve_followed_symbol(
            self.app_context.primary_symbol,
            self.symbol_input.text(),
            follow,
        )
        if symbol is None:
            return
        self.symbol_input.setText(symbol)
        if restart_running and self.iv_service.is_running():
            self.timer.stop()
            result = self.iv_service.start_stream_session(symbol)
            self._set_status(result.status)
            for message in result.messages:
                self._append_message(message)
            if result.success:
                self.timer.start()
            else:
                self._append_message("Unable to restart IV surface after symbol auto-follow update.")

    def closeEvent(self, event) -> None:
        try:
            self.timer.stop()
            self.iv_service.stop_stream()
        except Exception:
            logger.exception("IV surface tab shutdown failed")
        event.accept()
