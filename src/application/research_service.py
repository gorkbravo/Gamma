from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.analytics.returns import align_prices, compute_returns
from src.analytics.risk_metrics import compute_weights, portfolio_returns
from src.models.app_mode import ResearchScopeType, SyntheticPosition
from src.models.portfolio import PortfolioSnapshot
from src.services.data_providers import ResearchDataProvider


@dataclass(frozen=True)
class ResearchAnalysisRequest:
    scope_type: ResearchScopeType
    primary_symbol: str = ""
    synthetic_positions: list[SyntheticPosition] = field(default_factory=list)
    benchmark_symbol: str = "SPY"
    lookback_days: int = 252


@dataclass
class ResearchAnalysisResult:
    scope_type: ResearchScopeType
    snapshot: PortfolioSnapshot | None
    perf: pd.Series
    benchmark_returns: pd.Series
    benchmark_symbol: str
    weights: pd.Series
    primary_price: pd.Series
    warnings: list[str]


class ResearchService:
    def __init__(self, provider: ResearchDataProvider) -> None:
        self.provider = provider

    def analyze(self, request: ResearchAnalysisRequest) -> ResearchAnalysisResult:
        warnings: list[str] = []
        primary_symbol = str(request.primary_symbol or "").strip().upper()
        benchmark_symbol = str(request.benchmark_symbol or "").strip().upper() or "SPY"
        snapshot, snapshot_warnings = self.provider.build_snapshot_for_scope(
            request.scope_type,
            primary_symbol=primary_symbol,
            synthetic_positions=request.synthetic_positions,
        )
        warnings.extend(snapshot_warnings)
        if snapshot is None:
            return self._empty_result(
                scope_type=request.scope_type,
                benchmark_symbol=benchmark_symbol,
                warnings=warnings,
            )

        prices, missing = self.provider.load_prices(snapshot, lookback_days=request.lookback_days)
        primary_price = pd.Series(dtype=float)
        if request.scope_type == ResearchScopeType.SINGLE_TICKER:
            primary_price = prices.get(primary_symbol, pd.Series(dtype=float))
        if missing:
            warnings.append(f"Missing history for: {', '.join(missing)}")
        if not prices:
            warnings.append("No valid history found for selected scope")
            return self._empty_result(
                scope_type=request.scope_type,
                snapshot=snapshot,
                benchmark_symbol=benchmark_symbol,
                primary_price=primary_price,
                warnings=warnings,
            )

        returns_df = compute_returns(align_prices(prices))
        if returns_df.empty:
            warnings.append("No overlapping history across selected symbols")
            return self._empty_result(
                scope_type=request.scope_type,
                snapshot=snapshot,
                benchmark_symbol=benchmark_symbol,
                primary_price=primary_price,
                warnings=warnings,
            )

        values = {
            position.symbol: float(position.base_market_value)
            for position in snapshot.positions
            if position.base_market_value is not None and position.symbol in returns_df.columns
        }
        weights = compute_weights(pd.Series(values))
        if weights.empty:
            warnings.append("Weights are invalid for selected scope")
            return self._empty_result(
                scope_type=request.scope_type,
                snapshot=snapshot,
                benchmark_symbol=benchmark_symbol,
                weights=weights,
                primary_price=primary_price,
                warnings=warnings,
            )

        perf = portfolio_returns(returns_df.reindex(columns=weights.index.tolist()), weights)
        if perf.empty:
            warnings.append("No performance series could be computed")
            return self._empty_result(
                scope_type=request.scope_type,
                snapshot=snapshot,
                benchmark_symbol=benchmark_symbol,
                weights=weights,
                primary_price=primary_price,
                perf=perf,
                warnings=warnings,
            )

        benchmark_returns = self.load_benchmark_returns(benchmark_symbol, request.lookback_days, warnings)
        return ResearchAnalysisResult(
            scope_type=request.scope_type,
            snapshot=snapshot,
            perf=perf,
            benchmark_returns=benchmark_returns,
            benchmark_symbol=benchmark_symbol,
            weights=weights,
            primary_price=primary_price,
            warnings=warnings,
        )

    def load_benchmark_returns(
        self,
        benchmark_symbol: str,
        lookback_days: int,
        warnings: list[str] | None = None,
    ) -> pd.Series:
        warning_list = warnings if warnings is not None else []
        symbol = str(benchmark_symbol or "").strip().upper() or "SPY"
        bench_series = self.provider.load_symbol_history(symbol, lookback_days)
        if bench_series is None or bench_series.empty:
            warning_list.append(f"Benchmark history unavailable for {symbol}")
            return pd.Series(dtype=float)
        bench_returns = compute_returns(align_prices({symbol: bench_series}))[symbol]
        if bench_returns.empty:
            warning_list.append(f"Benchmark returns unavailable for {symbol}")
            return pd.Series(dtype=float)
        return bench_returns

    @staticmethod
    def _empty_result(
        scope_type: ResearchScopeType,
        benchmark_symbol: str,
        warnings: list[str],
        snapshot: PortfolioSnapshot | None = None,
        weights: pd.Series | None = None,
        primary_price: pd.Series | None = None,
        perf: pd.Series | None = None,
    ) -> ResearchAnalysisResult:
        return ResearchAnalysisResult(
            scope_type=scope_type,
            snapshot=snapshot,
            perf=perf if perf is not None else pd.Series(dtype=float),
            benchmark_returns=pd.Series(dtype=float),
            benchmark_symbol=benchmark_symbol,
            weights=weights if weights is not None else pd.Series(dtype=float),
            primary_price=primary_price if primary_price is not None else pd.Series(dtype=float),
            warnings=warnings,
        )
