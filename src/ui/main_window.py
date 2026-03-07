from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.models.app_mode import AppMode
from src.services.app_context import AppDataContext
from src.services.cache import CacheService
from src.services.data_providers import (
    PortfolioDataProvider,
    ResearchDataProvider,
    select_data_provider,
)
from src.services.fx import FXService
from src.services.ibkr_client import IBKRClient
from src.services.market_data import MarketDataService
from src.services.mock_data import MockDataService
from src.services.portfolio_history_store import PortfolioHistoryStore
from src.services.risk_free_rate import RiskFreeRateService
from src.ui.landing_page import LandingPage
from src.ui.tabs.iv_surface_tab import IVSurfaceTab
from src.ui.tabs.overview_tab import OverviewTab
from src.ui.tabs.research_overview_tab import ResearchOverviewTab
from src.ui.tabs.risk_tab import RiskTab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("StrataLab")

        base_currency = os.getenv("BASE_CURRENCY", "EUR")
        auto_refresh = int(os.getenv("AUTO_REFRESH_SECONDS", "60") or 0)
        lookback = int(os.getenv("HIST_LOOKBACK_DAYS_DEFAULT", "252") or 252)
        quote_timeout = float(os.getenv("IB_SNAPSHOT_TIMEOUT_SECONDS", "2") or 2.0)
        market_data_mode = self._normalize_market_data_mode(os.getenv("IB_MARKET_DATA_MODE", "delayed"))

        mock_env = os.getenv("MOCK_DATA")
        mock_mode = True if mock_env is None else mock_env.lower() == "true"
        host = os.getenv("IB_HOST", "127.0.0.1")
        port = int(os.getenv("IB_PORT", "7497"))
        client_id = int(os.getenv("IB_CLIENT_ID", "1"))
        account = (os.getenv("IB_ACCOUNT", "") or "").strip() or None

        self.app_context = AppDataContext()
        self.mock_service = MockDataService()
        self.client = IBKRClient(host, port, client_id, account, mock_mode, self.mock_service)
        self.client.set_market_data_mode(market_data_mode)
        self.cache = CacheService(ttl_hours=24)
        self.market_data = MarketDataService(
            self.client.ib,
            self.cache,
            ib_runner=self.client.ib_runner,
            market_data_mode=market_data_mode,
        )
        self.fx_service = FXService(
            self.client.ib, cache=self.cache, market_data=self.market_data, ib_runner=self.client.ib_runner
        )
        self.portfolio_history = PortfolioHistoryStore(mock=mock_mode)
        self.risk_free_service = RiskFreeRateService(cache=self.cache)

        self.portfolio_provider = PortfolioDataProvider(self.client, self.market_data, self.mock_service)
        self.research_provider = ResearchDataProvider(
            self.client,
            self.market_data,
            self.mock_service,
            self.app_context,
            base_currency,
        )

        self.tabs = QTabWidget()
        self.overview_tab = OverviewTab(
            client=self.client,
            market_data=self.market_data,
            fx_service=self.fx_service,
            history_store=self.portfolio_history,
            base_currency=base_currency,
            market_data_mode=market_data_mode,
            auto_refresh_seconds=auto_refresh,
            quote_timeout_seconds=quote_timeout,
        )
        self.research_overview_tab = ResearchOverviewTab(
            app_context=self.app_context,
            provider=self.research_provider,
            base_currency=base_currency,
        )
        self.risk_tab = RiskTab(
            client=self.client,
            market_data=self.market_data,
            mock_service=self.mock_service,
            risk_free_service=self.risk_free_service,
            base_currency=base_currency,
            default_lookback=lookback,
            app_context=self.app_context,
            data_provider=self.portfolio_provider,
        )
        self.iv_surface_tab = IVSurfaceTab(
            client=self.client,
            market_data_mode=market_data_mode,
            app_context=self.app_context,
        )

        self.overview_tab.snapshot_updated.connect(self.risk_tab.set_portfolio_snapshot)
        self.overview_tab.market_data_mode_changed.connect(self._on_market_data_mode_changed)
        self.research_overview_tab.open_risk_requested.connect(self._open_risk_from_research)
        self.research_overview_tab.open_iv_surface_requested.connect(self._open_iv_surface_from_research)

        self._build_shell()
        self._build_landing()
        self.risk_tab.set_data_provider(self.portfolio_provider)

        if mock_mode:
            self.overview_tab.set_mock_mode_ui()

    def _build_shell(self) -> None:
        self.stack = QStackedWidget()

        self.app_shell = QWidget()
        shell_layout = QVBoxLayout()
        top = QHBoxLayout()
        self.mode_label = QLabel("Mode: Portfolio View")
        self.switch_mode_btn = QPushButton("Switch Mode")
        self.switch_mode_btn.clicked.connect(self._show_landing)
        top.addWidget(self.mode_label)
        top.addStretch()
        top.addWidget(self.switch_mode_btn)
        shell_layout.addLayout(top)
        shell_layout.addWidget(self.tabs)
        self.app_shell.setLayout(shell_layout)

        self.stack.addWidget(QWidget())
        self.stack.addWidget(self.app_shell)
        self.setCentralWidget(self.stack)

    def _build_landing(self) -> None:
        self.landing = LandingPage()
        self.landing.mode_selected.connect(self._on_mode_selected)
        self.landing.connect_requested.connect(self.overview_tab.toggle_connection)
        self.overview_tab.connection_state_changed.connect(self.landing.set_connection_state)
        self.landing.set_connection_state(
            self.overview_tab.connection_status_text(),
            self.overview_tab.connection_action_text(),
            self.overview_tab.connection_action_enabled(),
        )
        self.stack.removeWidget(self.stack.widget(0))
        self.stack.insertWidget(0, self.landing)
        self.stack.setCurrentIndex(0)

    def _show_landing(self) -> None:
        self.stack.setCurrentWidget(self.landing)

    def _on_mode_selected(self, mode_text: str) -> None:
        mode = AppMode.RESEARCH if str(mode_text).strip().lower() == AppMode.RESEARCH.value else AppMode.PORTFOLIO
        self._select_mode(mode)

    def _select_mode(self, mode: AppMode) -> None:
        self.app_context.set_app_mode(mode)
        provider = select_data_provider(self.app_context, self.portfolio_provider, self.research_provider)
        self.risk_tab.set_data_provider(provider)
        self.tabs.clear()
        if mode == AppMode.RESEARCH:
            self.mode_label.setText("Mode: Research View")
            self.tabs.addTab(self.research_overview_tab, "Overview")
        else:
            self.mode_label.setText("Mode: Portfolio View")
            self.tabs.addTab(self.overview_tab, "Portfolio Overview")
        self.tabs.addTab(self.risk_tab, "Risk")
        self.tabs.addTab(self.iv_surface_tab, "IV Surface")
        self.stack.setCurrentWidget(self.app_shell)

    @staticmethod
    def _normalize_market_data_mode(value: str | None) -> str:
        mode = str(value or "").strip().lower()
        if mode in {"delayed", "live", "auto"}:
            return mode
        return "delayed"

    def _on_market_data_mode_changed(self, mode: str) -> None:
        normalized = self._normalize_market_data_mode(mode)
        self.market_data.set_market_data_mode(normalized)
        self.client.set_market_data_mode(normalized)
        self.iv_surface_tab.set_market_data_mode(normalized)

    def _open_risk_from_research(self) -> None:
        self.tabs.setCurrentWidget(self.risk_tab)
        self.risk_tab.compute()

    def _open_iv_surface_from_research(self) -> None:
        self.tabs.setCurrentWidget(self.iv_surface_tab)

    def closeEvent(self, event) -> None:
        try:
            if self.overview_tab.timer.isActive():
                self.overview_tab.timer.stop()
            if self.overview_tab.connection_timer.isActive():
                self.overview_tab.connection_timer.stop()
        except Exception:
            pass
        try:
            self.iv_surface_tab.timer.stop()
            self.iv_surface_tab.engine.stop()
        except Exception:
            pass
        try:
            if not self.client.mock and self.client.is_connected():
                self.client.disconnect()
        except Exception:
            pass
        try:
            self.client.shutdown()
        except Exception:
            pass
        event.accept()
