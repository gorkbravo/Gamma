from __future__ import annotations

import os

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
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
        self._market_data_mode = "delayed"
        self._last_connection_status = "Status: Disconnected"

        base_currency = os.getenv("BASE_CURRENCY", "EUR")
        auto_refresh = int(os.getenv("AUTO_REFRESH_SECONDS", "60") or 0)
        lookback = int(os.getenv("HIST_LOOKBACK_DAYS_DEFAULT", "252") or 252)
        quote_timeout = float(os.getenv("IB_SNAPSHOT_TIMEOUT_SECONDS", "2") or 2.0)
        market_data_mode = self._normalize_market_data_mode(os.getenv("IB_MARKET_DATA_MODE", "delayed"))
        self._market_data_mode = market_data_mode

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
        self.overview_tab.connection_state_changed.connect(self._on_connection_state_changed)
        self.research_overview_tab.open_risk_requested.connect(self._open_risk_from_research)
        self.research_overview_tab.open_iv_surface_requested.connect(self._open_iv_surface_from_research)
        self.app_context.app_mode_changed.connect(self._on_app_mode_changed)
        self.app_context.research_scope_changed.connect(self._sync_shell_state)

        self._build_shell()
        self._build_landing()
        self.risk_tab.set_data_provider(self.portfolio_provider)
        self._shell_timer = QTimer(self)
        self._shell_timer.setInterval(1000)
        self._shell_timer.timeout.connect(self._sync_shell_state)
        self._shell_timer.start()

        if mock_mode:
            self.overview_tab.set_mock_mode_ui()
        else:
            self._on_connection_state_changed(
                self.overview_tab.connection_status_text(),
                self.overview_tab.connection_action_text(),
                self.overview_tab.connection_action_enabled(),
            )
        self._sync_shell_state()

    def _build_shell(self) -> None:
        self.stack = QStackedWidget()

        self.app_shell = QWidget()
        self.app_shell.setObjectName("appShell")
        shell_layout = QVBoxLayout()
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(4)

        top_bar = QFrame()
        top_bar.setObjectName("shellTopBar")
        top_layout = QVBoxLayout()
        top_layout.setContentsMargins(12, 10, 12, 8)
        top_layout.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        self.brand_label = QLabel("StrataLab")
        self.brand_label.setObjectName("shellBrand")
        self.connection_label = QLabel("Status: Disconnected")
        self.connection_label.setObjectName("shellStatus")
        self.market_mode_label = QLabel("Market Data: Delayed")
        self.market_mode_label.setObjectName("shellMeta")
        self.workspace_label = QLabel("Workspace: Portfolio")
        self.workspace_label.setObjectName("shellMeta")
        self.active_symbol_label = QLabel("Active Symbol: --")
        self.active_symbol_label.setObjectName("shellMeta")
        self.last_update_label = QLabel("Last Update: N/A")
        self.last_update_label.setObjectName("shellMeta")
        self.switch_mode_btn = QPushButton("Switch Mode")
        self.switch_mode_btn.clicked.connect(self._show_landing)
        title_row.addWidget(self.brand_label)
        title_row.addSpacing(12)
        title_row.addWidget(self.connection_label)
        title_row.addWidget(self.market_mode_label)
        title_row.addWidget(self.workspace_label)
        title_row.addStretch()
        title_row.addWidget(self.active_symbol_label)
        title_row.addWidget(self.last_update_label)
        title_row.addWidget(self.switch_mode_btn)

        self.tabs.setObjectName("workspaceTabs")
        self.tabs.currentChanged.connect(self._sync_shell_state)
        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(0, 0, 0, 0)
        tab_row.addWidget(self.tabs)

        top_layout.addLayout(title_row)
        top_layout.addLayout(tab_row)
        top_bar.setLayout(top_layout)
        shell_layout.addWidget(top_bar)

        self.mode_label = QLabel("Mode: Portfolio View")
        self.mode_label.setObjectName("shellSubheading")
        self.mode_label.setContentsMargins(12, 0, 12, 0)
        shell_layout.addWidget(self.mode_label)

        self.shell_log = QPlainTextEdit()
        self.shell_log.setObjectName("shellLog")
        self.shell_log.setReadOnly(True)
        self.shell_log.setMaximumHeight(72)
        self.shell_log.setPlainText("System ready. Repository checkpoint created.")
        shell_layout.addWidget(self.shell_log)
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
        self._append_shell_message("Returned to workspace selector.")

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
            self.workspace_label.setText("Workspace: Research")
            self.tabs.addTab(self.research_overview_tab, "Overview")
        else:
            self.mode_label.setText("Mode: Portfolio View")
            self.workspace_label.setText("Workspace: Portfolio")
            self.tabs.addTab(self.overview_tab, "Portfolio Overview")
        self.tabs.addTab(self.risk_tab, "Risk")
        self.tabs.addTab(self.iv_surface_tab, "IV Surface")
        self.stack.setCurrentWidget(self.app_shell)
        self._append_shell_message(
            "Workspace loaded: Research view." if mode == AppMode.RESEARCH else "Workspace loaded: Portfolio view."
        )
        self._sync_shell_state()

    @staticmethod
    def _normalize_market_data_mode(value: str | None) -> str:
        mode = str(value or "").strip().lower()
        if mode in {"delayed", "live", "auto"}:
            return mode
        return "delayed"

    def _on_market_data_mode_changed(self, mode: str) -> None:
        normalized = self._normalize_market_data_mode(mode)
        self._market_data_mode = normalized
        self.market_data.set_market_data_mode(normalized)
        self.client.set_market_data_mode(normalized)
        self.iv_surface_tab.set_market_data_mode(normalized)
        self.market_mode_label.setText(f"Market Data: {'Live' if normalized == 'live' else 'Delayed'}")
        self._append_shell_message(
            f"Market data mode changed to {'live' if normalized == 'live' else 'delayed'}."
        )
        self._sync_shell_state()

    def _open_risk_from_research(self) -> None:
        self.tabs.setCurrentWidget(self.risk_tab)
        self._append_shell_message("Research context forwarded to Risk workspace.")
        self.risk_tab.compute()
        self._sync_shell_state()

    def _open_iv_surface_from_research(self) -> None:
        self.tabs.setCurrentWidget(self.iv_surface_tab)
        self._append_shell_message("Research context forwarded to IV Surface workspace.")
        self._sync_shell_state()

    def _append_shell_message(self, message: str) -> None:
        line = str(message or "").strip()
        if not line:
            return
        current = self.shell_log.toPlainText().strip()
        if current:
            self.shell_log.setPlainText(current + "\n" + line)
        else:
            self.shell_log.setPlainText(line)
        self.shell_log.verticalScrollBar().setValue(self.shell_log.verticalScrollBar().maximum())

    def _on_connection_state_changed(self, status_text: str, _action_text: str, _enabled: bool) -> None:
        if status_text == self._last_connection_status:
            self.connection_label.setText(status_text)
            return
        self._last_connection_status = status_text
        self.connection_label.setText(status_text)
        self._append_shell_message(status_text)
        self._sync_shell_state()

    def _on_app_mode_changed(self, mode_text: str) -> None:
        label = "Research" if mode_text == AppMode.RESEARCH.value else "Portfolio"
        self.workspace_label.setText(f"Workspace: {label}")
        self._sync_shell_state()

    def _sync_shell_state(self) -> None:
        self.market_mode_label.setText(f"Market Data: {'Live' if self._market_data_mode == 'live' else 'Delayed'}")
        current = self.tabs.currentWidget()
        active_symbol = "--"
        status_text = self._last_connection_status
        last_update = "Last Update: N/A"

        if current is self.overview_tab:
            active_symbol = "Portfolio Book"
            status_text = self.overview_tab.connection_status_text()
            last_update = self.overview_tab.last_refresh.text()
        elif current is self.research_overview_tab:
            active_symbol = self.research_overview_tab.shell_active_symbol()
            last_update = self.research_overview_tab.shell_status_text()
        elif current is self.risk_tab:
            active_symbol = self.risk_tab.shell_active_symbol()
            last_update = self.risk_tab.shell_status_text()
        elif current is self.iv_surface_tab:
            active_symbol = self.iv_surface_tab.shell_active_symbol()
            last_update = self.iv_surface_tab.shell_status_text()

        if self.app_context.primary_symbol and current is not self.overview_tab:
            active_symbol = self.app_context.primary_symbol

        self.connection_label.setText(status_text)
        self.active_symbol_label.setText(f"Active Symbol: {active_symbol}")
        self.last_update_label.setText(last_update)

    def closeEvent(self, event) -> None:
        try:
            if self._shell_timer.isActive():
                self._shell_timer.stop()
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
