from __future__ import annotations

from copy import deepcopy
import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd
from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QPlainTextEdit,
)

from src.application.risk_service import (
    RiskComputeRequest,
    RiskService,
)
from src.application.workspace_service import resolve_active_snapshot
from src.models.app_mode import AppMode
from src.models.portfolio import PortfolioSnapshot, RiskResults
from src.services.app_context import AppDataContext
from src.services.data_providers import AppDataProvider
from src.services.ibkr_client import IBKRClient
from src.services.market_data import MarketDataService
from src.services.mock_data import MockDataService
from src.services.risk_free_rate import RiskFreeRateService
from src.ui.plot_theme import (
    COLOR_NEGATIVE,
    COLOR_POSITIVE,
    COLOR_PRIMARY,
    COLOR_RISK,
    MUTED_TEXT,
    TEXT_COLOR,
    style_axes,
)
from src.ui.widgets.mpl_canvas import MplCanvas
from src.ui.widgets.worker import Worker


logger = logging.getLogger(__name__)

class RiskTab(QWidget):
    _MC_NUM_SIMULATIONS = 2000
    _CHART_MIN_HEIGHT = 280
    _CHART_MAX_HEIGHT = 320
    _DEFAULT_LABELS = {
        "hist_var_label": "Historical VaR (1D, covered): N/A",
        "hist_cvar_label": "Hist CVaR (covered): N/A",
        "param_var_label": "Parametric VaR (covered, \u221At): N/A",
        "hist_var_est_label": "Est Total Hist VaR (1D): N/A",
        "hist_cvar_est_label": "Est Total Hist CVaR: N/A",
        "param_var_est_label": "Est Total Param VaR (\u221At): N/A",
        "daily_vol_label": "Daily Vol: N/A",
        "annual_vol_label": "Annual Vol: N/A",
        "max_dd_label": "Max Drawdown: N/A",
        "beta_label": "Beta: N/A",
        "corr_label": "Correlation: N/A",
        "alpha_label": "Jensen Alpha (ann.): N/A",
        "coverage_label": "Risk-Basis Coverage: N/A",
        "obs_used_label": "Obs Used: N/A",
        "benchmark_overlap_label": "Benchmark Overlap: N/A",
        "hhi_label": "HHI: N/A",
        "top5_label": "Top-5 Weight: N/A",
        "effective_bets_label": "Effective Bets: N/A",
        "mc_summary_label": "Monte Carlo: N/A",
        "mc_var_label": "Monte Carlo VaR (covered): N/A",
        "mc_cvar_label": "Monte Carlo CVaR (covered): N/A",
        "mc_var_est_label": "Est Total Monte Carlo VaR: N/A",
        "mc_cvar_est_label": "Est Total Monte Carlo CVaR: N/A",
    }

    def __init__(
        self,
        client: IBKRClient,
        market_data: MarketDataService,
        mock_service: MockDataService,
        risk_free_service: RiskFreeRateService | None,
        risk_service: RiskService,
        base_currency: str,
        default_lookback: int,
        app_context: AppDataContext | None = None,
        data_provider: AppDataProvider | None = None,
    ) -> None:
        super().__init__()
        self.risk_service = risk_service
        self.base_currency = base_currency
        self.default_lookback = default_lookback
        self.app_context = app_context
        self.data_provider = data_provider
        self.thread_pool = QThreadPool()
        self.portfolio_snapshot: PortfolioSnapshot | None = None
        self._latest_request_id = 0
        if self.app_context is not None:
            self.app_context.research_snapshot_changed.connect(self._on_research_snapshot_changed)
            self.app_context.app_mode_changed.connect(self._on_app_mode_changed)

        self._build_ui()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)
        self.confidence_combo = QComboBox()
        self.confidence_combo.addItems(["90%", "95%", "99%"])
        self.confidence_combo.setCurrentText("95%")
        self.lookback_combo = QComboBox()
        self.lookback_combo.addItems(["126", "252", "504"])
        self.lookback_combo.setCurrentText(str(self.default_lookback))
        self.horizon_combo = QComboBox()
        self.horizon_combo.addItems(["1", "10", "21"])
        self.horizon_combo.setCurrentText("1")
        self.benchmark_input = QLineEdit("SPY")
        self.benchmark_input.setMaximumWidth(90)
        self.beta_window_combo = QComboBox()
        self.beta_window_combo.addItems(["63", "126", "252"])
        self.beta_window_combo.setCurrentText("126")
        self.compute_btn = QPushButton("Compute Risk")
        self.compute_btn.clicked.connect(self.compute)
        self.status_label = QLabel("Status: Idle")
        controls.addWidget(QLabel("Confidence"))
        controls.addWidget(self.confidence_combo)
        controls.addWidget(QLabel("Lookback (days)"))
        controls.addWidget(self.lookback_combo)
        controls.addWidget(QLabel("Horizon (days)"))
        controls.addWidget(self.horizon_combo)
        controls.addWidget(QLabel("Benchmark"))
        controls.addWidget(self.benchmark_input)
        controls.addWidget(QLabel("Beta Window"))
        controls.addWidget(self.beta_window_combo)
        controls.addStretch()
        controls.addWidget(self.compute_btn)
        controls.addWidget(self.status_label)
        layout.addLayout(controls)

        self.summary_row_widget = QWidget()
        summary_row = QHBoxLayout()
        summary_row.setContentsMargins(0, 0, 0, 0)
        summary_row.setSpacing(6)
        self.warning_summary_label = QLabel("")
        self.warning_summary_label.setVisible(False)
        self.details_toggle_btn = QToolButton()
        self.details_toggle_btn.setText("Details")
        self.details_toggle_btn.setCheckable(True)
        self.details_toggle_btn.setChecked(False)
        self.details_toggle_btn.setArrowType(Qt.RightArrow)
        self.details_toggle_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.details_toggle_btn.clicked.connect(self._toggle_details)
        self.details_toggle_btn.setVisible(False)
        summary_row.addWidget(self.warning_summary_label)
        summary_row.addStretch()
        summary_row.addWidget(self.details_toggle_btn)
        self.summary_row_widget.setLayout(summary_row)
        self.summary_row_widget.setVisible(False)
        self.summary_row_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(self.summary_row_widget)

        metrics_box = QGroupBox("Risk Metrics")
        metrics_layout = QGridLayout()
        metrics_layout.setContentsMargins(8, 6, 8, 6)
        metrics_layout.setHorizontalSpacing(10)
        metrics_layout.setVerticalSpacing(3)
        self.hist_var_label = QLabel("Historical VaR (1D, covered): N/A")
        self.hist_cvar_label = QLabel("Hist CVaR (covered): N/A")
        self.param_var_label = QLabel("Parametric VaR (covered, \u221At): N/A")
        self.hist_var_est_label = QLabel("Est Total Hist VaR (1D): N/A")
        self.hist_cvar_est_label = QLabel("Est Total Hist CVaR: N/A")
        self.param_var_est_label = QLabel("Est Total Param VaR (\u221At): N/A")
        self.daily_vol_label = QLabel("Daily Vol: N/A")
        self.annual_vol_label = QLabel("Annual Vol: N/A")
        self.max_dd_label = QLabel("Max Drawdown: N/A")
        self.beta_label = QLabel("Beta: N/A")
        self.corr_label = QLabel("Correlation: N/A")
        self.alpha_label = QLabel("Jensen Alpha (ann.): N/A")
        self.coverage_label = QLabel("Risk-Basis Coverage: N/A")
        self.obs_used_label = QLabel("Obs Used: N/A")
        self.benchmark_overlap_label = QLabel("Benchmark Overlap: N/A")
        metrics_layout.addWidget(self.hist_var_label, 0, 0)
        metrics_layout.addWidget(self.hist_cvar_label, 0, 1)
        metrics_layout.addWidget(self.param_var_label, 0, 2)
        metrics_layout.addWidget(self.hist_var_est_label, 1, 0)
        metrics_layout.addWidget(self.hist_cvar_est_label, 1, 1)
        metrics_layout.addWidget(self.param_var_est_label, 1, 2)
        metrics_layout.addWidget(self.daily_vol_label, 2, 0)
        metrics_layout.addWidget(self.annual_vol_label, 2, 1)
        metrics_layout.addWidget(self.max_dd_label, 2, 2)
        metrics_layout.addWidget(self.beta_label, 3, 0)
        metrics_layout.addWidget(self.corr_label, 3, 1)
        metrics_layout.addWidget(self.alpha_label, 3, 2)
        metrics_layout.addWidget(self.coverage_label, 4, 0)
        metrics_layout.addWidget(self.obs_used_label, 4, 1)
        metrics_layout.addWidget(self.benchmark_overlap_label, 4, 2)
        metrics_box.setLayout(metrics_layout)
        metrics_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        layout.addWidget(metrics_box)

        concentration_box = QGroupBox("Risk Concentration")
        concentration_layout = QGridLayout()
        concentration_layout.setContentsMargins(8, 6, 8, 6)
        concentration_layout.setHorizontalSpacing(10)
        concentration_layout.setVerticalSpacing(2)
        self.hhi_label = QLabel("HHI: N/A")
        self.top5_label = QLabel("Top-5 Weight: N/A")
        self.effective_bets_label = QLabel("Effective Bets: N/A")
        concentration_layout.addWidget(self.hhi_label, 0, 0)
        concentration_layout.addWidget(self.top5_label, 0, 1)
        concentration_layout.addWidget(self.effective_bets_label, 0, 2)
        concentration_box.setLayout(concentration_layout)
        concentration_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        layout.addWidget(concentration_box)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "Symbol",
                "Weight",
                "Daily Vol",
                "% of Portfolio Variance",
                "MCTR",
                "Component VaR",
                "Variance Bar",
            ]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(self.table)

        self.excluded_box = QGroupBox("Excluded Assets")
        excluded_layout = QVBoxLayout()
        self.excluded_table = QTableWidget(0, 2)
        self.excluded_table.setHorizontalHeaderLabels(["Symbol", "Reason"])
        self.excluded_table.horizontalHeader().setStretchLastSection(True)
        self.excluded_table.setMaximumHeight(120)
        excluded_layout.addWidget(self.excluded_table)
        self.excluded_box.setLayout(excluded_layout)
        self.excluded_box.setVisible(False)

        charts_box = QGroupBox("Charts")
        charts_layout = QGridLayout()
        hist_layout = QVBoxLayout()
        hist_label = QLabel("Returns Histogram")
        hist_label.setObjectName("chartSectionLabel")
        hist_layout.addWidget(hist_label)
        self.hist_canvas = MplCanvas(width=5, height=3)
        self.hist_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.hist_canvas.setMinimumHeight(self._CHART_MIN_HEIGHT)
        self.hist_canvas.setMaximumHeight(self._CHART_MAX_HEIGHT)
        hist_layout.addWidget(self.hist_canvas)

        drawdown_layout = QVBoxLayout()
        drawdown_label = QLabel("Drawdown Curve")
        drawdown_label.setObjectName("chartSectionLabel")
        drawdown_layout.addWidget(drawdown_label)
        self.cum_canvas = MplCanvas(width=5, height=3)
        self.cum_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.cum_canvas.setMinimumHeight(self._CHART_MIN_HEIGHT)
        self.cum_canvas.setMaximumHeight(self._CHART_MAX_HEIGHT)
        drawdown_layout.addWidget(self.cum_canvas)

        charts_layout.addLayout(hist_layout, 0, 0)
        charts_layout.addLayout(drawdown_layout, 0, 1)
        charts_box.setLayout(charts_layout)
        charts_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(charts_box)

        mc_box = QGroupBox("Monte Carlo VaR")
        mc_layout = QVBoxLayout()
        mc_controls = QHBoxLayout()
        mc_controls.setContentsMargins(0, 0, 0, 0)
        mc_controls.setSpacing(6)
        self.mc_horizon_combo = QComboBox()
        self.mc_horizon_combo.addItems(["1", "5", "10", "21", "63"])
        self.mc_horizon_combo.setCurrentText("10")
        self.mc_model_combo = QComboBox()
        self.mc_model_combo.addItems(["Gaussian", "Bootstrap"])
        self.mc_model_combo.setCurrentText("Gaussian")
        self.mc_simulations_combo = QComboBox()
        self.mc_simulations_combo.addItems(["1000", "2000", "5000"])
        self.mc_simulations_combo.setCurrentText(str(self._MC_NUM_SIMULATIONS))
        mc_controls.addWidget(QLabel("Horizon (days)"))
        mc_controls.addWidget(self.mc_horizon_combo)
        mc_controls.addWidget(QLabel("Model"))
        mc_controls.addWidget(self.mc_model_combo)
        mc_controls.addWidget(QLabel("Simulations"))
        mc_controls.addWidget(self.mc_simulations_combo)
        mc_controls.addStretch()
        mc_layout.addLayout(mc_controls)

        mc_metrics_layout = QGridLayout()
        mc_metrics_layout.setContentsMargins(0, 0, 0, 0)
        mc_metrics_layout.setHorizontalSpacing(10)
        mc_metrics_layout.setVerticalSpacing(3)
        self.mc_summary_label = QLabel("Monte Carlo: N/A")
        self.mc_var_label = QLabel("Monte Carlo VaR (covered): N/A")
        self.mc_cvar_label = QLabel("Monte Carlo CVaR (covered): N/A")
        self.mc_var_est_label = QLabel("Est Total Monte Carlo VaR: N/A")
        self.mc_cvar_est_label = QLabel("Est Total Monte Carlo CVaR: N/A")
        mc_metrics_layout.addWidget(self.mc_summary_label, 0, 0, 1, 2)
        mc_metrics_layout.addWidget(self.mc_var_label, 1, 0)
        mc_metrics_layout.addWidget(self.mc_cvar_label, 1, 1)
        mc_metrics_layout.addWidget(self.mc_var_est_label, 2, 0)
        mc_metrics_layout.addWidget(self.mc_cvar_est_label, 2, 1)
        mc_layout.addLayout(mc_metrics_layout)

        mc_charts_layout = QGridLayout()
        mc_hist_layout = QVBoxLayout()
        mc_hist_label = QLabel("Monte Carlo Terminal Return Histogram")
        mc_hist_label.setObjectName("chartSectionLabel")
        mc_hist_layout.addWidget(mc_hist_label)
        self.mc_hist_canvas = MplCanvas(width=5, height=3)
        self.mc_hist_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.mc_hist_canvas.setMinimumHeight(self._CHART_MIN_HEIGHT)
        self.mc_hist_canvas.setMaximumHeight(self._CHART_MAX_HEIGHT)
        mc_hist_layout.addWidget(self.mc_hist_canvas)

        mc_fan_layout = QVBoxLayout()
        mc_fan_label = QLabel("Monte Carlo Fan Chart")
        mc_fan_label.setObjectName("chartSectionLabel")
        mc_fan_layout.addWidget(mc_fan_label)
        self.mc_fan_canvas = MplCanvas(width=5, height=3)
        self.mc_fan_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.mc_fan_canvas.setMinimumHeight(self._CHART_MIN_HEIGHT)
        self.mc_fan_canvas.setMaximumHeight(self._CHART_MAX_HEIGHT)
        mc_fan_layout.addWidget(self.mc_fan_canvas)

        mc_charts_layout.addLayout(mc_hist_layout, 0, 0)
        mc_charts_layout.addLayout(mc_fan_layout, 0, 1)
        mc_layout.addLayout(mc_charts_layout)
        mc_box.setLayout(mc_layout)
        mc_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(mc_box)

        self.messages_box = QGroupBox("Messages")
        messages_layout = QVBoxLayout()
        self.message_area = QPlainTextEdit()
        self.message_area.setReadOnly(True)
        self.message_area.setMaximumHeight(80)
        messages_layout.addWidget(self.message_area)
        self.messages_box.setLayout(messages_layout)
        self.messages_box.setVisible(False)
        self.messages_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        self.details_panel = QWidget()
        details_layout = QVBoxLayout()
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(4)
        details_layout.addWidget(self.excluded_box)
        details_layout.addWidget(self.messages_box)
        self.details_panel.setLayout(details_layout)
        self.details_panel.setVisible(False)
        self.details_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        layout.addWidget(self.details_panel)

        layout.addStretch(1)

        content.setLayout(layout)
        self.scroll.setWidget(content)
        root_layout.addWidget(self.scroll)

        self.setLayout(root_layout)
        self._fit_contrib_table_height()

    def set_portfolio_snapshot(self, snapshot: PortfolioSnapshot | None) -> None:
        self.portfolio_snapshot = snapshot

    def set_data_provider(self, provider: AppDataProvider) -> None:
        self.data_provider = provider

    def _on_research_snapshot_changed(self, snapshot: PortfolioSnapshot | None) -> None:
        if self.app_context is not None and self.app_context.app_mode == AppMode.RESEARCH and snapshot is None:
            self.clear_results(status="Status: Idle")

    def _on_app_mode_changed(self, _mode: str) -> None:
        self.clear_results(status="Status: Idle")

    def _active_snapshot(self) -> PortfolioSnapshot | None:
        if self.app_context is None:
            return self.portfolio_snapshot
        return resolve_active_snapshot(
            self.app_context.app_mode,
            self.portfolio_snapshot,
            self.app_context.research_snapshot,
        )

    def compute(self) -> None:
        snapshot = self._active_snapshot()
        if snapshot is None:
            self.clear_results(status="Status: Idle")
            self._add_message("No snapshot yet")
            return
        self._latest_request_id += 1
        request_id = self._latest_request_id
        request = self._build_request(snapshot)
        self._set_controls_enabled(False)
        self.status_label.setText("Status: Computing...")
        worker = Worker(self._compute_worker, request_id, request)
        worker.signals.finished.connect(self._on_results)
        worker.signals.error.connect(self._on_error)
        worker.signals.progress.connect(self._on_progress)
        self.thread_pool.start(worker)

    def _build_request(self, snapshot: PortfolioSnapshot) -> RiskComputeRequest:
        return RiskComputeRequest(
            snapshot=deepcopy(snapshot),
            alpha=self._alpha(),
            lookback_days=int(self.lookback_combo.currentText()),
            horizon_days=int(self.horizon_combo.currentText()),
            mc_horizon_days=int(self.mc_horizon_combo.currentText()),
            mc_simulation_model=self.mc_model_combo.currentText(),
            mc_num_simulations=int(self.mc_simulations_combo.currentText()),
            beta_window=int(self.beta_window_combo.currentText()),
            benchmark_symbol=(self.benchmark_input.text().strip().upper() or "SPY"),
            base_currency=self.base_currency,
        )

    def _compute_worker(
        self, request_id: int, request: RiskComputeRequest, progress_cb=None
    ):
        payload = self.risk_service.compute(
            request,
            progress_cb=progress_cb,
            data_provider=self.data_provider,
        )
        return (
            request_id,
            payload.results,
            payload.portfolio_returns,
            payload.returns_df,
            payload.contributions,
            payload.weights,
            payload.marginal_contribution_to_risk,
            payload.component_var,
        )

    def _on_results(self, payload) -> None:
        request_id, results, port_ret, returns_df, contrib, weights, mctr, component_var = payload
        if request_id != self._latest_request_id:
            return
        self.status_label.setText("Status: Done")
        self._set_controls_enabled(True)
        self._update_metrics(results)
        self._update_table(returns_df, contrib, weights, mctr, component_var)
        self._update_excluded_assets(results.excluded_assets)
        self._plot_histogram(port_ret, results)
        self._plot_drawdown(port_ret)
        self._plot_monte_carlo_histogram(results)
        self._plot_monte_carlo_fan(results)
        self._show_warnings(results)

    def _update_metrics(self, results: RiskResults) -> None:
        self.hist_var_label.setText(self._fmt_currency("Historical VaR (1D, covered)", results.historical_var))
        self.hist_cvar_label.setText(self._fmt_currency("Hist CVaR (covered)", results.historical_cvar))
        self.param_var_label.setText(
            self._fmt_currency("Parametric VaR (covered, \u221At)", results.parametric_var)
        )
        self.hist_var_est_label.setText(
            self._fmt_currency("Est Total Hist VaR (1D)", results.historical_var_total_estimate)
        )
        self.hist_cvar_est_label.setText(
            self._fmt_currency("Est Total Hist CVaR", results.historical_cvar_total_estimate)
        )
        self.param_var_est_label.setText(
            self._fmt_currency("Est Total Param VaR (\u221At)", results.parametric_var_total_estimate)
        )
        summary = "Monte Carlo: N/A"
        if results.monte_carlo_model and results.monte_carlo_horizon_days and results.monte_carlo_num_simulations:
            summary = (
                f"Monte Carlo: {results.monte_carlo_model}, "
                f"{results.monte_carlo_horizon_days}D, "
                f"{results.monte_carlo_num_simulations:,} sims"
            )
        self.mc_summary_label.setText(summary)
        mc_label_suffix = (
            f"{results.monte_carlo_horizon_days or 'N/A'}D, covered, {results.monte_carlo_model or 'N/A'}"
        )
        self.mc_var_label.setText(
            self._fmt_currency(f"Monte Carlo VaR ({mc_label_suffix})", results.monte_carlo_var)
        )
        self.mc_cvar_label.setText(
            self._fmt_currency(f"Monte Carlo CVaR ({mc_label_suffix})", results.monte_carlo_cvar)
        )
        self.mc_var_est_label.setText(
            self._fmt_currency(
                (
                    "Est Total Monte Carlo VaR "
                    f"({results.monte_carlo_horizon_days or 'N/A'}D, {results.monte_carlo_model or 'N/A'})"
                ),
                results.monte_carlo_var_total_estimate,
            )
        )
        self.mc_cvar_est_label.setText(
            self._fmt_currency(
                (
                    "Est Total Monte Carlo CVaR "
                    f"({results.monte_carlo_horizon_days or 'N/A'}D, {results.monte_carlo_model or 'N/A'})"
                ),
                results.monte_carlo_cvar_total_estimate,
            )
        )
        self.daily_vol_label.setText(self._fmt_pct("Daily Vol", results.daily_vol))
        self.annual_vol_label.setText(self._fmt_pct("Annual Vol", results.annual_vol))
        self.max_dd_label.setText(self._fmt_pct("Max Drawdown", results.max_drawdown))
        self.beta_label.setText(self._fmt_number("Beta", results.beta))
        self.corr_label.setText(self._fmt_number("Correlation", results.correlation))
        self.alpha_label.setText(self._fmt_pct("Jensen Alpha (ann.)", results.alpha_annual))
        self.coverage_label.setText(self._fmt_pct("Risk-Basis Coverage", results.risk_coverage_ratio))
        self.obs_used_label.setText(self._fmt_int("Obs Used", results.aligned_obs_count))
        self.benchmark_overlap_label.setText(self._fmt_int("Benchmark Overlap", results.benchmark_overlap_count))
        self.hhi_label.setText(self._fmt_number("HHI", results.concentration_hhi))
        self.top5_label.setText(self._fmt_pct("Top-5 Weight", results.top5_weight))
        self.effective_bets_label.setText(self._fmt_number("Effective Bets", results.effective_bets))

    def _update_table(
        self,
        returns_df: pd.DataFrame,
        contrib: pd.Series,
        weights: pd.Series,
        mctr: pd.Series,
        component_var: pd.Series,
    ) -> None:
        self.table.setRowCount(0)
        if returns_df.empty:
            self._fit_contrib_table_height()
            return
        symbols = list(returns_df.columns)
        if not contrib.empty:
            symbols.sort(key=lambda s: float(contrib.get(s, np.nan)), reverse=True)
        for symbol in symbols:
            row = self.table.rowCount()
            self.table.insertRow(row)
            weight = weights.get(symbol, np.nan)
            daily_vol = returns_df[symbol].std()
            rc = contrib.get(symbol, np.nan)
            mctr_value = mctr.get(symbol, np.nan)
            component_var_value = component_var.get(symbol, np.nan)
            self.table.setItem(row, 0, QTableWidgetItem(symbol))
            self.table.setItem(row, 1, QTableWidgetItem(self._fmt_pct_value(weight)))
            self.table.setItem(row, 2, QTableWidgetItem(self._fmt_pct_value(daily_vol)))
            self.table.setItem(row, 3, QTableWidgetItem(self._fmt_pct_value(rc)))
            self.table.setItem(row, 4, QTableWidgetItem(self._fmt_number_value(mctr_value)))
            self.table.setItem(row, 5, QTableWidgetItem(self._fmt_currency_value(component_var_value)))
            bar = self._make_contrib_bar(rc)
            self.table.setCellWidget(row, 6, bar)
        self._fit_contrib_table_height()

    def _update_excluded_assets(self, excluded: Dict[str, str]) -> None:
        self.excluded_table.setRowCount(0)
        if not excluded:
            self.excluded_box.setTitle("Excluded Assets")
            self.excluded_box.setVisible(False)
            self._refresh_details_ui()
            return
        self.excluded_box.setVisible(True)
        self.excluded_box.setTitle(f"Excluded Assets ({len(excluded)})")
        for symbol, reason in sorted(excluded.items()):
            row = self.excluded_table.rowCount()
            self.excluded_table.insertRow(row)
            self.excluded_table.setItem(row, 0, QTableWidgetItem(symbol))
            self.excluded_table.setItem(row, 1, QTableWidgetItem(reason))
        self._refresh_details_ui()

    def _plot_histogram(self, port_ret: pd.Series, results: RiskResults) -> None:
        ax = self.hist_canvas.axes
        ax.clear()
        style_axes(ax)
        if port_ret.empty:
            self._show_plot_message(self.hist_canvas, "No returns")
            return

        values = port_ret.dropna().values
        ax.hist(values, bins=30, color=MUTED_TEXT, alpha=0.85, edgecolor="#0b0d0f")
        denom = results.covered_portfolio_value if results.covered_portfolio_value is not None else results.portfolio_value
        if denom and results.historical_var:
            var_line = -results.historical_var / denom
            ax.axvline(var_line, color=COLOR_RISK, linestyle="--", linewidth=1.4, label="Hist VaR")
        if denom and results.parametric_var:
            var_line = -results.parametric_var / denom
            ax.axvline(var_line, color=COLOR_RISK, linestyle=":", linewidth=1.4, label="Param VaR")
        ax.set_title("Portfolio Returns Histogram")
        ax.set_xlabel("Return")
        ax.set_ylabel("Frequency")
        if ax.get_legend_handles_labels()[0]:
            legend = ax.legend(frameon=False, loc="upper right")
            for text in legend.get_texts():
                text.set_color(TEXT_COLOR)
        self.hist_canvas.figure.tight_layout(pad=1.0)
        self.hist_canvas.draw_idle()

    def _plot_drawdown(self, port_ret: pd.Series) -> None:
        ax = self.cum_canvas.axes
        ax.clear()
        style_axes(ax)
        if port_ret.empty:
            self._show_plot_message(self.cum_canvas, "No returns")
            return

        cumulative = (1 + port_ret).cumprod()
        peak = cumulative.cummax()
        drawdown = (cumulative / peak) - 1.0

        ax.plot(drawdown.index, drawdown.values, color=COLOR_NEGATIVE, linewidth=1.25)
        ax.fill_between(drawdown.index, drawdown.values, 0.0, color=COLOR_NEGATIVE, alpha=0.18)
        ax.axhline(0.0, color=MUTED_TEXT, linewidth=0.8, linestyle="--", alpha=0.7)
        ax.set_title("Portfolio Drawdown (Underwater)")
        ax.set_xlabel("Date")
        ax.set_ylabel("Drawdown")
        self.cum_canvas.figure.autofmt_xdate()
        self.cum_canvas.figure.tight_layout(pad=1.0)
        self.cum_canvas.draw_idle()

    def _plot_monte_carlo_histogram(self, results: RiskResults) -> None:
        ax = self.mc_hist_canvas.axes
        ax.clear()
        style_axes(ax)
        terminal_returns = results.monte_carlo_terminal_returns
        if terminal_returns is None or terminal_returns.empty:
            self._show_plot_message(self.mc_hist_canvas, "Monte Carlo unavailable")
            return

        values = terminal_returns.dropna().to_numpy(dtype=float)
        ax.hist(values, bins=35, color=COLOR_PRIMARY, alpha=0.7, edgecolor="#0b0d0f")
        denom = results.covered_portfolio_value if results.covered_portfolio_value is not None else results.portfolio_value
        if denom and results.monte_carlo_var:
            ax.axvline(-results.monte_carlo_var / denom, color=COLOR_RISK, linestyle="--", linewidth=1.4, label="MC VaR")
        if denom and results.monte_carlo_cvar:
            ax.axvline(
                -results.monte_carlo_cvar / denom,
                color=COLOR_NEGATIVE,
                linestyle=":",
                linewidth=1.4,
                label="MC CVaR",
            )
        ax.set_title(
            f"{results.monte_carlo_model or 'Monte Carlo'} Terminal Returns ({results.monte_carlo_horizon_days or 'N/A'}D)"
        )
        ax.set_xlabel("Terminal return")
        ax.set_ylabel("Frequency")
        if ax.get_legend_handles_labels()[0]:
            legend = ax.legend(frameon=False, loc="upper left")
            for text in legend.get_texts():
                text.set_color(TEXT_COLOR)
        self.mc_hist_canvas.figure.tight_layout(pad=1.0)
        self.mc_hist_canvas.draw_idle()

    def _plot_monte_carlo_fan(self, results: RiskResults) -> None:
        ax = self.mc_fan_canvas.axes
        ax.clear()
        style_axes(ax)
        fan_df = results.monte_carlo_fan_percentiles
        if fan_df is None or fan_df.empty:
            self._show_plot_message(self.mc_fan_canvas, "Monte Carlo unavailable")
            return

        sample_paths = results.monte_carlo_sample_paths
        if sample_paths is not None and not sample_paths.empty:
            for column in sample_paths.columns:
                ax.plot(
                    sample_paths.index,
                    sample_paths[column],
                    color=COLOR_PRIMARY,
                    alpha=0.12,
                    linewidth=0.8,
                )

        x_values = fan_df.index.to_numpy(dtype=float)
        if {"p05", "p95"}.issubset(fan_df.columns):
            ax.fill_between(x_values, fan_df["p05"], fan_df["p95"], color=COLOR_PRIMARY, alpha=0.12, linewidth=0.0)
        if {"p25", "p75"}.issubset(fan_df.columns):
            ax.fill_between(x_values, fan_df["p25"], fan_df["p75"], color=COLOR_PRIMARY, alpha=0.22, linewidth=0.0)
        median_column = "p50" if "p50" in fan_df.columns else fan_df.columns[len(fan_df.columns) // 2]
        ax.plot(x_values, fan_df[median_column], color=TEXT_COLOR, linewidth=1.4, label="Median")
        ax.axhline(1.0, color=MUTED_TEXT, linewidth=0.8, linestyle="--", alpha=0.7)
        ax.set_title(
            f"{results.monte_carlo_model or 'Monte Carlo'} Fan Chart ({results.monte_carlo_horizon_days or 'N/A'}D)"
        )
        ax.set_xlabel("Day")
        ax.set_ylabel("Growth of 1.0")
        legend = ax.legend(frameon=False, loc="upper left")
        for text in legend.get_texts():
            text.set_color(TEXT_COLOR)
        self.mc_fan_canvas.figure.tight_layout(pad=1.0)
        self.mc_fan_canvas.draw_idle()

    def _show_plot_message(self, canvas: MplCanvas, message: str) -> None:
        ax = canvas.axes
        ax.clear()
        style_axes(ax)
        ax.text(0.5, 0.5, message, color=TEXT_COLOR, ha="center", va="center", transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])
        canvas.figure.tight_layout(pad=1.0)
        canvas.draw_idle()

    def _show_warnings(self, results: RiskResults) -> None:
        self.message_area.clear()
        for warning in results.warnings:
            self._add_message(warning)
        self._refresh_details_ui()

    def _on_progress(self, current: int, total: int, symbol: str) -> None:
        self.status_label.setText(f"Status: Loading {current}/{total} ({symbol})")

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.compute_btn.setEnabled(enabled)
        self.confidence_combo.setEnabled(enabled)
        self.lookback_combo.setEnabled(enabled)
        self.horizon_combo.setEnabled(enabled)
        self.mc_horizon_combo.setEnabled(enabled)
        self.mc_model_combo.setEnabled(enabled)
        self.mc_simulations_combo.setEnabled(enabled)
        self.benchmark_input.setEnabled(enabled)
        self.beta_window_combo.setEnabled(enabled)

    def _add_message(self, msg: str) -> None:
        current = self.message_area.toPlainText().strip()
        if current:
            self.message_area.setPlainText(current + "\n" + msg)
        else:
            self.message_area.setPlainText(msg)
        self._refresh_details_ui()

    def _on_error(self, msg: str) -> None:
        logger.error("Risk error: %s", msg)
        self._add_message(msg)
        self.status_label.setText("Status: Error")
        self._set_controls_enabled(True)

    def _alpha(self) -> float:
        text = self.confidence_combo.currentText().replace("%", "")
        return float(text) / 100.0

    def _fmt_currency(self, label: str, value: Optional[float]) -> str:
        if value is None:
            return f"{label}: N/A"
        return f"{label}: {value:,.2f} {self.base_currency}"

    def _fmt_pct(self, label: str, value: Optional[float]) -> str:
        if value is None:
            return f"{label}: N/A"
        return f"{label}: {value * 100:.2f}%"

    @staticmethod
    def _fmt_number(label: str, value: Optional[float]) -> str:
        if value is None:
            return f"{label}: N/A"
        return f"{label}: {value:.4f}"

    @staticmethod
    def _fmt_int(label: str, value: Optional[int]) -> str:
        if value is None:
            return f"{label}: N/A"
        return f"{label}: {int(value)}"

    @staticmethod
    def _fmt_pct_value(value: float | None) -> str:
        if value is None or np.isnan(value):
            return "N/A"
        return f"{value * 100:.2f}%"

    @staticmethod
    def _fmt_number_value(value: float | None) -> str:
        if value is None or np.isnan(value):
            return "N/A"
        return f"{value:.6f}"

    def _fmt_currency_value(self, value: float | None) -> str:
        if value is None or np.isnan(value):
            return "N/A"
        return f"{value:,.2f} {self.base_currency}"

    def _make_contrib_bar(self, value: float | None) -> QProgressBar:
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setAlignment(Qt.AlignCenter)
        bar.setTextVisible(False)
        bar.setMaximumHeight(14)
        bar.setStyleSheet("QProgressBar { border: 0; background: #2B2B2B; }")
        if value is None or np.isnan(value):
            bar.setValue(0)
            bar.setToolTip("N/A")
            return bar
        pct = value * 100
        scaled = int(min(abs(pct), 100))
        bar.setValue(scaled)
        bar.setToolTip(f"{pct:.2f}%")
        if value < 0:
            bar.setStyleSheet(
                "QProgressBar { border: 0; background: #2B2B2B; }"
                f"QProgressBar::chunk {{ background-color: {COLOR_NEGATIVE}; border: 0; }}"
            )
        else:
            bar.setStyleSheet(
                "QProgressBar { border: 0; background: #2B2B2B; }"
                f"QProgressBar::chunk {{ background-color: {COLOR_POSITIVE}; border: 0; }}"
            )
        return bar

    def _fit_contrib_table_height(self, visible_rows: int = 3) -> None:
        row_count = self.table.rowCount()
        target_rows = max(1, min(max(visible_rows, 1), row_count if row_count > 0 else visible_rows))
        header_h = self.table.horizontalHeader().height() if self.table.horizontalHeader() else 24
        row_h = 24
        if row_count > 0:
            row_h = max(self.table.rowHeight(0), 20)
        frame = self.table.frameWidth() * 2 + 6
        h_scroll = self.table.horizontalScrollBar().sizeHint().height() if self.table.horizontalScrollBar() else 0
        height = header_h + (target_rows * row_h) + frame + h_scroll
        self.table.setMinimumHeight(height)
        self.table.setMaximumHeight(height + 2)

    def _toggle_details(self, checked: bool) -> None:
        self.details_toggle_btn.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self._refresh_details_ui()

    def _refresh_details_ui(self) -> None:
        messages = [line.strip() for line in self.message_area.toPlainText().splitlines() if line.strip()]
        message_count = len(messages)
        excluded_count = int(self.excluded_table.rowCount())
        has_details = bool(message_count or excluded_count)

        self.messages_box.setVisible(message_count > 0)
        self.message_area.setVisible(message_count > 0)

        if message_count > 0:
            first = messages[0]
            suffix = f" | {first}" if first else ""
            if message_count > 1:
                self.warning_summary_label.setText(f"Warnings: {message_count}{suffix}")
            else:
                self.warning_summary_label.setText(f"Warning: {first}")
            self.warning_summary_label.setVisible(True)
        else:
            self.warning_summary_label.clear()
            self.warning_summary_label.setVisible(False)

        if has_details:
            parts = []
            if message_count:
                parts.append(f"W:{message_count}")
            if excluded_count:
                parts.append(f"X:{excluded_count}")
            suffix = f" ({', '.join(parts)})" if parts else ""
            self.details_toggle_btn.setText(f"Details{suffix}")
            self.details_toggle_btn.setVisible(True)
        else:
            self.details_toggle_btn.setText("Details")
            self.details_toggle_btn.setVisible(False)
            if self.details_toggle_btn.isChecked():
                self.details_toggle_btn.setChecked(False)
                self.details_toggle_btn.setArrowType(Qt.RightArrow)

        show_panel = has_details and self.details_toggle_btn.isChecked()
        self.details_panel.setVisible(show_panel)
        self.summary_row_widget.setVisible(self.warning_summary_label.isVisible() or self.details_toggle_btn.isVisible())

    def clear_results(self, status: str = "Status: Idle") -> None:
        self.status_label.setText(status)
        for attr, text in self._DEFAULT_LABELS.items():
            getattr(self, attr).setText(text)
        self.table.setRowCount(0)
        self._fit_contrib_table_height()
        self.excluded_table.setRowCount(0)
        self.excluded_box.setTitle("Excluded Assets")
        self.excluded_box.setVisible(False)
        self.message_area.clear()
        self.details_toggle_btn.setChecked(False)
        self.details_toggle_btn.setArrowType(Qt.RightArrow)
        self.hist_canvas.show_message("Compute risk to view results")
        self.cum_canvas.show_message("Compute risk to view drawdown")
        self.mc_hist_canvas.show_message("Compute risk to view Monte Carlo distribution")
        self.mc_fan_canvas.show_message("Compute risk to view Monte Carlo paths")
        self._refresh_details_ui()

    def shell_status_text(self) -> str:
        return self.status_label.text()

    def shell_active_symbol(self) -> str:
        if self.app_context is not None and self.app_context.primary_symbol:
            return self.app_context.primary_symbol
        return self.benchmark_input.text().strip().upper() or "Portfolio"
