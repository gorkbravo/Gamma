from __future__ import annotations

import logging
import re
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


_CLASS_SHARE_SYMBOL_RE = re.compile(r"^([A-Z0-9]+)[-.]([A-Z]{1,2})$")


@dataclass(frozen=True)
class ResearchHistoryResult:
    series: pd.Series | None
    source_provider: str
    source_label: str
    origin: str
    freshness_label: FreshnessLabel
    ohlcv: pd.DataFrame | None = None
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
            ohlcv=None,
            warnings=[warning] if warning else [],
        )


class ListedMarketHistoryProvider(Protocol):
    provider_id: str
    source_label: str

    def load_history(self, instrument: InstrumentReference, lookback_days: int) -> ResearchHistoryResult:
        ...


def contract_for_instrument(instrument: InstrumentReference) -> Contract:
    sec_type = instrument.sec_type or "STK"
    contract = Contract(
        symbol=_ibkr_stock_symbol(instrument.normalized_symbol(), sec_type),
        secType=sec_type,
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


def _ibkr_stock_symbol(symbol: str, sec_type: str | None) -> str:
    if normalize_symbol(sec_type) != "STK":
        return symbol
    match = _CLASS_SHARE_SYMBOL_RE.match(symbol)
    if not match:
        return symbol
    return f"{match.group(1)} {match.group(2)}"


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
            ohlcv=self.mock_service.load_ohlcv_history(symbol),
            transformation_note="Loaded from local sample data for offline/demo research workflows.",
        )


@dataclass
class IbkrListedMarketHistoryProvider:
    market_data: MarketDataService

    provider_id: str = "ibkr"
    source_label: str = "IBKR/TWS daily historical bars"

    def load_history(self, instrument: InstrumentReference, lookback_days: int) -> ResearchHistoryResult:
        symbol = instrument.normalized_display_symbol()
        contract = contract_for_instrument(instrument)
        fetch_ohlcv_history = getattr(self.market_data, "fetch_ohlcv_history", None)
        ohlcv = fetch_ohlcv_history(contract, lookback_days) if callable(fetch_ohlcv_history) else None
        series = _close_series_from_ohlcv(ohlcv)
        if series is None or series.empty:
            series = self.market_data.fetch_history(contract, lookback_days)
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
            ohlcv=ohlcv,
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

        ohlcv = self._ohlcv_frame(frame)
        series = _close_series_from_ohlcv(ohlcv)
        if series is None or series.empty:
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
            ohlcv=ohlcv,
            warnings=[
                "Yahoo Finance/yfinance is an unofficial public source; overview boards use it as live-ish research context, not institutional quote truth."
            ],
            transformation_note=(
                "Gamma uses yfinance adjusted daily close history as read-only public overview data or as a fallback "
                "when higher-fidelity providers have no usable history."
            ),
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

    @staticmethod
    def _ohlcv_frame(frame) -> pd.DataFrame | None:
        if frame is None or getattr(frame, "empty", True):
            return None
        source_columns = frame.columns
        selected: dict[str, pd.Series] = {}
        for output, candidates in {
            "open": ("Open", "open"),
            "high": ("High", "high"),
            "low": ("Low", "low"),
            "close": ("Close", "Adj Close", "close"),
            "volume": ("Volume", "volume"),
        }.items():
            raw = None
            if isinstance(source_columns, pd.MultiIndex):
                for candidate in candidates:
                    matches = [column for column in source_columns if column[0] == candidate]
                    if matches:
                        raw = frame[matches[0]]
                        break
            else:
                for candidate in candidates:
                    if candidate in source_columns:
                        raw = frame[candidate]
                        break
            if raw is not None:
                selected[output] = pd.to_numeric(raw, errors="coerce")
        if "close" not in selected:
            return None
        index = pd.to_datetime(frame.index, errors="coerce")
        normalized = pd.DataFrame(selected, index=index).dropna(subset=["close"])
        normalized = normalized[~normalized.index.isna()]
        if getattr(normalized.index, "tz", None) is not None:
            normalized.index = normalized.index.tz_convert(None)
        return normalized.sort_index() if not normalized.empty else None


@dataclass
class UnavailableListedMarketHistoryProvider:
    provider_id: str
    source_label: str
    warning: str

    def load_history(self, instrument: InstrumentReference, lookback_days: int) -> ResearchHistoryResult:
        del lookback_days
        symbol = instrument.normalized_display_symbol()
        return ResearchHistoryResult.unavailable(
            source_provider=self.provider_id,
            source_label=self.source_label,
            origin=f"{self.provider_id}.history.unavailable",
            warning=f"{self.warning} ({symbol})",
        )


def _close_series_from_ohlcv(frame: pd.DataFrame | None) -> pd.Series | None:
    if frame is None or frame.empty or "close" not in frame.columns:
        return None
    series = pd.to_numeric(frame["close"], errors="coerce").dropna()
    return series.astype(float).sort_index() if not series.empty else None
