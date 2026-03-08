from __future__ import annotations

import logging

import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.analytics.risk_metrics import max_drawdown, realized_vol
from src.application.research_service import (
    ResearchAnalysisRequest,
    ResearchAnalysisResult,
    ResearchService,
)
from src.application.workspace_service import can_forward_research_to_iv
from src.models.app_mode import ResearchScopeType, SyntheticPosition
from src.models.portfolio import PortfolioSnapshot
from src.services.app_context import AppDataContext
from src.services.data_providers import ResearchDataProvider
from src.ui.plot_theme import (
    COLOR_BENCHMARK,
    COLOR_NEGATIVE,
    COLOR_PRIMARY,
    MUTED_TEXT,
    TEXT_COLOR,
    style_axes,
)
from src.ui.widgets.mpl_canvas import MplCanvas
from src.ui.widgets.worker import Worker


logger = logging.getLogger(__name__)

class ResearchOverviewTab(QWidget):
    snapshot_updated = Signal(object)
    open_risk_requested = Signal()
    open_iv_surface_requested = Signal()

    def __init__(
        self,
        app_context: AppDataContext,
        provider: ResearchDataProvider,
        base_currency: str,
    ) -> None:
        super().__init__()
        self.app_context = app_context
        self.research_service = ResearchService(provider)
        self.base_currency = base_currency
        self.thread_pool = QThreadPool()
        self._apply_request_id = 0
        self._latest_result = ResearchAnalysisResult(
            scope_type=ResearchScopeType.NONE,
            snapshot=None,
            perf=pd.Series(dtype=float),
            benchmark_returns=pd.Series(dtype=float),
            benchmark_symbol="SPY",
            weights=pd.Series(dtype=float),
            primary_price=pd.Series(dtype=float),
            warnings=[],
        )
        self._build_ui()
        self._seed_synthetic_defaults()
        self._reset_dashboard()
        self._on_scope_changed(self.scope_combo.currentText())

    def _build_ui(self) -> None:
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(self._build_scope_section())

        workspace_row = QHBoxLayout()
        workspace_row.setSpacing(10)

        left_pane = QVBoxLayout()
        left_pane.setSpacing(8)
        left_pane.addWidget(self._build_kpi_section())
        left_pane.addWidget(self._build_analytics_section())
        left_pane.addWidget(self._build_structure_section(), 1)

        right_pane = QVBoxLayout()
        right_pane.setSpacing(8)
        context_box = self._build_context_section()
        context_box.setMinimumWidth(300)
        context_box.setMaximumWidth(360)
        right_pane.addWidget(context_box)
        right_pane.addStretch(1)

        workspace_row.addLayout(left_pane, 5)
        workspace_row.addLayout(right_pane, 2)
        layout.addLayout(workspace_row, 1)
        layout.addStretch(1)

        content.setLayout(layout)
        self.scroll.setWidget(content)
        root.addWidget(self.scroll)
        self.setLayout(root)

    def _build_scope_section(self) -> QGroupBox:
        box = QGroupBox("Research Command Deck")
        layout = QVBoxLayout()
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.scope_combo = QComboBox()
        self.scope_combo.addItems(["Single Ticker", "Synthetic Portfolio"])
        self.scope_combo.currentTextChanged.connect(self._on_scope_changed)
        self.status_label = QLabel("Status: Idle")
        header.addWidget(QLabel("Scope"))
        header.addWidget(self.scope_combo)
        header.addStretch()
        header.addWidget(self.status_label)
        layout.addLayout(header)

        single_row = QHBoxLayout()
        self.single_symbol_input = QLineEdit("SPY")
        self.single_symbol_input.setMaximumWidth(140)
        self.apply_single_btn = QPushButton("Apply")
        self.apply_single_btn.clicked.connect(self.apply_scope)
        self.reset_scope_btn = QPushButton("Reset")
        self.reset_scope_btn.clicked.connect(self._reset_scope_inputs)
        single_row.addWidget(QLabel("Ticker"))
        single_row.addWidget(self.single_symbol_input)
        single_row.addWidget(self.apply_single_btn)
        single_row.addWidget(self.reset_scope_btn)
        single_row.addStretch()
        layout.addLayout(single_row)

        self.synthetic_box = QGroupBox("Synthetic Portfolio Builder")
        synth_layout = QVBoxLayout()
        self.synthetic_table = QTableWidget(0, 2)
        self.synthetic_table.setHorizontalHeaderLabels(["Symbol", "Weight"])
        self.synthetic_table.horizontalHeader().setStretchLastSection(True)
        self.synthetic_table.setMinimumHeight(180)
        synth_layout.addWidget(self.synthetic_table)

        synth_actions = QHBoxLayout()
        self.add_row_btn = QPushButton("Add Row")
        self.remove_row_btn = QPushButton("Remove Row")
        self.normalize_btn = QPushButton("Normalize Weights")
        self.apply_synth_btn = QPushButton("Apply Synthetic")
        self.add_row_btn.clicked.connect(self._add_synthetic_row)
        self.remove_row_btn.clicked.connect(self._remove_synthetic_row)
        self.normalize_btn.clicked.connect(self._normalize_weights)
        self.apply_synth_btn.clicked.connect(self.apply_scope)
        self.reset_synth_btn = QPushButton("Reset")
        self.reset_synth_btn.clicked.connect(self._reset_scope_inputs)
        synth_actions.addWidget(self.add_row_btn)
        synth_actions.addWidget(self.remove_row_btn)
        synth_actions.addWidget(self.normalize_btn)
        synth_actions.addWidget(self.apply_synth_btn)
        synth_actions.addWidget(self.reset_synth_btn)
        synth_actions.addStretch()
        synth_layout.addLayout(synth_actions)
        self.synthetic_box.setLayout(synth_layout)
        layout.addWidget(self.synthetic_box)

        helper = QLabel(
            "Define a single-name or synthetic thesis here, inspect behavior, then move into Risk or IV workflows."
        )
        helper.setWordWrap(True)
        helper.setStyleSheet("color: #9da7b3;")
        layout.addWidget(helper)

        box.setLayout(layout)
        return box

    def _build_kpi_section(self) -> QGroupBox:
        box = QGroupBox("Research Snapshot")
        layout = QGridLayout()
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(10)

        self.total_return_value = QLabel()
        self.annual_return_value = QLabel()
        self.annual_vol_value = QLabel()
        self.max_dd_value = QLabel()
        self.beta_value = QLabel()
        self.corr_value = QLabel()

        self._add_kpi_cell(layout, 0, 0, "TOTAL RETURN", self.total_return_value)
        self._add_kpi_cell(layout, 0, 1, "ANNUAL RETURN", self.annual_return_value)
        self._add_kpi_cell(layout, 0, 2, "ANNUAL VOL", self.annual_vol_value)
        self._add_kpi_cell(layout, 1, 0, "MAX DRAWDOWN", self.max_dd_value)
        self._add_kpi_cell(layout, 1, 1, "BETA", self.beta_value)
        self._add_kpi_cell(layout, 1, 2, "CORRELATION", self.corr_value)
        box.setLayout(layout)
        return box

    def _build_analytics_section(self) -> QGroupBox:
        box = QGroupBox("Analysis Grid")
        layout = QVBoxLayout()

        controls = QHBoxLayout()
        self.left_chart_combo = QComboBox()
        self.left_chart_combo.addItems(["Performance", "Price", "Drawdown", "Rolling Vol", "Rolling Beta"])
        self.left_chart_combo.setCurrentText("Performance")
        self.left_chart_combo.currentTextChanged.connect(self._update_analytics_view)
        self.right_chart_combo = QComboBox()
        self.right_chart_combo.addItems(["Performance", "Price", "Drawdown", "Rolling Vol", "Rolling Beta"])
        self.right_chart_combo.setCurrentText("Rolling Vol")
        self.right_chart_combo.currentTextChanged.connect(self._update_analytics_view)
        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(["1M", "3M", "6M", "1Y", "MAX"])
        self.timeframe_combo.setCurrentText("1Y")
        self.timeframe_combo.currentTextChanged.connect(self._update_analytics_view)
        self.benchmark_input = QLineEdit("SPY")
        self.benchmark_input.setMaximumWidth(100)
        self.benchmark_input.editingFinished.connect(self._on_benchmark_symbol_changed)
        self.benchmark_check = QCheckBox("Overlay Benchmark")
        self.benchmark_check.setChecked(True)
        self.benchmark_check.toggled.connect(self._update_analytics_view)
        controls.addWidget(QLabel("Left"))
        controls.addWidget(self.left_chart_combo)
        controls.addSpacing(8)
        controls.addWidget(QLabel("Right"))
        controls.addWidget(self.right_chart_combo)
        controls.addSpacing(12)
        controls.addWidget(QLabel("Timeframe"))
        controls.addWidget(self.timeframe_combo)
        controls.addSpacing(12)
        controls.addWidget(QLabel("Benchmark"))
        controls.addWidget(self.benchmark_input)
        controls.addWidget(self.benchmark_check)
        controls.addStretch()
        layout.addLayout(controls)

        charts_row = QHBoxLayout()
        charts_row.setSpacing(10)
        self.left_canvas = MplCanvas(width=5.2, height=2.75)
        self.left_canvas.setMinimumHeight(230)
        self.right_canvas = MplCanvas(width=5.2, height=2.75)
        self.right_canvas.setMinimumHeight(230)
        charts_row.addWidget(self.left_canvas, 1)
        charts_row.addWidget(self.right_canvas, 1)
        layout.addLayout(charts_row)

        box.setLayout(layout)
        return box

    def _build_structure_section(self) -> QGroupBox:
        box = QGroupBox("Market Structure Overview")
        layout = QVBoxLayout()

        stats = QGridLayout()
        self.scope_summary_label = QLabel("Scope: N/A")
        self.asset_count_label = QLabel("Names: N/A")
        self.top_weight_label = QLabel("Top Weight: N/A")
        self.effective_positions_label = QLabel("Effective Positions: N/A")
        stats.addWidget(self.scope_summary_label, 0, 0)
        stats.addWidget(self.asset_count_label, 0, 1)
        stats.addWidget(self.top_weight_label, 1, 0)
        stats.addWidget(self.effective_positions_label, 1, 1)
        layout.addLayout(stats)

        self.structure_table = QTableWidget(0, 3)
        self.structure_table.setHorizontalHeaderLabels(["Symbol", "Weight", f"Value ({self.base_currency})"])
        self.structure_table.horizontalHeader().setStretchLastSection(True)
        self.structure_table.setMinimumHeight(220)
        layout.addWidget(self.structure_table)

        box.setLayout(layout)
        return box

    def _build_context_section(self) -> QGroupBox:
        box = QGroupBox("Context Rail")
        layout = QVBoxLayout()

        meta = QGridLayout()
        self.benchmark_status_label = QLabel("Benchmark: N/A")
        self.observation_label = QLabel("Observations: N/A")
        self.assumption_label = QLabel("Assumptions: daily close history, static weights, no transaction costs")
        self.assumption_label.setWordWrap(True)
        meta.addWidget(self.benchmark_status_label, 0, 0)
        meta.addWidget(self.observation_label, 1, 0)
        meta.addWidget(self.assumption_label, 2, 0)
        layout.addLayout(meta)

        actions = QHBoxLayout()
        self.open_risk_btn = QPushButton("Compute Risk")
        self.open_iv_btn = QPushButton("Open IV Surface")
        self.open_risk_btn.clicked.connect(self._emit_open_risk)
        self.open_iv_btn.clicked.connect(self._emit_open_iv_surface)
        actions.addWidget(self.open_risk_btn)
        actions.addWidget(self.open_iv_btn)
        actions.addStretch()
        layout.addLayout(actions)

        self.message_area = QPlainTextEdit()
        self.message_area.setObjectName("contextMessageLog")
        self.message_area.setReadOnly(True)
        self.message_area.setMinimumHeight(220)
        layout.addWidget(self.message_area)

        box.setLayout(layout)
        return box

    @staticmethod
    def _add_kpi_cell(layout: QGridLayout, row: int, col: int, title: str, value_label: QLabel) -> None:
        title_label = QLabel(title)
        title_label.setObjectName("kpiTitle")
        value_label.setObjectName("kpiValue")
        cell = QVBoxLayout()
        cell.addWidget(title_label)
        cell.addWidget(value_label)
        layout.addLayout(cell, row, col)

    def _seed_synthetic_defaults(self) -> None:
        self.synthetic_table.setRowCount(0)
        self._add_synthetic_row("SPY", 0.5)
        self._add_synthetic_row("QQQ", 0.5)

    def _on_scope_changed(self, text: str) -> None:
        is_single = text == "Single Ticker"
        self.single_symbol_input.setVisible(is_single)
        self.apply_single_btn.setVisible(is_single)
        self.synthetic_box.setVisible(not is_single)

    def _add_synthetic_row(self, symbol: str = "", weight: float | None = None) -> None:
        row = self.synthetic_table.rowCount()
        self.synthetic_table.insertRow(row)
        self.synthetic_table.setItem(row, 0, QTableWidgetItem(symbol))
        self.synthetic_table.setItem(row, 1, QTableWidgetItem("" if weight is None else f"{weight:.4f}"))

    def _remove_synthetic_row(self) -> None:
        row = self.synthetic_table.currentRow()
        if row >= 0:
            self.synthetic_table.removeRow(row)

    def _normalize_weights(self) -> None:
        rows = self.synthetic_table.rowCount()
        weights: list[float] = []
        for row in range(rows):
            item = self.synthetic_table.item(row, 1)
            try:
                val = float(item.text()) if item is not None and item.text().strip() else 0.0
            except ValueError:
                val = 0.0
            weights.append(max(0.0, val))
        total = sum(weights)
        if total <= 0:
            self._add_message("Cannot normalize: weights are empty or invalid")
            return
        for row, value in enumerate(weights):
            self.synthetic_table.setItem(row, 1, QTableWidgetItem(f"{value / total:.4f}"))

    def _reset_scope_inputs(self) -> None:
        self.scope_combo.setCurrentText("Single Ticker")
        self.single_symbol_input.setText("SPY")
        self._seed_synthetic_defaults()
        self.benchmark_input.setText("SPY")
        self.benchmark_check.setChecked(True)
        self.left_chart_combo.setCurrentText("Performance")
        self.right_chart_combo.setCurrentText("Rolling Vol")
        self.app_context.clear_research_state()
        self._reset_dashboard()

    def _collect_synthetic_positions(self) -> list[SyntheticPosition]:
        rows = self.synthetic_table.rowCount()
        result: list[SyntheticPosition] = []
        for row in range(rows):
            symbol_item = self.synthetic_table.item(row, 0)
            weight_item = self.synthetic_table.item(row, 1)
            symbol = (symbol_item.text().strip().upper() if symbol_item else "")
            if not symbol:
                continue
            try:
                weight = float(weight_item.text()) if weight_item and weight_item.text().strip() else 0.0
            except ValueError:
                weight = 0.0
            result.append(SyntheticPosition(symbol=symbol, weight=max(0.0, weight)))
        return result

    def apply_scope(self) -> None:
        self.message_area.clear()
        scope = (
            ResearchScopeType.SINGLE_TICKER
            if self.scope_combo.currentText() == "Single Ticker"
            else ResearchScopeType.SYNTHETIC_PORTFOLIO
        )
        symbol = self.single_symbol_input.text().strip().upper()
        synthetic_positions = self._collect_synthetic_positions()
        validation = AppDataContext.validate_scope(scope, symbol, synthetic_positions)
        if not validation.valid:
            for err in validation.errors:
                self._add_message(err)
            return

        self.app_context.set_research_scope(scope, primary_symbol=symbol, synthetic_positions=synthetic_positions)
        self._apply_request_id += 1
        request_id = self._apply_request_id
        benchmark_symbol = self.benchmark_input.text().strip().upper() or "SPY"
        self._set_controls_enabled(False)
        self.status_label.setText("Status: Loading...")
        worker = Worker(
            self._apply_scope_worker,
            request_id,
            scope,
            symbol,
            synthetic_positions,
            benchmark_symbol,
        )
        worker.signals.finished.connect(self._on_scope_applied)
        worker.signals.error.connect(self._on_error)
        self.thread_pool.start(worker)

    def _apply_scope_worker(
        self,
        request_id: int,
        scope: ResearchScopeType,
        symbol: str,
        synthetic_positions: list[SyntheticPosition],
        benchmark_symbol: str,
    ):
        result = self.research_service.analyze(
            ResearchAnalysisRequest(
                scope_type=scope,
                primary_symbol=symbol,
                synthetic_positions=synthetic_positions,
                benchmark_symbol=benchmark_symbol,
            )
        )
        return request_id, result

    def _on_scope_applied(self, payload) -> None:
        request_id, result = payload
        if request_id != self._apply_request_id:
            return
        self._set_controls_enabled(True)
        self._latest_result = result
        self.message_area.clear()
        for warning in result.warnings:
            self._add_message(warning)

        if result.snapshot is None or result.perf.empty:
            self.app_context.set_research_snapshot(None)
            self._reset_dashboard(empty_message="Apply research scope")
            for warning in result.warnings:
                self._add_message(warning)
            self.status_label.setText("Status: Error")
            return

        self._populate_structure(result.snapshot, result.weights)
        self._update_summary(result.perf, result.benchmark_returns)
        self._update_context(result)
        self._update_analytics_view()
        self.app_context.set_research_snapshot(result.snapshot)
        self.snapshot_updated.emit(result.snapshot)
        self.status_label.setText("Status: Ready")

    def _update_summary(self, perf: pd.Series, benchmark_returns: pd.Series) -> None:
        cumulative = (1.0 + perf).cumprod()
        total_return = float(cumulative.iloc[-1] - 1.0)
        annual_return = self._annualized_return(perf)
        daily_vol, annual_vol = realized_vol(perf)
        dd = max_drawdown(perf)
        beta, corr = self._beta_corr(perf, benchmark_returns)

        self.total_return_value.setText(self._fmt_pct_value(total_return))
        self.annual_return_value.setText(self._fmt_pct_value(annual_return))
        self.annual_vol_value.setText(self._fmt_pct_value(annual_vol))
        self.max_dd_value.setText(self._fmt_pct_value(dd))
        self.beta_value.setText(self._fmt_number(beta))
        self.corr_value.setText(self._fmt_number(corr))

    def _populate_structure(self, snapshot: PortfolioSnapshot, weights: pd.Series) -> None:
        self.structure_table.setRowCount(0)
        sorted_positions = [p for p in snapshot.positions if p.symbol in weights.index]
        sorted_positions.sort(key=lambda pos: float(weights.get(pos.symbol, 0.0)), reverse=True)
        for pos in sorted_positions:
            row = self.structure_table.rowCount()
            self.structure_table.insertRow(row)
            weight = float(weights.get(pos.symbol, np.nan))
            self.structure_table.setItem(row, 0, QTableWidgetItem(pos.symbol))
            self.structure_table.setItem(row, 1, QTableWidgetItem(self._fmt_pct_value(weight)))
            self.structure_table.setItem(row, 2, QTableWidgetItem(self._fmt_currency_value(pos.base_market_value)))

        scope_name = "Single Ticker" if len(sorted_positions) == 1 else "Synthetic Portfolio"
        self.scope_summary_label.setText(f"Scope: {scope_name}")
        self.asset_count_label.setText(f"Names: {len(sorted_positions)}")
        self.top_weight_label.setText(
            "Top Weight: N/A" if weights.empty else f"Top Weight: {float(weights.max()) * 100:.2f}%"
        )
        self.effective_positions_label.setText(
            "Effective Positions: N/A"
            if weights.empty
            else f"Effective Positions: {self._effective_positions(weights):.2f}"
        )

    def _update_context(self, result: ResearchAnalysisResult) -> None:
        benchmark_status = (
            result.benchmark_symbol
            if not result.benchmark_returns.empty
            else f"{result.benchmark_symbol} unavailable"
        )
        self.benchmark_status_label.setText(f"Benchmark: {benchmark_status}")
        self.observation_label.setText(f"Observations: {int(len(result.perf))}")
        has_result = result.snapshot is not None and not result.perf.empty
        self.open_risk_btn.setEnabled(has_result)
        self.open_iv_btn.setEnabled(has_result and can_forward_research_to_iv(result.scope_type))

    def _update_analytics_view(self, *_args) -> None:
        result = self._latest_result
        if result.snapshot is None or result.perf.empty:
            self.left_canvas.show_message("Apply research scope")
            self.right_canvas.show_message("Apply research scope")
            return

        timeframe = self.timeframe_combo.currentText()
        perf = self._slice_series(result.perf, timeframe)
        benchmark_returns = (
            self._slice_series(result.benchmark_returns, timeframe)
            if self.benchmark_check.isChecked()
            else pd.Series(dtype=float)
        )
        primary_price = self._slice_series(result.primary_price, timeframe)

        if perf.empty:
            self.left_canvas.show_message("No data for selected timeframe")
            self.right_canvas.show_message("No data for selected timeframe")
            return
        self._render_chart(
            self.left_chart_combo.currentText(),
            result,
            perf,
            benchmark_returns,
            primary_price,
            timeframe,
            self.left_canvas,
        )
        self._render_chart(
            self.right_chart_combo.currentText(),
            result,
            perf,
            benchmark_returns,
            primary_price,
            timeframe,
            self.right_canvas,
        )

    def _render_chart(
        self,
        chart_name: str,
        result: ResearchAnalysisResult,
        perf: pd.Series,
        benchmark_returns: pd.Series,
        primary_price: pd.Series,
        timeframe: str,
        canvas: MplCanvas,
    ) -> None:
        if chart_name == "Price":
            if result.scope_type != ResearchScopeType.SINGLE_TICKER:
                canvas.show_message("Price chart is available for single-ticker research")
                return
            self._plot_price_chart(primary_price, canvas, "Price")
            return
        if chart_name == "Drawdown":
            self._plot_drawdown(perf, canvas=canvas, title="Drawdown")
            return
        if chart_name == "Rolling Vol":
            self._plot_rolling_vol(result.perf, canvas=canvas, title="Rolling Vol (21D)", timeframe=timeframe)
            return
        if chart_name == "Rolling Beta":
            self._plot_rolling_beta(result.perf, result.benchmark_returns, result.benchmark_symbol, canvas, timeframe)
            return
        self._plot_performance(perf, benchmark_returns, result.benchmark_symbol, canvas, "Performance")

    def _plot_performance(
        self,
        perf: pd.Series,
        benchmark_returns: pd.Series,
        benchmark_symbol: str,
        canvas: MplCanvas,
        title: str,
    ) -> None:
        ax = canvas.axes
        ax.clear()
        style_axes(ax)
        cumulative = (1.0 + perf).cumprod()
        cumulative = cumulative / float(cumulative.iloc[0])
        ax.plot(cumulative.index, cumulative.values, color=COLOR_PRIMARY, linewidth=1.3, label="Research")
        if not benchmark_returns.empty:
            aligned = pd.concat([perf.rename("p"), benchmark_returns.rename("b")], axis=1, join="inner").dropna()
            if not aligned.empty:
                bench_cum = (1.0 + aligned["b"]).cumprod()
                bench_cum = bench_cum / float(bench_cum.iloc[0])
                ax.plot(
                    bench_cum.index,
                    bench_cum.values,
                    color=COLOR_BENCHMARK,
                    linestyle="--",
                    linewidth=1.1,
                    label=benchmark_symbol,
                )
        ax.set_title(title)
        self._format_date_axis(ax)
        self._style_legend(ax)
        self._style_ticks(ax)
        canvas.figure.tight_layout(pad=1.0)
        canvas.draw_idle()

    def _plot_drawdown(self, perf: pd.Series, canvas: MplCanvas | None = None, title: str = "Drawdown") -> None:
        target = canvas or self.left_canvas
        ax = target.axes
        ax.clear()
        style_axes(ax)
        cumulative = (1.0 + perf).cumprod()
        peak = cumulative.cummax()
        drawdown = (cumulative / peak) - 1.0
        ax.plot(drawdown.index, drawdown.values, color=COLOR_NEGATIVE, linewidth=1.2)
        ax.fill_between(drawdown.index, drawdown.values, 0.0, color=COLOR_NEGATIVE, alpha=0.18)
        ax.set_title(title)
        self._format_date_axis(ax)
        self._style_ticks(ax)
        target.figure.tight_layout(pad=1.0)
        target.draw_idle()

    def _plot_rolling_vol(
        self,
        perf: pd.Series,
        canvas: MplCanvas | None = None,
        title: str = "Rolling Vol (21D)",
        timeframe: str = "MAX",
    ) -> None:
        target = canvas or self.left_canvas
        ax = target.axes
        ax.clear()
        style_axes(ax)
        rolling = perf.rolling(21).std() * np.sqrt(252.0)
        rolling = self._slice_series(rolling.dropna(), timeframe)
        if rolling.empty:
            target.show_message("Not enough observations for rolling vol")
            return
        ax.plot(rolling.index, rolling.values, color=COLOR_PRIMARY, linewidth=1.25)
        ax.set_title(title)
        self._format_date_axis(ax)
        self._style_ticks(ax)
        target.figure.tight_layout(pad=1.0)
        target.draw_idle()

    def _plot_rolling_beta(
        self,
        perf: pd.Series,
        benchmark_returns: pd.Series,
        benchmark_symbol: str,
        canvas: MplCanvas,
        timeframe: str = "MAX",
    ) -> None:
        aligned = pd.concat([perf.rename("portfolio"), benchmark_returns.rename("benchmark")], axis=1, join="inner").dropna()
        if len(aligned) < 21:
            canvas.show_message(f"Not enough overlap for rolling beta vs {benchmark_symbol}")
            return
        portfolio_s = aligned["portfolio"]
        benchmark_s = aligned["benchmark"]
        rolling_beta = portfolio_s.rolling(63).cov(benchmark_s) / benchmark_s.rolling(63).var()
        rolling_corr = portfolio_s.rolling(63).corr(benchmark_s)
        rolling_beta = self._slice_series(rolling_beta.dropna(), timeframe)
        rolling_corr = self._slice_series(rolling_corr.dropna(), timeframe)
        if rolling_beta.empty:
            canvas.show_message(f"Not enough overlap for rolling beta vs {benchmark_symbol}")
            return

        ax = canvas.axes
        ax.clear()
        style_axes(ax)
        ax.plot(rolling_beta.index, rolling_beta.values, color=COLOR_PRIMARY, linewidth=1.25, label="Rolling Beta")
        if not rolling_corr.empty:
            ax.plot(
                rolling_corr.index,
                rolling_corr.values,
                color=COLOR_BENCHMARK,
                linewidth=1.05,
                linestyle="--",
                label="Rolling Corr",
            )
        ax.set_title(f"Rolling Beta / Corr vs {benchmark_symbol} (63D)")
        self._format_date_axis(ax)
        self._style_legend(ax)
        self._style_ticks(ax)
        canvas.figure.tight_layout(pad=1.0)
        canvas.draw_idle()

    def _plot_price_chart(self, price_series: pd.Series, canvas: MplCanvas, title: str) -> None:
        ax = canvas.axes
        ax.clear()
        style_axes(ax)
        if price_series.empty:
            canvas.show_message("No price history")
            return
        ax.plot(price_series.index, price_series.values, color=COLOR_BENCHMARK, linewidth=1.2)
        ax.set_title(title)
        self._format_date_axis(ax)
        self._style_ticks(ax)
        canvas.figure.tight_layout(pad=1.0)
        canvas.draw_idle()

    @staticmethod
    def _annualized_return(perf: pd.Series) -> float | None:
        if perf.empty:
            return None
        cumulative = float((1.0 + perf).prod())
        periods = int(len(perf))
        if periods <= 0 or cumulative <= 0:
            return None
        return float(cumulative ** (252.0 / periods) - 1.0)

    @staticmethod
    def _beta_corr(perf: pd.Series, benchmark_returns: pd.Series) -> tuple[float | None, float | None]:
        if perf.empty or benchmark_returns.empty:
            return None, None
        aligned = pd.concat([perf.rename("p"), benchmark_returns.rename("b")], axis=1, join="inner").dropna()
        if len(aligned) < 2:
            return None, None
        benchmark_var = float(aligned["b"].var())
        corr = float(aligned["p"].corr(aligned["b"])) if len(aligned) > 1 else None
        if benchmark_var <= 0:
            return None, corr
        cov = float(aligned["p"].cov(aligned["b"]))
        return cov / benchmark_var, corr

    @staticmethod
    def _effective_positions(weights: pd.Series) -> float:
        if weights.empty:
            return 0.0
        normalized = weights.abs()
        total = float(normalized.sum())
        if total <= 0:
            return 0.0
        normalized = normalized / total
        hhi = float((normalized ** 2).sum())
        return float(1.0 / hhi) if hhi > 0 else 0.0

    def _emit_open_risk(self) -> None:
        if self._latest_result.snapshot is None or self._latest_result.perf.empty:
            self._add_message("Run a research analysis first")
            return
        self.open_risk_requested.emit()

    def _emit_open_iv_surface(self) -> None:
        if self._latest_result.snapshot is None:
            self._add_message("Run a research analysis first")
            return
        if not can_forward_research_to_iv(self._latest_result.scope_type):
            self._add_message("IV surface forwarding is only available for single-ticker research")
            return
        self.open_iv_surface_requested.emit()

    def _on_benchmark_symbol_changed(self) -> None:
        text = self.benchmark_input.text().strip().upper() or "SPY"
        self.benchmark_input.setText(text)
        if self._latest_result.snapshot is not None and not self._latest_result.perf.empty:
            self.apply_scope()

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.scope_combo.setEnabled(enabled)
        self.single_symbol_input.setEnabled(enabled)
        self.apply_single_btn.setEnabled(enabled)
        self.reset_scope_btn.setEnabled(enabled)
        self.synthetic_table.setEnabled(enabled)
        self.add_row_btn.setEnabled(enabled)
        self.remove_row_btn.setEnabled(enabled)
        self.normalize_btn.setEnabled(enabled)
        self.apply_synth_btn.setEnabled(enabled)
        self.reset_synth_btn.setEnabled(enabled)
        self.left_chart_combo.setEnabled(enabled)
        self.right_chart_combo.setEnabled(enabled)
        self.timeframe_combo.setEnabled(enabled)
        self.benchmark_input.setEnabled(enabled)
        self.benchmark_check.setEnabled(enabled)

    def _reset_dashboard(self, empty_message: str = "Apply research scope") -> None:
        self._latest_result = ResearchAnalysisResult(
            scope_type=ResearchScopeType.NONE,
            snapshot=None,
            perf=pd.Series(dtype=float),
            benchmark_returns=pd.Series(dtype=float),
            benchmark_symbol=self.benchmark_input.text().strip().upper() or "SPY",
            weights=pd.Series(dtype=float),
            primary_price=pd.Series(dtype=float),
            warnings=[],
        )
        for label in (
            self.total_return_value,
            self.annual_return_value,
            self.annual_vol_value,
            self.max_dd_value,
            self.beta_value,
            self.corr_value,
        ):
            label.setText("N/A")
        self.scope_summary_label.setText("Scope: N/A")
        self.asset_count_label.setText("Names: N/A")
        self.top_weight_label.setText("Top Weight: N/A")
        self.effective_positions_label.setText("Effective Positions: N/A")
        self.benchmark_status_label.setText("Benchmark: N/A")
        self.observation_label.setText("Observations: N/A")
        self.structure_table.setRowCount(0)
        self.message_area.clear()
        self.left_canvas.show_message(empty_message)
        self.right_canvas.show_message(empty_message)
        self.open_risk_btn.setEnabled(False)
        self.open_iv_btn.setEnabled(False)
        self.status_label.setText("Status: Idle")

    def shell_status_text(self) -> str:
        return self.status_label.text()

    def shell_active_symbol(self) -> str:
        symbol = (self.app_context.primary_symbol or "").strip().upper()
        if symbol:
            return symbol
        if self.scope_combo.currentText() == "Single Ticker":
            return self.single_symbol_input.text().strip().upper() or "--"
        return "Synthetic Basket"

    @staticmethod
    def _style_ticks(ax) -> None:
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_color(MUTED_TEXT)

    @staticmethod
    def _format_date_axis(ax) -> None:
        locator = mdates.AutoDateLocator(minticks=4, maxticks=7)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))

    @staticmethod
    def _style_legend(ax) -> None:
        legend = ax.legend(loc="upper left")
        if legend is not None:
            for text in legend.get_texts():
                text.set_color(TEXT_COLOR)

    def _add_message(self, msg: str) -> None:
        current = self.message_area.toPlainText().strip()
        if current:
            self.message_area.setPlainText(current + "\n" + msg)
        else:
            self.message_area.setPlainText(msg)

    @staticmethod
    def _fmt_pct_value(value: float | None) -> str:
        if value is None or not np.isfinite(value):
            return "N/A"
        return f"{value * 100:.2f}%"

    @staticmethod
    def _fmt_number(value: float | None) -> str:
        if value is None or not np.isfinite(value):
            return "N/A"
        return f"{value:.3f}"

    def _fmt_currency_value(self, value: float | None) -> str:
        if value is None or not np.isfinite(value):
            return "N/A"
        return f"{value:,.2f} {self.base_currency}"

    def _on_error(self, msg: str) -> None:
        logger.error("Research overview error: %s", msg)
        self._set_controls_enabled(True)
        self.app_context.set_research_snapshot(None)
        self._reset_dashboard(empty_message="Research analysis failed")
        self.status_label.setText("Status: Error")
        self._add_message(msg.splitlines()[0] if msg else "Unknown worker error")

    def _slice_series(self, series: pd.Series, timeframe: str) -> pd.Series:
        if series.empty or timeframe == "MAX":
            return series
        days_map = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}
        days = days_map.get(timeframe, 365)
        cutoff = series.index.max() - pd.Timedelta(days=days)
        return series[series.index >= cutoff]
