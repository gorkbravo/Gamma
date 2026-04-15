from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.analytics.research_overview import (
    compute_overview_metrics,
    returns_from_price_series,
    total_return_from_returns,
    weighted_group_returns,
    latest_price,
)
from src.analytics.returns import align_prices, compute_returns
from src.analytics.risk_metrics import compute_weights, max_drawdown, portfolio_returns, realized_vol
from src.application.instrument_identity import find_identity_by_symbol, snapshot_identity_map
from src.application.research_validation import ensure_valid_research_scope
from src.models.app_mode import ResearchScopeType, SyntheticPosition
from src.models.instruments import InstrumentDefaults, InstrumentReference
from src.models.portfolio import PortfolioSnapshot
from src.models.provenance import FreshnessLabel
from src.models.research_overview import (
    RESEARCH_OVERVIEW_METRIC_OPTIONS,
    RESEARCH_OVERVIEW_TIMEFRAMES,
    RESEARCH_OVERVIEW_UNIVERSES,
    ResearchOverviewCoverage,
    ResearchOverviewMetrics,
    ResearchOverviewNode,
    ResearchOverviewRankItem,
    ResearchOverviewRankings,
    ResearchOverviewRequest,
    ResearchOverviewResult,
    ResearchOverviewSummary,
    ResearchOverviewUniverse,
    ResearchOverviewUniverseInstrument,
)
from src.services.data_providers import ResearchDataProvider, normalize_snapshot_price_histories
from src.utils.time import now_utc


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
    primary_symbol: str | None
    weights: pd.Series
    primary_price: pd.Series
    available_symbols: list[str]
    missing_symbols: list[str]
    benchmark_overlap_count: int
    constituent_total_returns: pd.Series
    constituent_annual_vol: pd.Series
    constituent_max_drawdown: pd.Series
    warnings: list[str]


class ResearchService:
    def __init__(self, provider: ResearchDataProvider) -> None:
        self.provider = provider

    def overview(self, request: ResearchOverviewRequest) -> ResearchOverviewResult:
        warnings: list[str] = []
        retrieved_at = now_utc()
        universe = self._overview_universe(request.universe_id, warnings)
        timeframe = self._overview_timeframe(request.timeframe, warnings)
        lookback_days = RESEARCH_OVERVIEW_TIMEFRAMES[timeframe]
        benchmark_symbol = str(request.benchmark_symbol or "").strip().upper() or "SPY"
        source_provider = self._overview_source_provider()
        freshness_label = FreshnessLabel.MOCKED if source_provider == "mock" else FreshnessLabel.HISTORICAL

        warnings.extend(universe.limitations)

        benchmark_returns = self._overview_benchmark_returns(benchmark_symbol, lookback_days, warnings)
        benchmark_total_return = total_return_from_returns(benchmark_returns)
        if benchmark_returns.empty:
            warnings.append(f"Benchmark history unavailable for {benchmark_symbol}; beta and relative return are limited.")

        returns_by_symbol: dict[str, pd.Series] = {}
        weights_by_symbol: dict[str, float] = {}
        instrument_nodes: list[ResearchOverviewNode] = []
        missing_symbols: list[str] = []

        for instrument in universe.instruments:
            reference = self._overview_reference(instrument)
            symbol = instrument.normalized_symbol()
            series = self.provider.load_instrument_history(reference, lookback_days)
            returns = returns_from_price_series(series, lookback_days)
            node_warnings: list[str] = []
            if returns.empty:
                missing_symbols.append(symbol)
                node_warnings.append("Price history is unavailable for this overview timeframe.")
            else:
                returns_by_symbol[symbol] = returns
            weights_by_symbol[symbol] = max(float(instrument.weight), 0.0)
            metrics = compute_overview_metrics(
                returns,
                benchmark_returns=benchmark_returns,
                benchmark_total_return=benchmark_total_return,
                latest=latest_price(series),
            )
            instrument_nodes.append(
                self._overview_instrument_node(
                    instrument,
                    reference,
                    metrics,
                    source_provider=source_provider,
                    retrieved_at=retrieved_at,
                    timeframe=timeframe,
                    freshness_label=freshness_label,
                    warnings=node_warnings,
                )
            )

        group_nodes = self._overview_group_nodes(
            universe.instruments,
            returns_by_symbol,
            weights_by_symbol,
            benchmark_returns=benchmark_returns,
            benchmark_total_return=benchmark_total_return,
            source_provider=source_provider,
            retrieved_at=retrieved_at,
            timeframe=timeframe,
            freshness_label=freshness_label,
        )
        nodes = [*group_nodes, *instrument_nodes]
        coverage = ResearchOverviewCoverage(
            instrument_count=len(universe.instruments),
            priced_count=len(returns_by_symbol),
            missing_symbols=missing_symbols,
            benchmark_symbol=benchmark_symbol,
            benchmark_available=not benchmark_returns.empty,
            benchmark_observation_count=int(len(benchmark_returns)),
        )
        rankings = self._overview_rankings(instrument_nodes)
        summary = self._overview_summary(group_nodes, coverage)
        coverage_note = summary.coverage_note
        if coverage_note:
            warnings.append(coverage_note)

        return ResearchOverviewResult(
            universe_id=universe.universe_id,
            universe_label=universe.label,
            universe_description=universe.description,
            timeframe=timeframe,
            lookback_days=lookback_days,
            benchmark_symbol=benchmark_symbol,
            available_universes=list(RESEARCH_OVERVIEW_UNIVERSES),
            available_timeframes=list(RESEARCH_OVERVIEW_TIMEFRAMES.keys()),
            metric_options=list(RESEARCH_OVERVIEW_METRIC_OPTIONS),
            nodes=nodes,
            coverage=coverage,
            rankings=rankings,
            summary=summary,
            warnings=list(dict.fromkeys(warnings)),
            source_provider=source_provider,
            retrieved_at=retrieved_at,
            origin="research_service.overview",
            transformation_note=(
                "Research Overview computes return, volatility, beta, drawdown, and relative-return metrics from "
                "daily close histories. Group nodes are weighted return streams from available constituents; tile "
                "size is equal-weight until market-cap or index-weight data is available."
            ),
            freshness_label=freshness_label,
        )

    def analyze(self, request: ResearchAnalysisRequest) -> ResearchAnalysisResult:
        warnings: list[str] = []
        validated_scope = ensure_valid_research_scope(
            request.scope_type,
            request.primary_symbol,
            request.synthetic_positions,
        )
        primary_symbol = validated_scope.primary_symbol
        benchmark_symbol = str(request.benchmark_symbol or "").strip().upper() or "SPY"
        snapshot, snapshot_warnings = self.provider.build_snapshot_for_scope(
            request.scope_type,
            primary_symbol=primary_symbol,
            synthetic_positions=validated_scope.synthetic_positions,
        )
        warnings.extend(snapshot_warnings)
        if snapshot is None:
            return self._empty_result(
                scope_type=request.scope_type,
                benchmark_symbol=benchmark_symbol,
                primary_symbol=primary_symbol or None,
                warnings=warnings,
            )

        identity_map = snapshot_identity_map(snapshot)
        raw_prices, missing = self.provider.load_prices(snapshot, lookback_days=request.lookback_days)
        if missing:
            warnings.append(f"Missing history for: {', '.join(missing)}")
        normalized_prices = normalize_snapshot_price_histories(
            snapshot,
            raw_prices,
            request.lookback_days,
            self.provider.market_data,
        )
        warnings.extend(normalized_prices.warnings)
        prices = normalized_prices.prices
        primary_price = pd.Series(dtype=float)
        if request.scope_type == ResearchScopeType.SINGLE_TICKER:
            primary_identity = find_identity_by_symbol(snapshot, primary_symbol)
            if primary_identity is not None:
                primary_price = prices.get(primary_identity.instrument_id, pd.Series(dtype=float))
        if not prices:
            warnings.append("No valid history found for selected scope")
            return self._empty_result(
                scope_type=request.scope_type,
                snapshot=snapshot,
                benchmark_symbol=benchmark_symbol,
                primary_symbol=primary_symbol or None,
                primary_price=primary_price,
                missing_symbols=missing,
                warnings=warnings,
            )

        returns_df = compute_returns(align_prices(prices))
        if returns_df.empty:
            warnings.append("No overlapping history across selected symbols")
            return self._empty_result(
                scope_type=request.scope_type,
                snapshot=snapshot,
                benchmark_symbol=benchmark_symbol,
                primary_symbol=primary_symbol or None,
                primary_price=primary_price,
                missing_symbols=missing,
                warnings=warnings,
            )

        values = {
            position.resolved_instrument_id(): float(position.base_market_value)
            for position in snapshot.positions
            if position.base_market_value is not None and position.resolved_instrument_id() in returns_df.columns
        }
        weights = compute_weights(pd.Series(values))
        if weights.empty:
            warnings.append("Weights are invalid for selected scope")
            return self._empty_result(
                scope_type=request.scope_type,
                snapshot=snapshot,
                benchmark_symbol=benchmark_symbol,
                primary_symbol=primary_symbol or None,
                weights=weights,
                primary_price=primary_price,
                available_symbols=self._labels_for_ids(list(returns_df.columns), identity_map),
                missing_symbols=missing,
                warnings=warnings,
            )

        perf = portfolio_returns(returns_df.reindex(columns=weights.index.tolist()), weights)
        if perf.empty:
            warnings.append("No performance series could be computed")
            return self._empty_result(
                scope_type=request.scope_type,
                snapshot=snapshot,
                benchmark_symbol=benchmark_symbol,
                primary_symbol=primary_symbol or None,
                weights=weights,
                primary_price=primary_price,
                perf=perf,
                available_symbols=self._labels_for_ids(weights.index.tolist(), identity_map),
                missing_symbols=missing,
                warnings=warnings,
            )

        benchmark_returns = self.load_benchmark_returns(
            benchmark_symbol,
            request.lookback_days,
            snapshot.base_currency,
            warnings,
        )
        aligned_returns = returns_df.reindex(columns=weights.index.tolist())
        constituent_total_returns = self._constituent_total_returns(aligned_returns)
        constituent_annual_vol = aligned_returns.apply(lambda series: realized_vol(series.dropna())[1])
        constituent_max_drawdown = aligned_returns.apply(lambda series: max_drawdown(series.dropna()))
        benchmark_overlap_count = int(
            len(perf.to_frame("portfolio").join(benchmark_returns.to_frame("benchmark"), how="inner").dropna())
        )
        return ResearchAnalysisResult(
            scope_type=request.scope_type,
            snapshot=snapshot,
            perf=perf,
            benchmark_returns=benchmark_returns,
            benchmark_symbol=benchmark_symbol,
            primary_symbol=primary_symbol or None,
            weights=weights,
            primary_price=primary_price,
            available_symbols=self._labels_for_ids(weights.index.tolist(), identity_map),
            missing_symbols=missing,
            benchmark_overlap_count=benchmark_overlap_count,
            constituent_total_returns=constituent_total_returns,
            constituent_annual_vol=constituent_annual_vol,
            constituent_max_drawdown=constituent_max_drawdown,
            warnings=warnings,
        )

    def _overview_benchmark_returns(
        self,
        benchmark_symbol: str,
        lookback_days: int,
        warnings: list[str],
    ) -> pd.Series:
        base_currency = str(getattr(self.provider, "base_currency", "USD") or "USD").upper()
        try:
            benchmark_history = self.provider.load_benchmark_history(
                benchmark_symbol,
                lookback_days,
                base_currency=base_currency,
                warnings=warnings,
            )
        except TypeError:
            benchmark_history = self.provider.load_benchmark_history(benchmark_symbol, lookback_days)
        return returns_from_price_series(benchmark_history, lookback_days)

    @staticmethod
    def _overview_universe(
        universe_id: str | None,
        warnings: list[str],
    ) -> ResearchOverviewUniverse:
        normalized = str(universe_id or "").strip().lower() or "sample_equities"
        for universe in RESEARCH_OVERVIEW_UNIVERSES:
            if universe.universe_id == normalized:
                return universe
        warnings.append(f"Unknown Research Overview universe '{universe_id}'; using sample equities.")
        return RESEARCH_OVERVIEW_UNIVERSES[0]

    @staticmethod
    def _overview_timeframe(timeframe: str | None, warnings: list[str]) -> str:
        normalized = str(timeframe or "").strip().upper() or "3M"
        if normalized in RESEARCH_OVERVIEW_TIMEFRAMES:
            return normalized
        warnings.append(f"Unknown Research Overview timeframe '{timeframe}'; using 3M.")
        return "3M"

    def _overview_reference(self, instrument: ResearchOverviewUniverseInstrument) -> InstrumentReference:
        defaults = getattr(
            self.provider,
            "instrument_defaults",
            InstrumentDefaults(provider="research", sec_type="STK", exchange="SMART", currency="USD"),
        )
        return instrument.to_reference().with_defaults(defaults)

    def _overview_source_provider(self) -> str:
        client = getattr(self.provider, "client", None)
        if bool(getattr(client, "mock", False)):
            return "mock"
        return "ibkr"

    @staticmethod
    def _overview_group_id(group: str) -> str:
        slug = str(group or "Ungrouped").strip().lower().replace("&", "and")
        slug = "_".join(part for part in slug.replace("/", " ").split() if part)
        return f"group:{slug or 'ungrouped'}"

    def _overview_instrument_node(
        self,
        instrument: ResearchOverviewUniverseInstrument,
        reference: InstrumentReference,
        metrics: ResearchOverviewMetrics,
        *,
        source_provider: str,
        retrieved_at,
        timeframe: str,
        freshness_label: FreshnessLabel,
        warnings: list[str],
    ) -> ResearchOverviewNode:
        group_id = self._overview_group_id(instrument.group)
        symbol = instrument.normalized_symbol()
        return ResearchOverviewNode(
            node_id=f"instrument:{symbol}",
            normalized_id=reference.instrument_id or symbol,
            label=instrument.label or symbol,
            level="instrument",
            parent_id=group_id,
            group=instrument.group,
            sector=instrument.sector,
            industry=instrument.industry,
            symbol=symbol,
            instrument_id=reference.instrument_id,
            weight=float(instrument.weight),
            size=max(float(instrument.weight), 0.0) or 1.0,
            metrics=metrics,
            source_provider=source_provider,
            retrieved_at=retrieved_at,
            origin="research_service.overview.instrument",
            transformation_note=(
                f"Computed from daily close history over {timeframe}. Tile size uses equal-weight/sample "
                "universe weights because market-cap weights are not yet available."
            ),
            freshness_label=freshness_label,
            warnings=list(warnings),
        )

    def _overview_group_nodes(
        self,
        instruments: tuple[ResearchOverviewUniverseInstrument, ...],
        returns_by_symbol: dict[str, pd.Series],
        weights_by_symbol: dict[str, float],
        *,
        benchmark_returns: pd.Series,
        benchmark_total_return: float | None,
        source_provider: str,
        retrieved_at,
        timeframe: str,
        freshness_label: FreshnessLabel,
    ) -> list[ResearchOverviewNode]:
        group_map: dict[str, list[ResearchOverviewUniverseInstrument]] = {}
        for instrument in instruments:
            group_map.setdefault(instrument.group, []).append(instrument)

        nodes: list[ResearchOverviewNode] = []
        for group, rows in group_map.items():
            symbols = [row.normalized_symbol() for row in rows]
            group_returns = weighted_group_returns(
                {symbol: returns_by_symbol[symbol] for symbol in symbols if symbol in returns_by_symbol},
                {symbol: weights_by_symbol.get(symbol, 0.0) for symbol in symbols},
            )
            metrics = compute_overview_metrics(
                group_returns,
                benchmark_returns=benchmark_returns,
                benchmark_total_return=benchmark_total_return,
            )
            group_id = self._overview_group_id(group)
            group_weight = sum(max(float(row.weight), 0.0) for row in rows)
            warnings = [] if not group_returns.empty else ["No priced constituents are available for this group."]
            nodes.append(
                ResearchOverviewNode(
                    node_id=group_id,
                    normalized_id=group_id,
                    label=group,
                    level="group",
                    parent_id=None,
                    group=group,
                    sector=rows[0].sector if rows else None,
                    industry=None,
                    symbol=None,
                    instrument_id=None,
                    weight=group_weight,
                    size=group_weight or float(len(rows) or 1),
                    metrics=metrics,
                    source_provider=source_provider,
                    retrieved_at=retrieved_at,
                    origin="research_service.overview.group",
                    transformation_note=(
                        f"Computed as a weighted return stream from available {group} constituents over {timeframe}. "
                        "This is a sample/watchlist group, not a complete sector aggregate."
                    ),
                    freshness_label=freshness_label,
                    warnings=warnings,
                )
            )
        return nodes

    @staticmethod
    def _overview_rank_items(
        nodes: list[ResearchOverviewNode],
        metric_name: str,
        *,
        descending: bool,
        limit: int = 5,
    ) -> list[ResearchOverviewRankItem]:
        candidates: list[tuple[ResearchOverviewNode, float]] = []
        for node in nodes:
            value = getattr(node.metrics, metric_name)
            if value is None:
                continue
            candidates.append((node, float(value)))
        ranked = sorted(candidates, key=lambda item: item[1], reverse=descending)[:limit]
        return [
            ResearchOverviewRankItem(
                node_id=node.node_id,
                label=node.label,
                group=node.group,
                symbol=node.symbol,
                value=value,
            )
            for node, value in ranked
        ]

    def _overview_rankings(self, instrument_nodes: list[ResearchOverviewNode]) -> ResearchOverviewRankings:
        return ResearchOverviewRankings(
            leaders=self._overview_rank_items(instrument_nodes, "total_return", descending=True),
            laggards=self._overview_rank_items(instrument_nodes, "total_return", descending=False),
            highest_volatility=self._overview_rank_items(instrument_nodes, "annual_volatility", descending=True),
            highest_beta=self._overview_rank_items(instrument_nodes, "beta", descending=True),
            largest_drawdowns=self._overview_rank_items(instrument_nodes, "max_drawdown", descending=False),
        )

    def _overview_summary(
        self,
        group_nodes: list[ResearchOverviewNode],
        coverage: ResearchOverviewCoverage,
    ) -> ResearchOverviewSummary:
        leaders = self._overview_rank_items(group_nodes, "total_return", descending=True, limit=1)
        laggards = self._overview_rank_items(group_nodes, "total_return", descending=False, limit=1)
        volatile = self._overview_rank_items(group_nodes, "annual_volatility", descending=True, limit=1)
        coverage_note = None
        if coverage.priced_count < coverage.instrument_count:
            coverage_note = (
                f"Coverage is partial: {coverage.priced_count}/{coverage.instrument_count} overview instruments "
                "have usable price history."
            )
        return ResearchOverviewSummary(
            leading_group=leaders[0] if leaders else None,
            lagging_group=laggards[0] if laggards else None,
            highest_volatility_group=volatile[0] if volatile else None,
            coverage_note=coverage_note,
        )

    def load_benchmark_returns(
        self,
        benchmark_symbol: str,
        lookback_days: int,
        base_currency: str,
        warnings: list[str] | None = None,
    ) -> pd.Series:
        warning_list = warnings if warnings is not None else []
        symbol = str(benchmark_symbol or "").strip().upper() or "SPY"
        bench_series = self.provider.load_benchmark_history(
            symbol,
            lookback_days,
            base_currency=base_currency,
            warnings=warning_list,
        )
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
        primary_symbol: str | None = None,
        weights: pd.Series | None = None,
        primary_price: pd.Series | None = None,
        perf: pd.Series | None = None,
        available_symbols: list[str] | None = None,
        missing_symbols: list[str] | None = None,
    ) -> ResearchAnalysisResult:
        return ResearchAnalysisResult(
            scope_type=scope_type,
            snapshot=snapshot,
            perf=perf if perf is not None else pd.Series(dtype=float),
            benchmark_returns=pd.Series(dtype=float),
            benchmark_symbol=benchmark_symbol,
            primary_symbol=primary_symbol,
            weights=weights if weights is not None else pd.Series(dtype=float),
            primary_price=primary_price if primary_price is not None else pd.Series(dtype=float),
            available_symbols=list(available_symbols or []),
            missing_symbols=list(missing_symbols or []),
            benchmark_overlap_count=0,
            constituent_total_returns=pd.Series(dtype=float),
            constituent_annual_vol=pd.Series(dtype=float),
            constituent_max_drawdown=pd.Series(dtype=float),
            warnings=warnings,
        )

    @staticmethod
    def _constituent_total_returns(returns_df: pd.DataFrame) -> pd.Series:
        if returns_df.empty:
            return pd.Series(dtype=float)
        cumulative = (1.0 + returns_df).prod() - 1.0
        return cumulative.astype(float)

    @staticmethod
    def _labels_for_ids(
        instrument_ids: list[str],
        identity_map: dict[str, object],
    ) -> list[str]:
        labels: list[str] = []
        for instrument_id in instrument_ids:
            identity = identity_map.get(instrument_id)
            label = getattr(identity, "display_symbol", None) or getattr(identity, "symbol", None) or str(instrument_id)
            labels.append(str(label))
        return labels
