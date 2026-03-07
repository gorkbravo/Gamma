from __future__ import annotations

from src.services.data_providers import AppDataProvider
from src.services.market_data import MarketDataService
from src.services.mock_data import MockDataService
from src.services.risk_free_rate import RiskFreeRateService


class RiskService:
    def __init__(
        self,
        data_provider: AppDataProvider | None,
        market_data: MarketDataService,
        mock_service: MockDataService,
        risk_free_service: RiskFreeRateService | None,
    ) -> None:
        self.data_provider = data_provider
        self.market_data = market_data
        self.mock_service = mock_service
        self.risk_free_service = risk_free_service

    def compute(self, *args, **kwargs):
        raise NotImplementedError("RiskService extraction is pending; use RiskTab for now.")
