from __future__ import annotations

from dataclasses import dataclass

from src.models.portfolio import PortfolioSnapshot
from src.services.fx import FXService
from src.services.ibkr_client import IBKRClient
from src.services.market_data import MarketDataService


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
    ) -> None:
        self.client = client
        self.market_data = market_data
        self.fx_service = fx_service

    def fetch_snapshot(self, request: PortfolioSnapshotRequest) -> PortfolioSnapshot:
        return self.client.fetch_snapshot(
            request.base_currency,
            self.fx_service,
            self.market_data,
            request.quote_mode,
            request.quote_timeout_seconds,
        )

    def run_diagnostics(self) -> list[str]:
        return self.client.run_diagnostics()

    def force_account_subscribe(self) -> list[str]:
        return self.client.force_account_subscribe()

    def formatted_errors(self, limit: int = 50) -> list[str]:
        return self.client.format_error_records(limit)
