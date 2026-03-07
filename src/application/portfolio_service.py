from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from src.models.portfolio import PortfolioSnapshot
from src.services.fx import FXService
from src.services.ibkr_client import IBKRClient
from src.services.market_data import MarketDataService
from src.services.portfolio_history_store import PortfolioHistoryStore


@dataclass(frozen=True)
class PortfolioSnapshotRequest:
    base_currency: str
    quote_mode: str = "Snapshot"
    quote_timeout_seconds: float = 2.0


class PortfolioService:
    def __init__(
        self,
        client: IBKRClient,
        market_data: MarketDataService,
        fx_service: FXService,
        history_store: PortfolioHistoryStore,
    ) -> None:
        self.client = client
        self.market_data = market_data
        self.fx_service = fx_service
        self.history_store = history_store

    def fetch_snapshot(self, request: PortfolioSnapshotRequest) -> PortfolioSnapshot:
        snapshot = self.client.fetch_snapshot(
            request.base_currency,
            self.fx_service,
            self.market_data,
            request.quote_mode,
            request.quote_timeout_seconds,
        )
        self.history_store.append_snapshot(
            snapshot.timestamp,
            snapshot.net_liquidation,
            snapshot.total_market_value,
            snapshot.total_cash,
            snapshot.base_currency,
        )
        return snapshot

    def load_history(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        return self.history_store.load_series(start=start, end=end)

    def clear_history(self) -> None:
        self.history_store.clear()

    def run_diagnostics(self) -> list[str]:
        return self.client.run_diagnostics()

    def force_account_subscribe(self) -> list[str]:
        return self.client.force_account_subscribe()

    def formatted_errors(self, limit: int = 50) -> list[str]:
        return self.client.format_error_records(limit)
