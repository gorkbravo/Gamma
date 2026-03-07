from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from ib_insync import Contract

from src.analytics.returns import align_prices, compute_returns
from src.analytics.risk_metrics import (
    compute_weights,
    max_drawdown,
    portfolio_returns,
    realized_vol,
    risk_contributions,
)
from src.analytics.var import historical_var_cvar, monte_carlo_var_cvar, parametric_var
from src.models.portfolio import PortfolioSnapshot, RiskResults
from src.services.ibkr_client import IBKRClient
from src.services.market_data import MarketDataService
from src.services.mock_data import MockDataService
from src.services.risk_free_rate import RiskFreeRateService


@dataclass(frozen=True)
class RiskComputeRequest:
    snapshot: PortfolioSnapshot
    alpha: float
    lookback_days: int
    horizon_days: int
    mc_horizon_days: int
    mc_simulation_model: str
    mc_num_simulations: int
    beta_window: int
    benchmark_symbol: str
    base_currency: str
    recommended_min_obs: int = 60


@dataclass
class BenchmarkMetricsResult:
    beta: float | None = None
    correlation: float | None = None
    alpha_annual: float | None = None
    overlap_count: int | None = None
    warnings: List[str] | None = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


@dataclass
class RiskComputationPayload:
    results: RiskResults
    portfolio_returns: pd.Series
    returns_df: pd.DataFrame
    contributions: pd.Series
    weights: pd.Series
    marginal_contribution_to_risk: pd.Series
    component_var: pd.Series


class RiskService:
    _MC_RANDOM_SEED = 42

    def __init__(
        self,
        client: IBKRClient,
        market_data: MarketDataService,
        mock_service: MockDataService,
        risk_free_service: RiskFreeRateService | None,
    ) -> None:
        self.client = client
        self.market_data = market_data
        self.mock_service = mock_service
        self.risk_free_service = risk_free_service

    def compute(self, request: RiskComputeRequest, progress_cb=None) -> RiskComputationPayload:
        snapshot = request.snapshot
        warnings: List[str] = []
        excluded_assets: Dict[str, str] = {}
        total_portfolio_value = snapshot.net_liquidation
        if total_portfolio_value is None:
            if snapshot.total_market_value is None and snapshot.total_cash is None:
                warnings.append("Portfolio value unavailable; using 0")
                total_portfolio_value = 0.0
            else:
                total_portfolio_value = (snapshot.total_market_value or 0.0) + (snapshot.total_cash or 0.0)
        if request.horizon_days > 1:
            warnings.append("Historical VaR/CVaR shown for 1d; parametric scaled by sqrt(time).")

        prices, missing = self._load_prices(snapshot, request.lookback_days, progress_cb)
        if missing:
            warnings.append(f"Missing history for: {', '.join(missing)}")
            for symbol in missing:
                excluded_assets[symbol] = "No historical bars"
        warnings.extend(self.market_data.drain_errors())

        price_df = align_prices(prices)
        returns_df = compute_returns(price_df)
        if returns_df.empty:
            warnings.append("No return history available")
            for symbol in prices.keys():
                excluded_assets.setdefault(symbol, "Insufficient overlapping history")

        returns_df = self._ensure_cash_returns(snapshot, returns_df)
        weights = self._weights_for_symbols(snapshot, returns_df.columns.tolist())
        for symbol in returns_df.columns:
            if symbol not in weights.index:
                excluded_assets.setdefault(symbol, "Missing base market value")
        if weights.empty:
            warnings.append("No weights available for VaR")

        risk_symbols = [symbol for symbol in returns_df.columns if symbol in weights.index]
        risk_returns_df = returns_df.reindex(columns=risk_symbols) if not returns_df.empty else pd.DataFrame()
        weights_aligned = weights.reindex(risk_symbols).dropna()
        if not risk_returns_df.empty:
            risk_returns_df = risk_returns_df.reindex(columns=weights_aligned.index.tolist())

        covered_portfolio_value = 0.0
        if not weights_aligned.empty:
            covered_symbols = set(weights_aligned.index)
            covered_portfolio_value = float(
                sum(
                    float(position.base_market_value or 0.0)
                    for position in snapshot.positions
                    if position.symbol in covered_symbols and position.base_market_value is not None
                )
            )
        elif total_portfolio_value == 0:
            covered_portfolio_value = 0.0

        port_ret = portfolio_returns(risk_returns_df, weights_aligned)
        if len(port_ret) < 2 and not returns_df.empty:
            warnings.append("Return series too short for stable risk metrics")
        if 0 < len(port_ret) < request.recommended_min_obs:
            warnings.append(
                f"Only {len(port_ret)} observations available ({request.recommended_min_obs} recommended minimum); "
                "interpret with care."
            )

        hist_var_r, hist_cvar_r = historical_var_cvar(port_ret, request.alpha)
        param_var_r = None
        cov = None
        if not risk_returns_df.empty and not weights_aligned.empty:
            cov_df = risk_returns_df.cov().reindex(index=weights_aligned.index, columns=weights_aligned.index)
            cov_values = cov_df.to_numpy(dtype=float, copy=True)
            if cov_values.size == 0 or not np.isfinite(cov_values).all():
                warnings.append("Parametric VaR unavailable: invalid covariance (NaN/insufficient data)")
            elif np.any(np.diag(cov_values) < -1e-12):
                warnings.append("Parametric VaR unavailable: covariance has negative diagonal variance")
            else:
                cov = cov_values
            param_var_r = parametric_var(weights_aligned.values, cov, request.alpha) if cov is not None else None
            if request.horizon_days > 1 and param_var_r is not None:
                param_var_r = param_var_r * (request.horizon_days ** 0.5)

        hist_var = hist_var_r * covered_portfolio_value if hist_var_r is not None else None
        hist_cvar = hist_cvar_r * covered_portfolio_value if hist_cvar_r is not None else None
        param_var = param_var_r * covered_portfolio_value if param_var_r is not None else None

        risk_coverage_ratio = None
        if total_portfolio_value is not None and total_portfolio_value > 0:
            risk_coverage_ratio = covered_portfolio_value / float(total_portfolio_value)
        scale_to_total = None
        if covered_portfolio_value and total_portfolio_value and covered_portfolio_value > 0:
            scale_to_total = float(total_portfolio_value) / float(covered_portfolio_value)
        hist_var_total_estimate = hist_var * scale_to_total if hist_var is not None and scale_to_total else None
        hist_cvar_total_estimate = hist_cvar * scale_to_total if hist_cvar is not None and scale_to_total else None
        param_var_total_estimate = param_var * scale_to_total if param_var is not None and scale_to_total else None

        monte_carlo_warning = self._monte_carlo_eligibility_warning(
            snapshot=snapshot,
            weights=weights_aligned,
            total_portfolio_value=total_portfolio_value,
        )
        monte_carlo_result = None
        if monte_carlo_warning is not None:
            warnings.append(monte_carlo_warning)
        elif not risk_returns_df.empty and not weights_aligned.empty:
            monte_carlo_result = monte_carlo_var_cvar(
                asset_returns=risk_returns_df,
                weights=weights_aligned,
                alpha=request.alpha,
                horizon_days=request.mc_horizon_days,
                model_name=request.mc_simulation_model,
                num_simulations=request.mc_num_simulations,
                random_seed=self._MC_RANDOM_SEED,
            )
            if monte_carlo_result is None:
                warnings.append(
                    f"Monte Carlo VaR unavailable for {request.mc_simulation_model}: invalid aligned returns or weights."
                )

        monte_carlo_var = (
            monte_carlo_result.var_return * covered_portfolio_value
            if monte_carlo_result is not None and monte_carlo_result.var_return is not None
            else None
        )
        monte_carlo_cvar = (
            monte_carlo_result.cvar_return * covered_portfolio_value
            if monte_carlo_result is not None and monte_carlo_result.cvar_return is not None
            else None
        )
        monte_carlo_var_total_estimate = (
            monte_carlo_var * scale_to_total if monte_carlo_var is not None and scale_to_total else None
        )
        monte_carlo_cvar_total_estimate = (
            monte_carlo_cvar * scale_to_total if monte_carlo_cvar is not None and scale_to_total else None
        )
        if risk_coverage_ratio is not None and risk_coverage_ratio < 0.999:
            warnings.append(
                "Risk coverage is "
                f"{risk_coverage_ratio * 100:.1f}% of portfolio value; covered risk is exact for included assets and "
                "total VaR figures are coverage-scaled estimates."
            )
        if risk_coverage_ratio is not None and risk_coverage_ratio < 0.95:
            warnings.append("Risk coverage below 95%; headline risk estimates may be materially incomplete.")

        daily_vol, annual_vol = realized_vol(port_ret)
        max_dd = max_drawdown(port_ret)

        benchmark = self._beta_corr_alpha(
            port_ret=port_ret,
            lookback_days=request.lookback_days,
            beta_window=request.beta_window,
            base_currency=request.base_currency,
            benchmark_symbol=request.benchmark_symbol,
        )
        warnings.extend(benchmark.warnings or [])
        if benchmark.beta is None or benchmark.correlation is None:
            warnings.append("Benchmark beta/correlation unavailable")

        concentration_hhi, top5_weight, effective_bets = self._concentration_metrics(weights)

        results = RiskResults(
            alpha=request.alpha,
            lookback_days=request.lookback_days,
            horizon_days=request.horizon_days,
            portfolio_value=float(total_portfolio_value),
            historical_var=hist_var,
            historical_cvar=hist_cvar,
            parametric_var=param_var,
            daily_vol=daily_vol,
            annual_vol=annual_vol,
            max_drawdown=max_dd,
            beta=benchmark.beta,
            correlation=benchmark.correlation,
            alpha_annual=benchmark.alpha_annual,
            covered_portfolio_value=covered_portfolio_value,
            risk_coverage_ratio=risk_coverage_ratio,
            historical_var_total_estimate=hist_var_total_estimate,
            historical_cvar_total_estimate=hist_cvar_total_estimate,
            parametric_var_total_estimate=param_var_total_estimate,
            monte_carlo_model=request.mc_simulation_model,
            monte_carlo_horizon_days=request.mc_horizon_days,
            monte_carlo_num_simulations=request.mc_num_simulations,
            monte_carlo_var=monte_carlo_var,
            monte_carlo_cvar=monte_carlo_cvar,
            monte_carlo_var_total_estimate=monte_carlo_var_total_estimate,
            monte_carlo_cvar_total_estimate=monte_carlo_cvar_total_estimate,
            monte_carlo_terminal_returns=(
                monte_carlo_result.terminal_returns if monte_carlo_result is not None else None
            ),
            monte_carlo_fan_percentiles=(
                monte_carlo_result.fan_percentiles if monte_carlo_result is not None else None
            ),
            monte_carlo_sample_paths=monte_carlo_result.sample_paths if monte_carlo_result is not None else None,
            aligned_obs_count=int(len(port_ret)) if not port_ret.empty else 0,
            benchmark_overlap_count=benchmark.overlap_count,
            concentration_hhi=concentration_hhi,
            top5_weight=top5_weight,
            effective_bets=effective_bets,
            excluded_assets=excluded_assets,
            warnings=warnings,
        )

        contributions = pd.Series(dtype=float)
        marginal_contribution_to_risk = pd.Series(dtype=float)
        component_var = pd.Series(dtype=float)
        if cov is not None and not weights_aligned.empty:
            contribution_values = risk_contributions(weights_aligned.values, cov)
            if contribution_values.size == weights_aligned.size:
                contributions = pd.Series(contribution_values, index=weights_aligned.index)
            portfolio_var = float(weights_aligned.values.T @ cov @ weights_aligned.values)
            if portfolio_var < 0 and abs(portfolio_var) < 1e-12:
                portfolio_var = 0.0
            portfolio_sigma = float(np.sqrt(portfolio_var)) if portfolio_var > 0 else 0.0
            if portfolio_sigma > 0:
                mctr_values = (cov @ weights_aligned.values) / portfolio_sigma
                marginal_contribution_to_risk = pd.Series(mctr_values, index=weights_aligned.index)
                z_score = NormalDist().inv_cdf(request.alpha)
                component_var_values = weights_aligned.values * mctr_values * z_score
                if request.horizon_days > 1:
                    component_var_values = component_var_values * (request.horizon_days ** 0.5)
                component_var = pd.Series(component_var_values * covered_portfolio_value, index=weights_aligned.index)
            else:
                warnings.append("Risk contributions unavailable: non-positive portfolio variance")

        return RiskComputationPayload(
            results=results,
            portfolio_returns=port_ret,
            returns_df=returns_df,
            contributions=contributions,
            weights=weights,
            marginal_contribution_to_risk=marginal_contribution_to_risk,
            component_var=component_var,
        )

    @staticmethod
    def _monte_carlo_eligibility_warning(
        snapshot: PortfolioSnapshot,
        weights: pd.Series,
        total_portfolio_value: float | None,
    ) -> str | None:
        if weights.empty:
            return "Monte Carlo VaR unavailable: no covered weights or return history to simulate."
        tolerance = 1e-9
        negative_weight_symbols = [
            symbol for symbol, value in weights.items() if not str(symbol).startswith("CASH") and float(value) < -tolerance
        ]
        if negative_weight_symbols:
            return (
                "Monte Carlo VaR unavailable: negative covered weights detected "
                f"({', '.join(sorted(negative_weight_symbols))}); v1 supports long-only, unlevered portfolios only."
            )
        if total_portfolio_value is None or float(total_portfolio_value) <= 0:
            return "Monte Carlo VaR unavailable: portfolio value must be positive for long-only, unlevered simulation."

        flagged_symbols: List[str] = []
        gross_risky_exposure = 0.0
        for position in snapshot.positions:
            is_cash = position.sec_type == "CASH" or position.symbol.startswith("CASH")
            base_value = position.base_market_value
            market_value = position.market_value
            quantity = float(position.quantity or 0.0)
            explicit_weight = float(position.weight or 0.0) if position.weight is not None else None
            exposure = float(base_value) if base_value is not None else (float(market_value) if market_value is not None else None)
            if not is_cash and (
                (exposure is not None and exposure < -tolerance)
                or quantity < -tolerance
                or (explicit_weight is not None and explicit_weight < -tolerance)
            ):
                flagged_symbols.append(position.symbol)
            if not is_cash and exposure is not None:
                gross_risky_exposure += max(float(exposure), 0.0)

        if flagged_symbols:
            return (
                "Monte Carlo VaR unavailable: short or negative positions detected "
                f"({', '.join(sorted(set(flagged_symbols)))}); v1 supports long-only, unlevered portfolios only."
            )
        gross_ratio = gross_risky_exposure / float(total_portfolio_value) if total_portfolio_value else None
        if gross_ratio is not None and gross_ratio > 1.02:
            return (
                "Monte Carlo VaR unavailable: risky gross exposure exceeds portfolio value "
                f"({gross_ratio:.2f}x), which indicates leverage-like or offsetting positions."
            )
        return None

    def _load_prices(
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
            symbol = position.symbol
            if self.client.mock:
                series = self.mock_service.load_history(symbol)
            else:
                contract = Contract(
                    symbol=symbol,
                    secType=position.sec_type or "STK",
                    exchange="SMART",
                    currency=position.currency or "USD",
                )
                series = self.market_data.fetch_history(contract, lookback_days)
            if series is None or series.empty:
                missing.append(symbol)
            else:
                prices[symbol] = series.astype(float)
            if progress_cb is not None:
                progress_cb(index, total, symbol)
        return prices, missing

    @staticmethod
    def _ensure_cash_returns(snapshot: PortfolioSnapshot, returns_df: pd.DataFrame) -> pd.DataFrame:
        cash_symbols = [
            position.symbol
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
    def _weights_for_symbols(snapshot: PortfolioSnapshot, symbols: List[str]) -> pd.Series:
        values = {
            position.symbol: position.base_market_value
            for position in snapshot.positions
            if position.symbol in symbols and position.base_market_value is not None
        }
        return compute_weights(pd.Series(values))

    def _beta_corr_alpha(
        self,
        port_ret: pd.Series,
        lookback_days: int,
        beta_window: int,
        base_currency: str,
        benchmark_symbol: str,
    ) -> BenchmarkMetricsResult:
        result = BenchmarkMetricsResult()
        benchmark_returns, benchmark_warnings = self._load_benchmark_returns(lookback_days, base_currency, benchmark_symbol)
        result.warnings.extend(benchmark_warnings)
        if benchmark_returns is None or benchmark_returns.empty or port_ret.empty:
            return result
        aligned = pd.concat([port_ret.rename("portfolio"), benchmark_returns.rename("benchmark")], axis=1, join="inner").dropna()
        result.overlap_count = int(len(aligned))
        if len(aligned) < beta_window:
            result.warnings.append(
                f"Benchmark overlap {len(aligned)} < beta window {beta_window}; beta/correlation/Jensen alpha unavailable"
            )
            return result
        portfolio_series = aligned["portfolio"]
        benchmark_series = aligned["benchmark"]
        rolling_beta = portfolio_series.rolling(beta_window).cov(benchmark_series) / benchmark_series.rolling(beta_window).var()
        rolling_corr = portfolio_series.rolling(beta_window).corr(benchmark_series)
        beta = rolling_beta.dropna()
        corr = rolling_corr.dropna()
        if beta.empty or corr.empty:
            result.warnings.append("Benchmark beta/correlation unavailable after rolling window calculation")
            return result
        result.beta = float(beta.iloc[-1])
        result.correlation = float(corr.iloc[-1])

        base_ccy = str(base_currency or "").upper()
        if base_ccy != "USD":
            result.warnings.append(
                f"Jensen alpha unavailable for base currency {base_ccy or 'unknown'} (USD risk-free source only)."
            )
            return result
        if self.risk_free_service is None:
            result.warnings.append("Jensen alpha unavailable: risk-free service not configured")
            return result

        rf_series, rf_warnings = self.risk_free_service.get_usd_daily_returns(aligned.index.min(), aligned.index.max())
        result.warnings.extend(rf_warnings)
        if rf_series is None or rf_series.empty:
            result.warnings.append("Jensen alpha unavailable: no risk-free return series")
            return result
        aligned_rf = pd.concat([aligned, rf_series.rename("rf")], axis=1, join="inner").dropna()
        if len(aligned_rf) < beta_window:
            result.warnings.append(
                f"Risk-free aligned overlap {len(aligned_rf)} < beta window {beta_window}; Jensen alpha unavailable"
            )
            return result
        portfolio_excess = aligned_rf["portfolio"] - aligned_rf["rf"]
        benchmark_excess = aligned_rf["benchmark"] - aligned_rf["rf"]
        rolling_beta_excess = portfolio_excess.rolling(beta_window).cov(benchmark_excess) / benchmark_excess.rolling(beta_window).var()
        rolling_alpha = portfolio_excess.rolling(beta_window).mean() - rolling_beta_excess * benchmark_excess.rolling(beta_window).mean()
        alpha_series = rolling_alpha.dropna()
        if alpha_series.empty:
            result.warnings.append("Jensen alpha unavailable after rolling excess-return calculation")
            return result
        result.alpha_annual = float(alpha_series.iloc[-1] * 252.0)
        return result

    def _load_benchmark_returns(
        self,
        lookback_days: int,
        base_currency: str,
        symbol: str,
    ) -> tuple[pd.Series | None, List[str]]:
        warnings: List[str] = []
        if self.client.mock:
            series = self.mock_service.load_history(symbol)
        else:
            contract = Contract(symbol=symbol, secType="STK", exchange="SMART", currency="USD")
            series = self.market_data.fetch_history(contract, lookback_days)
        if series is None or series.empty:
            warnings.append(f"Benchmark history unavailable for {symbol}")
            return None, warnings
        converted, fx_warnings = self._convert_benchmark_to_base(series.astype(float), "USD", base_currency, lookback_days)
        warnings.extend(fx_warnings)
        if converted is None or converted.empty:
            warnings.append(f"Benchmark FX conversion failed for {symbol} into {base_currency}")
            return None, warnings
        return converted.pct_change().dropna(), warnings

    def _convert_benchmark_to_base(
        self,
        series: pd.Series,
        quote_ccy: str,
        base_ccy: str,
        lookback_days: int,
    ) -> tuple[pd.Series | None, List[str]]:
        warnings: List[str] = []
        quote = str(quote_ccy or "").upper()
        base = str(base_ccy or "").upper()
        if quote == base:
            return series, warnings
        fx_series = self.market_data.fetch_fx_history(base, quote, lookback_days)
        if fx_series is not None and not fx_series.empty:
            aligned = fx_series.reindex(series.index).ffill().dropna()
            if not aligned.empty:
                common_index = series.index.intersection(aligned.index)
                if not common_index.empty:
                    return series.reindex(common_index) * aligned.reindex(common_index), warnings
        fx_rate = self.market_data.fetch_fx_rate(base, quote)
        if fx_rate is None:
            return None, warnings
        warnings.append(f"Benchmark FX conversion used spot {quote}->{base} rate fallback")
        return series * float(fx_rate), warnings

    @staticmethod
    def _concentration_metrics(weights: pd.Series) -> Tuple[float | None, float | None, float | None]:
        if weights.empty:
            return None, None, None
        absolute_weights = weights.abs()
        total = float(absolute_weights.sum())
        if total <= 0:
            return None, None, None
        normalized = absolute_weights / total
        hhi = float((normalized ** 2).sum())
        top5 = float(normalized.sort_values(ascending=False).head(5).sum())
        effective_bets = float(1.0 / hhi) if hhi > 0 else None
        return hhi, top5, effective_bets
