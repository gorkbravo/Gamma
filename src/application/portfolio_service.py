from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Mapping

import pandas as pd

from src.application.instrument_identity import identity_for_position
from src.models.instruments import InstrumentDefaults, InstrumentReference
from src.models.portfolio import (
    PortfolioHistoryClearResult,
    PortfolioHistoryHealth,
    PortfolioHistoryLoadResult,
    PortfolioHistoryState,
    PortfolioPerformanceState,
    PortfolioSnapshot,
    PortfolioSnapshotState,
)
from src.services.data_providers import (
    PortfolioDataProvider,
    contract_for_instrument,
    contract_for_position,
    convert_history_to_base_currency,
    normalize_snapshot_price_histories,
)
from src.services.fx import FXService
from src.services.ibkr_client import IBKRClient
from src.services.market_data import MarketDataService
from src.services.mock_data import MockDataService
from src.services.portfolio_history_store import (
    PortfolioHistoryCurrencyMismatchError,
    PortfolioHistoryStore,
)
from src.utils.time import format_ts, now_utc


@dataclass(frozen=True)
class PortfolioSnapshotRequest:
    base_currency: str
    quote_mode: str = "Snapshot"
    quote_timeout_seconds: float = 2.0


@dataclass(frozen=True)
class PortfolioPerformanceRequest:
    snapshot: PortfolioSnapshot
    benchmark_symbol: str = "SPY"
    lookback_days: int = 504


@dataclass
class PortfolioPerformanceResult:
    warnings: list[str] = field(default_factory=list)
    message: str | None = None
    portfolio_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    portfolio_cumulative: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    benchmark_cumulative: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    portfolio_base_value: float | None = None
    missing_symbols: list[str] = field(default_factory=list)
    benchmark_source: str = "none"
    benchmark_source_provider: str = "unavailable"
    benchmark_freshness_label: str = "unavailable"
    benchmark_transformation_note: str | None = None
    day_pnl: float | None = None
    day_pnl_pct: float | None = None
    day_pnl_source: str | None = None
    state: PortfolioPerformanceState = PortfolioPerformanceState.UNAVAILABLE
    source_provider: str = "gamma"
    retrieved_at: datetime | None = None
    origin: str = "gamma.portfolio.performance"
    freshness_label: str = "derived"
    transformation_note: str = (
        "Gamma-derived weighted performance from aligned constituent histories, "
        "or from the explicitly labeled local snapshot trail when constituent history is unavailable."
    )
    complete: bool = False
    requested_position_count: int = 0
    covered_position_count: int = 0
    history_coverage_ratio: float | None = None
    missing_history_symbols: list[str] = field(default_factory=list)
    missing_fx_symbols: list[str] = field(default_factory=list)
    history_source: str = "unavailable"
    history_source_provider: str = "unavailable"
    history_freshness_label: str = "unavailable"
    history_transformation_note: str | None = None
    history_point_count: int = 0


@dataclass(frozen=True)
class PortfolioDiagnosticsRequest:
    last_refresh_duration_ms: float | None
    warning_categories: Mapping[str, int]
    warning_count: int
    positions_count: int
    missing_history: list[str]
    benchmark_symbol: str
    benchmark_source: str
    day_pnl_source: str


class PortfolioService:
    def __init__(
        self,
        client: IBKRClient,
        market_data: MarketDataService,
        fx_service: FXService,
        history_store: PortfolioHistoryStore,
        data_provider: PortfolioDataProvider | None = None,
        mock_service: MockDataService | None = None,
        benchmark_defaults: InstrumentDefaults | None = None,
    ) -> None:
        self.client = client
        self.market_data = market_data
        self.fx_service = fx_service
        self.history_store = history_store
        self.data_provider = data_provider
        self.mock_service = mock_service
        self.benchmark_defaults = benchmark_defaults or InstrumentDefaults(
            provider="benchmark",
            sec_type="STK",
            exchange="SMART",
            currency="USD",
        )

    def fetch_snapshot(self, request: PortfolioSnapshotRequest) -> PortfolioSnapshot:
        snapshot = self.client.fetch_snapshot(
            request.base_currency,
            self.fx_service,
            self.market_data,
            request.quote_mode,
            request.quote_timeout_seconds,
        )
        self._apply_snapshot_metadata(snapshot, request)
        try:
            snapshot.history_store_health = self.history_store.append_snapshot(
                snapshot.timestamp,
                snapshot.net_liquidation,
                snapshot.total_market_value,
                snapshot.total_cash,
                snapshot.base_currency,
            )
            if snapshot.history_store_health.status in {
                PortfolioHistoryState.RECOVERED,
                PortfolioHistoryState.DEGRADED,
                PortfolioHistoryState.FAILED,
            }:
                snapshot.warnings.extend(snapshot.history_store_health.warnings)
        except PortfolioHistoryCurrencyMismatchError as exc:
            health = self.history_store.health()
            health.status = PortfolioHistoryState.DEGRADED
            health.warnings = list(dict.fromkeys([*health.warnings, str(exc)]))
            snapshot.history_store_health = health
            snapshot.warnings.append(str(exc))
        except Exception as exc:
            health = PortfolioHistoryHealth(
                status=PortfolioHistoryState.FAILED,
                warnings=[
                    "The current portfolio snapshot is usable, but it could not be added "
                    f"to local history ({type(exc).__name__})."
                ],
            )
            snapshot.history_store_health = health
            snapshot.warnings.extend(health.warnings)
        snapshot.warnings = self._safe_snapshot_warnings(snapshot.warnings)
        return snapshot

    def load_history(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        return self.history_store.load_series(start=start, end=end)

    def load_history_result(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> PortfolioHistoryLoadResult:
        return self.history_store.load_result(start=start, end=end)

    def clear_history(self) -> PortfolioHistoryClearResult:
        return self.history_store.clear()

    def run_diagnostics(self) -> list[str]:
        return self.client.run_diagnostics()

    def force_account_subscribe(self) -> list[str]:
        return self.client.force_account_subscribe()

    def formatted_errors(self, limit: int = 50) -> list[str]:
        return self.client.format_error_records(limit)

    def compute_performance(self, request: PortfolioPerformanceRequest) -> PortfolioPerformanceResult:
        snapshot = request.snapshot
        warnings: list[str] = []
        raw_prices, missing = self._load_prices(snapshot, request.lookback_days)
        if self.data_provider is not None and hasattr(
            self.data_provider,
            "drain_history_warnings",
        ):
            warnings.extend(self.data_provider.drain_history_warnings())
        missing = list(dict.fromkeys(missing))
        day_pnl, day_pnl_pct, day_pnl_source, pnl_warning = self.estimate_day_pnl_from_history(
            snapshot,
            raw_prices,
        )
        if pnl_warning:
            warnings.append(pnl_warning)
        normalized_prices = normalize_snapshot_price_histories(
            snapshot,
            raw_prices,
            request.lookback_days,
            self.market_data,
            fx_service=self.fx_service,
        )
        prices = normalized_prices.prices
        warnings.extend(normalized_prices.warnings)
        warnings.extend(self.market_data.drain_errors())
        if missing:
            warnings.append(f"Missing history for: {', '.join(missing)}")

        price_df = self._align_prices(prices)
        returns_df = self._compute_returns(price_df)
        if returns_df.empty:
            history_result = self.history_store.load_result()
            warnings.extend(history_result.health.warnings)
            hist_perf = self.load_performance_from_store(history_result)
            if hist_perf is None:
                result = PortfolioPerformanceResult(
                    warnings=warnings,
                    message="No performance data",
                    missing_symbols=missing,
                    day_pnl=day_pnl,
                    day_pnl_pct=day_pnl_pct,
                    day_pnl_source=day_pnl_source,
                )
                return self._finalize_performance_result(
                    result,
                    snapshot=snapshot,
                    missing_history=missing,
                    covered_position_count=0,
                    history_source="unavailable",
                )
            perf_returns, cumulative, base_value = hist_perf
            benchmark, benchmark_source, benchmark_warnings = self.build_benchmark(
                snapshot=snapshot,
                benchmark_symbol=request.benchmark_symbol,
                lookback_days=request.lookback_days,
                target_index=cumulative.index,
            )
            warnings.extend(benchmark_warnings)
            warnings.append("Using stored portfolio history (local snapshots)")
            result = PortfolioPerformanceResult(
                warnings=warnings,
                portfolio_returns=perf_returns,
                portfolio_cumulative=cumulative,
                benchmark_cumulative=benchmark,
                portfolio_base_value=base_value,
                missing_symbols=missing,
                benchmark_source=benchmark_source,
                day_pnl=day_pnl,
                day_pnl_pct=day_pnl_pct,
                day_pnl_source=day_pnl_source,
            )
            return self._finalize_performance_result(
                result,
                snapshot=snapshot,
                missing_history=missing,
                covered_position_count=0,
                history_source="local_history_store",
            )

        returns_df = self.ensure_cash_returns(snapshot, returns_df)
        weights = self.weights_for_symbols(snapshot, returns_df.columns.tolist())
        covered_position_count = self._covered_position_count(snapshot, returns_df.columns)
        if weights.empty:
            result = PortfolioPerformanceResult(
                warnings=warnings + ["No weights for performance"],
                message="No weights for performance",
                missing_symbols=missing,
                day_pnl=day_pnl,
                day_pnl_pct=day_pnl_pct,
                day_pnl_source=day_pnl_source,
            )
            return self._finalize_performance_result(
                result,
                snapshot=snapshot,
                missing_history=missing,
                covered_position_count=covered_position_count,
                history_source="constituent_history",
            )

        perf_returns = self._portfolio_returns(returns_df, weights)
        if perf_returns.empty:
            result = PortfolioPerformanceResult(
                warnings=warnings + ["No performance data"],
                message="No performance data",
                missing_symbols=missing,
                day_pnl=day_pnl,
                day_pnl_pct=day_pnl_pct,
                day_pnl_source=day_pnl_source,
            )
            return self._finalize_performance_result(
                result,
                snapshot=snapshot,
                missing_history=missing,
                covered_position_count=covered_position_count,
                history_source="constituent_history",
            )

        cumulative = (1 + perf_returns).cumprod()
        if not cumulative.empty:
            cumulative = cumulative / float(cumulative.iloc[0])

        benchmark, benchmark_source, benchmark_warnings = self.build_benchmark(
            snapshot=snapshot,
            benchmark_symbol=request.benchmark_symbol,
            lookback_days=request.lookback_days,
            target_index=cumulative.index,
        )
        warnings.extend(benchmark_warnings)
        result = PortfolioPerformanceResult(
            warnings=warnings,
            portfolio_returns=perf_returns,
            portfolio_cumulative=cumulative,
            benchmark_cumulative=benchmark,
            portfolio_base_value=self.portfolio_base_value(snapshot),
            missing_symbols=missing,
            benchmark_source=benchmark_source,
            day_pnl=day_pnl,
            day_pnl_pct=day_pnl_pct,
            day_pnl_source=day_pnl_source,
        )
        return self._finalize_performance_result(
            result,
            snapshot=snapshot,
            missing_history=missing,
            covered_position_count=covered_position_count,
            history_source="constituent_history",
        )

    def build_diagnostics_report(self, request: PortfolioDiagnosticsRequest) -> str:
        connection = "connected" if self.client.is_connected() else "disconnected"
        cache_stats = self.market_data.history_cache_stats()
        records = self.client.get_error_records(200)
        code_counts = Counter(int(record.code) for record in records)
        top_codes = ", ".join(f"{code}:{count}" for code, count in code_counts.most_common(5)) or "none"
        warning_summary = ", ".join(
            f"{name}={count}" for name, count in sorted(request.warning_categories.items())
        ) or "none"
        missing = ", ".join(request.missing_history) if request.missing_history else "none"
        duration_text = f"{request.last_refresh_duration_ms:.0f} ms" if request.last_refresh_duration_ms is not None else "N/A"
        return "\n".join(
            [
                "=== Gamma Diagnostics Report ===",
                f"Generated: {format_ts(now_utc())}",
                f"Mode: {'Mock' if self.client.mock else 'Live'}",
                f"Connection: {connection}",
                f"Last refresh duration: {duration_text}",
                f"Positions count: {request.positions_count}",
                f"Last warnings: {request.warning_count}",
                f"Warning categories: {warning_summary}",
                f"Missing historical tickers: {missing}",
                f"Benchmark symbol/source: {request.benchmark_symbol} / {request.benchmark_source}",
                f"Day P&L source: {request.day_pnl_source}",
                "History cache stats: "
                f"hits={int(cache_stats['hits'])}, misses={int(cache_stats['misses'])}, "
                f"hit_rate={cache_stats['hit_rate'] * 100:.1f}%",
                f"Top IB error codes: {top_codes}",
            ]
        )

    @staticmethod
    def categorize_warning(warning: str) -> str:
        text = warning.lower()
        if "10089" in text or "10167" in text or "10168" in text or "354" in text:
            return "entitlement"
        if "entitlement" in text or "market data subscription" in text:
            return "entitlement"
        if "timeout" in text or "timed out" in text:
            return "timeout"
        if "fx" in text:
            return "fx"
        if "contract" in text or "qualif" in text or "[positions]" in text:
            return "contract_resolution"
        return "other"

    def _apply_snapshot_metadata(
        self,
        snapshot: PortfolioSnapshot,
        request: PortfolioSnapshotRequest,
    ) -> None:
        requested_positions = [
            position
            for position in snapshot.positions
            if not self._is_cash_position(position)
        ]
        requested_symbols = [
            position.resolved_display_symbol() for position in requested_positions
        ]
        missing_quote_symbols: list[str] = []
        cached_quote_symbols: list[str] = []
        delayed_quote_symbols: list[str] = []
        for warning in snapshot.warnings:
            missing_match = re.search(
                r"Snapshot quote missing for ([^;]+?)(; using cached value)?$",
                warning,
                flags=re.IGNORECASE,
            )
            if missing_match:
                symbol = missing_match.group(1).strip().upper()
                if missing_match.group(2):
                    cached_quote_symbols.append(symbol)
                else:
                    missing_quote_symbols.append(symbol)
            delayed_match = re.search(
                r"Delayed market data for (.+)$",
                warning,
                flags=re.IGNORECASE,
            )
            if delayed_match:
                delayed_quote_symbols.append(delayed_match.group(1).strip().upper())

        quote_operation_failed = any(
            "snapshot quote fetch failed" in warning.lower()
            or "snapshot quotes skipped" in warning.lower()
            or "market data unavailable" in warning.lower()
            for warning in snapshot.warnings
        )
        if quote_operation_failed and str(request.quote_mode).lower() == "snapshot":
            missing_quote_symbols.extend(requested_symbols)

        missing_quote_symbols = list(dict.fromkeys(missing_quote_symbols))
        cached_quote_symbols = list(dict.fromkeys(cached_quote_symbols))
        delayed_quote_symbols = list(dict.fromkeys(delayed_quote_symbols))
        account_summary_available = bool(snapshot.account_summary)
        connection_ready = bool(self.client.mock or self.client.is_connected())
        snapshot_failed = any(
            warning.lower().startswith("snapshot fetch failed")
            for warning in snapshot.warnings
        )
        data_incomplete = bool(
            missing_quote_symbols
            or cached_quote_symbols
            or not account_summary_available
            or any(
                token in warning.lower()
                for warning in snapshot.warnings
                for token in (
                    "fx unavailable",
                    "snapshot totals failed",
                    "no positions returned",
                )
            )
        )

        if snapshot_failed:
            state = PortfolioSnapshotState.FAILED
        elif not connection_ready or (
            not account_summary_available and not snapshot.positions
        ):
            state = PortfolioSnapshotState.UNAVAILABLE
        elif account_summary_available and not snapshot.positions:
            state = PortfolioSnapshotState.EMPTY
        elif data_incomplete:
            state = PortfolioSnapshotState.PARTIAL
        else:
            state = PortfolioSnapshotState.READY

        market_data_mode = str(
            getattr(self.market_data, "market_data_mode", None)
            or getattr(self.client, "market_data_mode", None)
            or "unknown"
        ).strip().lower()
        if self.client.mock:
            freshness_label = "mocked"
        elif delayed_quote_symbols or market_data_mode in {"delayed", "delayed_frozen"}:
            freshness_label = "delayed"
        elif cached_quote_symbols:
            freshness_label = "stale"
        elif market_data_mode in {"live", "frozen"}:
            freshness_label = "live"
        elif state in {
            PortfolioSnapshotState.UNAVAILABLE,
            PortfolioSnapshotState.FAILED,
        }:
            freshness_label = "unavailable"
        else:
            freshness_label = "unknown"

        snapshot.state = state
        snapshot.source_provider = "mock" if self.client.mock else "ibkr"
        snapshot.retrieved_at = snapshot.timestamp
        snapshot.origin = "gamma.portfolio.snapshot"
        snapshot.freshness_label = freshness_label
        snapshot.transformation_note = (
            "Read-only broker account and position inspection with Gamma base-currency "
            "normalization. Mock mode uses an explicit sample portfolio."
        )
        snapshot.quote_mode = request.quote_mode
        snapshot.market_data_mode = market_data_mode
        snapshot.complete = state in {
            PortfolioSnapshotState.READY,
            PortfolioSnapshotState.EMPTY,
        }
        snapshot.connection_ready = connection_ready
        snapshot.account_summary_available = account_summary_available
        subscription_probe = getattr(self.client, "account_subscription_usable", None)
        snapshot.account_subscription_usable = (
            bool(subscription_probe())
            if callable(subscription_probe)
            else account_summary_available
        )
        missing_quote_set = set(missing_quote_symbols)
        cached_quote_set = set(cached_quote_symbols)
        delayed_quote_set = set(delayed_quote_symbols)
        snapshot.requested_position_count = len(requested_positions)
        snapshot.quoted_position_count = sum(
            1
            for position in requested_positions
            if position.resolved_display_symbol().upper()
            not in (missing_quote_set | cached_quote_set)
        )
        snapshot.missing_quote_symbols = missing_quote_symbols
        snapshot.missing_quote_count = sum(
            1
            for position in requested_positions
            if position.resolved_display_symbol().upper() in missing_quote_set
        )
        snapshot.cached_quote_symbols = cached_quote_symbols
        snapshot.cached_quote_count = sum(
            1
            for position in requested_positions
            if position.resolved_display_symbol().upper() in cached_quote_set
        )
        snapshot.delayed_quote_symbols = delayed_quote_symbols
        snapshot.delayed_quote_count = sum(
            1
            for position in requested_positions
            if position.resolved_display_symbol().upper() in delayed_quote_set
        )
        snapshot.available_value_count = sum(
            1
            for position in snapshot.positions
            if not self._is_cash_position(position)
            and (
                position.market_price is not None
                or position.market_value is not None
                or position.base_market_value is not None
            )
        )

    def _finalize_performance_result(
        self,
        result: PortfolioPerformanceResult,
        *,
        snapshot: PortfolioSnapshot,
        missing_history: list[str],
        covered_position_count: int,
        history_source: str,
    ) -> PortfolioPerformanceResult:
        requested_position_count = sum(
            1 for position in snapshot.positions if not self._is_cash_position(position)
        )
        missing_history = list(dict.fromkeys(missing_history))
        missing_fx = self._symbols_from_fx_warnings(snapshot, result.warnings)
        has_performance = not result.portfolio_cumulative.empty
        benchmark_source_provider = self._benchmark_source_provider(result.benchmark_source)
        benchmark_freshness_label = (
            "derived" if result.benchmark_source == "cash_0" else
            "historical" if not result.benchmark_cumulative.empty else
            "unavailable"
        )
        benchmark_note = (
            "Cash 0% is a Gamma-derived zero-return fallback used because the requested "
            "benchmark history or conversion was unavailable."
            if result.benchmark_source == "cash_0"
            else (
                "Historical benchmark prices converted to the portfolio base currency "
                "and rebased to 1.0 by Gamma."
                if not result.benchmark_cumulative.empty
                else "The requested benchmark could not be represented."
            )
        )
        coverage_ratio = (
            float(covered_position_count / requested_position_count)
            if requested_position_count > 0
            else None
        )
        is_partial = bool(
            missing_history
            or missing_fx
            or result.benchmark_source == "cash_0"
            or history_source == "local_history_store"
            or (
                requested_position_count > 0
                and covered_position_count < requested_position_count
            )
        )

        if not has_performance:
            state = PortfolioPerformanceState.UNAVAILABLE
        elif is_partial:
            state = PortfolioPerformanceState.PARTIAL
        else:
            state = PortfolioPerformanceState.READY

        result.state = state
        result.source_provider = "gamma"
        result.retrieved_at = now_utc()
        result.origin = "gamma.portfolio.performance"
        result.freshness_label = "derived" if has_performance else "unavailable"
        result.complete = state == PortfolioPerformanceState.READY
        result.requested_position_count = requested_position_count
        result.covered_position_count = covered_position_count
        result.history_coverage_ratio = coverage_ratio
        result.missing_history_symbols = missing_history
        result.missing_symbols = missing_history
        result.missing_fx_symbols = missing_fx
        result.history_source = history_source
        result.history_source_provider = self._history_source_provider(history_source)
        result.history_freshness_label = self._history_freshness_label(
            history_source,
            result.warnings,
        )
        result.history_transformation_note = self._history_transformation_note(
            history_source,
            result.history_freshness_label,
        )
        result.history_point_count = int(len(result.portfolio_cumulative))
        result.benchmark_source_provider = benchmark_source_provider
        result.benchmark_freshness_label = benchmark_freshness_label
        result.benchmark_transformation_note = benchmark_note
        result.warnings = list(dict.fromkeys(result.warnings))
        return result

    def _benchmark_source_provider(self, benchmark_source: str) -> str:
        if benchmark_source == "cash_0":
            return "gamma_cash_0"
        if benchmark_source.startswith("history_"):
            return "mock" if self.client.mock else "ibkr"
        return "unavailable"

    def _history_source_provider(self, history_source: str) -> str:
        if history_source == "local_history_store":
            return "local_history_store"
        if history_source == "constituent_history":
            return "mock" if self.client.mock else "configured_provider_chain"
        return "unavailable"

    def _history_freshness_label(
        self,
        history_source: str,
        warnings: list[str],
    ) -> str:
        if history_source == "unavailable":
            return "unavailable"
        if history_source == "local_history_store":
            return "historical"
        if self.client.mock:
            return "mocked"
        warning_text = " ".join(warnings).lower()
        if "stale" in warning_text:
            return "stale"
        if "cache" in warning_text or "cached" in warning_text:
            return "cached"
        return "historical"

    @staticmethod
    def _history_transformation_note(
        history_source: str,
        freshness_label: str,
    ) -> str:
        if history_source == "local_history_store":
            return (
                "Performance uses Gamma's locally accumulated daily snapshot trail; "
                "it is not a broker backfill."
            )
        if history_source == "constituent_history":
            return (
                "Gamma aligned available constituent histories on common dates, converted "
                "them to the portfolio base currency, and applied snapshot weights. "
                f"History freshness is labeled {freshness_label}."
            )
        return "Constituent and local snapshot history were unavailable."

    @staticmethod
    def _covered_position_count(snapshot: PortfolioSnapshot, columns: pd.Index) -> int:
        available = set(str(column) for column in columns)
        return sum(
            1
            for position in snapshot.positions
            if not PortfolioService._is_cash_position(position)
            and position.resolved_instrument_id() in available
        )

    @staticmethod
    def _symbols_from_fx_warnings(
        snapshot: PortfolioSnapshot,
        warnings: list[str],
    ) -> list[str]:
        fx_warnings = [
            warning.lower()
            for warning in warnings
            if "fx" in warning.lower() or "currency conversion" in warning.lower()
        ]
        if not fx_warnings:
            return []
        symbols: list[str] = []
        for position in snapshot.positions:
            if PortfolioService._is_cash_position(position):
                continue
            symbol = position.resolved_display_symbol()
            currency = str(position.currency or "").lower()
            if any(
                symbol.lower() in warning or (currency and currency in warning)
                for warning in fx_warnings
            ):
                symbols.append(symbol)
        return list(dict.fromkeys(symbols))

    @staticmethod
    def _safe_snapshot_warnings(warnings: list[str]) -> list[str]:
        safe: list[str] = []
        for warning in warnings:
            text = str(warning or "").strip()
            lowered = text.lower()
            if not text:
                continue
            if lowered.startswith("snapshot fetch failed:"):
                text = (
                    "Portfolio snapshot retrieval failed. Check the TWS connection and "
                    "open Diagnostics for provider details."
                )
            elif lowered.startswith("snapshot totals failed:"):
                text = (
                    "Portfolio totals are incomplete. Check FX coverage and open "
                    "Diagnostics for provider details."
                )
            elif "[positions][ib]" in lowered:
                text = (
                    "Some broker positions could not be resolved. Open Diagnostics for "
                    "the provider codes and affected contracts."
                )
            elif lowered.startswith("fx lookup failed for"):
                pair = text.split(":", 1)[0].removeprefix("FX lookup failed for ").strip()
                text = f"FX unavailable for {pair}; affected base-currency values are incomplete."
            safe.append(text)
        return list(dict.fromkeys(safe))

    @staticmethod
    def _is_cash_position(position) -> bool:
        return position.sec_type == "CASH" or position.symbol.startswith("CASH")

    def build_benchmark(
        self,
        snapshot: PortfolioSnapshot,
        benchmark_symbol: str,
        lookback_days: int,
        target_index: pd.Index,
    ) -> tuple[pd.Series, str, list[str]]:
        warnings: list[str] = []
        if target_index.empty:
            return pd.Series(dtype=float), "none", warnings

        symbol = str(benchmark_symbol or "").strip().upper() or "SPY"
        benchmark_instrument = InstrumentReference(symbol=symbol).with_defaults(self.benchmark_defaults)
        if self.client.mock and self.mock_service is not None:
            series = self.mock_service.load_history(symbol)
        else:
            contract = contract_for_instrument(benchmark_instrument)
            series = self.market_data.fetch_history(contract, lookback_days)
        if series is None or series.empty:
            warnings.append(f"No benchmark data for {symbol}; using Cash (0%) benchmark")
            return pd.Series(1.0, index=target_index), "cash_0", warnings

        converted = self.convert_series_to_base(
            series.astype(float),
            quote_ccy=benchmark_instrument.currency,
            base_ccy=snapshot.base_currency,
            lookback_days=lookback_days,
            warnings=warnings,
            label=symbol,
            context="Benchmark",
        )
        if converted is None or converted.empty:
            warnings.append(f"Benchmark conversion failed for {symbol}; using Cash (0%) benchmark")
            return pd.Series(1.0, index=target_index), "cash_0", warnings

        benchmark_returns = converted.pct_change().dropna()
        if benchmark_returns.empty:
            warnings.append(f"No benchmark returns for {symbol}; using Cash (0%) benchmark")
            return pd.Series(1.0, index=target_index), "cash_0", warnings

        benchmark_cumulative = (1 + benchmark_returns).cumprod()
        benchmark_cumulative = benchmark_cumulative.reindex(target_index).ffill().dropna()
        if benchmark_cumulative.empty:
            warnings.append(f"No benchmark overlap for {symbol}; using Cash (0%) benchmark")
            return pd.Series(1.0, index=target_index), "cash_0", warnings
        benchmark_cumulative = benchmark_cumulative / float(benchmark_cumulative.iloc[0])
        benchmark_cumulative = benchmark_cumulative.reindex(target_index).ffill().fillna(1.0)
        return benchmark_cumulative, f"history_{symbol}", warnings

    def convert_series_to_base(
        self,
        series: pd.Series,
        quote_ccy: str,
        base_ccy: str,
        lookback_days: int,
        warnings: list[str],
        *,
        label: str = "series",
        context: str = "Series",
    ) -> pd.Series | None:
        result = convert_history_to_base_currency(
            series,
            quote_ccy,
            base_ccy,
            lookback_days,
            self.market_data,
            fx_service=self.fx_service,
            label=label,
            context=context,
        )
        warnings.extend(result.warnings)
        return result.series

    def estimate_day_pnl_from_history(
        self,
        snapshot: PortfolioSnapshot,
        prices: dict[str, pd.Series],
    ) -> tuple[float | None, float | None, str | None, str | None]:
        if snapshot.day_pnl is not None:
            return snapshot.day_pnl, snapshot.day_pnl_pct, snapshot.day_pnl_source or "account_summary", None

        fx_by_currency: dict[str, float | None] = {}
        total_pnl = 0.0
        missing_symbols: list[str] = []
        for position in snapshot.positions:
            if position.symbol.startswith("CASH") or position.sec_type == "CASH":
                continue
            identity = identity_for_position(position)
            series = prices.get(identity.instrument_id)
            if series is None:
                missing_symbols.append(identity.display_symbol)
                continue
            clean = series.dropna()
            if len(clean) < 2:
                missing_symbols.append(identity.display_symbol)
                continue
            latest = float(clean.iloc[-1])
            previous = float(clean.iloc[-2])
            currency = str(position.currency or "").upper()
            if currency == snapshot.base_currency.upper():
                fx_rate = 1.0
            elif position.fx_rate is not None:
                fx_rate = float(position.fx_rate)
            elif currency in fx_by_currency:
                fx_rate = fx_by_currency[currency]
            else:
                fx_rate = self.fx_service.get_rate(snapshot.base_currency, currency)
                fx_by_currency[currency] = fx_rate
            if fx_rate is None:
                missing_symbols.append(identity.display_symbol)
                continue
            total_pnl += float(position.quantity) * (latest - previous) * float(fx_rate)

        if missing_symbols:
            symbols = ", ".join(sorted(set(missing_symbols)))
            return None, None, "historical_eod", f"Day P&L unavailable: missing daily bars/FX for {symbols}"

        previous_value = None
        if snapshot.net_liquidation is not None:
            previous_value = snapshot.net_liquidation - total_pnl
        elif snapshot.total_market_value is not None or snapshot.total_cash is not None:
            current_value = float((snapshot.total_market_value or 0.0) + (snapshot.total_cash or 0.0))
            previous_value = current_value - total_pnl
        pct = None
        if previous_value and previous_value != 0:
            pct = float(total_pnl / previous_value)
        return float(total_pnl), pct, "historical_eod", "Day P&L estimated from latest two daily bars (EOD approximation)"

    def load_performance_from_store(
        self,
        history_result: PortfolioHistoryLoadResult | None = None,
    ) -> tuple[pd.Series, pd.Series, float] | None:
        history_df = (
            history_result.frame
            if history_result is not None
            else self.history_store.load_series()
        )
        if history_df.empty or "portfolio_value" not in history_df.columns:
            return None
        values = pd.to_numeric(history_df["portfolio_value"], errors="coerce").dropna()
        if len(values) < 2:
            return None
        returns = values.pct_change().dropna()
        if returns.empty:
            return None
        cumulative = values / float(values.iloc[0])
        return returns, cumulative, float(values.iloc[0])

    @staticmethod
    def portfolio_base_value(snapshot: PortfolioSnapshot) -> float | None:
        if snapshot.net_liquidation is not None:
            return snapshot.net_liquidation
        if snapshot.total_market_value is None and snapshot.total_cash is None:
            return None
        return float((snapshot.total_market_value or 0.0) + (snapshot.total_cash or 0.0))

    def _load_prices(
        self,
        snapshot: PortfolioSnapshot,
        lookback_days: int,
    ) -> tuple[dict[str, pd.Series], list[str]]:
        if self.data_provider is not None:
            return self.data_provider.load_prices(snapshot, lookback_days)
        if self.client.mock and self.mock_service is not None:
            prices: dict[str, pd.Series] = {}
            missing: list[str] = []
            for position in snapshot.positions:
                if position.symbol.startswith("CASH"):
                    continue
                identity = identity_for_position(position)
                series = self.mock_service.load_history(position.symbol)
                if series is None:
                    missing.append(identity.display_symbol)
                else:
                    prices[identity.instrument_id] = series.astype(float)
            return prices, missing

        contracts: list[Contract] = []
        keys: list[str] = []
        labels: list[str] = []
        for position in snapshot.positions:
            if position.symbol.startswith("CASH"):
                continue
            identity = identity_for_position(position)
            contracts.append(contract_for_position(position))
            keys.append(identity.instrument_id)
            labels.append(identity.display_symbol)
        return self.market_data.fetch_histories(contracts, lookback_days, keys=keys, labels=labels)

    @staticmethod
    def ensure_cash_returns(snapshot: PortfolioSnapshot, returns_df: pd.DataFrame) -> pd.DataFrame:
        cash_symbols = [
            position.resolved_instrument_id()
            for position in snapshot.positions
            if position.symbol.startswith("CASH") and position.base_market_value is not None
        ]
        if cash_symbols:
            returns_df = returns_df.copy()
            for symbol in cash_symbols:
                if symbol not in returns_df.columns:
                    returns_df[symbol] = 0.0
        return returns_df

    @staticmethod
    def weights_for_symbols(snapshot: PortfolioSnapshot, symbols: list[str]) -> pd.Series:
        values: dict[str, float] = {}
        for position in snapshot.positions:
            instrument_id = position.resolved_instrument_id()
            if instrument_id in symbols and position.base_market_value is not None:
                values[instrument_id] = float(position.base_market_value)
        return PortfolioService._compute_weights(pd.Series(values))

    @staticmethod
    def _align_prices(prices: dict[str, pd.Series]) -> pd.DataFrame:
        from src.analytics.returns import align_prices

        return align_prices(prices)

    @staticmethod
    def _compute_returns(price_df: pd.DataFrame) -> pd.DataFrame:
        from src.analytics.returns import compute_returns

        return compute_returns(price_df)

    @staticmethod
    def _compute_weights(values: pd.Series) -> pd.Series:
        from src.analytics.risk_metrics import compute_weights

        return compute_weights(values)

    @staticmethod
    def _portfolio_returns(returns_df: pd.DataFrame, weights: pd.Series) -> pd.Series:
        from src.analytics.risk_metrics import portfolio_returns

        return portfolio_returns(returns_df, weights)
