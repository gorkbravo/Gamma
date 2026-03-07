from __future__ import annotations

import logging
import os
import time
from collections import Counter
from typing import Optional

import matplotlib.dates as mdates
import pandas as pd
from ib_insync import Contract
from PySide6.QtCore import QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QPlainTextEdit,
)

from src.analytics.returns import align_prices, compute_returns
from src.analytics.risk_metrics import compute_weights, portfolio_returns
from src.models.portfolio import PortfolioSnapshot
from src.services.ibkr_client import IBKRClient
from src.services.fx import FXService
from src.services.market_data import MarketDataService
from src.services.portfolio_history_store import PortfolioHistoryStore
from src.ui.plot_theme import (
    COLOR_BENCHMARK,
    COLOR_NEGATIVE,
    COLOR_PRIMARY,
    COLOR_POSITIVE,
    COLOR_WARNING,
    MUTED_TEXT,
    TEXT_COLOR,
)
from src.ui.widgets.mpl_canvas import MplCanvas
from src.ui.widgets.worker import Worker
from src.utils.time import format_ts, now_utc


logger = logging.getLogger(__name__)


class OverviewTab(QWidget):
    snapshot_updated = Signal(object)
    market_data_mode_changed = Signal(str)
    connection_state_changed = Signal(str, str, bool)

    def __init__(
        self,
        client: IBKRClient,
        market_data: MarketDataService,
        fx_service: FXService,
        history_store: PortfolioHistoryStore,
        base_currency: str,
        market_data_mode: str = "delayed",
        auto_refresh_seconds: int = 0,
        quote_timeout_seconds: float = 2.0,
    ) -> None:
        super().__init__()
        self.client = client
        self.market_data = market_data
        self.fx_service = fx_service
        self.history_store = history_store
        self.base_currency = base_currency
        self.market_data_mode = self._normalize_market_data_mode(market_data_mode)
        self.thread_pool = QThreadPool()
        self.auto_refresh_seconds = auto_refresh_seconds
        self.quote_timeout_seconds = quote_timeout_seconds
        self._perf_returns = pd.Series(dtype=float)
        self._perf_cum = pd.Series(dtype=float)
        self._benchmark_cum = pd.Series(dtype=float)
        self._perf_base_value: float | None = None
        self._perf_lookback_days = 504
        self._perf_task_id = 0
        self._latest_snapshot: PortfolioSnapshot | None = None
        self._refresh_started_at: float | None = None
        self._last_refresh_duration_ms: float | None = None
        self._last_warning_categories: Counter[str] = Counter()
        self._last_warning_count = 0
        self._last_positions_count = 0
        self._last_missing_history: list[str] = []
        self._last_benchmark_source = "none"
        self._last_benchmark_symbol = os.getenv("BENCHMARK_TICKER", "SPY").strip().upper() or "SPY"
        self._last_day_pnl_source = "none"
        self._connection_action_label = "Connect to IBKR"
        self._connection_action_enabled = not self.client.mock

        self._build_ui()
        self._set_status("Disconnected")

        self.timer = QTimer(self)
        if auto_refresh_seconds and auto_refresh_seconds > 0:
            self.timer.setInterval(auto_refresh_seconds * 1000)
            self.timer.timeout.connect(self.refresh)

        self.connection_timer = QTimer(self)
        self.connection_timer.setInterval(5000)
        self.connection_timer.timeout.connect(self._check_connection)
        self.connect_watchdog = QTimer(self)
        self.connect_watchdog.setSingleShot(True)
        self.connect_watchdog.setInterval(15000)
        self.connect_watchdog.timeout.connect(self._connect_timeout)

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout()

        top_row = QHBoxLayout()
        self.status_label = QLabel("Status: Disconnected")
        mode_text = "Mock" if self.client.mock else "Live"
        self.data_mode_label = QLabel(f"Data Mode: {mode_text}")
        self.quote_mode_combo = QComboBox()
        self.quote_mode_combo.addItems(["Snapshot", "Stream"])
        self.quote_mode_combo.setCurrentText("Snapshot")
        model = self.quote_mode_combo.model()
        item = model.item(1)
        if item is not None:
            item.setEnabled(False)
        self.quote_mode_combo.setToolTip("Snapshot only (streaming disabled for now)")
        self.market_data_mode_combo = QComboBox()
        self.market_data_mode_combo.addItems(["Delayed", "Live"])
        self.market_data_mode_combo.setCurrentText("Live" if self.market_data_mode == "live" else "Delayed")
        self.market_data_mode_combo.currentTextChanged.connect(self._on_market_data_mode_combo_changed)
        self.market_data_mode_combo.setToolTip("Global market data mode for quotes and IV surface")
        if self.client.mock:
            self.market_data_mode_combo.setEnabled(False)
            self.market_data_mode_combo.setToolTip("Market data mode is fixed in mock mode")
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        self.last_refresh = QLabel("Last Update: N/A")
        top_row.addWidget(self.status_label)
        top_row.addWidget(self.data_mode_label)
        top_row.addWidget(QLabel("Quote Mode"))
        top_row.addWidget(self.quote_mode_combo)
        top_row.addWidget(QLabel("Mkt Data"))
        top_row.addWidget(self.market_data_mode_combo)
        top_row.addStretch()
        top_row.addWidget(self.refresh_btn)
        top_row.addWidget(self.last_refresh)
        root_layout.addLayout(top_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        layout = QVBoxLayout()

        summary_box = QGroupBox("Summary")
        summary_layout = QGridLayout()

        def _metric_cell(title: str, value: QLabel, row: int, col: int) -> None:
            title_label = QLabel(title)
            title_label.setObjectName("kpiTitle")
            value.setObjectName("kpiValue")
            value.setText("N/A")
            cell = QVBoxLayout()
            cell.addWidget(title_label)
            cell.addWidget(value)
            summary_layout.addLayout(cell, row, col)

        self.nlv_label = QLabel()
        self.market_value_label = QLabel()
        self.cash_label = QLabel()
        self.pnl_label = QLabel()
        _metric_cell("NET LIQ", self.nlv_label, 0, 0)
        _metric_cell("MARKET VALUE", self.market_value_label, 0, 1)
        _metric_cell("CASH", self.cash_label, 0, 2)
        _metric_cell("DAY P&L", self.pnl_label, 0, 3)
        summary_box.setLayout(summary_layout)
        layout.addWidget(summary_box)

        positions_box = QGroupBox("Positions")
        positions_layout = QVBoxLayout()
        self.table = QTableWidget(0, 9)
        self.table.setObjectName("positionsTable")
        self.table.setHorizontalHeaderLabels(
            [
                "Symbol",
                "SecType",
                "Currency",
                "Qty",
                "Avg Cost",
                "Last",
                "Mkt Value",
                "Unreal. P&L",
                "% Weight",
            ]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(180)
        positions_layout.addWidget(self.table)
        positions_box.setLayout(positions_layout)
        layout.addWidget(positions_box)

        charts_box = QGroupBox("Portfolio Charts")
        charts_layout = QGridLayout()

        composition_layout = QVBoxLayout()
        composition_title = QLabel("Portfolio Composition")
        composition_title.setObjectName("chartSectionLabel")
        composition_layout.addWidget(composition_title)
        self.weights_canvas = MplCanvas(width=5, height=3)
        self.weights_canvas.setMinimumHeight(280)
        composition_layout.addWidget(self.weights_canvas)

        perf_layout = QVBoxLayout()
        perf_title = QLabel("Portfolio Performance")
        perf_title.setObjectName("chartSectionLabel")
        perf_layout.addWidget(perf_title)
        perf_controls = QHBoxLayout()
        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(["1M", "3M", "6M", "1Y", "MAX"])
        self.timeframe_combo.setCurrentText("1Y")
        self.timeframe_combo.currentTextChanged.connect(self._update_performance_chart)
        self.benchmark_input = QLineEdit(self._last_benchmark_symbol)
        self.benchmark_input.setMaximumWidth(90)
        self.benchmark_input.setPlaceholderText("SPY")
        self.benchmark_input.editingFinished.connect(self._reload_benchmark)
        self.benchmark_check = QCheckBox("Show Benchmark")
        self.benchmark_check.setChecked(False)
        self.benchmark_check.stateChanged.connect(self._update_performance_chart)
        perf_controls.addWidget(QLabel("Timeframe"))
        perf_controls.addWidget(self.timeframe_combo)
        perf_controls.addWidget(QLabel("Benchmark"))
        perf_controls.addWidget(self.benchmark_input)
        perf_controls.addWidget(self.benchmark_check)
        perf_controls.addStretch()
        perf_layout.addLayout(perf_controls)
        self.performance_canvas = MplCanvas(width=5, height=3)
        self.performance_canvas.setMinimumHeight(280)
        perf_layout.addWidget(self.performance_canvas)

        charts_layout.addLayout(composition_layout, 0, 0)
        charts_layout.addLayout(perf_layout, 0, 1)
        charts_layout.setColumnStretch(0, 1)
        charts_layout.setColumnStretch(1, 1)
        charts_box.setLayout(charts_layout)
        layout.addWidget(charts_box)

        self.message_area = QPlainTextEdit()
        self.message_area.setObjectName("warningLog")
        self.message_area.setReadOnly(True)
        self.message_area.setFixedHeight(84)
        self.message_area.setStyleSheet(f"QPlainTextEdit#warningLog {{ color: {COLOR_WARNING}; }}")
        layout.addWidget(self.message_area)

        self.diagnostics_box = QGroupBox("Diagnostics")
        self._diagnostics_expanded = False
        diagnostics_layout = QVBoxLayout()
        diagnostics_header = QHBoxLayout()
        self.toggle_diag_btn = QPushButton("Show Diagnostics")
        self.toggle_diag_btn.clicked.connect(self._toggle_diagnostics)
        diagnostics_header.addWidget(self.toggle_diag_btn)
        diagnostics_header.addStretch()
        diagnostics_layout.addLayout(diagnostics_header)

        self.diagnostics_body = QWidget()
        diagnostics_body_layout = QVBoxLayout()
        diagnostics_controls = QHBoxLayout()
        self.run_diag_btn = QPushButton("Run Diagnostics")
        self.run_diag_btn.clicked.connect(self._run_diagnostics)
        self.force_subscribe_btn = QPushButton("Force Account Subscribe")
        self.force_subscribe_btn.clicked.connect(self._force_account_subscribe)
        self.refresh_errors_btn = QPushButton("Refresh IB Errors")
        self.refresh_errors_btn.clicked.connect(self._refresh_error_view)
        self.copy_diag_btn = QPushButton("Copy Diagnostics")
        self.copy_diag_btn.clicked.connect(self._copy_diagnostics)
        self.clear_history_btn = QPushButton("Clear History")
        self.clear_history_btn.clicked.connect(self._clear_history)
        diagnostics_controls.addWidget(self.run_diag_btn)
        diagnostics_controls.addWidget(self.force_subscribe_btn)
        diagnostics_controls.addWidget(self.refresh_errors_btn)
        diagnostics_controls.addWidget(self.copy_diag_btn)
        diagnostics_controls.addWidget(self.clear_history_btn)
        diagnostics_controls.addStretch()
        diagnostics_body_layout.addLayout(diagnostics_controls)

        self.diagnostics_details = QWidget()
        details_layout = QVBoxLayout()
        self.diagnostics_log_label = QLabel("Diagnostics Log")
        details_layout.addWidget(self.diagnostics_log_label)
        self.diagnostics_log = QPlainTextEdit()
        self.diagnostics_log.setObjectName("diagnosticsLog")
        self.diagnostics_log.setReadOnly(True)
        self.diagnostics_log.setMaximumHeight(130)
        details_layout.addWidget(self.diagnostics_log)
        self.ib_error_label = QLabel("Last IB Errors")
        details_layout.addWidget(self.ib_error_label)
        self.ib_error_log = QPlainTextEdit()
        self.ib_error_log.setObjectName("ibErrorLog")
        self.ib_error_log.setReadOnly(True)
        self.ib_error_log.setMaximumHeight(120)
        details_layout.addWidget(self.ib_error_log)
        self.diagnostics_details.setLayout(details_layout)
        diagnostics_body_layout.addWidget(self.diagnostics_details)
        self.diagnostics_body.setLayout(diagnostics_body_layout)
        diagnostics_layout.addWidget(self.diagnostics_body)
        self.diagnostics_box.setLayout(diagnostics_layout)
        layout.addWidget(self.diagnostics_box)

        content.setLayout(layout)
        self.scroll.setWidget(content)
        root_layout.addWidget(self.scroll)
        self.setLayout(root_layout)

        self.weights_canvas.show_message("Waiting for data")
        self.performance_canvas.show_message("Waiting for data")
        self._on_diagnostics_toggled(False)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(f"Status: {text}")
        self._emit_connection_state()

    def _set_connection_action(self, text: str, enabled: bool | None = None) -> None:
        self._connection_action_label = text
        if enabled is not None:
            self._connection_action_enabled = enabled
        self._emit_connection_state()

    def _emit_connection_state(self) -> None:
        self.connection_state_changed.emit(
            self.connection_status_text(),
            self.connection_action_text(),
            self.connection_action_enabled(),
        )

    def connection_status_text(self) -> str:
        return self.status_label.text()

    def connection_action_text(self) -> str:
        return self._connection_action_label

    def connection_action_enabled(self) -> bool:
        return self._connection_action_enabled

    def set_mock_mode_ui(self) -> None:
        self._set_status("Mock")
        self._set_connection_action("Mock Mode", False)

    @staticmethod
    def _normalize_market_data_mode(value: str | None) -> str:
        mode = str(value or "").strip().lower()
        if mode in {"delayed", "live", "auto"}:
            return mode
        return "delayed"

    def _on_market_data_mode_combo_changed(self, text: str) -> None:
        mode = "live" if str(text).strip().lower() == "live" else "delayed"
        if mode == self.market_data_mode:
            return
        self.market_data_mode = mode
        self.market_data_mode_changed.emit(mode)

    def toggle_connection(self) -> None:
        if self.client.is_connected():
            self.client.disconnect()
            self._set_status("Disconnected")
            self._set_connection_action("Connect to IBKR", not self.client.mock)
            if self.timer.isActive():
                self.timer.stop()
            if self.connection_timer.isActive():
                self.connection_timer.stop()
            return

        self._set_status("Connecting")
        self._set_connection_action("Connecting...", False)
        self.connect_watchdog.start()
        worker = Worker(self.client.connect)
        worker.signals.finished.connect(self._on_connected)
        worker.signals.error.connect(self._on_error)
        self.thread_pool.start(worker)

    def _on_connected(self, success: bool) -> None:
        if self.connect_watchdog.isActive():
            self.connect_watchdog.stop()
        if success:
            active_account = self.client.active_account or self.client.account
            if active_account:
                self._set_status(f"Connected ({active_account})")
            else:
                self._set_status("Connected")
            self._set_connection_action("Disconnect", True)
            if self.auto_refresh_seconds and self.auto_refresh_seconds > 0:
                self.timer.start()
            self.connection_timer.start()
            self.refresh()
        else:
            self._set_status("Error")
            self._set_connection_action("Connect to IBKR", not self.client.mock)
            self._add_message("Connection failed")

    def refresh(self) -> None:
        if not self.client.is_connected() and not self.client.mock:
            self._add_message("Not connected")
            self._set_status("Disconnected")
            return
        self._refresh_started_at = time.perf_counter()
        self.last_refresh.setText("Last Update: Updating...")
        quote_mode = self.quote_mode_combo.currentText()
        worker = Worker(
            self.client.fetch_snapshot,
            self.base_currency,
            self.fx_service,
            self.market_data,
            quote_mode,
            self.quote_timeout_seconds,
        )
        worker.signals.finished.connect(self._on_snapshot)
        worker.signals.error.connect(self._on_error)
        self.thread_pool.start(worker)

    def _on_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        if self._refresh_started_at is not None:
            self._last_refresh_duration_ms = max(0.0, (time.perf_counter() - self._refresh_started_at) * 1000.0)
            self._refresh_started_at = None
        self._latest_snapshot = snapshot
        self.last_refresh.setText(f"Last Update: {format_ts(snapshot.timestamp)}")
        if snapshot.net_liquidation is not None:
            self.nlv_label.setText(f"{snapshot.net_liquidation:,.2f} {snapshot.base_currency}")
        else:
            self.nlv_label.setText("N/A")
        if snapshot.total_market_value is not None:
            self.market_value_label.setText(f"{snapshot.total_market_value:,.2f} {snapshot.base_currency}")
        else:
            self.market_value_label.setText("N/A")
        if snapshot.total_cash is not None:
            self.cash_label.setText(f"{snapshot.total_cash:,.2f} {snapshot.base_currency}")
        else:
            self.cash_label.setText("N/A")
        self._set_day_pnl(snapshot.day_pnl, snapshot.day_pnl_pct, snapshot.day_pnl_source)
        self._last_positions_count = len(snapshot.positions)

        self.history_store.append_snapshot(
            snapshot.timestamp,
            snapshot.net_liquidation,
            snapshot.total_market_value,
            snapshot.total_cash,
            snapshot.base_currency,
        )

        self._populate_table(snapshot)
        self._plot_weights(snapshot)
        self._start_performance_load(snapshot)
        self._show_warnings(snapshot)
        self.snapshot_updated.emit(snapshot)

    def _populate_table(self, snapshot: PortfolioSnapshot) -> None:
        self.table.setRowCount(0)
        def sort_rank(sec_type: str) -> int:
            st = (sec_type or "").upper()
            if st == "STK":
                return 0
            if st == "CASH":
                return 2
            return 1

        def sort_value(pos) -> float:
            if pos.market_value is not None:
                return float(pos.market_value)
            if pos.base_market_value is not None:
                return float(pos.base_market_value)
            return float("-inf")

        ordered_positions = sorted(
            snapshot.positions,
            key=lambda p: (sort_rank(p.sec_type), p.sec_type, -sort_value(p), p.symbol),
        )

        for pos in ordered_positions:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(pos.symbol))
            self.table.setItem(row, 1, QTableWidgetItem(pos.sec_type))
            self.table.setItem(row, 2, QTableWidgetItem(pos.currency))
            self.table.setItem(row, 3, QTableWidgetItem(f"{pos.quantity:.2f}"))
            self.table.setItem(row, 4, QTableWidgetItem(self._fmt(pos.avg_cost)))
            self.table.setItem(row, 5, QTableWidgetItem(self._fmt(pos.market_price)))
            self.table.setItem(row, 6, QTableWidgetItem(self._fmt(pos.market_value)))
            pnl_item = QTableWidgetItem(self._fmt(pos.unrealized_pnl))
            if pos.unrealized_pnl is not None:
                if pos.unrealized_pnl > 0:
                    pnl_item.setForeground(QColor(COLOR_POSITIVE))
                elif pos.unrealized_pnl < 0:
                    pnl_item.setForeground(QColor(COLOR_NEGATIVE))
            self.table.setItem(row, 7, pnl_item)
            weight = f"{pos.weight * 100:.2f}%" if pos.weight is not None else "N/A"
            self.table.setItem(row, 8, QTableWidgetItem(weight))

    def _plot_weights(self, snapshot: PortfolioSnapshot) -> None:
        positions = [p for p in snapshot.positions if p.weight is not None]
        if not positions:
            self.weights_canvas.show_message("No weight data")
            return

        positions = sorted(positions, key=lambda p: p.weight or 0.0, reverse=True)
        labels = [p.symbol for p in positions]
        values = [float((p.weight or 0.0) * 100) for p in positions]
        pie_colors = [
            COLOR_PRIMARY,
            "#3fb950",
            "#79c0ff",
            "#d29922",
            "#a5d6ff",
            "#ff7b72",
            "#56d364",
            "#2f81f7",
            "#e3b341",
            "#ffa657",
        ]
        colors = [COLOR_BENCHMARK if str(symbol).startswith("CASH") else pie_colors[i % len(pie_colors)] for i, symbol in enumerate(labels)]
        display_labels = [label if value >= 4.5 else "" for label, value in zip(labels, values)]

        ax = self.weights_canvas.axes
        self.weights_canvas.clear_axes()
        wedges, texts, autotexts = ax.pie(
            values,
            labels=display_labels,
            colors=colors,
            startangle=90,
            counterclock=False,
            autopct=lambda pct: f"{pct:.1f}%" if pct >= 4.5 else "",
            pctdistance=0.72,
            labeldistance=1.02,
            wedgeprops={"linewidth": 0.8, "edgecolor": "#0d1117"},
            textprops={"color": TEXT_COLOR, "fontsize": 6.5},
        )
        for text in texts:
            text.set_color(MUTED_TEXT)
            text.set_fontsize(6.5)
        for text in autotexts:
            text.set_color(TEXT_COLOR)
            text.set_fontsize(6.5)
        ax.grid(False)
        ax.set_aspect("equal")
        self.weights_canvas.figure.subplots_adjust(left=0.05, right=0.95, top=0.90, bottom=0.08)
        self.weights_canvas.draw_idle()

    def _start_performance_load(self, snapshot: PortfolioSnapshot) -> None:
        self._perf_task_id += 1
        task_id = self._perf_task_id
        worker = Worker(self._performance_worker, snapshot, task_id)
        worker.signals.finished.connect(self._on_performance_loaded)
        worker.signals.error.connect(self._on_error)
        self.thread_pool.start(worker)

    def _performance_worker(self, snapshot: PortfolioSnapshot, task_id: int):
        warnings: list[str] = []
        prices, missing = self._load_prices(snapshot, self._perf_lookback_days)
        day_pnl, day_pnl_pct, day_pnl_source, pnl_warning = self._estimate_day_pnl_from_history(snapshot, prices)
        if pnl_warning:
            warnings.append(pnl_warning)
        errors = self.market_data.drain_errors()
        if errors:
            warnings.extend(errors)
        if missing:
            warnings.append(f"Missing history for: {', '.join(missing)}")

        price_df = align_prices(prices)
        returns_df = compute_returns(price_df)
        if returns_df.empty:
            hist_perf = self._load_performance_from_store()
            if hist_perf is None:
                return (
                    task_id,
                    warnings,
                    "No performance data",
                    None,
                    None,
                    None,
                    None,
                    missing,
                    "none",
                    day_pnl,
                    day_pnl_pct,
                    day_pnl_source,
                )
            perf_returns, cum, perf_base_value = hist_perf
            benchmark, benchmark_source, benchmark_warnings = self._build_benchmark(
                snapshot, self._perf_lookback_days, cum.index
            )
            warnings.extend(benchmark_warnings)
            warnings.append("Using stored portfolio history (local snapshots)")
            return (
                task_id,
                warnings,
                None,
                perf_returns,
                cum,
                benchmark,
                perf_base_value,
                missing,
                benchmark_source,
                day_pnl,
                day_pnl_pct,
                day_pnl_source,
            )

        returns_df = self._ensure_cash_returns(snapshot, returns_df)
        weights = self._weights_for_symbols(snapshot, returns_df.columns.tolist())
        if weights.empty:
            warnings.append("No weights for performance")
            return (
                task_id,
                warnings,
                "No weights for performance",
                None,
                None,
                None,
                None,
                missing,
                "none",
                day_pnl,
                day_pnl_pct,
                day_pnl_source,
            )

        perf_returns = portfolio_returns(returns_df, weights)
        if perf_returns.empty:
            warnings.append("No performance data")
            return (
                task_id,
                warnings,
                "No performance data",
                None,
                None,
                None,
                None,
                missing,
                "none",
                day_pnl,
                day_pnl_pct,
                day_pnl_source,
            )

        cum = (1 + perf_returns).cumprod()
        if not cum.empty:
            cum = cum / cum.iloc[0]
        benchmark, benchmark_source, benchmark_warnings = self._build_benchmark(
            snapshot, self._perf_lookback_days, cum.index
        )
        warnings.extend(benchmark_warnings)
        perf_base_value = self._portfolio_base_value(snapshot)
        return (
            task_id,
            warnings,
            None,
            perf_returns,
            cum,
            benchmark,
            perf_base_value,
            missing,
            benchmark_source,
            day_pnl,
            day_pnl_pct,
            day_pnl_source,
        )

    def _on_performance_loaded(self, payload) -> None:
        (
            task_id,
            warnings,
            message,
            perf_returns,
            perf_cum,
            benchmark_cum,
            perf_base_value,
            missing,
            benchmark_source,
            day_pnl,
            day_pnl_pct,
            day_pnl_source,
        ) = payload
        if task_id != self._perf_task_id:
            return
        self._last_missing_history = list(missing or [])
        self._last_benchmark_source = benchmark_source or "none"
        if day_pnl_source:
            self._set_day_pnl(day_pnl, day_pnl_pct, day_pnl_source)
        if warnings:
            for warning in warnings:
                self._last_warning_categories[self._warning_category(warning)] += 1
            self._last_warning_count += len(warnings)
            for warning in warnings:
                self._add_message(warning)
        if message:
            self._perf_returns = pd.Series(dtype=float)
            self._perf_cum = pd.Series(dtype=float)
            self._benchmark_cum = pd.Series(dtype=float)
            self._perf_base_value = None
            self.performance_canvas.show_message(message)
            return
        self._perf_returns = perf_returns
        self._perf_cum = perf_cum
        self._benchmark_cum = benchmark_cum
        self._perf_base_value = perf_base_value
        self._update_performance_chart()

    def _update_performance_chart(self, *_args) -> None:
        if self._perf_cum.empty:
            self.performance_canvas.show_message("No performance data")
            return

        timeframe = self.timeframe_combo.currentText()
        perf = self._slice_series(self._perf_cum, timeframe)
        bench = self._slice_series(self._benchmark_cum, timeframe)
        if perf.empty:
            self.performance_canvas.show_message("No performance data")
            return
        ax = self.performance_canvas.axes
        self.performance_canvas.clear_axes()
        ax.plot(perf.index, perf.values, color=COLOR_PRIMARY, linewidth=1.25, label="Portfolio")

        if self.benchmark_check.isChecked() and not bench.empty:
            bench_name = (
                f"{self._last_benchmark_symbol} (Cash 0%)"
                if self._last_benchmark_source == "cash_0"
                else self._last_benchmark_symbol
            )
            ax.plot(bench.index, bench.values, color=COLOR_BENCHMARK, linewidth=1.1, linestyle="--", label=bench_name)
            legend = ax.legend(loc="upper left")
            if legend is not None:
                for text in legend.get_texts():
                    text.set_color(TEXT_COLOR)

        ax.set_ylabel("Growth", fontsize=8)
        ax.yaxis.set_major_formatter(lambda val, _pos: f"{val:.2f}")
        locator = mdates.AutoDateLocator(minticks=4, maxticks=8)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        for label in ax.get_xticklabels():
            label.set_color(MUTED_TEXT)
            label.set_fontsize(8)
        for label in ax.get_yticklabels():
            label.set_fontsize(8)

        self.performance_canvas.figure.tight_layout(pad=1.0)
        self.performance_canvas.draw_idle()

    def _slice_series(self, series: pd.Series, timeframe: str) -> pd.Series:
        if series.empty:
            return series
        if timeframe == "MAX":
            return series
        days_map = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}
        days = days_map.get(timeframe, 365)
        cutoff = series.index.max() - pd.Timedelta(days=days)
        return series[series.index >= cutoff]

    def _portfolio_base_value(self, snapshot: PortfolioSnapshot) -> float | None:
        if snapshot.net_liquidation is not None:
            return snapshot.net_liquidation
        if snapshot.total_market_value is None and snapshot.total_cash is None:
            return None
        return float((snapshot.total_market_value or 0.0) + (snapshot.total_cash or 0.0))

    def _set_day_pnl(self, day_pnl: float | None, day_pnl_pct: float | None, source: str | None) -> None:
        self._last_day_pnl_source = source or "none"
        if day_pnl is None:
            self.pnl_label.setText("N/A")
            self.pnl_label.setStyleSheet(f"color: {TEXT_COLOR};")
            self.pnl_label.setToolTip("Day P&L unavailable with current account/history data.")
            return
        text = f"{day_pnl:,.2f} {self.base_currency}"
        if day_pnl_pct is not None:
            text = f"{text} ({day_pnl_pct * 100:.2f}%)"
        self.pnl_label.setText(text)
        if day_pnl > 0:
            self.pnl_label.setStyleSheet(f"color: {COLOR_POSITIVE};")
        elif day_pnl < 0:
            self.pnl_label.setStyleSheet(f"color: {COLOR_NEGATIVE};")
        else:
            self.pnl_label.setStyleSheet(f"color: {TEXT_COLOR};")
        if source == "historical_eod":
            self.pnl_label.setToolTip("Approximate day P&L based on latest two daily bars (EOD approximation).")
        else:
            self.pnl_label.setToolTip("")

    def _benchmark_symbol(self) -> str:
        text = self.benchmark_input.text().strip().upper()
        return text or "SPY"

    def _reload_benchmark(self) -> None:
        symbol = self._benchmark_symbol()
        self.benchmark_input.setText(symbol)
        self._last_benchmark_symbol = symbol
        if self._latest_snapshot is not None:
            self._start_performance_load(self._latest_snapshot)

    def _build_benchmark(
        self,
        snapshot: PortfolioSnapshot,
        lookback_days: int,
        target_index: pd.Index,
    ) -> tuple[pd.Series, str, list[str]]:
        warnings: list[str] = []
        if target_index.empty:
            return pd.Series(dtype=float), "none", warnings

        symbol = self._benchmark_symbol()
        self._last_benchmark_symbol = symbol
        if self.client.mock:
            series = self.client.mock_service.load_history(symbol)
        else:
            contract = Contract(symbol=symbol, secType="STK", exchange="SMART", currency="USD")
            series = self.market_data.fetch_history(contract, lookback_days)
        if series is None or series.empty:
            warnings.append(f"No benchmark data for {symbol}; using Cash (0%) benchmark")
            return pd.Series(1.0, index=target_index), "cash_0", warnings

        converted = self._convert_series_to_base(
            series.astype(float),
            quote_ccy="USD",
            base_ccy=snapshot.base_currency,
            lookback_days=lookback_days,
            warnings=warnings,
        )
        if converted is None or converted.empty:
            warnings.append(f"Benchmark conversion failed for {symbol}; using Cash (0%) benchmark")
            return pd.Series(1.0, index=target_index), "cash_0", warnings

        bench_returns = converted.pct_change().dropna()
        if bench_returns.empty:
            warnings.append(f"No benchmark returns for {symbol}; using Cash (0%) benchmark")
            return pd.Series(1.0, index=target_index), "cash_0", warnings

        bench_cum = (1 + bench_returns).cumprod()
        bench_cum = bench_cum.reindex(target_index).ffill()
        bench_cum = bench_cum.dropna()
        if bench_cum.empty:
            warnings.append(f"No benchmark overlap for {symbol}; using Cash (0%) benchmark")
            return pd.Series(1.0, index=target_index), "cash_0", warnings
        bench_cum = bench_cum / float(bench_cum.iloc[0])
        bench_cum = bench_cum.reindex(target_index).ffill().fillna(1.0)
        return bench_cum, f"history_{symbol}", warnings

    def _convert_series_to_base(
        self,
        series: pd.Series,
        quote_ccy: str,
        base_ccy: str,
        lookback_days: int,
        warnings: list[str],
    ) -> pd.Series | None:
        quote = str(quote_ccy or "").upper()
        base = str(base_ccy or "").upper()
        if quote == base:
            return series
        fx_series = self.market_data.fetch_fx_history(base, quote, lookback_days)
        if fx_series is not None and not fx_series.empty:
            aligned = fx_series.reindex(series.index).ffill()
            aligned = aligned.dropna()
            if not aligned.empty:
                common_index = series.index.intersection(aligned.index)
                if not common_index.empty:
                    return series.reindex(common_index) * aligned.reindex(common_index)
        rate = self.fx_service.get_rate(base, quote)
        if rate is None:
            warnings.append(f"FX unavailable for benchmark conversion {quote}->{base}")
            return None
        warnings.append(f"Benchmark FX conversion {quote}->{base} uses latest spot rate")
        return series * float(rate)

    def _estimate_day_pnl_from_history(
        self,
        snapshot: PortfolioSnapshot,
        prices: dict[str, pd.Series],
    ) -> tuple[float | None, float | None, str | None, str | None]:
        if snapshot.day_pnl is not None:
            return snapshot.day_pnl, snapshot.day_pnl_pct, snapshot.day_pnl_source or "account_summary", None

        fx_by_currency: dict[str, float | None] = {}
        total_pnl = 0.0
        missing_symbols: list[str] = []
        for pos in snapshot.positions:
            if pos.symbol.startswith("CASH") or pos.sec_type == "CASH":
                continue
            series = prices.get(pos.symbol)
            if series is None:
                missing_symbols.append(pos.symbol)
                continue
            clean = series.dropna()
            if len(clean) < 2:
                missing_symbols.append(pos.symbol)
                continue
            latest = float(clean.iloc[-1])
            previous = float(clean.iloc[-2])
            ccy = str(pos.currency or "").upper()
            if ccy == snapshot.base_currency.upper():
                fx_rate = 1.0
            elif pos.fx_rate is not None:
                fx_rate = float(pos.fx_rate)
            elif ccy in fx_by_currency:
                fx_rate = fx_by_currency[ccy]
            else:
                fx_rate = self.fx_service.get_rate(snapshot.base_currency, ccy)
                fx_by_currency[ccy] = fx_rate
            if fx_rate is None:
                missing_symbols.append(pos.symbol)
                continue
            total_pnl += float(pos.quantity) * (latest - previous) * float(fx_rate)

        if missing_symbols:
            symbols = ", ".join(sorted(set(missing_symbols)))
            warning = f"Day P&L unavailable: missing daily bars/FX for {symbols}"
            return None, None, "historical_eod", warning

        previous_value = None
        if snapshot.net_liquidation is not None:
            previous_value = snapshot.net_liquidation - total_pnl
        elif snapshot.total_market_value is not None or snapshot.total_cash is not None:
            current_value = float((snapshot.total_market_value or 0.0) + (snapshot.total_cash or 0.0))
            previous_value = current_value - total_pnl
        pct = None
        if previous_value and previous_value != 0:
            pct = float(total_pnl / previous_value)
        warning = "Day P&L estimated from latest two daily bars (EOD approximation)"
        return float(total_pnl), pct, "historical_eod", warning

    def _load_performance_from_store(self) -> tuple[pd.Series, pd.Series, float] | None:
        series_df = self.history_store.load_series()
        if series_df.empty or "portfolio_value" not in series_df.columns:
            return None
        values = pd.to_numeric(series_df["portfolio_value"], errors="coerce").dropna()
        if len(values) < 2:
            return None
        returns = values.pct_change().dropna()
        if returns.empty:
            return None
        cum = values / float(values.iloc[0])
        return returns, cum, float(values.iloc[0])

    def _load_prices(
        self, snapshot: PortfolioSnapshot, lookback_days: int
    ) -> tuple[dict[str, pd.Series], list[str]]:
        if self.client.mock:
            prices: dict[str, pd.Series] = {}
            missing: list[str] = []
            for pos in snapshot.positions:
                if pos.symbol.startswith("CASH"):
                    continue
                series = self.client.mock_service.load_history(pos.symbol)
                if series is None:
                    missing.append(pos.symbol)
                else:
                    prices[pos.symbol] = series
            return prices, missing

        contracts = self.client.get_contracts()
        return self.market_data.fetch_histories(contracts, lookback_days)

    def _ensure_cash_returns(self, snapshot: PortfolioSnapshot, returns_df: pd.DataFrame) -> pd.DataFrame:
        cash_symbols = [
            pos.symbol for pos in snapshot.positions if pos.symbol.startswith("CASH") and pos.base_market_value is not None
        ]
        if cash_symbols:
            returns_df = returns_df.copy()
            for symbol in cash_symbols:
                if symbol not in returns_df.columns:
                    returns_df[symbol] = 0.0
        return returns_df

    def _weights_for_symbols(self, snapshot: PortfolioSnapshot, symbols: list[str]) -> pd.Series:
        values: dict[str, float] = {}
        for pos in snapshot.positions:
            if pos.symbol in symbols and pos.base_market_value is not None:
                values[pos.symbol] = float(pos.base_market_value)
        series = pd.Series(values)
        return compute_weights(series)

    def _show_warnings(self, snapshot: PortfolioSnapshot) -> None:
        self.message_area.clear()
        categories: Counter[str] = Counter()
        for warning in snapshot.warnings:
            categories[self._warning_category(warning)] += 1
            self._add_message(warning)
        self._last_warning_categories = categories
        self._last_warning_count = len(snapshot.warnings)
        self._refresh_error_view()

    def _add_message(self, msg: str) -> None:
        current = self.message_area.toPlainText().strip()
        if current:
            self.message_area.setPlainText(current + "\n" + msg)
        else:
            self.message_area.setPlainText(msg)

    def _append_diagnostics(self, lines: list[str]) -> None:
        if not lines:
            return
        for line in lines:
            self.diagnostics_log.appendPlainText(line)
        self.diagnostics_log.moveCursor(QTextCursor.End)

    @staticmethod
    def _warning_category(warning: str) -> str:
        text = warning.lower()
        if "10089" in text or "10167" in text or "10168" in text or "354" in text:
            return "entitlement"
        if "entitlement" in text or "market data subscription" in text:
            return "entitlement"
        if "timeout" in text or "timed out" in text:
            return "timeout"
        if "fx" in text:
            return "fx"
        if "contract" in text or "qualif" in text or "[positions]" in text:
            return "contract_resolution"
        return "other"

    def _run_diagnostics(self) -> None:
        self._append_diagnostics(["[UI] Diagnostics requested"])
        self._add_message("Diagnostics requested")
        worker = Worker(self.client.run_diagnostics)
        worker.signals.finished.connect(self._on_diagnostics)
        worker.signals.error.connect(self._on_error)
        self.thread_pool.start(worker)

    def _on_diagnostics(self, lines: list[str]) -> None:
        if not lines:
            lines = ["[UI] Diagnostics returned no output"]
        self._append_diagnostics(lines)
        self._append_diagnostics(["", self._build_diagnostics_report(), ""])
        self._add_message("Diagnostics completed")
        self._refresh_error_view()

    def _force_account_subscribe(self) -> None:
        self._append_diagnostics(["[UI] Force account subscribe requested"])
        self._add_message("Force account subscribe requested")
        worker = Worker(self.client.force_account_subscribe)
        worker.signals.finished.connect(self._on_force_subscribe)
        worker.signals.error.connect(self._on_error)
        self.thread_pool.start(worker)

    def _on_force_subscribe(self, lines: list[str]) -> None:
        if not lines:
            lines = ["[UI] Force account subscribe returned no output"]
        self._append_diagnostics(lines)
        self._add_message("Force account subscribe completed")
        self._refresh_error_view()

    def _refresh_error_view(self) -> None:
        lines = self.client.format_error_records(50)
        if not lines:
            self.ib_error_log.setPlainText("No IB errors recorded")
        else:
            self.ib_error_log.setPlainText("\n".join(lines))

    def _build_diagnostics_report(self) -> str:
        now = format_ts(now_utc())
        connection = "connected" if self.client.is_connected() else "disconnected"
        cache_stats = self.market_data.history_cache_stats()
        records = self.client.get_error_records(200)
        code_counts = Counter(int(r.code) for r in records)
        top_codes = ", ".join(f"{code}:{count}" for code, count in code_counts.most_common(5)) or "none"
        warning_summary = ", ".join(
            f"{name}={count}" for name, count in sorted(self._last_warning_categories.items())
        ) or "none"
        missing = ", ".join(self._last_missing_history) if self._last_missing_history else "none"
        duration_text = (
            f"{self._last_refresh_duration_ms:.0f} ms"
            if self._last_refresh_duration_ms is not None
            else "N/A"
        )
        return "\n".join(
            [
                "=== StrataLab Diagnostics Report ===",
                f"Generated: {now}",
                f"Mode: {'Mock' if self.client.mock else 'Live'}",
                f"Connection: {connection}",
                f"Last refresh duration: {duration_text}",
                f"Positions count: {self._last_positions_count}",
                f"Last warnings: {self._last_warning_count}",
                f"Warning categories: {warning_summary}",
                f"Missing historical tickers: {missing}",
                f"Benchmark symbol/source: {self._last_benchmark_symbol} / {self._last_benchmark_source}",
                f"Day P&L source: {self._last_day_pnl_source}",
                "History cache stats: "
                f"hits={int(cache_stats['hits'])}, misses={int(cache_stats['misses'])}, "
                f"hit_rate={cache_stats['hit_rate'] * 100:.1f}%",
                f"Top IB error codes: {top_codes}",
            ]
        )

    def _copy_diagnostics(self) -> None:
        report = self._build_diagnostics_report()
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(report)
            self._append_diagnostics(["[UI] Diagnostics report copied to clipboard"])
            self._add_message("Diagnostics copied to clipboard")

    def _clear_history(self) -> None:
        self.history_store.clear()
        self._append_diagnostics(["[UI] Portfolio history cleared"])
        self._add_message("Local portfolio history cleared")
        if self._latest_snapshot is not None:
            self._start_performance_load(self._latest_snapshot)

    def _on_diagnostics_toggled(self, expanded: bool) -> None:
        self._diagnostics_expanded = expanded
        self.diagnostics_body.setVisible(expanded)
        self.toggle_diag_btn.setText("Hide Diagnostics" if expanded else "Show Diagnostics")
        self.diagnostics_box.setMaximumHeight(16777215 if expanded else 56)

    def _toggle_diagnostics(self) -> None:
        self._diagnostics_expanded = not self._diagnostics_expanded
        self._on_diagnostics_toggled(self._diagnostics_expanded)

    def _on_error(self, msg: str) -> None:
        error_text = msg.strip() if msg else "Unknown worker error"
        logger.error("Overview error:\n%s", error_text)
        if self.last_refresh.text().endswith("Updating..."):
            self.last_refresh.setText(f"Last Update: Error ({format_ts(now_utc())})")
        if self._refresh_started_at is not None:
            self._last_refresh_duration_ms = max(0.0, (time.perf_counter() - self._refresh_started_at) * 1000.0)
            self._refresh_started_at = None
        self._add_message(error_text)
        if "not connected" in error_text.lower():
            self._handle_connection_lost()
        if self.connect_watchdog.isActive():
            self.connect_watchdog.stop()

    @staticmethod
    def _fmt(value: Optional[float]) -> str:
        if value is None:
            return "N/A"
        return f"{value:.2f}"

    def _check_connection(self) -> None:
        if self.client.mock:
            return
        if not self.client.is_connected():
            self._handle_connection_lost()

    def _handle_connection_lost(self) -> None:
        self._set_status("Disconnected")
        self._set_connection_action("Connect to IBKR", not self.client.mock)
        if self.timer.isActive():
            self.timer.stop()
        if self.connection_timer.isActive():
            self.connection_timer.stop()
        self._add_message("Connection lost")

    def _connect_timeout(self) -> None:
        if self.client.is_connected():
            self._on_connected(True)
            return
        self._set_status("Error")
        self._set_connection_action("Connect to IBKR", not self.client.mock)
        self._add_message("Connection timed out")
