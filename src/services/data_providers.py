from __future__ import annotations

from dataclasses import dataclass, field, replace
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
from src.models.provenance import FreshnessLabel
from src.services.ibkr_client import IBKRClient
from src.services.fx import FXService
from src.services.market_data import MarketDataService
from src.services.mock_data import MockDataService
from src.services.research_market_data import (
    IbkrListedMarketHistoryProvider,
    ListedMarketHistoryProvider,
    MockListedMarketHistoryProvider,
    ResearchHistoryResult,
    contract_for_instrument,
)
from src.services.research_cache import ResearchHistoryCache
from src.utils.time import now_utc


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
    history_providers: List[ListedMarketHistoryProvider] | None = None
    _last_history_warnings: list[str] = field(default_factory=list, init=False)

    def load_prices(
        self,
        snapshot: PortfolioSnapshot,
        lookback_days: int,
        progress_cb=None,
    ) -> Tuple[Dict[str, pd.Series], List[str]]:
        self._last_history_warnings = []
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

        if self.history_providers:
            return self._load_prices_from_provider_chain(snapshot, lookback_days, progress_cb)

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

    def drain_history_warnings(self) -> list[str]:
        warnings = list(dict.fromkeys(self._last_history_warnings))
        self._last_history_warnings = []
        return warnings

    def _load_prices_from_provider_chain(
        self,
        snapshot: PortfolioSnapshot,
        lookback_days: int,
        progress_cb=None,
    ) -> Tuple[Dict[str, pd.Series], List[str]]:
        prices: Dict[str, pd.Series] = {}
        missing: List[str] = []
        positions = [position for position in snapshot.positions if not position.symbol.startswith("CASH")]
        total = len(positions)
        for index, position in enumerate(positions, start=1):
            instrument = self._instrument_for_position(position)
            instrument_id = position.resolved_instrument_id()
            display_symbol = position.resolved_display_symbol()
            provider_warnings: list[str] = []
            for provider in self.history_providers or []:
                result = provider.load_history(instrument, lookback_days)
                provider_warnings.extend(result.warnings)
                if result.series is not None and not result.series.empty:
                    prices[instrument_id] = result.series.astype(float)
                    self._last_history_warnings.extend(provider_warnings)
                    break
            else:
                missing.append(display_symbol)
                self._last_history_warnings.extend(provider_warnings)
            if progress_cb:
                progress_cb(index, total, display_symbol)
        return prices, missing

    @staticmethod
    def _instrument_for_position(position: PositionItem) -> InstrumentReference:
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
    history_providers: List[ListedMarketHistoryProvider] | None = None
    history_provider_sets: dict[str, List[ListedMarketHistoryProvider]] = field(default_factory=dict)
    history_cache_seconds_by_policy: dict[str, int] = field(default_factory=dict)
    _history_metadata: dict[str, ResearchHistoryResult] = field(default_factory=dict, init=False)
    _last_history_warnings: list[str] = field(default_factory=list, init=False)
    _last_history_sources: dict[str, ResearchHistoryResult] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.history_providers is not None:
            return
        if self.client.mock:
            self.history_providers = [MockListedMarketHistoryProvider(self.mock_service)]
        else:
            self.history_providers = [IbkrListedMarketHistoryProvider(self.market_data)]

    def load_symbol_history(self, symbol: str, lookback_days: int) -> pd.Series | None:
        return self.load_instrument_history(InstrumentReference(symbol=symbol), lookback_days)

    def load_benchmark_history(
        self,
        symbol: str,
        lookback_days: int,
        *,
        base_currency: str | None = None,
        warnings: list[str] | None = None,
        provider_policy: str | None = None,
        bypass_cache: bool = False,
        max_age_seconds: int | float | None = None,
    ) -> pd.Series | None:
        result = self.load_benchmark_history_result(
            symbol,
            lookback_days,
            base_currency=base_currency,
            warnings=warnings,
            provider_policy=provider_policy,
            bypass_cache=bypass_cache,
            max_age_seconds=max_age_seconds,
        )
        return result.series

    def load_benchmark_history_result(
        self,
        symbol: str,
        lookback_days: int,
        *,
        base_currency: str | None = None,
        warnings: list[str] | None = None,
        provider_policy: str | None = None,
        bypass_cache: bool = False,
        max_age_seconds: int | float | None = None,
    ) -> ResearchHistoryResult:
        instrument = InstrumentReference(symbol=symbol).with_defaults(self.benchmark_defaults)
        history_result = self.load_instrument_history_result(
            instrument,
            lookback_days,
            defaults=self.benchmark_defaults,
            provider_policy=provider_policy,
            bypass_cache=bypass_cache,
            max_age_seconds=max_age_seconds,
        )
        if warnings is not None:
            warnings.extend(history_result.warnings)
        series = history_result.series
        if series is None or series.empty or base_currency is None:
            return history_result
        conversion = convert_history_to_base_currency(
            series.astype(float),
            instrument.currency,
            base_currency,
            lookback_days,
            self.market_data,
            label=instrument.normalized_display_symbol(),
            context="Benchmark",
        )
        if warnings is not None:
            warnings.extend(conversion.warnings)
        return replace(
            history_result,
            series=conversion.series,
            warnings=list(dict.fromkeys([*history_result.warnings, *conversion.warnings])),
        )

    def load_instrument_history(
        self,
        instrument: InstrumentReference,
        lookback_days: int,
        *,
        defaults: InstrumentDefaults | None = None,
        provider_policy: str | None = None,
        bypass_cache: bool = False,
        max_age_seconds: int | float | None = None,
    ) -> pd.Series | None:
        return self.load_instrument_history_result(
            instrument,
            lookback_days,
            defaults=defaults,
            provider_policy=provider_policy,
            bypass_cache=bypass_cache,
            max_age_seconds=max_age_seconds,
        ).series

    def load_instrument_history_result(
        self,
        instrument: InstrumentReference,
        lookback_days: int,
        *,
        defaults: InstrumentDefaults | None = None,
        provider_policy: str | None = None,
        bypass_cache: bool = False,
        max_age_seconds: int | float | None = None,
    ) -> ResearchHistoryResult:
        resolved_defaults = defaults or self.instrument_defaults
        resolved = instrument.with_defaults(resolved_defaults)
        cache_key = self._history_cache_key(resolved, resolved_defaults, provider_policy=provider_policy)
        if not cache_key:
            return ResearchHistoryResult.unavailable(
                source_provider="unavailable",
                source_label="Unavailable history source",
                origin="research_data_provider.load_instrument_history",
                warning="Instrument history cache key is empty",
            )
        cached = None if bypass_cache else self.history_cache.get(
            cache_key,
            lookback_days,
            max_age_seconds=max_age_seconds,
        )
        if cached is not None and not cached.empty:
            metadata = self._history_metadata.get(cache_key)
            if metadata is not None:
                self._last_history_sources[resolved.instrument_id or resolved.normalized_symbol()] = metadata
                return replace(metadata, series=cached.astype(float), warnings=[])
            self._last_history_sources[resolved.instrument_id or resolved.normalized_symbol()] = ResearchHistoryResult(
                series=None,
                source_provider="research_cache",
                source_label="Research history cache",
                origin="research_cache.memory",
                freshness_label=FreshnessLabel.HISTORICAL,
                transformation_note="Loaded from Gamma's in-memory research history cache.",
            )
            return ResearchHistoryResult(
                series=cached.astype(float),
                source_provider="research_cache",
                source_label="Research history cache",
                origin="research_cache.memory",
                freshness_label=FreshnessLabel.HISTORICAL,
                transformation_note="Loaded from Gamma's in-memory research history cache.",
            )

        result = self._fetch_from_history_providers(resolved, lookback_days, provider_policy=provider_policy)
        if result.series is not None and not result.series.empty:
            clean_series = result.series.astype(float)
            self.history_cache.set(cache_key, clean_series, lookback_days)
            stored = replace(result, series=None)
            self._history_metadata[cache_key] = stored
            self._last_history_sources[resolved.instrument_id or resolved.normalized_symbol()] = stored
            return replace(result, series=clean_series)
        return result

    def drain_history_warnings(self) -> list[str]:
        warnings = list(dict.fromkeys(self._last_history_warnings))
        self._last_history_warnings = []
        return warnings

    def reset_history_tracking(self) -> None:
        self._last_history_warnings = []
        self._last_history_sources = {}

    def history_source_summary(self) -> ResearchHistoryResult:
        sources = list(self._last_history_sources.values())
        if not sources:
            return ResearchHistoryResult(
                series=None,
                source_provider="unknown",
                source_label="Unknown history source",
                origin="research_data_provider.history_source_summary",
                freshness_label=FreshnessLabel.UNKNOWN,
            )
        providers = sorted({source.source_provider for source in sources})
        if len(providers) == 1:
            return sources[0]
        labels = sorted({source.source_label for source in sources})
        return ResearchHistoryResult(
            series=None,
            source_provider="mixed",
            source_label=f"Mixed listed-market history providers: {', '.join(labels)}",
            origin="research_data_provider.history_source_summary",
            freshness_label=FreshnessLabel.HISTORICAL,
            warnings=["Scope uses more than one listed-market history provider."],
            transformation_note="Gamma selected the first configured provider with usable daily history for each instrument.",
        )

    def _fetch_from_history_providers(
        self,
        instrument: InstrumentReference,
        lookback_days: int,
        *,
        provider_policy: str | None = None,
    ) -> ResearchHistoryResult:
        warnings: list[str] = []
        for provider in self._history_providers_for_policy(provider_policy):
            result = provider.load_history(instrument, lookback_days)
            if result.series is not None and not result.series.empty:
                combined = replace(result, warnings=list(dict.fromkeys([*warnings, *result.warnings])))
                self._last_history_warnings.extend(combined.warnings)
                return combined
            warnings.extend(result.warnings)
        warning = (
            f"No configured history provider returned usable data for {instrument.normalized_display_symbol()}."
        )
        warnings.append(warning)
        self._last_history_warnings.extend(warnings)
        return ResearchHistoryResult(
            series=None,
            source_provider="unavailable",
            source_label="Unavailable history source",
            origin="research_data_provider.provider_chain",
            freshness_label=FreshnessLabel.UNAVAILABLE,
            warnings=list(dict.fromkeys(warnings)),
        )

    def _history_providers_for_policy(self, provider_policy: str | None) -> list[ListedMarketHistoryProvider]:
        policy = str(provider_policy or "").strip().lower()
        if policy and policy in self.history_provider_sets:
            return list(self.history_provider_sets[policy])
        return list(self.history_providers or [])

    def load_prices(
        self,
        snapshot: PortfolioSnapshot,
        lookback_days: int,
        progress_cb=None,
    ) -> Tuple[Dict[str, pd.Series], List[str]]:
        prices: Dict[str, pd.Series] = {}
        missing: List[str] = []
        self._last_history_warnings = []
        self._last_history_sources = {}
        positions = [pos for pos in snapshot.positions if not pos.symbol.startswith("CASH")]
        total = len(positions)
        for idx, position in enumerate(positions, start=1):
            instrument = self._instrument_for_position(position)
            instrument_id = position.resolved_instrument_id()
            display_symbol = position.resolved_display_symbol()
            result = self.load_instrument_history_result(instrument, lookback_days)
            if result.series is None or result.series.empty:
                missing.append(display_symbol)
            else:
                prices[instrument_id] = result.series.astype(float)
                self._last_history_sources[instrument_id] = replace(result, series=None)
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

    def _history_cache_key(
        self,
        instrument: InstrumentReference,
        defaults: InstrumentDefaults,
        *,
        provider_policy: str | None = None,
    ) -> str:
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
            base_key = instrument.normalized_symbol()
        else:
            base_key = str(instrument.instrument_id or instrument.normalized_symbol())
        policy = str(provider_policy or "").strip().lower()
        return f"{policy}:{base_key}" if policy else base_key


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
