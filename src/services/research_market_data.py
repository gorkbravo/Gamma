from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

import pandas as pd
from ib_insync import Contract

from src.models.instruments import InstrumentReference, normalize_symbol
from src.models.provenance import FreshnessLabel
from src.services.market_data import MarketDataService
from src.services.mock_data import MockDataService
from src.utils.time import now_utc


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResearchHistoryResult:
    series: pd.Series | None
    source_provider: str
    source_label: str
    origin: str
    freshness_label: FreshnessLabel
    retrieved_at: datetime = field(default_factory=now_utc)
    warnings: list[str] = field(default_factory=list)
    transformation_note: str | None = None

    @classmethod
    def unavailable(
        cls,
        *,
        source_provider: str,
        source_label: str,
        origin: str,
        warning: str | None = None,
    ) -> "ResearchHistoryResult":
        return cls(
            series=None,
            source_provider=source_provider,
            source_label=source_label,
            origin=origin,
            freshness_label=FreshnessLabel.UNAVAILABLE,
            warnings=[warning] if warning else [],
        )


class ListedMarketHistoryProvider(Protocol):
    provider_id: str
    source_label: str

    def load_history(self, instrument: InstrumentReference, lookback_days: int) -> ResearchHistoryResult:
        ...


def contract_for_instrument(instrument: InstrumentReference) -> Contract:
    contract = Contract(
        symbol=instrument.normalized_symbol(),
        secType=instrument.sec_type or "STK",
        exchange=instrument.exchange or "SMART",
        currency=instrument.currency or "USD",
    )
    provider_id = str(instrument.provider_id or "").strip()
    if provider_id.isdigit():
        contract.conId = int(provider_id)
    primary_exchange = str(instrument.primary_exchange or "").strip()
    if primary_exchange:
        contract.primaryExchange = primary_exchange
    return contract


@dataclass
class MockListedMarketHistoryProvider:
    mock_service: MockDataService

    provider_id: str = "mock"
    source_label: str = "Mock sample-data daily history"

    def load_history(self, instrument: InstrumentReference, lookback_days: int) -> ResearchHistoryResult:
        symbol = instrument.normalized_symbol()
        series = self.mock_service.load_history(symbol)
        if series is None or series.empty:
            return ResearchHistoryResult.unavailable(
                source_provider=self.provider_id,
                source_label=self.source_label,
                origin="mock_data.load_history",
                warning=f"Mock history unavailable for {symbol}",
            )
        return ResearchHistoryResult(
            series=series.astype(float),
            source_provider=self.provider_id,
            source_label=self.source_label,
            origin="mock_data.load_history",
            freshness_label=FreshnessLabel.MOCKED,
            transformation_note="Loaded from local sample data for offline/demo research workflows.",
        )


@dataclass
class IbkrListedMarketHistoryProvider:
    market_data: MarketDataService

    provider_id: str = "ibkr"
    source_label: str = "IBKR/TWS daily historical bars"

    def load_history(self, instrument: InstrumentReference, lookback_days: int) -> ResearchHistoryResult:
        symbol = instrument.normalized_display_symbol()
        series = self.market_data.fetch_history(contract_for_instrument(instrument), lookback_days)
        if series is None or series.empty:
            return ResearchHistoryResult.unavailable(
                source_provider=self.provider_id,
                source_label=self.source_label,
                origin="ibkr.reqHistoricalData",
                warning=f"IBKR/TWS history unavailable for {symbol}",
            )
        return ResearchHistoryResult(
            series=series.astype(float),
            source_provider=self.provider_id,
            source_label=self.source_label,
            origin="ibkr.reqHistoricalData",
            freshness_label=FreshnessLabel.HISTORICAL,
            transformation_note="Daily historical bars requested through Gamma's read-only IBKR/TWS market-data service.",
        )


@dataclass
class YFinanceListedMarketHistoryProvider:
    timeout_seconds: float = 10.0

    provider_id: str = "yfinance"
    source_label: str = "Yahoo Finance/yfinance daily history"

    def load_history(self, instrument: InstrumentReference, lookback_days: int) -> ResearchHistoryResult:
        symbol = self._provider_symbol(instrument)
        if not symbol:
            return ResearchHistoryResult.unavailable(
                source_provider=self.provider_id,
                source_label=self.source_label,
                origin="yfinance.download",
                warning="yfinance history unavailable: symbol is empty",
            )
        try:
            import yfinance as yf  # type: ignore[import-not-found]
        except Exception:
            return ResearchHistoryResult.unavailable(
                source_provider=self.provider_id,
                source_label=self.source_label,
                origin="yfinance.download",
                warning="yfinance fallback is configured but the yfinance package is not installed.",
            )

        start = datetime.utcnow().date() - timedelta(days=max(int(lookback_days * 1.8), 30) + 10)
        try:
            frame = yf.download(
                symbol,
                start=start.isoformat(),
                progress=False,
                auto_adjust=True,
                threads=False,
                timeout=float(self.timeout_seconds),
            )
        except Exception as exc:
            logger.debug("yfinance history request failed for %s", symbol, exc_info=True)
            return ResearchHistoryResult.unavailable(
                source_provider=self.provider_id,
                source_label=self.source_label,
                origin="yfinance.download",
                warning=f"yfinance history unavailable for {symbol}: {exc}",
            )

        series = self._close_series(frame)
        if series is None or series.empty:
            return ResearchHistoryResult.unavailable(
                source_provider=self.provider_id,
                source_label=self.source_label,
                origin="yfinance.download",
                warning=f"yfinance history unavailable for {symbol}",
            )
        return ResearchHistoryResult(
            series=series.astype(float),
            source_provider=self.provider_id,
            source_label=self.source_label,
            origin="yfinance.download",
            freshness_label=FreshnessLabel.HISTORICAL,
            warnings=[
                "Yahoo Finance/yfinance is an unofficial fallback source; use it for demo or coverage gaps, not as an institutional-quality feed."
            ],
            transformation_note="Gamma uses yfinance adjusted daily close history as a read-only fallback when higher-priority providers have no usable history.",
        )

    @staticmethod
    def _provider_symbol(instrument: InstrumentReference) -> str:
        symbol = normalize_symbol(instrument.symbol)
        if not symbol:
            return ""
        return symbol.replace("/", "-")

    @staticmethod
    def _close_series(frame) -> pd.Series | None:
        if frame is None or getattr(frame, "empty", True):
            return None
        if isinstance(frame.columns, pd.MultiIndex):
            for field in ("Close", "Adj Close"):
                matches = [column for column in frame.columns if column[0] == field]
                if matches:
                    raw = frame[matches[0]]
                    break
            else:
                return None
        else:
            column = "Close" if "Close" in frame.columns else "Adj Close" if "Adj Close" in frame.columns else None
            if column is None:
                return None
            raw = frame[column]
        series = pd.to_numeric(raw, errors="coerce").dropna()
        if series.empty:
            return None
        index = pd.to_datetime(series.index, errors="coerce")
        series = pd.Series(series.to_numpy(dtype=float), index=index).dropna()
        series = series[~series.index.isna()]
        if getattr(series.index, "tz", None) is not None:
            series.index = series.index.tz_convert(None)
        return series.sort_index()

