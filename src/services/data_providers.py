from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Protocol, Tuple

import pandas as pd
from ib_insync import Contract

from src.application.workspace_service import should_auto_follow_research_symbol
from src.models.app_mode import AppMode, ResearchScopeType, SyntheticPosition
from src.models.instruments import (
    InstrumentDefaults,
    InstrumentReference,
    build_instrument_id,
    normalize_symbol,
)
from src.models.portfolio import PortfolioSnapshot, PositionItem
from src.services.ibkr_client import IBKRClient
from src.services.fx import FXService
from src.services.market_data import MarketDataService
from src.services.mock_data import MockDataService
from src.services.research_cache import ResearchHistoryCache
from src.utils.time import now_utc


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


def contract_for_position(position: PositionItem) -> Contract:
    return contract_for_instrument(
        InstrumentReference(
            symbol=position.symbol,
            sec_type=position.sec_type,
            currency=position.currency,
            exchange=position.exchange,
            primary_exchange=position.primary_exchange,
            provider_id=position.provider_id,
        )
    )


class AppDataProvider(Protocol):
    def load_prices(
        self,
        snapshot: PortfolioSnapshot,
        lookback_days: int,
        progress_cb=None,
    ) -> Tuple[Dict[str, pd.Series], List[str]]:
        ...


class AppModeContext(Protocol):
    app_mode: AppMode


class ResearchScopeContext(Protocol):
    research_scope_type: ResearchScopeType
    primary_symbol: str
    synthetic_positions: List[SyntheticPosition]


@dataclass
class BaseCurrencyHistoryResult:
    series: pd.Series | None
    warnings: List[str] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass
class NormalizedSnapshotPrices:
    prices: Dict[str, pd.Series] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    excluded_assets: Dict[str, str] = field(default_factory=dict)


def convert_history_to_base_currency(
    series: pd.Series,
    quote_currency: str | None,
    base_currency: str | None,
    lookback_days: int,
    market_data: MarketDataService,
    *,
    fx_service: FXService | None = None,
    spot_rate_override: float | None = None,
    label: str,
    context: str,
) -> BaseCurrencyHistoryResult:
    clean_series = pd.to_numeric(series, errors="coerce").dropna()
    if clean_series.empty:
        return BaseCurrencyHistoryResult(
            series=pd.Series(dtype=float),
            failure_reason=f"{context} history is empty after cleaning",
        )

    quote = str(quote_currency or "").strip().upper()
    base = str(base_currency or "").strip().upper()
    if not quote or not base or quote == base:
        return BaseCurrencyHistoryResult(series=clean_series.astype(float))

    fx_series = market_data.fetch_fx_history(base, quote, lookback_days)
    if fx_series is not None and not fx_series.empty:
        clean_fx = pd.to_numeric(fx_series, errors="coerce").dropna()
        common_index = clean_series.index.intersection(clean_fx.index)
        if common_index.empty:
            reason = f"No overlapping FX history for {quote}->{base}"
            return BaseCurrencyHistoryResult(
                series=pd.Series(dtype=float),
                warnings=[f"{context} {label} {reason}"],
                failure_reason=reason,
            )
        converted = clean_series.reindex(common_index).astype(float) * clean_fx.reindex(common_index).astype(float)
        converted = converted.dropna()
        if converted.empty:
            reason = f"No base-currency history for {quote}->{base}"
            return BaseCurrencyHistoryResult(
                series=pd.Series(dtype=float),
                warnings=[f"{context} {label} {reason}"],
                failure_reason=reason,
            )
        return BaseCurrencyHistoryResult(series=converted.astype(float))

    fx_rate = market_data.fetch_fx_rate(base, quote)
    if fx_rate is None and spot_rate_override is not None:
        fx_rate = float(spot_rate_override)
    if fx_rate is None and fx_service is not None:
        fx_rate = fx_service.get_rate(base, quote)
    if fx_rate is None:
        reason = f"FX unavailable for {quote}->{base}"
        return BaseCurrencyHistoryResult(
            series=None,
            warnings=[f"{context} {label} {reason} conversion"],
            failure_reason=reason,
        )
    return BaseCurrencyHistoryResult(
        series=clean_series.astype(float) * float(fx_rate),
        warnings=[f"{context} {label} FX conversion {quote}->{base} uses spot rate fallback"],
    )


def normalize_snapshot_price_histories(
    snapshot: PortfolioSnapshot,
    prices: Dict[str, pd.Series],
    lookback_days: int,
    market_data: MarketDataService,
    *,
    fx_service: FXService | None = None,
) -> NormalizedSnapshotPrices:
    normalized = NormalizedSnapshotPrices()
    positions_by_id = {position.resolved_instrument_id(): position for position in snapshot.positions}
    for instrument_id, series in prices.items():
        position = positions_by_id.get(instrument_id)
        if position is None:
            normalized.prices[instrument_id] = pd.to_numeric(series, errors="coerce").dropna().astype(float)
            continue
        result = convert_history_to_base_currency(
            series,
            position.currency,
            snapshot.base_currency,
            lookback_days,
            market_data,
            fx_service=fx_service,
            spot_rate_override=_position_spot_fx_rate(position),
            label=position.resolved_display_symbol(),
            context="Position",
        )
        normalized.warnings.extend(result.warnings)
        if result.series is None or result.series.empty:
            normalized.excluded_assets[instrument_id] = result.failure_reason or "Base-currency history unavailable"
            continue
        normalized.prices[instrument_id] = result.series.astype(float)
    return normalized


def _position_spot_fx_rate(position: PositionItem) -> float | None:
    if position.fx_rate is not None:
        return float(position.fx_rate)
    if position.market_value is None or position.base_market_value is None:
        return None
    market_value = float(position.market_value)
    if market_value == 0:
        return None
    return float(position.base_market_value) / market_value


@dataclass
class PortfolioDataProvider:
    client: IBKRClient
    market_data: MarketDataService
    mock_service: MockDataService

    def load_prices(
        self,
        snapshot: PortfolioSnapshot,
        lookback_days: int,
        progress_cb=None,
    ) -> Tuple[Dict[str, pd.Series], List[str]]:
        if self.client.mock:
            prices: Dict[str, pd.Series] = {}
            missing: List[str] = []
            for pos in snapshot.positions:
                if pos.symbol.startswith("CASH"):
                    continue
                series = self.mock_service.load_history(pos.symbol)
                instrument_id = pos.resolved_instrument_id()
                display_symbol = pos.resolved_display_symbol()
                if series is None:
                    missing.append(display_symbol)
                else:
                    prices[instrument_id] = series.astype(float)
            return prices, missing

        contracts: List[Contract] = []
        keys: List[str] = []
        labels: List[str] = []
        for pos in snapshot.positions:
            if pos.symbol.startswith("CASH"):
                continue
            contracts.append(contract_for_position(pos))
            keys.append(pos.resolved_instrument_id())
            labels.append(pos.resolved_display_symbol())
        return self.market_data.fetch_histories(
            contracts,
            lookback_days,
            progress_cb=progress_cb,
            keys=keys,
            labels=labels,
        )


@dataclass
class ResearchDataProvider:
    client: IBKRClient
    market_data: MarketDataService
    mock_service: MockDataService
    context: ResearchScopeContext | None
    base_currency: str
    history_cache: ResearchHistoryCache
    instrument_defaults: InstrumentDefaults = field(
        default_factory=lambda: InstrumentDefaults(
            provider="research",
            sec_type="STK",
            exchange="SMART",
            currency="USD",
        )
    )
    benchmark_defaults: InstrumentDefaults = field(
        default_factory=lambda: InstrumentDefaults(
            provider="benchmark",
            sec_type="STK",
            exchange="SMART",
            currency="USD",
        )
    )

    def load_symbol_history(self, symbol: str, lookback_days: int) -> pd.Series | None:
        return self.load_instrument_history(InstrumentReference(symbol=symbol), lookback_days)

    def load_benchmark_history(
        self,
        symbol: str,
        lookback_days: int,
        *,
        base_currency: str | None = None,
        warnings: list[str] | None = None,
    ) -> pd.Series | None:
        instrument = InstrumentReference(symbol=symbol).with_defaults(self.benchmark_defaults)
        series = self.load_instrument_history(
            instrument,
            lookback_days,
            defaults=self.benchmark_defaults,
        )
        if series is None or series.empty or base_currency is None:
            return series
        result = convert_history_to_base_currency(
            series.astype(float),
            instrument.currency,
            base_currency,
            lookback_days,
            self.market_data,
            label=instrument.normalized_display_symbol(),
            context="Benchmark",
        )
        if warnings is not None:
            warnings.extend(result.warnings)
        return result.series

    def load_instrument_history(
        self,
        instrument: InstrumentReference,
        lookback_days: int,
        *,
        defaults: InstrumentDefaults | None = None,
    ) -> pd.Series | None:
        resolved_defaults = defaults or self.instrument_defaults
        resolved = instrument.with_defaults(resolved_defaults)
        cache_key = self._history_cache_key(resolved, resolved_defaults)
        if not cache_key:
            return None
        cached = self.history_cache.get(cache_key, lookback_days)
        if cached is not None and not cached.empty:
            return cached
        if self.client.mock:
            series = self.mock_service.load_history(resolved.normalized_symbol())
        else:
            contract = contract_for_instrument(resolved)
            series = self.market_data.fetch_history(contract, lookback_days)
        if series is not None and not series.empty:
            self.history_cache.set(cache_key, series, lookback_days)
        return series

    def load_prices(
        self,
        snapshot: PortfolioSnapshot,
        lookback_days: int,
        progress_cb=None,
    ) -> Tuple[Dict[str, pd.Series], List[str]]:
        prices: Dict[str, pd.Series] = {}
        missing: List[str] = []
        positions = [pos for pos in snapshot.positions if not pos.symbol.startswith("CASH")]
        total = len(positions)
        for idx, position in enumerate(positions, start=1):
            instrument = self._instrument_for_position(position)
            instrument_id = position.resolved_instrument_id()
            display_symbol = position.resolved_display_symbol()
            series = self.load_instrument_history(instrument, lookback_days)
            if series is None or series.empty:
                missing.append(display_symbol)
            else:
                prices[instrument_id] = series.astype(float)
            if progress_cb:
                progress_cb(idx, total, display_symbol)
        return prices, missing

    def build_snapshot(self) -> tuple[PortfolioSnapshot | None, List[str]]:
        if self.context is None:
            return None, ["Research scope is not configured"]
        return self.build_snapshot_for_scope(
            self.context.research_scope_type,
            primary_symbol=self.context.primary_symbol,
            synthetic_positions=self.context.synthetic_positions,
        )

    def build_snapshot_for_scope(
        self,
        scope: ResearchScopeType,
        primary_symbol: str = "",
        synthetic_positions: List[SyntheticPosition] | None = None,
    ) -> tuple[PortfolioSnapshot | None, List[str]]:
        warnings: List[str] = []
        if scope == ResearchScopeType.SINGLE_TICKER:
            instrument = self._single_scope_instrument(primary_symbol)
            if not instrument.normalized_symbol():
                warnings.append("Ticker is required")
                return None, warnings
            pos = PositionItem(
                symbol=instrument.normalized_symbol(),
                sec_type=instrument.sec_type or "",
                currency=instrument.currency or "",
                quantity=1.0,
                avg_cost=None,
                market_price=None,
                market_value=100.0,
                unrealized_pnl=None,
                weight=1.0,
                base_market_value=100.0,
                instrument_id=instrument.instrument_id,
                display_symbol=instrument.display_symbol,
                exchange=instrument.exchange,
                primary_exchange=instrument.primary_exchange,
                provider=instrument.provider,
                provider_id=instrument.provider_id,
            )
            snapshot = PortfolioSnapshot(
                timestamp=now_utc(),
                base_currency=self.base_currency,
                account_summary={},
                positions=[pos],
                total_market_value=100.0,
                total_cash=0.0,
                net_liquidation=100.0,
                warnings=[],
            )
            return snapshot, warnings

        if scope == ResearchScopeType.SYNTHETIC_PORTFOLIO:
            positions = [p for p in list(synthetic_positions or []) if str(p.symbol or "").strip()]
            if not positions:
                warnings.append("Synthetic portfolio is empty")
                return None, warnings
            total_weight = sum(float(p.weight) for p in positions)
            if total_weight <= 0:
                warnings.append("Synthetic weights must not all be zero")
                return None, warnings
            items: List[PositionItem] = []
            total_value = 100.0
            for pos in positions:
                instrument = self._synthetic_scope_instrument(pos)
                norm_weight = float(pos.weight) / total_weight
                items.append(
                    PositionItem(
                        symbol=instrument.normalized_symbol(),
                        sec_type=instrument.sec_type or "",
                        currency=instrument.currency or "",
                        quantity=norm_weight,
                        avg_cost=None,
                        market_price=None,
                        market_value=total_value * norm_weight,
                        unrealized_pnl=None,
                        weight=norm_weight,
                        base_market_value=total_value * norm_weight,
                        instrument_id=instrument.instrument_id,
                        display_symbol=instrument.display_symbol,
                        exchange=instrument.exchange,
                        primary_exchange=instrument.primary_exchange,
                        provider=instrument.provider,
                        provider_id=instrument.provider_id,
                    )
                )
            snapshot = PortfolioSnapshot(
                timestamp=now_utc(),
                base_currency=self.base_currency,
                account_summary={},
                positions=items,
                total_market_value=total_value,
                total_cash=0.0,
                net_liquidation=total_value,
                warnings=[],
            )
            return snapshot, warnings

        warnings.append("Research scope is not configured")
        return None, warnings

    def _single_scope_instrument(self, symbol: str) -> InstrumentReference:
        return InstrumentReference(symbol=symbol).with_defaults(self.instrument_defaults)

    def _synthetic_scope_instrument(self, position: SyntheticPosition) -> InstrumentReference:
        return InstrumentReference(
            symbol=normalize_symbol(position.symbol),
            instrument_id=position.instrument_id,
            display_symbol=position.display_symbol,
            sec_type=position.sec_type,
            currency=position.currency,
            exchange=position.exchange,
            primary_exchange=position.primary_exchange,
            provider=position.provider,
            provider_id=position.provider_id,
        ).with_defaults(self.instrument_defaults)

    def _instrument_for_position(self, position: PositionItem) -> InstrumentReference:
        return InstrumentReference(
            symbol=position.symbol,
            instrument_id=position.instrument_id,
            display_symbol=position.display_symbol,
            sec_type=position.sec_type,
            currency=position.currency,
            exchange=position.exchange,
            primary_exchange=position.primary_exchange,
            provider=position.provider,
            provider_id=position.provider_id,
        ).with_defaults(self.instrument_defaults)

    def _history_cache_key(self, instrument: InstrumentReference, defaults: InstrumentDefaults) -> str:
        provider = instrument.normalized_provider(defaults.provider)
        default_instrument_id = build_instrument_id(
            provider=defaults.provider,
            symbol=instrument.normalized_symbol(),
            sec_type=defaults.sec_type,
            exchange=defaults.exchange,
            primary_exchange=None,
            currency=defaults.currency,
        )
        if (
            instrument.instrument_id == default_instrument_id
            and provider == str(defaults.provider or "").strip().lower()
            and normalize_symbol(instrument.sec_type) == normalize_symbol(defaults.sec_type)
            and normalize_symbol(instrument.exchange) == normalize_symbol(defaults.exchange)
            and normalize_symbol(instrument.currency) == normalize_symbol(defaults.currency)
            and not normalize_symbol(instrument.primary_exchange)
            and not str(instrument.provider_id or "").strip()
        ):
            return instrument.normalized_symbol()
        return str(instrument.instrument_id or instrument.normalized_symbol())


def select_data_provider(
    context: AppModeContext,
    portfolio_provider: PortfolioDataProvider,
    research_provider: ResearchDataProvider,
) -> AppDataProvider:
    return select_data_provider_for_mode(context.app_mode, portfolio_provider, research_provider)


def select_data_provider_for_mode(
    app_mode: AppMode,
    portfolio_provider: PortfolioDataProvider,
    research_provider: ResearchDataProvider,
) -> AppDataProvider:
    if app_mode == AppMode.RESEARCH:
        return research_provider
    return portfolio_provider
