from __future__ import annotations

from dataclasses import dataclass

from src.services.ibkr_client import IBKRClient
from src.services.iv_surface_engine import IVSurfaceEngine


@dataclass(frozen=True)
class IVSurfaceRequest:
    symbol: str
    market_data_mode: str = "delayed"


class IVService:
    def __init__(self, client: IBKRClient, market_data_mode: str = "delayed") -> None:
        self.client = client
        self.market_data_mode = self.normalize_market_data_mode(market_data_mode)

    @staticmethod
    def normalize_market_data_mode(value: str | None) -> str:
        mode = str(value or "").strip().lower()
        if mode in {"delayed", "live", "auto"}:
            return mode
        return "delayed"

    def create_engine(self, market_data_mode: str | None = None) -> IVSurfaceEngine:
        mode = self.normalize_market_data_mode(market_data_mode or self.market_data_mode)
        return IVSurfaceEngine(client=self.client, market_data_mode=mode)
