from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping

import pandas as pd

from src.application.instrument_identity import identity_for_position
from src.models.instruments import InstrumentDefaults, InstrumentReference
from src.models.portfolio import PortfolioSnapshot
from src.services.data_providers import PortfolioDataProvider, contract_for_instrument, contract_for_position
from src.services.fx import FXService
from src.services.ibkr_client import IBKRClient
from src.services.market_data import MarketDataService
from src.services.mock_data import MockDataService
from src.services.portfolio_history_store import PortfolioHistoryStore
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
    day_pnl: float | None = None
    day_pnl_pct: float | None = None
    day_pnl_source: str | None = None


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

    def compute_performance(self, request: PortfolioPerformanceRequest) -> PortfolioPerformanceResult:
        snapshot = request.snapshot
        warnings: list[str] = []
        prices, missing = self._load_prices(snapshot, request.lookback_days)
        day_pnl, day_pnl_pct, day_pnl_source, pnl_warning = self.estimate_day_pnl_from_history(snapshot, prices)
        if pnl_warning:
            warnings.append(pnl_warning)
        warnings.extend(self.market_data.drain_errors())
        if missing:
            warnings.append(f"Missing history for: {', '.join(missing)}")

        price_df = self._align_prices(prices)
        returns_df = self._compute_returns(price_df)
        if returns_df.empty:
            hist_perf = self.load_performance_from_store()
            if hist_perf is None:
                return PortfolioPerformanceResult(
                    warnings=warnings,
                    message="No performance data",
                    missing_symbols=missing,
                    day_pnl=day_pnl,
                    day_pnl_pct=day_pnl_pct,
                    day_pnl_source=day_pnl_source,
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
            return PortfolioPerformanceResult(
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

        returns_df = self.ensure_cash_returns(snapshot, returns_df)
        weights = self.weights_for_symbols(snapshot, returns_df.columns.tolist())
        if weights.empty:
            return PortfolioPerformanceResult(
                warnings=warnings + ["No weights for performance"],
                message="No weights for performance",
                missing_symbols=missing,
                day_pnl=day_pnl,
                day_pnl_pct=day_pnl_pct,
                day_pnl_source=day_pnl_source,
            )

        perf_returns = self._portfolio_returns(returns_df, weights)
        if perf_returns.empty:
            return PortfolioPerformanceResult(
                warnings=warnings + ["No performance data"],
                message="No performance data",
                missing_symbols=missing,
                day_pnl=day_pnl,
                day_pnl_pct=day_pnl_pct,
                day_pnl_source=day_pnl_source,
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
        return PortfolioPerformanceResult(
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
        if self.client.mock and self.mock_service is not None:
            series = self.mock_service.load_history(symbol)
        else:
            contract = contract_for_instrument(
                InstrumentReference(symbol=symbol).with_defaults(self.benchmark_defaults)
            )
            series = self.market_data.fetch_history(contract, lookback_days)
        if series is None or series.empty:
            warnings.append(f"No benchmark data for {symbol}; using Cash (0%) benchmark")
            return pd.Series(1.0, index=target_index), "cash_0", warnings

        converted = self.convert_series_to_base(
            series.astype(float),
            quote_ccy="USD",
            base_ccy=snapshot.base_currency,
            lookback_days=lookback_days,
            warnings=warnings,
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
    ) -> pd.Series | None:
        quote = str(quote_ccy or "").upper()
        base = str(base_ccy or "").upper()
        if quote == base:
            return series
        fx_series = self.market_data.fetch_fx_history(base, quote, lookback_days)
        if fx_series is not None and not fx_series.empty:
            aligned = fx_series.reindex(series.index).ffill().dropna()
            if not aligned.empty:
                common_index = series.index.intersection(aligned.index)
                if not common_index.empty:
                    return series.reindex(common_index) * aligned.reindex(common_index)
        rate = self.fx_service.get_rate(base, quote)
        if rate is None:
            warnings.append(f"FX unavailable for benchmark conversion {quote}->{base}")
            return None
        warnings.append(f"Benchmark FX conversion {quote}->{base} uses latest spot rate")
        return series * float(rate)

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

    def load_performance_from_store(self) -> tuple[pd.Series, pd.Series, float] | None:
        history_df = self.history_store.load_series()
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
