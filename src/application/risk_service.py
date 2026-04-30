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
from src.application.instrument_identity import identity_for_position
from src.models.instruments import InstrumentDefaults, InstrumentReference
from src.models.portfolio import PortfolioSnapshot, RiskResults
from src.services.data_providers import (
    AppDataProvider,
    contract_for_instrument,
    contract_for_position,
    convert_history_to_base_currency,
    normalize_snapshot_price_histories,
)
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
    include_monte_carlo: bool = True
    recommended_min_obs: int = 60


@dataclass
class BenchmarkMetricsResult:
    beta: float | None = None
    correlation: float | None = None
    alpha_annual: float | None = None
    overlap_count: int | None = None
    returns: pd.Series | None = None
    warnings: List[str] | None = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


@dataclass
class RiskComputationPayload:
    snapshot: PortfolioSnapshot
    results: RiskResults
    portfolio_returns: pd.Series
    benchmark_returns: pd.Series
    returns_df: pd.DataFrame
    contributions: pd.Series
    weights: pd.Series
    marginal_contribution_to_risk: pd.Series
    component_var: pd.Series
    frontier_points: list["RiskFrontierPoint"]
    correlation_matrix: pd.DataFrame


@dataclass(frozen=True)
class RiskFrontierWeight:
    symbol: str
    instrument_id: str | None
    display_symbol: str | None
    weight: float


@dataclass(frozen=True)
class RiskFrontierPoint:
    label: str
    kind: str
    annual_return: float
    annual_vol: float
    sharpe: float | None
    weights: list[RiskFrontierWeight]


class RiskService:
    _MC_RANDOM_SEED = 42

    def __init__(
        self,
        client: IBKRClient,
        market_data: MarketDataService,
        mock_service: MockDataService,
        risk_free_service: RiskFreeRateService | None,
        benchmark_defaults: InstrumentDefaults | None = None,
    ) -> None:
        self.client = client
        self.market_data = market_data
        self.mock_service = mock_service
        self.risk_free_service = risk_free_service
        self.benchmark_defaults = benchmark_defaults or InstrumentDefaults(
            provider="benchmark",
            sec_type="STK",
            exchange="SMART",
            currency="USD",
        )

    def compute(
        self,
        request: RiskComputeRequest,
        progress_cb=None,
        data_provider: AppDataProvider | None = None,
    ) -> RiskComputationPayload:
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

        raw_prices, missing = self._load_prices(snapshot, request.lookback_days, progress_cb, data_provider=data_provider)
        provider_warnings = self._drain_provider_history_warnings(data_provider)
        if missing:
            warnings.append(f"Missing history for: {', '.join(missing)}")
        warnings.extend(provider_warnings)
        normalized_prices = normalize_snapshot_price_histories(
            snapshot,
            raw_prices,
            request.lookback_days,
            self.market_data,
        )
        prices = normalized_prices.prices
        warnings.extend(normalized_prices.warnings)
        excluded_assets.update(normalized_prices.excluded_assets)
        for position in snapshot.positions:
            if position.symbol.startswith("CASH"):
                continue
            identity = identity_for_position(position)
            if identity.instrument_id not in raw_prices:
                excluded_assets.setdefault(identity.instrument_id, "No historical bars")
            elif identity.instrument_id not in prices:
                excluded_assets.setdefault(identity.instrument_id, "No base-currency history")
        warnings.extend(self.market_data.drain_errors())

        price_df = align_prices(prices)
        returns_df = compute_returns(price_df)
        if returns_df.empty:
            warnings.append("No return history available")
            for instrument_id in prices.keys():
                excluded_assets.setdefault(instrument_id, "Insufficient overlapping history")

        returns_df = self._ensure_cash_returns(snapshot, returns_df)
        weights = self._weights_for_symbols(snapshot, returns_df.columns.tolist())
        for instrument_id in returns_df.columns:
            if instrument_id not in weights.index:
                excluded_assets.setdefault(instrument_id, "Missing base market value")
        if weights.empty:
            warnings.append("No weights available for VaR")

        risk_instrument_ids = [instrument_id for instrument_id in returns_df.columns if instrument_id in weights.index]
        risk_returns_df = returns_df.reindex(columns=risk_instrument_ids) if not returns_df.empty else pd.DataFrame()
        weights_aligned = weights.reindex(risk_instrument_ids).dropna()
        if not risk_returns_df.empty:
            risk_returns_df = risk_returns_df.reindex(columns=weights_aligned.index.tolist())

        covered_portfolio_value = 0.0
        covered_risk_basis_value = 0.0
        if not weights_aligned.empty:
            covered_instrument_ids = set(weights_aligned.index)
            covered_positions = [
                position
                for position in snapshot.positions
                if position.resolved_instrument_id() in covered_instrument_ids and position.base_market_value is not None
            ]
            covered_portfolio_value = float(
                sum(float(position.base_market_value or 0.0) for position in covered_positions)
            )
            covered_risk_basis_value = float(
                sum(abs(float(position.base_market_value or 0.0)) for position in covered_positions if not self._is_cash(position))
            )
        elif total_portfolio_value == 0:
            covered_portfolio_value = 0.0
            covered_risk_basis_value = 0.0

        known_risk_basis_value = float(
            sum(
                abs(float(position.base_market_value or 0.0))
                for position in snapshot.positions
                if position.base_market_value is not None and not self._is_cash(position)
            )
        )
        risk_basis_value = known_risk_basis_value
        if self._has_unknown_risky_values(snapshot):
            risk_basis_value = max(float(total_portfolio_value or 0.0), known_risk_basis_value)

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
        if risk_basis_value > 0:
            risk_coverage_ratio = covered_risk_basis_value / float(risk_basis_value)
        scale_to_total = None
        if covered_risk_basis_value > 0 and risk_basis_value > 0:
            scale_to_total = float(risk_basis_value) / float(covered_risk_basis_value)
        hist_var_total_estimate = hist_var * scale_to_total if hist_var is not None and scale_to_total else None
        hist_cvar_total_estimate = hist_cvar * scale_to_total if hist_cvar is not None and scale_to_total else None
        param_var_total_estimate = param_var * scale_to_total if param_var is not None and scale_to_total else None

        monte_carlo_warning = None
        monte_carlo_result = None
        if request.include_monte_carlo:
            monte_carlo_warning = self._monte_carlo_eligibility_warning(
                snapshot=snapshot,
                weights=weights_aligned,
                total_portfolio_value=total_portfolio_value,
            )
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
                f"{risk_coverage_ratio * 100:.1f}% of the modeled risk basis; covered risk is exact for included assets "
                "and total VaR figures are risk-basis-scaled estimates."
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
            covered_risk_basis_value=covered_risk_basis_value,
            risk_basis_value=risk_basis_value,
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

        risk_free_rate_annual, risk_free_warnings = self._risk_free_rate_for_frontier(
            request=request,
            returns_df=risk_returns_df,
        )
        warnings.extend(risk_free_warnings)

        frontier_points, frontier_warnings = self._build_efficient_frontier(
            snapshot=snapshot,
            returns_df=risk_returns_df,
            weights=weights_aligned,
            risk_free_rate_annual=risk_free_rate_annual,
        )
        warnings.extend(frontier_warnings)
        results.warnings = warnings

        return RiskComputationPayload(
            snapshot=snapshot,
            results=results,
            portfolio_returns=port_ret,
            benchmark_returns=benchmark.returns if benchmark.returns is not None else pd.Series(dtype=float),
            returns_df=returns_df,
            contributions=contributions,
            weights=weights,
            marginal_contribution_to_risk=marginal_contribution_to_risk,
            component_var=component_var,
            frontier_points=frontier_points,
            correlation_matrix=self._correlation_matrix(risk_returns_df, snapshot),
        )

    @staticmethod
    def _drain_provider_history_warnings(data_provider: AppDataProvider | None) -> list[str]:
        drain = getattr(data_provider, "drain_history_warnings", None)
        if not callable(drain):
            return []
        try:
            return list(drain())
        except Exception:
            return []

    @classmethod
    def _build_efficient_frontier(
        cls,
        *,
        snapshot: PortfolioSnapshot,
        returns_df: pd.DataFrame,
        weights: pd.Series,
        risk_free_rate_annual: float | None = None,
    ) -> tuple[list[RiskFrontierPoint], list[str]]:
        warnings: list[str] = []
        if returns_df.empty or weights.empty:
            return [], ["Efficient frontier unavailable: no covered return history and weights."]

        positions_by_id = {position.resolved_instrument_id(): position for position in snapshot.positions}
        risky_snapshot_count = sum(
            1
            for position in snapshot.positions
            if not cls._is_cash(position) and float(position.base_market_value or 0.0) > 0
        )
        positive_covered_risky_count = sum(
            1
            for instrument_id in weights.index
            if not cls._is_cash(positions_by_id.get(str(instrument_id)))
            and float(weights.get(instrument_id, 0.0) or 0.0) > 0
        )
        eligible: list[str] = []
        for instrument_id in weights.index:
            position = positions_by_id.get(str(instrument_id))
            if position is None or cls._is_cash(position):
                continue
            if float(weights.get(instrument_id, 0.0) or 0.0) <= 0:
                continue
            if instrument_id not in returns_df.columns:
                continue
            series = pd.to_numeric(returns_df[instrument_id], errors="coerce").dropna()
            if len(series) >= 3 and float(series.std() or 0.0) > 1e-10:
                eligible.append(str(instrument_id))

        if len(eligible) < 2:
            return [], [
                "Efficient frontier unavailable: need at least two eligible non-cash long positions with usable return variance "
                f"(eligible {len(eligible)}; positive covered risky {positive_covered_risky_count}; "
                f"snapshot risky {risky_snapshot_count}; return columns {len(returns_df.columns)})."
            ]

        aligned = returns_df.reindex(columns=eligible).apply(pd.to_numeric, errors="coerce").dropna(how="any")
        if len(aligned) < 3:
            return [], [
                f"Efficient frontier unavailable: only {len(aligned)} overlapping observations after alignment."
            ]

        mean_returns = aligned.mean().to_numpy(dtype=float) * 252.0
        cov = aligned.cov().to_numpy(dtype=float) * 252.0
        if cov.size == 0 or not np.isfinite(cov).all() or not np.isfinite(mean_returns).all():
            return [], ["Efficient frontier unavailable: invalid expected-return or covariance inputs."]

        variances = np.diag(cov)
        if np.any(variances <= 0):
            return [], ["Efficient frontier unavailable: one or more eligible assets has non-positive variance."]

        current = weights.reindex(eligible).astype(float).clip(lower=0.0).to_numpy(dtype=float)
        current_sum = float(current.sum())
        if current_sum <= 0:
            return [], ["Efficient frontier unavailable: covered risky weights sum to zero."]
        current = current / current_sum

        rng = np.random.default_rng(42)
        n_assets = len(eligible)
        random_count = min(6000, max(1500, n_assets * 450))
        portfolios = [current, np.full(n_assets, 1.0 / n_assets)]
        inverse_vol = 1.0 / np.sqrt(variances)
        portfolios.append(inverse_vol / float(inverse_vol.sum()))
        portfolios.extend(rng.dirichlet(np.ones(n_assets), size=random_count))

        candidates: list[tuple[np.ndarray, float, float, float | None]] = []
        for raw_weights in portfolios:
            annual_return, annual_vol, sharpe = cls._frontier_stats(raw_weights, mean_returns, cov, risk_free_rate_annual)
            if annual_vol > 0 and np.isfinite(annual_return) and np.isfinite(annual_vol):
                candidates.append((np.asarray(raw_weights, dtype=float), annual_return, annual_vol, sharpe))

        if not candidates:
            return [], ["Efficient frontier unavailable: no valid candidate portfolios."]

        min_vol = min(candidates, key=lambda item: item[2])
        max_sharpe = max(candidates, key=lambda item: item[3] if item[3] is not None else -np.inf)
        equal_weight = candidates[1] if len(candidates) > 1 else candidates[0]
        risk_parity = candidates[2] if len(candidates) > 2 else candidates[0]

        frontier_candidates = sorted(candidates, key=lambda item: (item[2], -item[1]))
        frontier: list[tuple[np.ndarray, float, float, float | None]] = []
        best_return = -np.inf
        for candidate in frontier_candidates:
            if candidate[1] > best_return + 1e-8:
                frontier.append(candidate)
                best_return = candidate[1]

        if len(frontier) > 24:
            selected_indexes = np.linspace(0, len(frontier) - 1, 24).round().astype(int)
            frontier = [frontier[int(index)] for index in selected_indexes]

        points = [
            cls._frontier_point("Current", "current", current, mean_returns, cov, eligible, positions_by_id, risk_free_rate_annual),
            cls._tuple_to_frontier_point("Min Vol", "candidate", min_vol, eligible, positions_by_id),
            cls._tuple_to_frontier_point("Max Sharpe", "candidate", max_sharpe, eligible, positions_by_id),
            cls._tuple_to_frontier_point("Equal Weight", "candidate", equal_weight, eligible, positions_by_id),
            cls._tuple_to_frontier_point("Risk Parity", "candidate", risk_parity, eligible, positions_by_id),
        ]
        points.extend(
            cls._tuple_to_frontier_point(f"Frontier {index + 1}", "frontier", candidate, eligible, positions_by_id)
            for index, candidate in enumerate(frontier)
        )
        if risk_free_rate_annual is not None and np.isfinite(risk_free_rate_annual):
            points.append(
                RiskFrontierPoint(
                    label="Risk-free",
                    kind="risk_free",
                    annual_return=float(risk_free_rate_annual),
                    annual_vol=0.0,
                    sharpe=None,
                    weights=[],
                )
            )
        return points, []

    @classmethod
    def _frontier_point(
        cls,
        label: str,
        kind: str,
        weights: np.ndarray,
        mean_returns: np.ndarray,
        cov: np.ndarray,
        eligible: list[str],
        positions_by_id: dict[str, object],
        risk_free_rate_annual: float | None = None,
    ) -> RiskFrontierPoint:
        annual_return, annual_vol, sharpe = cls._frontier_stats(weights, mean_returns, cov, risk_free_rate_annual)
        return RiskFrontierPoint(
            label=label,
            kind=kind,
            annual_return=annual_return,
            annual_vol=annual_vol,
            sharpe=sharpe,
            weights=cls._frontier_weights(weights, eligible, positions_by_id),
        )

    def _risk_free_rate_for_frontier(
        self,
        *,
        request: RiskComputeRequest,
        returns_df: pd.DataFrame,
    ) -> tuple[float | None, list[str]]:
        if self.risk_free_service is None or returns_df.empty:
            return None, []
        if str(request.base_currency or "").upper() != "USD":
            return None, []
        start = returns_df.index.min()
        end = returns_df.index.max()
        rf_series, warnings = self.risk_free_service.get_usd_daily_returns(start, end)
        if rf_series is None or rf_series.empty:
            return None, warnings
        annual_rate = float((1.0 + rf_series.astype(float).mean()) ** 252.0 - 1.0)
        if not np.isfinite(annual_rate):
            return None, warnings
        return annual_rate, warnings

    @classmethod
    def _correlation_matrix(cls, returns_df: pd.DataFrame, snapshot: PortfolioSnapshot) -> pd.DataFrame:
        if returns_df.empty:
            return pd.DataFrame()
        positions_by_id = {position.resolved_instrument_id(): position for position in snapshot.positions}
        eligible: list[str] = []
        for instrument_id in returns_df.columns:
            position = positions_by_id.get(str(instrument_id))
            if cls._is_cash(position):
                continue
            series = pd.to_numeric(returns_df[instrument_id], errors="coerce").dropna()
            if len(series) >= 3 and float(series.std() or 0.0) > 1e-10:
                eligible.append(str(instrument_id))
        if not eligible:
            return pd.DataFrame()
        return returns_df.reindex(columns=eligible).apply(pd.to_numeric, errors="coerce").corr(min_periods=3)

    @classmethod
    def _tuple_to_frontier_point(
        cls,
        label: str,
        kind: str,
        candidate: tuple[np.ndarray, float, float, float | None],
        eligible: list[str],
        positions_by_id: dict[str, object],
    ) -> RiskFrontierPoint:
        weights, annual_return, annual_vol, sharpe = candidate
        return RiskFrontierPoint(
            label=label,
            kind=kind,
            annual_return=float(annual_return),
            annual_vol=float(annual_vol),
            sharpe=None if sharpe is None else float(sharpe),
            weights=cls._frontier_weights(weights, eligible, positions_by_id),
        )

    @staticmethod
    def _frontier_stats(
        weights: np.ndarray,
        mean_returns: np.ndarray,
        cov: np.ndarray,
        risk_free_rate_annual: float | None = None,
    ) -> tuple[float, float, float | None]:
        annual_return = float(weights @ mean_returns)
        variance = float(weights.T @ cov @ weights)
        if variance < 0 and abs(variance) < 1e-12:
            variance = 0.0
        annual_vol = float(np.sqrt(variance)) if variance > 0 else 0.0
        excess_return = annual_return - float(risk_free_rate_annual or 0.0)
        sharpe = excess_return / annual_vol if annual_vol > 0 else None
        return annual_return, annual_vol, sharpe

    @staticmethod
    def _frontier_weights(
        weights: np.ndarray,
        eligible: list[str],
        positions_by_id: dict[str, object],
    ) -> list[RiskFrontierWeight]:
        rows: list[RiskFrontierWeight] = []
        for instrument_id, weight in zip(eligible, weights):
            position = positions_by_id.get(instrument_id)
            rows.append(
                RiskFrontierWeight(
                    symbol=getattr(position, "symbol", instrument_id),
                    instrument_id=instrument_id,
                    display_symbol=getattr(position, "display_symbol", None),
                    weight=float(weight),
                )
            )
        return sorted(rows, key=lambda row: abs(row.weight), reverse=True)

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
        data_provider: AppDataProvider | None = None,
    ) -> Tuple[Dict[str, pd.Series], List[str]]:
        if data_provider is not None:
            return data_provider.load_prices(snapshot, lookback_days, progress_cb)
        prices: Dict[str, pd.Series] = {}
        missing: List[str] = []
        positions = [position for position in snapshot.positions if not position.symbol.startswith("CASH")]
        total = len(positions)
        for index, position in enumerate(positions, start=1):
            identity = identity_for_position(position)
            symbol = identity.symbol
            if self.client.mock:
                series = self.mock_service.load_history(symbol)
            else:
                contract = contract_for_position(position)
                series = self.market_data.fetch_history(contract, lookback_days)
            if series is None or series.empty:
                missing.append(identity.display_symbol)
            else:
                prices[identity.instrument_id] = series.astype(float)
            if progress_cb is not None:
                progress_cb(index, total, identity.display_symbol)
        return prices, missing

    @staticmethod
    def _ensure_cash_returns(snapshot: PortfolioSnapshot, returns_df: pd.DataFrame) -> pd.DataFrame:
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
    def _weights_for_symbols(snapshot: PortfolioSnapshot, symbols: List[str]) -> pd.Series:
        values = {
            position.resolved_instrument_id(): position.base_market_value
            for position in snapshot.positions
            if position.resolved_instrument_id() in symbols and position.base_market_value is not None
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
        result.returns = benchmark_returns
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
        benchmark_instrument = InstrumentReference(symbol=symbol).with_defaults(self.benchmark_defaults)
        if self.client.mock:
            series = self.mock_service.load_history(symbol)
        else:
            contract = contract_for_instrument(benchmark_instrument)
            series = self.market_data.fetch_history(contract, lookback_days)
        if series is None or series.empty:
            warnings.append(f"Benchmark history unavailable for {symbol}")
            return None, warnings
        converted, fx_warnings = self._convert_benchmark_to_base(
            series.astype(float),
            benchmark_instrument.currency,
            base_currency,
            lookback_days,
            label=symbol,
            context="Benchmark",
        )
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
        *,
        label: str = "series",
        context: str = "Series",
    ) -> tuple[pd.Series | None, List[str]]:
        result = convert_history_to_base_currency(
            series,
            quote_ccy,
            base_ccy,
            lookback_days,
            self.market_data,
            label=label,
            context=context,
        )
        return result.series, result.warnings

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

    @staticmethod
    def _is_cash(position) -> bool:
        if position is None:
            return False
        return position.sec_type == "CASH" or position.symbol.startswith("CASH")

    @classmethod
    def _has_unknown_risky_values(cls, snapshot: PortfolioSnapshot) -> bool:
        return any(position.base_market_value is None and not cls._is_cash(position) for position in snapshot.positions)
