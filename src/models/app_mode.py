from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.models.instruments import build_instrument_id, normalize_symbol


class AppMode(str, Enum):
    PORTFOLIO = "portfolio"
    RESEARCH = "research"


class ResearchScopeType(str, Enum):
    NONE = "none"
    SINGLE_TICKER = "single_ticker"
    SYNTHETIC_PORTFOLIO = "synthetic_portfolio"


@dataclass(frozen=True)
class SyntheticPosition:
    symbol: str
    weight: float
    instrument_id: str | None = None
    display_symbol: str | None = None
    sec_type: str | None = None
    currency: str | None = None
    exchange: str | None = None
    primary_exchange: str | None = None
    provider: str | None = None
    provider_id: str | None = None

    def resolved_symbol(self) -> str:
        return normalize_symbol(self.symbol)

    def resolved_display_symbol(self, symbol: str | None = None) -> str:
        return normalize_symbol(self.display_symbol or symbol or self.symbol)

    def resolved_instrument_id(self, symbol: str | None = None) -> str:
        return str(
            self.instrument_id
            or build_instrument_id(
                provider=self.provider or "synthetic",
                provider_id=self.provider_id,
                symbol=symbol or self.symbol,
                sec_type=self.sec_type,
                exchange=self.exchange,
                primary_exchange=self.primary_exchange,
                currency=self.currency,
            )
        )
