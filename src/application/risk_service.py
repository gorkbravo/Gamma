from __future__ import annotations

import re
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
    dependency_network: "RiskDependencyNetwork"


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
    history_rows: int | None = None
    history_start: str | None = None
    history_end: str | None = None
    source_provider: str | None = None


@dataclass(frozen=True)
class CachedEquityHistory:
    symbol: str
    series: pd.Series
    lookback_days: int
    rows: int
    start: str
    end: str
    source_provider: str = "market_data_cache"


@dataclass(frozen=True)
class RiskDependencyNetworkNode:
    symbol: str
    label: str
    cluster_id: int
    is_portfolio: bool
    portfolio_weight: float | None
    risk_contribution: float | None
    annual_vol: float | None
    degree: int
    strength: float
    centrality: float
    source_provider: str | None = None


@dataclass(frozen=True)
class RiskDependencyNetworkEdge:
    source: str
    target: str
    partial_correlation: float
    strength: float
    sign: int


@dataclass(frozen=True)
class RiskDependencyNetworkCluster:
    cluster_id: int
    label: str
    node_count: int
    portfolio_node_count: int
    portfolio_weight: float
    average_annual_vol: float | None
    density: float
    top_symbols: list[str]
    central_symbols: list[str]


@dataclass(frozen=True)
class RiskDependencyNetwork:
    nodes: list[RiskDependencyNetworkNode]
    edges: list[RiskDependencyNetworkEdge]
    clusters: list[RiskDependencyNetworkCluster]
    methodology: str | None = None
    universe_size: int = 0
    observation_count: int = 0
    edge_threshold: float | None = None
    warnings: list[str] | None = None
    source_provider: str = "gamma.risk.dependency_network"


class RiskService:
    _MC_RANDOM_SEED = 42
    _DEFAULT_FRONTIER_UNIVERSE = ("SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "HYG")
    _CACHE_STK_HISTORY_RE = re.compile(
        r"^(?P<symbol>.+)_stk_(?P<currency>[a-z]{3})(?:_(?P<exchange>[a-z0-9]+))?_lookback_(?P<lookback>\d+)(?:--[0-9a-f]{64})?\.csv$",
        re.IGNORECASE,
    )
    _MAX_CACHED_EQUITY_FRONTIER_SYMBOLS = 160
    _MAX_DEPENDENCY_NETWORK_NODES = 120
    _DEPENDENCY_NETWORK_EDGE_TARGET = 260
    _DEPENDENCY_NETWORK_MIN_OBS = 60
    _DEPENDENCY_NETWORK_MIN_ABS_PARTIAL = 0.05

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

        frontier_universe_returns, frontier_universe_warnings = self._load_frontier_universe_returns(
            request=request,
            data_provider=data_provider,
        )
        warnings.extend(frontier_universe_warnings)
        cached_equity_returns, cached_equity_metadata, cached_equity_warnings = self._load_cached_equity_reference_returns(
            request=request,
        )
        warnings.extend(cached_equity_warnings)
        (
            frontier_risk_returns_df,
            frontier_universe_returns,
            cached_equity_returns,
            frontier_window_warnings,
        ) = self._align_frontier_return_windows(
            portfolio_returns_df=risk_returns_df,
            reference_returns_df=frontier_universe_returns,
            cached_equity_returns_df=cached_equity_returns,
        )
        warnings.extend(frontier_window_warnings)
        risk_free_rate_annual, risk_free_warnings = self._risk_free_rate_for_frontier(
            request=request,
            returns_df=frontier_risk_returns_df,
        )
        warnings.extend(risk_free_warnings)

        frontier_points, frontier_warnings = self._build_efficient_frontier(
            snapshot=snapshot,
            returns_df=frontier_risk_returns_df,
            weights=weights_aligned,
            risk_free_rate_annual=risk_free_rate_annual,
            reference_returns_df=frontier_universe_returns,
            cached_equity_returns_df=cached_equity_returns,
            cached_equity_metadata=cached_equity_metadata,
        )
        warnings.extend(frontier_warnings)
        dependency_network = self._build_dependency_network(
            snapshot=snapshot,
            portfolio_returns_df=frontier_risk_returns_df,
            weights=weights_aligned,
            contributions=contributions,
            reference_returns_df=frontier_universe_returns,
            cached_equity_returns_df=cached_equity_returns,
            cached_equity_metadata=cached_equity_metadata,
        )
        if dependency_network.warnings:
            warnings.extend(dependency_network.warnings)
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
            dependency_network=dependency_network,
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
    def _build_dependency_network(
        cls,
        *,
        snapshot: PortfolioSnapshot,
        portfolio_returns_df: pd.DataFrame,
        weights: pd.Series,
        contributions: pd.Series,
        reference_returns_df: pd.DataFrame | None = None,
        cached_equity_returns_df: pd.DataFrame | None = None,
        cached_equity_metadata: dict[str, CachedEquityHistory] | None = None,
    ) -> RiskDependencyNetwork:
        warnings: list[str] = []
        portfolio_map = cls._portfolio_symbol_map(snapshot)
        portfolio_symbols = set(portfolio_map)
        portfolio_frame = cls._display_symbol_returns(portfolio_returns_df, portfolio_map)
        reference_frame = cls._plain_symbol_returns(reference_returns_df)
        cached_frame = cls._plain_symbol_returns(cached_equity_returns_df)

        combined = cls._combine_dependency_return_frames(
            portfolio_frame=portfolio_frame,
            reference_frame=reference_frame,
            cached_frame=cached_frame,
            portfolio_symbols=portfolio_symbols,
        )
        if combined.empty or len(combined.columns) < 3:
            return RiskDependencyNetwork(
                nodes=[],
                edges=[],
                clusters=[],
                methodology="Unavailable",
                warnings=["Dependency network unavailable: fewer than three usable return series."],
            )

        selected_columns = cls._select_dependency_universe(combined, portfolio_symbols)
        selected = combined.reindex(columns=selected_columns).apply(pd.to_numeric, errors="coerce")
        min_obs = max(20, min(cls._DEPENDENCY_NETWORK_MIN_OBS, max(20, int(len(selected) * 0.35))))
        selected = selected.dropna(axis=1, thresh=min_obs).dropna(how="all")
        selected = selected.loc[:, selected.std(skipna=True) > 1e-10]
        if selected.empty or len(selected.columns) < 3:
            return RiskDependencyNetwork(
                nodes=[],
                edges=[],
                clusters=[],
                methodology="Unavailable",
                warnings=["Dependency network unavailable: insufficient overlapping non-flat return histories."],
            )
        if len(selected.columns) > cls._MAX_DEPENDENCY_NETWORK_NODES:
            selected = selected.reindex(columns=cls._select_dependency_universe(selected, portfolio_symbols))

        imputed = selected.copy()
        imputed = imputed.fillna(imputed.mean()).dropna(how="any")
        if len(imputed) < 20:
            return RiskDependencyNetwork(
                nodes=[],
                edges=[],
                clusters=[],
                methodology="Unavailable",
                warnings=[f"Dependency network unavailable: only {len(imputed)} overlapping observations."],
            )

        partial_corr, methodology, pcorr_warnings = cls._estimate_dependency_partial_correlations(imputed)
        warnings.extend(pcorr_warnings)
        if partial_corr is None or partial_corr.empty:
            return RiskDependencyNetwork(
                nodes=[],
                edges=[],
                clusters=[],
                methodology=methodology,
                warnings=[*warnings, "Dependency network unavailable: partial-correlation estimation failed."],
            )

        edges, edge_threshold = cls._dependency_edges(partial_corr)
        if not edges:
            return RiskDependencyNetwork(
                nodes=[],
                edges=[],
                clusters=[],
                methodology=methodology,
                universe_size=int(len(partial_corr.columns)),
                observation_count=int(len(imputed)),
                edge_threshold=edge_threshold,
                warnings=[*warnings, "Dependency network unavailable: no sparse links survived the threshold."],
            )

        communities = cls._dependency_communities(list(partial_corr.columns), edges)
        degree, strength = cls._dependency_node_scores(list(partial_corr.columns), edges)
        max_strength = max(strength.values()) if strength else 0.0
        annual_vol = selected.reindex(columns=partial_corr.columns).std(skipna=True) * np.sqrt(252.0)
        weight_by_symbol = cls._display_symbol_series(weights, portfolio_map)
        contribution_by_symbol = cls._display_symbol_series(contributions, portfolio_map)

        nodes: list[RiskDependencyNetworkNode] = []
        for symbol in partial_corr.columns:
            portfolio_row = portfolio_map.get(str(symbol))
            metadata = (cached_equity_metadata or {}).get(str(symbol))
            node_strength = float(strength.get(str(symbol), 0.0))
            nodes.append(
                RiskDependencyNetworkNode(
                    symbol=str(symbol),
                    label=str(symbol),
                    cluster_id=int(communities.get(str(symbol), -1)),
                    is_portfolio=str(symbol) in portfolio_symbols,
                    portfolio_weight=cls._series_value(weight_by_symbol, str(symbol)),
                    risk_contribution=cls._series_value(contribution_by_symbol, str(symbol)),
                    annual_vol=cls._series_value(annual_vol, str(symbol)),
                    degree=int(degree.get(str(symbol), 0)),
                    strength=node_strength,
                    centrality=float(node_strength / max_strength) if max_strength > 0 else 0.0,
                    source_provider=(
                        "portfolio_scope"
                        if portfolio_row is not None
                        else metadata.source_provider if metadata is not None else "reference_universe"
                    ),
                )
            )

        clusters = cls._dependency_cluster_summaries(nodes, edges)
        if len(partial_corr.columns) >= cls._MAX_DEPENDENCY_NETWORK_NODES:
            warnings.append(
                "Dependency network capped at "
                f"{cls._MAX_DEPENDENCY_NETWORK_NODES} nodes, prioritizing portfolio names and deepest reference histories."
            )
        return RiskDependencyNetwork(
            nodes=nodes,
            edges=edges,
            clusters=clusters,
            methodology=methodology,
            universe_size=int(len(nodes)),
            observation_count=int(len(imputed)),
            edge_threshold=float(edge_threshold),
            warnings=warnings,
        )

    @staticmethod
    def _portfolio_symbol_map(snapshot: PortfolioSnapshot) -> dict[str, object]:
        rows: dict[str, object] = {}
        for position in snapshot.positions:
            if RiskService._is_cash(position):
                continue
            symbol = str(position.resolved_display_symbol() or position.resolved_symbol()).strip().upper()
            if symbol:
                rows[symbol] = position
        return rows

    @classmethod
    def _display_symbol_returns(cls, returns_df: pd.DataFrame, portfolio_map: dict[str, object]) -> pd.DataFrame:
        if returns_df is None or returns_df.empty:
            return pd.DataFrame()
        by_instrument = {
            str(getattr(position, "resolved_instrument_id")()): symbol
            for symbol, position in portfolio_map.items()
            if callable(getattr(position, "resolved_instrument_id", None))
        }
        columns: dict[str, pd.Series] = {}
        for column in returns_df.columns:
            label = by_instrument.get(str(column), str(column).strip().upper())
            if not label or label.startswith("CASH"):
                continue
            series = pd.to_numeric(returns_df[column], errors="coerce")
            columns[label] = series if label not in columns else columns[label].combine_first(series)
        return pd.DataFrame(columns)

    @staticmethod
    def _plain_symbol_returns(returns_df: pd.DataFrame | None) -> pd.DataFrame:
        if returns_df is None or returns_df.empty:
            return pd.DataFrame()
        columns: dict[str, pd.Series] = {}
        for column in returns_df.columns:
            symbol = str(column).strip().upper()
            if not symbol or symbol.startswith("CASH"):
                continue
            columns[symbol] = pd.to_numeric(returns_df[column], errors="coerce")
        return pd.DataFrame(columns)

    @classmethod
    def _combine_dependency_return_frames(
        cls,
        *,
        portfolio_frame: pd.DataFrame,
        reference_frame: pd.DataFrame,
        cached_frame: pd.DataFrame,
        portfolio_symbols: set[str],
    ) -> pd.DataFrame:
        ordered_frames = [cached_frame, reference_frame, portfolio_frame]
        columns: dict[str, pd.Series] = {}
        for frame in ordered_frames:
            if frame is None or frame.empty:
                continue
            for column in frame.columns:
                symbol = str(column).strip().upper()
                series = pd.to_numeric(frame[column], errors="coerce")
                if symbol in columns:
                    columns[symbol] = columns[symbol].combine_first(series)
                else:
                    columns[symbol] = series
        for symbol in portfolio_symbols:
            if symbol in portfolio_frame.columns:
                columns[symbol] = pd.to_numeric(portfolio_frame[symbol], errors="coerce")
        if not columns:
            return pd.DataFrame()
        combined = pd.DataFrame(columns).sort_index()
        return combined.loc[:, ~combined.columns.duplicated()]

    @classmethod
    def _select_dependency_universe(cls, returns_df: pd.DataFrame, portfolio_symbols: set[str]) -> list[str]:
        stats = []
        for column in returns_df.columns:
            series = pd.to_numeric(returns_df[column], errors="coerce").dropna()
            if len(series) < 20 or float(series.std() or 0.0) <= 1e-10:
                continue
            symbol = str(column)
            stats.append((symbol in portfolio_symbols, len(series), float(series.std() or 0.0), symbol))
        stats.sort(key=lambda row: (row[0], row[1], row[2], row[3]), reverse=True)
        selected = [row[3] for row in stats[: cls._MAX_DEPENDENCY_NETWORK_NODES]]
        for symbol in sorted(portfolio_symbols):
            if symbol in returns_df.columns and symbol not in selected:
                selected.insert(0, symbol)
        return selected[: cls._MAX_DEPENDENCY_NETWORK_NODES]

    @classmethod
    def _estimate_dependency_partial_correlations(
        cls,
        returns_df: pd.DataFrame,
    ) -> tuple[pd.DataFrame | None, str, list[str]]:
        clean = returns_df.apply(pd.to_numeric, errors="coerce")
        clean = clean.loc[:, clean.std(skipna=True) > 1e-10]
        if clean.empty or len(clean.columns) < 3:
            return None, "Unavailable", []
        standardized = (clean - clean.mean()) / clean.std(ddof=1)
        standardized = standardized.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        emp_cov = np.cov(standardized.to_numpy(dtype=float), rowvar=False, ddof=1)
        emp_cov = np.atleast_2d(np.asarray(emp_cov, dtype=float))
        if emp_cov.shape[0] != len(clean.columns) or not np.isfinite(emp_cov).all():
            return None, "Unavailable", ["Dependency network covariance was invalid."]

        warnings: list[str] = []
        precision = None
        methodology = "Shrinkage inverse covariance partial correlations"
        try:
            from sklearn.covariance import graphical_lasso

            alpha = cls._dependency_glasso_alpha(emp_cov)
            _, precision = graphical_lasso(emp_cov, alpha=alpha, max_iter=300, tol=1e-4)
            methodology = f"Graphical LASSO partial correlations (alpha={alpha:.4f})"
        except Exception as exc:
            warnings.append(
                "Dependency network used shrinkage inverse covariance fallback; "
                f"Graphical LASSO unavailable or failed ({type(exc).__name__})."
            )
            shrink = 0.15
            target = np.diag(np.diag(emp_cov))
            shrunk = (1.0 - shrink) * emp_cov + shrink * target
            ridge = np.eye(shrunk.shape[0]) * 1e-4
            try:
                precision = np.linalg.pinv(shrunk + ridge)
            except Exception:
                return None, methodology, warnings

        if precision is None or not np.isfinite(precision).all():
            return None, methodology, warnings
        diag = np.diag(precision)
        if np.any(diag <= 0):
            precision = precision + np.eye(precision.shape[0]) * (abs(float(diag.min())) + 1e-6)
            diag = np.diag(precision)
        denom = np.sqrt(np.outer(diag, diag))
        partial = -precision / denom
        partial = np.clip(partial, -0.999, 0.999)
        np.fill_diagonal(partial, 1.0)
        return pd.DataFrame(partial, index=clean.columns, columns=clean.columns), methodology, warnings

    @staticmethod
    def _dependency_glasso_alpha(emp_cov: np.ndarray) -> float:
        mask = ~np.eye(emp_cov.shape[0], dtype=bool)
        offdiag_abs = np.abs(emp_cov[mask])
        alpha_max = float(np.percentile(offdiag_abs, 90)) if offdiag_abs.size else 0.05
        return max(alpha_max * 0.18, 0.015)

    @classmethod
    def _dependency_edges(cls, partial_corr: pd.DataFrame) -> tuple[list[RiskDependencyNetworkEdge], float]:
        candidates: list[RiskDependencyNetworkEdge] = []
        columns = list(partial_corr.columns)
        values = partial_corr.to_numpy(dtype=float)
        for i, source in enumerate(columns):
            for j in range(i + 1, len(columns)):
                value = float(values[i, j])
                if not np.isfinite(value):
                    continue
                strength = abs(value)
                if strength < cls._DEPENDENCY_NETWORK_MIN_ABS_PARTIAL:
                    continue
                candidates.append(
                    RiskDependencyNetworkEdge(
                        source=str(source),
                        target=str(columns[j]),
                        partial_correlation=value,
                        strength=strength,
                        sign=1 if value >= 0 else -1,
                    )
                )
        candidates.sort(key=lambda edge: (edge.strength, edge.source, edge.target), reverse=True)
        selected = candidates[: cls._DEPENDENCY_NETWORK_EDGE_TARGET]
        threshold = selected[-1].strength if selected else cls._DEPENDENCY_NETWORK_MIN_ABS_PARTIAL
        return selected, float(threshold)

    @staticmethod
    def _dependency_node_scores(
        symbols: list[str],
        edges: list[RiskDependencyNetworkEdge],
    ) -> tuple[dict[str, int], dict[str, float]]:
        degree = {symbol: 0 for symbol in symbols}
        strength = {symbol: 0.0 for symbol in symbols}
        for edge in edges:
            degree[edge.source] = degree.get(edge.source, 0) + 1
            degree[edge.target] = degree.get(edge.target, 0) + 1
            strength[edge.source] = strength.get(edge.source, 0.0) + edge.strength
            strength[edge.target] = strength.get(edge.target, 0.0) + edge.strength
        return degree, strength

    @classmethod
    def _dependency_communities(
        cls,
        symbols: list[str],
        edges: list[RiskDependencyNetworkEdge],
    ) -> dict[str, int]:
        try:
            import networkx as nx

            graph = nx.Graph()
            graph.add_nodes_from(symbols)
            graph.add_weighted_edges_from((edge.source, edge.target, edge.strength) for edge in edges)
            if hasattr(nx.algorithms.community, "louvain_communities"):
                communities = nx.algorithms.community.louvain_communities(graph, weight="weight", seed=42)
            else:
                communities = nx.algorithms.community.greedy_modularity_communities(graph, weight="weight")
            return {
                symbol: cluster_id
                for cluster_id, community in enumerate(sorted([sorted(item) for item in communities], key=lambda row: (-len(row), row)))
                for symbol in community
            }
        except Exception:
            return cls._label_propagation_communities(symbols, edges)

    @staticmethod
    def _label_propagation_communities(
        symbols: list[str],
        edges: list[RiskDependencyNetworkEdge],
    ) -> dict[str, int]:
        neighbors: dict[str, list[tuple[str, float]]] = {symbol: [] for symbol in symbols}
        for edge in edges:
            neighbors.setdefault(edge.source, []).append((edge.target, edge.strength))
            neighbors.setdefault(edge.target, []).append((edge.source, edge.strength))
        labels = {symbol: symbol for symbol in symbols}
        for _ in range(24):
            changed = False
            for symbol in sorted(symbols):
                scores: dict[str, float] = {}
                for neighbor, weight in neighbors.get(symbol, []):
                    scores[labels.get(neighbor, neighbor)] = scores.get(labels.get(neighbor, neighbor), 0.0) + weight
                if not scores:
                    continue
                best = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0][0]
                if labels[symbol] != best:
                    labels[symbol] = best
                    changed = True
            if not changed:
                break
        groups: dict[str, list[str]] = {}
        for symbol, label in labels.items():
            groups.setdefault(label, []).append(symbol)
        ordered_labels = sorted(groups, key=lambda label: (-len(groups[label]), sorted(groups[label])[0]))
        label_ids = {label: index for index, label in enumerate(ordered_labels)}
        return {symbol: label_ids[label] for symbol, label in labels.items()}

    @classmethod
    def _dependency_cluster_summaries(
        cls,
        nodes: list[RiskDependencyNetworkNode],
        edges: list[RiskDependencyNetworkEdge],
    ) -> list[RiskDependencyNetworkCluster]:
        nodes_by_cluster: dict[int, list[RiskDependencyNetworkNode]] = {}
        for node in nodes:
            nodes_by_cluster.setdefault(node.cluster_id, []).append(node)
        edge_counts: dict[int, int] = {cluster_id: 0 for cluster_id in nodes_by_cluster}
        for edge in edges:
            source = next((node for node in nodes if node.symbol == edge.source), None)
            target = next((node for node in nodes if node.symbol == edge.target), None)
            if source is not None and target is not None and source.cluster_id == target.cluster_id:
                edge_counts[source.cluster_id] = edge_counts.get(source.cluster_id, 0) + 1
        clusters: list[RiskDependencyNetworkCluster] = []
        for cluster_id, cluster_nodes in nodes_by_cluster.items():
            ranked = sorted(cluster_nodes, key=lambda node: (node.is_portfolio, node.strength, node.symbol), reverse=True)
            vols = [node.annual_vol for node in cluster_nodes if node.annual_vol is not None and np.isfinite(node.annual_vol)]
            portfolio_weight = sum(abs(float(node.portfolio_weight or 0.0)) for node in cluster_nodes)
            n = len(cluster_nodes)
            max_edges = n * (n - 1) / 2
            clusters.append(
                RiskDependencyNetworkCluster(
                    cluster_id=int(cluster_id),
                    label=f"Cluster {cluster_id + 1}",
                    node_count=n,
                    portfolio_node_count=sum(1 for node in cluster_nodes if node.is_portfolio),
                    portfolio_weight=float(portfolio_weight),
                    average_annual_vol=float(np.mean(vols)) if vols else None,
                    density=float(edge_counts.get(cluster_id, 0) / max_edges) if max_edges > 0 else 0.0,
                    top_symbols=[node.symbol for node in ranked[:8]],
                    central_symbols=[node.symbol for node in sorted(cluster_nodes, key=lambda node: node.strength, reverse=True)[:5]],
                )
            )
        return sorted(clusters, key=lambda row: (row.portfolio_weight, row.node_count), reverse=True)

    @staticmethod
    def _display_symbol_series(series: pd.Series, portfolio_map: dict[str, object]) -> pd.Series:
        if series is None or series.empty:
            return pd.Series(dtype=float)
        by_instrument = {
            str(getattr(position, "resolved_instrument_id")()): symbol
            for symbol, position in portfolio_map.items()
            if callable(getattr(position, "resolved_instrument_id", None))
        }
        values: dict[str, float] = {}
        for key, value in series.items():
            symbol = by_instrument.get(str(key), str(key).strip().upper())
            try:
                numeric = float(value)
            except Exception:
                continue
            if np.isfinite(numeric):
                values[symbol] = values.get(symbol, 0.0) + numeric
        return pd.Series(values, dtype=float)

    @staticmethod
    def _series_value(series: pd.Series, key: str) -> float | None:
        if series is None or series.empty or key not in series.index:
            return None
        try:
            value = float(series.loc[key])
        except Exception:
            return None
        return value if np.isfinite(value) else None

    @classmethod
    def _build_efficient_frontier(
        cls,
        *,
        snapshot: PortfolioSnapshot,
        returns_df: pd.DataFrame,
        weights: pd.Series,
        risk_free_rate_annual: float | None = None,
        reference_returns_df: pd.DataFrame | None = None,
        cached_equity_returns_df: pd.DataFrame | None = None,
        cached_equity_metadata: dict[str, CachedEquityHistory] | None = None,
    ) -> tuple[list[RiskFrontierPoint], list[str]]:
        warnings: list[str] = []
        def unavailable(message: str) -> tuple[list[RiskFrontierPoint], list[str]]:
            reference_points, reference_warnings = cls._reference_frontier_points_with_cml(
                reference_returns_df=reference_returns_df,
                risk_free_rate_annual=risk_free_rate_annual,
                include_risk_free_marker=False,
            )
            cached_points, cached_warnings, _cached_tangency = cls._build_reference_frontier_points(
                returns_df=cached_equity_returns_df if cached_equity_returns_df is not None else pd.DataFrame(),
                risk_free_rate_annual=risk_free_rate_annual,
                asset_kind="cached_equity_asset",
                frontier_kind="cached_equity_frontier",
                candidate_kind="cached_equity_candidate",
                frontier_label_prefix="Cached Equity Frontier",
                tangency_label="Cached Equity Max Sharpe",
                unavailable_label="Cached equity reference frontier",
                history_metadata=cached_equity_metadata or {},
            )
            return [*reference_points, *cached_points], [message, *reference_warnings, *cached_warnings]

        if returns_df.empty or weights.empty:
            return unavailable("Efficient frontier unavailable: no covered return history and weights.")

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
            return unavailable(
                "Efficient frontier unavailable: need at least two eligible non-cash long positions with usable return variance "
                f"(eligible {len(eligible)}; positive covered risky {positive_covered_risky_count}; "
                f"snapshot risky {risky_snapshot_count}; return columns {len(returns_df.columns)})."
            )

        aligned = returns_df.reindex(columns=eligible).apply(pd.to_numeric, errors="coerce").dropna(how="any")
        if len(aligned) < 3:
            return unavailable(
                f"Efficient frontier unavailable: only {len(aligned)} overlapping observations after alignment."
            )

        mean_returns = aligned.mean().to_numpy(dtype=float) * 252.0
        cov = aligned.cov().to_numpy(dtype=float) * 252.0
        if cov.size == 0 or not np.isfinite(cov).all() or not np.isfinite(mean_returns).all():
            return unavailable("Efficient frontier unavailable: invalid expected-return or covariance inputs.")

        variances = np.diag(cov)
        if np.any(variances <= 0):
            return unavailable("Efficient frontier unavailable: one or more eligible assets has non-positive variance.")

        current = weights.reindex(eligible).astype(float).clip(lower=0.0).to_numpy(dtype=float)
        current_sum = float(current.sum())
        if current_sum <= 0:
            return unavailable("Efficient frontier unavailable: covered risky weights sum to zero.")
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
            return unavailable("Efficient frontier unavailable: no valid candidate portfolios.")

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
            cls._single_asset_frontier_point(
                index=index,
                instrument_id=instrument_id,
                mean_returns=mean_returns,
                cov=cov,
                positions_by_id=positions_by_id,
                risk_free_rate_annual=risk_free_rate_annual,
            )
            for index, instrument_id in enumerate(eligible)
        )
        points.extend(
            cls._tuple_to_frontier_point(f"Frontier {index + 1}", "frontier", candidate, eligible, positions_by_id)
            for index, candidate in enumerate(frontier)
        )
        if risk_free_rate_annual is not None and np.isfinite(risk_free_rate_annual):
            points.extend(
                [
                    RiskFrontierPoint(
                        label="Portfolio CML Risk-free",
                        kind="portfolio_cml",
                        annual_return=float(risk_free_rate_annual),
                        annual_vol=0.0,
                        sharpe=None,
                        weights=[],
                    ),
                    cls._tuple_to_frontier_point(
                        "Portfolio CML Tangency",
                        "portfolio_cml",
                        max_sharpe,
                        eligible,
                        positions_by_id,
                    ),
                ]
            )
        reference_points, reference_warnings = cls._reference_frontier_points_with_cml(
            reference_returns_df=reference_returns_df,
            risk_free_rate_annual=risk_free_rate_annual,
            include_risk_free_marker=True,
        )
        points.extend(reference_points)
        warnings.extend(reference_warnings)
        cached_points, cached_warnings, _cached_tangency = cls._build_reference_frontier_points(
            returns_df=cached_equity_returns_df if cached_equity_returns_df is not None else pd.DataFrame(),
            risk_free_rate_annual=risk_free_rate_annual,
            asset_kind="cached_equity_asset",
            frontier_kind="cached_equity_frontier",
            candidate_kind="cached_equity_candidate",
            frontier_label_prefix="Cached Equity Frontier",
            tangency_label="Cached Equity Max Sharpe",
            unavailable_label="Cached equity reference frontier",
            history_metadata=cached_equity_metadata or {},
        )
        points.extend(cached_points)
        warnings.extend(cached_warnings)
        return points, warnings

    @classmethod
    def _align_frontier_return_windows(
        cls,
        *,
        portfolio_returns_df: pd.DataFrame,
        reference_returns_df: pd.DataFrame | None = None,
        cached_equity_returns_df: pd.DataFrame | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None, list[str]]:
        warnings: list[str] = []
        if portfolio_returns_df.empty:
            return portfolio_returns_df, reference_returns_df, cached_equity_returns_df, warnings

        frames = [
            ("portfolio", portfolio_returns_df),
            ("reference universe", reference_returns_df),
            ("cached equity reference", cached_equity_returns_df),
        ]
        usable = [(label, frame) for label, frame in frames if frame is not None and not frame.empty]
        if len(usable) <= 1:
            return portfolio_returns_df, reference_returns_df, cached_equity_returns_df, warnings

        starts = [frame.index.min() for _, frame in usable]
        ends = [frame.index.max() for _, frame in usable]
        common_start = max(starts)
        common_end = min(ends)
        if common_start > common_end:
            warnings.append(
                "Efficient frontier reference series excluded: no overlapping return window with the portfolio."
            )
            return portfolio_returns_df, None, None, warnings

        def trim(frame: pd.DataFrame | None) -> pd.DataFrame | None:
            if frame is None or frame.empty:
                return frame
            trimmed = frame.loc[(frame.index >= common_start) & (frame.index <= common_end)]
            return trimmed.dropna(how="all")

        portfolio_aligned = trim(portfolio_returns_df)
        if portfolio_aligned is None or len(portfolio_aligned) < 3:
            warnings.append(
                "Efficient frontier references excluded: common return window leaves fewer than three portfolio observations."
            )
            return portfolio_returns_df, None, None, warnings

        reference_aligned = trim(reference_returns_df)
        cached_aligned = trim(cached_equity_returns_df)
        if reference_returns_df is not None and (reference_aligned is None or len(reference_aligned) < 3):
            warnings.append(
                "Reference frontier unavailable: common return window leaves fewer than three observations."
            )
            reference_aligned = None
        if cached_equity_returns_df is not None and (cached_aligned is None or len(cached_aligned) < 3):
            warnings.append(
                "Cached equity reference frontier unavailable: common return window leaves fewer than three observations."
            )
            cached_aligned = None
        if reference_aligned is not None or cached_aligned is not None:
            warnings.append(
                "Efficient frontier inputs aligned to common return window "
                f"{common_start.date()} through {common_end.date()}."
            )
        return portfolio_aligned, reference_aligned, cached_aligned, warnings

    @classmethod
    def _reference_frontier_points_with_cml(
        cls,
        *,
        reference_returns_df: pd.DataFrame | None,
        risk_free_rate_annual: float | None = None,
        include_risk_free_marker: bool = True,
    ) -> tuple[list[RiskFrontierPoint], list[str]]:
        points: list[RiskFrontierPoint] = []
        warnings: list[str] = []
        has_risk_free = risk_free_rate_annual is not None and np.isfinite(risk_free_rate_annual)
        if include_risk_free_marker and has_risk_free:
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
        if reference_returns_df is None or reference_returns_df.empty:
            return points, warnings
        reference_points, reference_warnings, reference_tangency = cls._build_reference_frontier_points(
            returns_df=reference_returns_df,
            risk_free_rate_annual=risk_free_rate_annual,
        )
        points.extend(reference_points)
        warnings.extend(reference_warnings)
        if reference_tangency is not None and has_risk_free:
            points.extend(
                [
                    RiskFrontierPoint(
                        label="CML Risk-free",
                        kind="cml",
                        annual_return=float(risk_free_rate_annual),
                        annual_vol=0.0,
                        sharpe=None,
                        weights=[],
                    ),
                    RiskFrontierPoint(
                        label="CML Tangency",
                        kind="cml",
                        annual_return=reference_tangency.annual_return,
                        annual_vol=reference_tangency.annual_vol,
                        sharpe=reference_tangency.sharpe,
                        weights=reference_tangency.weights,
                    ),
                ]
            )
        return points, warnings

    @classmethod
    def _build_reference_frontier_points(
        cls,
        *,
        returns_df: pd.DataFrame,
        risk_free_rate_annual: float | None = None,
        asset_kind: str = "universe_asset",
        frontier_kind: str = "universe_frontier",
        candidate_kind: str = "universe_candidate",
        frontier_label_prefix: str = "Universe Frontier",
        tangency_label: str = "Universe Max Sharpe",
        unavailable_label: str = "Reference frontier",
        history_metadata: dict[str, CachedEquityHistory] | None = None,
    ) -> tuple[list[RiskFrontierPoint], list[str], RiskFrontierPoint | None]:
        eligible: list[str] = []
        for column in returns_df.columns:
            series = pd.to_numeric(returns_df[column], errors="coerce").dropna()
            if len(series) >= 3 and float(series.std() or 0.0) > 1e-10:
                eligible.append(str(column))
        if len(eligible) < 2:
            return [], [f"{unavailable_label} unavailable: need at least two assets with usable return variance."], None

        aligned = returns_df.reindex(columns=eligible).apply(pd.to_numeric, errors="coerce").dropna(how="any")
        if len(aligned) < 3:
            return [], [f"{unavailable_label} unavailable: only {len(aligned)} overlapping observations."], None

        mean_returns = aligned.mean().to_numpy(dtype=float) * 252.0
        cov = aligned.cov().to_numpy(dtype=float) * 252.0
        if cov.size == 0 or not np.isfinite(cov).all() or not np.isfinite(mean_returns).all():
            return [], [f"{unavailable_label} unavailable: invalid expected-return or covariance inputs."], None

        variances = np.diag(cov)
        if np.any(variances <= 0):
            return [], [f"{unavailable_label} unavailable: one or more assets has non-positive variance."], None

        rng = np.random.default_rng(84)
        n_assets = len(eligible)
        random_count = min(7000, max(2500, n_assets * 550))
        inverse_vol = 1.0 / np.sqrt(variances)
        portfolios = [
            np.full(n_assets, 1.0 / n_assets),
            inverse_vol / float(inverse_vol.sum()),
            *rng.dirichlet(np.ones(n_assets), size=random_count),
        ]

        candidates: list[tuple[np.ndarray, float, float, float | None]] = []
        for raw_weights in portfolios:
            annual_return, annual_vol, sharpe = cls._frontier_stats(raw_weights, mean_returns, cov, risk_free_rate_annual)
            if annual_vol > 0 and np.isfinite(annual_return) and np.isfinite(annual_vol):
                candidates.append((np.asarray(raw_weights, dtype=float), annual_return, annual_vol, sharpe))
        if not candidates:
            return [], [f"{unavailable_label} unavailable: no valid candidate portfolios."], None

        frontier_candidates = sorted(candidates, key=lambda item: (item[2], -item[1]))
        frontier: list[tuple[np.ndarray, float, float, float | None]] = []
        best_return = -np.inf
        for candidate in frontier_candidates:
            if candidate[1] > best_return + 1e-8:
                frontier.append(candidate)
                best_return = candidate[1]
        if len(frontier) > 28:
            selected_indexes = np.linspace(0, len(frontier) - 1, 28).round().astype(int)
            frontier = [frontier[int(index)] for index in selected_indexes]

        tangency_tuple = max(candidates, key=lambda item: item[3] if item[3] is not None else -np.inf)
        tangency = cls._reference_tuple_to_frontier_point(tangency_label, candidate_kind, tangency_tuple, eligible)
        points = [
            cls._reference_single_asset_point(
                index,
                instrument_id,
                mean_returns,
                cov,
                eligible,
                risk_free_rate_annual,
                kind=asset_kind,
                history_metadata=history_metadata or {},
            )
            for index, instrument_id in enumerate(eligible)
        ]
        points.extend(
            cls._reference_tuple_to_frontier_point(
                f"{frontier_label_prefix} {index + 1}",
                frontier_kind,
                candidate,
                eligible,
            )
            for index, candidate in enumerate(frontier)
        )
        points.append(tangency)
        return points, [], tangency

    @classmethod
    def _single_asset_frontier_point(
        cls,
        *,
        index: int,
        instrument_id: str,
        mean_returns: np.ndarray,
        cov: np.ndarray,
        positions_by_id: dict[str, object],
        risk_free_rate_annual: float | None = None,
    ) -> RiskFrontierPoint:
        weights = np.zeros(len(mean_returns), dtype=float)
        weights[index] = 1.0
        position = positions_by_id.get(instrument_id)
        label = str(getattr(position, "display_symbol", None) or getattr(position, "symbol", None) or instrument_id)
        annual_return, annual_vol, sharpe = cls._frontier_stats(
            weights,
            mean_returns,
            cov,
            risk_free_rate_annual,
        )
        return RiskFrontierPoint(
            label=label,
            kind="asset",
            annual_return=annual_return,
            annual_vol=annual_vol,
            sharpe=sharpe,
            weights=cls._frontier_weights(np.array([1.0], dtype=float), [instrument_id], positions_by_id),
        )

    @classmethod
    def _reference_single_asset_point(
        cls,
        index: int,
        instrument_id: str,
        mean_returns: np.ndarray,
        cov: np.ndarray,
        eligible: list[str],
        risk_free_rate_annual: float | None = None,
        *,
        kind: str = "universe_asset",
        history_metadata: dict[str, CachedEquityHistory] | None = None,
    ) -> RiskFrontierPoint:
        weights = np.zeros(len(mean_returns), dtype=float)
        weights[index] = 1.0
        annual_return, annual_vol, sharpe = cls._frontier_stats(
            weights,
            mean_returns,
            cov,
            risk_free_rate_annual,
        )
        return RiskFrontierPoint(
            label=instrument_id,
            kind=kind,
            annual_return=annual_return,
            annual_vol=annual_vol,
            sharpe=sharpe,
            weights=cls._reference_frontier_weights(np.array([1.0], dtype=float), [eligible[index]]),
            history_rows=history_metadata.get(instrument_id).rows if history_metadata and instrument_id in history_metadata else None,
            history_start=history_metadata.get(instrument_id).start if history_metadata and instrument_id in history_metadata else None,
            history_end=history_metadata.get(instrument_id).end if history_metadata and instrument_id in history_metadata else None,
            source_provider=(
                history_metadata.get(instrument_id).source_provider
                if history_metadata and instrument_id in history_metadata
                else None
            ),
        )

    @classmethod
    def _reference_tuple_to_frontier_point(
        cls,
        label: str,
        kind: str,
        candidate: tuple[np.ndarray, float, float, float | None],
        eligible: list[str],
    ) -> RiskFrontierPoint:
        weights, annual_return, annual_vol, sharpe = candidate
        return RiskFrontierPoint(
            label=label,
            kind=kind,
            annual_return=float(annual_return),
            annual_vol=float(annual_vol),
            sharpe=None if sharpe is None else float(sharpe),
            weights=cls._reference_frontier_weights(weights, eligible),
        )

    @staticmethod
    def _reference_frontier_weights(weights: np.ndarray, eligible: list[str]) -> list[RiskFrontierWeight]:
        rows = [
            RiskFrontierWeight(
                symbol=instrument_id,
                instrument_id=instrument_id,
                display_symbol=instrument_id,
                weight=float(weight),
            )
            for instrument_id, weight in zip(eligible, weights)
        ]
        return sorted(rows, key=lambda row: abs(row.weight), reverse=True)

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

    def _load_frontier_universe_returns(
        self,
        *,
        request: RiskComputeRequest,
        data_provider: AppDataProvider | None = None,
    ) -> tuple[pd.DataFrame | None, list[str]]:
        prices: dict[str, pd.Series] = {}
        unavailable: list[str] = []
        conversion_warnings: list[str] = []
        for symbol in self._DEFAULT_FRONTIER_UNIVERSE:
            series = self._load_frontier_universe_history(symbol, request.lookback_days, data_provider)
            if series is None or series.empty:
                unavailable.append(symbol)
                continue
            converted, fx_warnings = self._convert_benchmark_to_base(
                series.astype(float),
                "USD",
                request.base_currency,
                request.lookback_days,
                label=symbol,
                context="Reference universe",
            )
            conversion_warnings.extend(fx_warnings)
            if converted is None or converted.empty:
                unavailable.append(symbol)
                continue
            prices[symbol] = converted.astype(float)

        warnings = list(dict.fromkeys(conversion_warnings))
        if len(prices) < 2:
            if prices or unavailable:
                warnings.append(
                    "Reference frontier unavailable: broad ETF universe has fewer than two usable histories "
                    f"({len(prices)} usable; missing {', '.join(unavailable[:6])}{'...' if len(unavailable) > 6 else ''})."
                )
            return None, warnings

        returns = compute_returns(align_prices(prices))
        if returns.empty or len(returns.columns) < 2:
            warnings.append("Reference frontier unavailable: broad ETF universe histories did not produce overlapping returns.")
            return None, warnings
        return returns, warnings

    def _load_cached_equity_reference_returns(
        self,
        *,
        request: RiskComputeRequest,
    ) -> tuple[pd.DataFrame | None, dict[str, CachedEquityHistory], list[str]]:
        histories, warnings = self._discover_cached_equity_histories(
            lookback_days=request.lookback_days,
            base_currency=request.base_currency,
        )
        if len(histories) < 2:
            if histories or warnings:
                warnings.append(
                    "Cached equity reference frontier unavailable: fewer than two usable file-backed STK histories."
                )
            return None, histories, warnings

        prices = {symbol: row.series.astype(float) for symbol, row in histories.items()}
        returns = compute_returns(align_prices(prices))
        if returns.empty or len(returns.columns) < 2:
            warnings.append("Cached equity reference frontier unavailable: cached histories did not produce overlapping returns.")
            return None, histories, warnings
        return returns, histories, warnings

    def _discover_cached_equity_histories(
        self,
        *,
        lookback_days: int,
        base_currency: str,
    ) -> tuple[dict[str, CachedEquityHistory], list[str]]:
        cache = getattr(self.market_data, "cache", None)
        base_dir = getattr(cache, "base_dir", None)
        if cache is None or base_dir is None:
            return {}, []

        try:
            cache_dir = getattr(cache, "base_dir")
            files = sorted(cache_dir.glob("*_stk_*_lookback_*.csv"))
        except Exception:
            return {}, ["Cached equity reference cloud unavailable: market-data cache directory could not be scanned."]

        target_currency = str(base_currency or "USD").strip().upper() or "USD"
        min_rows = max(30, min(int(lookback_days or 0), 63))
        skipped_numeric = 0
        skipped_currency = 0
        skipped_invalid = 0
        skipped_shallow = 0
        expired_used = 0
        candidates: dict[str, CachedEquityHistory] = {}

        for path in files:
            match = self._CACHE_STK_HISTORY_RE.match(path.name)
            if not match:
                continue
            symbol = str(match.group("symbol") or "").strip().upper()
            if not symbol or symbol.isdigit():
                skipped_numeric += 1
                continue
            currency = str(match.group("currency") or "").strip().upper()
            if currency != target_currency:
                skipped_currency += 1
                continue
            try:
                lookback = int(match.group("lookback"))
            except Exception:
                skipped_invalid += 1
                continue

            source_provider = "market_data_cache"
            series = cache.get_series_file(path)
            if series is None or series.empty:
                series = self._read_expired_cache_series(path)
                if series is None or series.empty:
                    skipped_invalid += 1
                    continue
                source_provider = "market_data_cache_expired"
                expired_used += 1
            clean = pd.to_numeric(series, errors="coerce").dropna().sort_index()
            if len(clean) < min_rows or float(clean.std() or 0.0) <= 1e-10:
                skipped_shallow += 1
                continue

            index = pd.to_datetime(clean.index, errors="coerce")
            clean = pd.Series(clean.to_numpy(dtype=float), index=index).dropna()
            clean = clean[~clean.index.isna()].sort_index()
            if len(clean) < min_rows:
                skipped_shallow += 1
                continue

            history = CachedEquityHistory(
                symbol=symbol,
                series=clean.astype(float),
                lookback_days=lookback,
                rows=int(len(clean)),
                start=clean.index.min().date().isoformat(),
                end=clean.index.max().date().isoformat(),
                source_provider=source_provider,
            )
            existing = candidates.get(symbol)
            if existing is None or (history.rows, history.lookback_days) > (existing.rows, existing.lookback_days):
                candidates[symbol] = history

        selected = dict(
            sorted(
                candidates.items(),
                key=lambda item: (item[1].rows, item[1].lookback_days, item[0]),
                reverse=True,
            )[: self._MAX_CACHED_EQUITY_FRONTIER_SYMBOLS]
        )

        warnings: list[str] = []
        skipped = skipped_numeric + skipped_currency + skipped_invalid + skipped_shallow
        if skipped:
            warnings.append(
                "Cached equity reference cloud skipped "
                f"{skipped} cache file(s) ({skipped_numeric} numeric ids, {skipped_currency} non-{target_currency}, "
                f"{skipped_invalid} invalid/unreadable, {skipped_shallow} shallow/flat)."
            )
        if expired_used:
            warnings.append(
                "Cached equity reference cloud included "
                f"{expired_used} expired file-backed history file(s) as stale visual context only."
            )
        if len(candidates) > len(selected):
            warnings.append(
                "Cached equity reference cloud capped at "
                f"{len(selected)} deepest symbols from {len(candidates)} usable file-backed STK histories."
            )
        return selected, warnings

    @staticmethod
    def _read_expired_cache_series(path) -> pd.Series | None:
        try:
            df = pd.read_csv(path, parse_dates=["date"], index_col="date")
            if "close" not in df:
                return None
            series = pd.to_numeric(df["close"], errors="coerce").dropna()
        except Exception:
            return None
        if series.empty:
            return None
        if getattr(series.index, "tz", None) is not None:
            series.index = series.index.tz_convert(None)
        return series.sort_index()

    def _load_frontier_universe_history(
        self,
        symbol: str,
        lookback_days: int,
        data_provider: AppDataProvider | None = None,
    ) -> pd.Series | None:
        instrument = InstrumentReference(symbol=symbol).with_defaults(self.benchmark_defaults)

        load_instrument_history_result = getattr(data_provider, "load_instrument_history_result", None)
        if callable(load_instrument_history_result):
            try:
                result = load_instrument_history_result(
                    instrument,
                    lookback_days,
                    defaults=self.benchmark_defaults,
                )
                if result.series is not None and not result.series.empty:
                    return result.series.astype(float)
            except Exception:
                return None

        history_providers = getattr(data_provider, "history_providers", None)
        for provider in history_providers or []:
            try:
                result = provider.load_history(instrument, lookback_days)
            except Exception:
                continue
            if result.series is not None and not result.series.empty:
                return result.series.astype(float)

        if self.client.mock:
            series = self.mock_service.load_history(symbol)
        else:
            contract = contract_for_instrument(instrument)
            series = self.market_data.fetch_history(contract, lookback_days)
        return None if series is None or series.empty else series.astype(float)

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
