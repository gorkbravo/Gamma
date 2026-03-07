from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import logging
from statistics import NormalDist
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from ib_insync import Contract
from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QPlainTextEdit,
)

from src.analytics.returns import align_prices, compute_returns
from src.analytics.risk_metrics import (
    compute_weights,
    max_drawdown,
    portfolio_returns,
    realized_vol,
    risk_contributions,
)
from src.analytics.var import historical_var_cvar, parametric_var
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


@dataclass(frozen=True)
class RiskComputeRequest:
    request_id: int
    snapshot: PortfolioSnapshot
    alpha: float
    lookback_days: int
    horizon_days: int
    beta_window: int
    benchmark_symbol: str
    base_currency: str
    recommended_min_obs: int = 60


@dataclass
class BenchmarkMetricsResult:
    beta: float | None = None
    correlation: float | None = None
    alpha_annual: float | None = None
    overlap_count: int | None = None
    warnings: List[str] = field(default_factory=list)


class RiskTab(QWidget):
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
        "coverage_label": "Risk Coverage: N/A",
        "obs_used_label": "Obs Used: N/A",
        "benchmark_overlap_label": "Benchmark Overlap: N/A",
        "hhi_label": "HHI: N/A",
        "top5_label": "Top-5 Weight: N/A",
        "effective_bets_label": "Effective Bets: N/A",
    }

    def __init__(
        self,
        client: IBKRClient,
        market_data: MarketDataService,
        mock_service: MockDataService,
        risk_free_service: RiskFreeRateService | None,
        base_currency: str,
        default_lookback: int,
        app_context: AppDataContext | None = None,
        data_provider: AppDataProvider | None = None,
    ) -> None:
        super().__init__()
        self.client = client
        self.market_data = market_data
        self.mock_service = mock_service
        self.risk_free_service = risk_free_service
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
        self.horizon_combo.addItems(["1", "10"])
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
        self.coverage_label = QLabel("Risk Coverage: N/A")
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
        self.hist_canvas.setMinimumHeight(170)
        self.hist_canvas.setMaximumHeight(190)
        hist_layout.addWidget(self.hist_canvas)

        cum_layout = QVBoxLayout()
        cum_label = QLabel("Drawdown Curve")
        cum_label.setObjectName("chartSectionLabel")
        cum_layout.addWidget(cum_label)
        self.cum_canvas = MplCanvas(width=5, height=3)
        self.cum_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.cum_canvas.setMinimumHeight(170)
        self.cum_canvas.setMaximumHeight(190)
        cum_layout.addWidget(self.cum_canvas)

        charts_layout.addLayout(hist_layout, 0, 0)
        charts_layout.addLayout(cum_layout, 0, 1)
        charts_box.setLayout(charts_layout)
        charts_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(charts_box)

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

        self.setLayout(layout)
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
        if self.app_context.app_mode == AppMode.RESEARCH:
            return self.app_context.research_snapshot
        return self.portfolio_snapshot

    def compute(self) -> None:
        if self._active_snapshot() is None:
            self.clear_results(status="Status: Idle")
            self._add_message("No snapshot yet")
            return
        request = self._build_request()
        self._latest_request_id = request.request_id
        self._set_controls_enabled(False)
        self.status_label.setText("Status: Computing...")
        worker = Worker(self._compute_worker, request)
        worker.signals.finished.connect(self._on_results)
        worker.signals.error.connect(self._on_error)
        worker.signals.progress.connect(self._on_progress)
        self.thread_pool.start(worker)

    def _build_request(self) -> RiskComputeRequest:
        snapshot = self._active_snapshot()
        if snapshot is None:
            raise ValueError("No snapshot")
        self._latest_request_id += 1
        return RiskComputeRequest(
            request_id=self._latest_request_id,
            snapshot=deepcopy(snapshot),
            alpha=self._alpha(),
            lookback_days=int(self.lookback_combo.currentText()),
            horizon_days=int(self.horizon_combo.currentText()),
            beta_window=int(self.beta_window_combo.currentText()),
            benchmark_symbol=(self.benchmark_input.text().strip().upper() or "SPY"),
            base_currency=self.base_currency,
        )

    def _compute_worker(
        self, request: RiskComputeRequest, progress_cb=None
    ) -> Tuple[int, RiskResults, pd.Series, pd.DataFrame, pd.Series, pd.Series, pd.Series, pd.Series]:
        snapshot = request.snapshot
        alpha = request.alpha
        lookback_days = request.lookback_days
        horizon_days = request.horizon_days
        beta_window = request.beta_window

        warnings: List[str] = []
        excluded_assets: Dict[str, str] = {}
        total_portfolio_value = snapshot.net_liquidation
        if total_portfolio_value is None:
            if snapshot.total_market_value is None and snapshot.total_cash is None:
                warnings.append("Portfolio value unavailable; using 0")
                total_portfolio_value = 0.0
            else:
                total_portfolio_value = (snapshot.total_market_value or 0.0) + (snapshot.total_cash or 0.0)
        if horizon_days > 1:
            warnings.append("Historical VaR/CVaR shown for 1d; parametric scaled by sqrt(time).")

        prices, missing = self._load_prices(snapshot, lookback_days, progress_cb)
        if missing:
            warnings.append(f"Missing history for: {', '.join(missing)}")
            for symbol in missing:
                excluded_assets[symbol] = "No historical bars"
        errors = self.market_data.drain_errors()
        if errors:
            warnings.extend(errors)

        price_df = align_prices(prices)
        returns_df = compute_returns(price_df)
        if returns_df.empty:
            warnings.append("No return history available")
            for symbol in prices.keys():
                excluded_assets.setdefault(symbol, "Insufficient overlapping history")

        returns_df = self._ensure_cash_returns(snapshot, returns_df)
        weights = self._weights_for_symbols(snapshot, returns_df.columns.tolist())
        for symbol in returns_df.columns:
            if symbol not in weights.index:
                excluded_assets.setdefault(symbol, "Missing base market value")
        if weights.empty:
            warnings.append("No weights available for VaR")

        risk_symbols = [symbol for symbol in returns_df.columns if symbol in weights.index]
        risk_returns_df = returns_df.reindex(columns=risk_symbols) if not returns_df.empty else pd.DataFrame()
        weights_aligned = weights.reindex(risk_symbols).dropna()
        if not risk_returns_df.empty:
            risk_returns_df = risk_returns_df.reindex(columns=weights_aligned.index.tolist())

        covered_portfolio_value = 0.0
        if not weights_aligned.empty:
            covered_symbols = set(weights_aligned.index)
            covered_portfolio_value = float(
                sum(
                    float(pos.base_market_value or 0.0)
                    for pos in snapshot.positions
                    if pos.symbol in covered_symbols and pos.base_market_value is not None
                )
            )
        elif total_portfolio_value == 0:
            covered_portfolio_value = 0.0

        port_ret = portfolio_returns(risk_returns_df, weights_aligned)
        if len(port_ret) < 2 and not returns_df.empty:
            warnings.append("Return series too short for stable risk metrics")
        if 0 < len(port_ret) < request.recommended_min_obs:
            warnings.append(
                f"Only {len(port_ret)} observations available ({request.recommended_min_obs} recommended minimum); "
                "interpret with care."
            )

        hist_var_r, hist_cvar_r = historical_var_cvar(port_ret, alpha)
        param_var_r = None
        cov = None
        if not risk_returns_df.empty and not weights_aligned.empty:
            cov_df = risk_returns_df.cov().reindex(index=weights_aligned.index, columns=weights_aligned.index)
            cov_values = cov_df.to_numpy(dtype=float, copy=True)
            if cov_values.size == 0 or not np.isfinite(cov_values).all():
                warnings.append("Parametric VaR unavailable: invalid covariance (NaN/insufficient data)")
            elif np.any(np.diag(cov_values) < -1e-12):
                warnings.append("Parametric VaR unavailable: covariance has negative diagonal variance")
            else:
                cov = cov_values
            param_var_r = parametric_var(weights_aligned.values, cov, alpha) if cov is not None else None
            if horizon_days > 1 and param_var_r is not None:
                param_var_r = param_var_r * (horizon_days ** 0.5)

        hist_var = hist_var_r * covered_portfolio_value if hist_var_r is not None else None
        hist_cvar = hist_cvar_r * covered_portfolio_value if hist_cvar_r is not None else None
        param_var = param_var_r * covered_portfolio_value if param_var_r is not None else None

        risk_coverage_ratio = None
        if total_portfolio_value is not None and total_portfolio_value > 0:
            risk_coverage_ratio = covered_portfolio_value / float(total_portfolio_value)
        scale_to_total = None
        if (
            hist_var is not None or hist_cvar is not None or param_var is not None
        ) and covered_portfolio_value and total_portfolio_value and covered_portfolio_value > 0:
            scale_to_total = float(total_portfolio_value) / float(covered_portfolio_value)
        hist_var_total_estimate = hist_var * scale_to_total if hist_var is not None and scale_to_total else None
        hist_cvar_total_estimate = hist_cvar * scale_to_total if hist_cvar is not None and scale_to_total else None
        param_var_total_estimate = param_var * scale_to_total if param_var is not None and scale_to_total else None
        if risk_coverage_ratio is not None and risk_coverage_ratio < 0.999:
            warnings.append(
                "Risk coverage is "
                f"{risk_coverage_ratio * 100:.1f}% of portfolio value; covered risk is exact for included assets and "
                "total VaR figures are coverage-scaled estimates."
            )
        if risk_coverage_ratio is not None and risk_coverage_ratio < 0.95:
            warnings.append("Risk coverage below 95%; headline risk estimates may be materially incomplete.")

        daily_vol, annual_vol = realized_vol(port_ret)
        max_dd = max_drawdown(port_ret)

        benchmark = self._beta_corr_alpha(
            port_ret=port_ret,
            lookback_days=lookback_days,
            beta_window=beta_window,
            base_currency=request.base_currency,
            benchmark_symbol=request.benchmark_symbol,
        )
        warnings.extend(benchmark.warnings)
        if benchmark.beta is None or benchmark.correlation is None:
            warnings.append("Benchmark beta/correlation unavailable")

        concentration_hhi, top5_weight, effective_bets = self._concentration_metrics(weights)

        results = RiskResults(
            alpha=alpha,
            lookback_days=lookback_days,
            horizon_days=horizon_days,
            portfolio_value=float(total_portfolio_value),
            historical_var=hist_var,
            historical_cvar=hist_cvar,
            parametric_var=param_var,
            daily_vol=daily_vol,
            annual_vol=annual_vol,
            max_drawdown=max_dd,
            beta=benchmark.beta,
            correlation=benchmark.correlation,
            alpha_annual=benchmark.alpha_annual,
            covered_portfolio_value=covered_portfolio_value,
            risk_coverage_ratio=risk_coverage_ratio,
            historical_var_total_estimate=hist_var_total_estimate,
            historical_cvar_total_estimate=hist_cvar_total_estimate,
            parametric_var_total_estimate=param_var_total_estimate,
            aligned_obs_count=int(len(port_ret)) if not port_ret.empty else 0,
            benchmark_overlap_count=benchmark.overlap_count,
            concentration_hhi=concentration_hhi,
            top5_weight=top5_weight,
            effective_bets=effective_bets,
            excluded_assets=excluded_assets,
            warnings=warnings,
        )

        contrib = pd.Series(dtype=float)
        mctr = pd.Series(dtype=float)
        component_var = pd.Series(dtype=float)
        if cov is not None and not weights_aligned.empty:
            contrib_values = risk_contributions(weights_aligned.values, cov)
            if contrib_values.size == weights_aligned.size:
                contrib = pd.Series(contrib_values, index=weights_aligned.index)
            portfolio_var = float(weights_aligned.values.T @ cov @ weights_aligned.values)
            if portfolio_var < 0 and abs(portfolio_var) < 1e-12:
                portfolio_var = 0.0
            portfolio_sigma = float(np.sqrt(portfolio_var)) if portfolio_var > 0 else 0.0
            if portfolio_sigma > 0:
                mctr_values = (cov @ weights_aligned.values) / portfolio_sigma
                mctr = pd.Series(mctr_values, index=weights_aligned.index)
                z = NormalDist().inv_cdf(alpha)
                component_var_values = weights_aligned.values * mctr_values * z
                if horizon_days > 1:
                    component_var_values = component_var_values * (horizon_days ** 0.5)
                component_var = pd.Series(component_var_values * covered_portfolio_value, index=weights_aligned.index)
            else:
                warnings.append("Risk contributions unavailable: non-positive portfolio variance")

        return request.request_id, results, port_ret, returns_df, contrib, weights, mctr, component_var

    def _load_prices(
        self, snapshot: PortfolioSnapshot, lookback_days: int, progress_cb=None
    ) -> Tuple[Dict[str, pd.Series], List[str]]:
        if self.data_provider is not None:
            return self.data_provider.load_prices(snapshot, lookback_days, progress_cb)
        if self.client.mock:
            prices: Dict[str, pd.Series] = {}
            missing: List[str] = []
            for pos in snapshot.positions:
                if pos.symbol.startswith("CASH"):
                    continue
                series = self.mock_service.load_history(pos.symbol)
                if series is None:
                    missing.append(pos.symbol)
                else:
                    prices[pos.symbol] = series
            return prices, missing

        contracts = self.client.get_contracts()
        return self.market_data.fetch_histories(contracts, lookback_days, progress_cb)

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

    def _weights_for_symbols(self, snapshot: PortfolioSnapshot, symbols: List[str]) -> pd.Series:
        values = {}
        for pos in snapshot.positions:
            if pos.symbol in symbols and pos.base_market_value is not None:
                values[pos.symbol] = pos.base_market_value
        series = pd.Series(values)
        weights = compute_weights(series)
        return weights

    def _beta_corr_alpha(
        self,
        port_ret: pd.Series,
        lookback_days: int,
        beta_window: int,
        base_currency: str,
        benchmark_symbol: str,
    ) -> BenchmarkMetricsResult:
        result = BenchmarkMetricsResult()
        benchmark_returns, benchmark_warnings = self._load_benchmark_returns(lookback_days, base_currency, benchmark_symbol)
        result.warnings.extend(benchmark_warnings)
        if benchmark_returns is None or benchmark_returns.empty or port_ret.empty:
            return result
        aligned = pd.concat(
            [port_ret.rename("portfolio"), benchmark_returns.rename("benchmark")],
            axis=1,
            join="inner",
        ).dropna()
        result.overlap_count = int(len(aligned))
        if len(aligned) < beta_window:
            result.warnings.append(
                f"Benchmark overlap {len(aligned)} < beta window {beta_window}; beta/correlation/Jensen alpha unavailable"
            )
            return result
        portfolio_s = aligned["portfolio"]
        benchmark_s = aligned["benchmark"]
        rolling_beta = portfolio_s.rolling(beta_window).cov(benchmark_s) / benchmark_s.rolling(beta_window).var()
        rolling_corr = portfolio_s.rolling(beta_window).corr(benchmark_s)
        beta = rolling_beta.dropna()
        corr = rolling_corr.dropna()
        if beta.empty or corr.empty:
            result.warnings.append("Benchmark beta/correlation unavailable after rolling window calculation")
            return result
        result.beta = float(beta.iloc[-1])
        result.correlation = float(corr.iloc[-1])

        base_ccy = str(base_currency or "").upper()
        if base_ccy != "USD":
            result.warnings.append(
                f"Jensen alpha unavailable for base currency {base_ccy or 'unknown'} (USD risk-free source only)."
            )
            return result
        if self.risk_free_service is None:
            result.warnings.append("Jensen alpha unavailable: risk-free service not configured")
            return result

        rf_series, rf_warnings = self.risk_free_service.get_usd_daily_returns(aligned.index.min(), aligned.index.max())
        result.warnings.extend(rf_warnings)
        if rf_series is None or rf_series.empty:
            result.warnings.append("Jensen alpha unavailable: no risk-free return series")
            return result
        aligned_rf = pd.concat([aligned, rf_series.rename("rf")], axis=1, join="inner").dropna()
        if len(aligned_rf) < beta_window:
            result.warnings.append(
                f"Risk-free aligned overlap {len(aligned_rf)} < beta window {beta_window}; Jensen alpha unavailable"
            )
            return result
        p_excess = aligned_rf["portfolio"] - aligned_rf["rf"]
        b_excess = aligned_rf["benchmark"] - aligned_rf["rf"]
        rolling_beta_excess = p_excess.rolling(beta_window).cov(b_excess) / b_excess.rolling(beta_window).var()
        rolling_alpha = p_excess.rolling(beta_window).mean() - rolling_beta_excess * b_excess.rolling(beta_window).mean()
        alpha_s = rolling_alpha.dropna()
        if alpha_s.empty:
            result.warnings.append("Jensen alpha unavailable after rolling excess-return calculation")
            return result
        result.alpha_annual = float(alpha_s.iloc[-1] * 252.0)
        return result

    def _load_benchmark_returns(
        self, lookback_days: int, base_currency: str, symbol: str
    ) -> tuple[pd.Series | None, List[str]]:
        warnings: List[str] = []
        if self.client.mock:
            series = self.mock_service.load_history(symbol)
        else:
            contract = Contract(symbol=symbol, secType="STK", exchange="SMART", currency="USD")
            series = self.market_data.fetch_history(contract, lookback_days)
        if series is None or series.empty:
            warnings.append(f"Benchmark history unavailable for {symbol}")
            return None, warnings
        converted, fx_warnings = self._convert_benchmark_to_base(series.astype(float), "USD", base_currency, lookback_days)
        warnings.extend(fx_warnings)
        if converted is None or converted.empty:
            warnings.append(f"Benchmark FX conversion failed for {symbol} into {base_currency}")
            return None, warnings
        return converted.pct_change().dropna(), warnings

    def _convert_benchmark_to_base(
        self,
        series: pd.Series,
        quote_ccy: str,
        base_ccy: str,
        lookback_days: int,
    ) -> tuple[pd.Series | None, List[str]]:
        warnings: List[str] = []
        quote = str(quote_ccy or "").upper()
        base = str(base_ccy or "").upper()
        if quote == base:
            return series, warnings
        fx_series = self.market_data.fetch_fx_history(base, quote, lookback_days)
        if fx_series is not None and not fx_series.empty:
            aligned = fx_series.reindex(series.index).ffill().dropna()
            if not aligned.empty:
                idx = series.index.intersection(aligned.index)
                if not idx.empty:
                    return series.reindex(idx) * aligned.reindex(idx), warnings
        fx_rate = self.market_data.fetch_fx_rate(base, quote)
        if fx_rate is None:
            return None, warnings
        warnings.append(f"Benchmark FX conversion used spot {quote}->{base} rate fallback")
        return series * float(fx_rate), warnings

    @staticmethod
    def _concentration_metrics(weights: pd.Series) -> Tuple[float | None, float | None, float | None]:
        if weights.empty:
            return None, None, None
        abs_weights = weights.abs()
        total = float(abs_weights.sum())
        if total <= 0:
            return None, None, None
        normalized = abs_weights / total
        hhi = float((normalized ** 2).sum())
        top5 = float(normalized.sort_values(ascending=False).head(5).sum())
        effective_bets = float(1.0 / hhi) if hhi > 0 else None
        return hhi, top5, effective_bets

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
        self.daily_vol_label.setText(self._fmt_pct("Daily Vol", results.daily_vol))
        self.annual_vol_label.setText(self._fmt_pct("Annual Vol", results.annual_vol))
        self.max_dd_label.setText(self._fmt_pct("Max Drawdown", results.max_drawdown))
        self.beta_label.setText(self._fmt_number("Beta", results.beta))
        self.corr_label.setText(self._fmt_number("Correlation", results.correlation))
        self.alpha_label.setText(self._fmt_pct("Jensen Alpha (ann.)", results.alpha_annual))
        self.coverage_label.setText(self._fmt_pct("Risk Coverage", results.risk_coverage_ratio))
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
        self.cum_canvas.show_message("Compute risk to view results")
        self._refresh_details_ui()
