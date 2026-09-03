from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from concurrent.futures import Future
import math
from threading import Lock
from typing import Any

import pandas as pd

from src.analytics.research_overview import (
    compute_overview_metrics,
    returns_from_price_series,
    total_return_from_returns,
    weighted_group_returns,
    latest_price,
)
from src.analytics.research_returns import (
    OUTLIER_ABS_RETURN_THRESHOLD,
    analyze_return_stream,
    clean_return_series,
    compare_return_streams,
    equity_curve_from_returns,
)
from src.analytics.returns import align_prices, compute_returns
from src.analytics.risk_metrics import compute_weights, max_drawdown, portfolio_returns, realized_vol
from src.application.commodities_service import CommodityWorkspaceRequest
from src.application.instrument_identity import find_identity_by_symbol, snapshot_identity_map
from src.application.research_validation import ResearchValidationError, ensure_valid_research_scope
from src.models.app_mode import ResearchScopeType, SyntheticPosition
from src.models.instruments import InstrumentDefaults, InstrumentReference
from src.models.portfolio import PortfolioSnapshot
from src.models.provenance import FreshnessLabel
from src.models.research_lab import (
    GammaResearchObject,
    ImportedReturnStreamRequest,
    ResearchComparisonLeg,
    ResearchComparisonRequest,
    ResearchComparisonResult,
    ResearchBookRiskLeg,
    ResearchObjectReturnPoint,
    SavedResearchCreateRequest,
    SavedResearchItem,
    StrategyLabHandoffResolveRequest,
    StrategyLabResolvedHandoff,
    CrossTabHandoffSeries,
    CrossTabHandoffTimeframe,
    StrategyLabAnalysisResult,
    StrategyLabCompositionLeg,
    StrategyLabCompositionRequest,
    StrategyLabBookValidationResult,
    StrategyLabCompositionResult,
    StrategyLabPortfolioCompositionRequest,
    StrategyLabPortfolioLeg,
)
from src.models.research_overview import (
    RESEARCH_OVERVIEW_METRIC_OPTIONS,
    RESEARCH_OVERVIEW_SORT_OPTIONS,
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
from src.services.research_market_data import ResearchHistoryResult
from src.services.saved_research_store import SavedResearchStore
from src.utils.time import ensure_utc, now_utc


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
    source_provider: str = "unknown"
    history_source_label: str = "Unknown history source"
    freshness_label: FreshnessLabel = FreshnessLabel.UNKNOWN
    primary_price_ohlcv: pd.DataFrame | None = None


def _primary_ohlcv_for_result(
    provider: object,
    instrument_id: str | None,
    primary_price: pd.Series,
) -> pd.DataFrame | None:
    if not instrument_id or primary_price is None or primary_price.empty:
        return None
    loader = getattr(provider, "last_ohlcv_for_instrument", None)
    if not callable(loader):
        return None
    frame = loader(str(instrument_id))
    return _align_ohlcv_to_close(frame, primary_price)


def _align_ohlcv_to_close(frame: pd.DataFrame | None, close_series: pd.Series) -> pd.DataFrame | None:
    if frame is None or frame.empty or close_series is None or close_series.empty:
        return None
    columns = {str(column).strip().lower(): column for column in frame.columns}
    selected: dict[str, pd.Series] = {}
    for key in ("open", "high", "low", "close", "volume"):
        column = columns.get(key)
        if column is not None:
            selected[key] = pd.to_numeric(frame[column], errors="coerce")
    if "close" not in selected:
        return None
    normalized = pd.DataFrame(selected, index=frame.index).dropna(subset=["close"])
    if normalized.empty:
        return None
    clean_close = pd.to_numeric(close_series, errors="coerce").dropna()
    common_index = normalized.index.intersection(clean_close.index)
    if common_index.empty:
        return None
    aligned = normalized.reindex(common_index).copy()
    close = clean_close.reindex(common_index).astype(float)
    raw_close = pd.to_numeric(aligned["close"], errors="coerce").replace(0, pd.NA)
    ratio = (close / raw_close).replace([float("inf"), float("-inf")], pd.NA).fillna(1.0)
    for column in ("open", "high", "low", "close"):
        if column in aligned.columns:
            aligned[column] = pd.to_numeric(aligned[column], errors="coerce").astype(float) * ratio
    if "volume" in aligned.columns:
        aligned["volume"] = pd.to_numeric(aligned["volume"], errors="coerce")
    aligned["close"] = close
    return aligned.dropna(subset=["close"]).sort_index()


@dataclass(frozen=True)
class _CarriedSeriesHistory:
    """Adapts a series carried on a handoff to the price-history shape the
    commodity resolver's provenance and staleness helpers already read."""

    label: str
    points: list[Any]
    source_provider: str | None
    origin: str | None
    retrieved_at: datetime | None
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_series(cls, series: CrossTabHandoffSeries) -> "_CarriedSeriesHistory":
        retrieved_at = pd.to_datetime(series.retrieved_at, errors="coerce", utc=True)
        return cls(
            label=series.label,
            points=list(series.points),
            source_provider=series.source_provider,
            origin=series.origin,
            retrieved_at=None if pd.isna(retrieved_at) else retrieved_at.to_pydatetime(),
        )


class ResearchService:
    def __init__(self, provider: ResearchDataProvider, saved_store: SavedResearchStore | None = None) -> None:
        self.provider = provider
        self.saved_store = saved_store
        self._overview_cache: dict[tuple[str, str, str, str, str], ResearchOverviewResult] = {}
        self._overview_lock = Lock()
        self._overview_inflight: dict[tuple[str, str, str, str, str], Future[ResearchOverviewResult]] = {}

    def overview(self, request: ResearchOverviewRequest) -> ResearchOverviewResult:
        key_warnings: list[str] = []
        provider_policy = self._overview_provider_policy(request.provider_policy)
        universe = self._overview_universe(request.universe_id, key_warnings)
        timeframe = self._overview_timeframe(request.timeframe, key_warnings)
        benchmark_symbol = str(request.benchmark_symbol or "").strip().upper() or "SPY"
        cache_seconds = self._overview_cache_seconds(provider_policy)
        cache_key = self._overview_cache_key(provider_policy, universe.universe_id, timeframe, benchmark_symbol)
        with self._overview_lock:
            future = self._overview_inflight.get(cache_key)
            if future is not None:
                owner = False
            else:
                owner = True
            cached = self._get_cached_overview(cache_key, cache_seconds, force_refresh=request.force_refresh)
            if future is None and cached is not None:
                return cached
            if future is None:
                future = Future()
                self._overview_inflight[cache_key] = future
        if not owner:
            return future.result()
        try:
            result = self._compute_overview(request)
            future.set_result(result)
            return result
        except BaseException as exc:
            future.set_exception(exc)
            raise
        finally:
            with self._overview_lock:
                if self._overview_inflight.get(cache_key) is future:
                    self._overview_inflight.pop(cache_key, None)

    def _compute_overview(self, request: ResearchOverviewRequest) -> ResearchOverviewResult:
        warnings: list[str] = []
        retrieved_at = now_utc()
        provider_policy = self._overview_provider_policy(request.provider_policy)
        cache_seconds = self._overview_cache_seconds(provider_policy)
        universe = self._overview_universe(request.universe_id, warnings)
        timeframe = self._overview_timeframe(request.timeframe, warnings)
        lookback_days = RESEARCH_OVERVIEW_TIMEFRAMES[timeframe]
        benchmark_symbol = str(request.benchmark_symbol or "").strip().upper() or "SPY"
        cache_key = self._overview_cache_key(provider_policy, universe.universe_id, timeframe, benchmark_symbol)
        cached = self._get_cached_overview(cache_key, cache_seconds, force_refresh=request.force_refresh)
        if cached is not None:
            return cached

        source_provider = self._overview_source_provider()
        history_source_label = self._overview_history_source_label(source_provider)
        freshness_label = FreshnessLabel.MOCKED if source_provider == "mock" else FreshnessLabel.HISTORICAL

        warnings.extend(universe.limitations)
        reset_tracking = getattr(self.provider, "reset_history_tracking", None)
        if callable(reset_tracking):
            reset_tracking()

        benchmark_returns = self._overview_benchmark_returns(
            benchmark_symbol,
            lookback_days,
            warnings,
            provider_policy=provider_policy,
            force_refresh=request.force_refresh,
            cache_seconds=cache_seconds,
        )
        benchmark_total_return = total_return_from_returns(benchmark_returns)
        if benchmark_returns.empty:
            warnings.append(f"Benchmark history unavailable for {benchmark_symbol}; beta and relative return are limited.")

        returns_by_symbol: dict[str, pd.Series] = {}
        weights_by_symbol: dict[str, float] = {}
        instrument_nodes: list[ResearchOverviewNode] = []
        missing_symbols: list[str] = []
        thin_history_symbols: list[str] = []
        observation_counts: dict[str, int] = {}

        references = [self._overview_reference(instrument) for instrument in universe.instruments]
        bulk_loader = getattr(self.provider, "load_instrument_history_results", None)
        bulk_histories: dict[str, ResearchHistoryResult] = {}
        if callable(bulk_loader):
            bulk_histories = bulk_loader(
                references,
                lookback_days,
                provider_policy=provider_policy,
                bypass_cache=request.force_refresh,
                max_age_seconds=cache_seconds,
            )
        history_results: list[ResearchHistoryResult] = []

        for instrument, reference in zip(universe.instruments, references):
            symbol = instrument.normalized_symbol()
            history_result = bulk_histories.get(symbol) if bulk_histories else None
            if history_result is None:
                history_result = self._load_overview_history(
                    reference,
                    lookback_days,
                    provider_policy=provider_policy,
                    force_refresh=request.force_refresh,
                    cache_seconds=cache_seconds,
                )
            history_results.append(history_result)
            series = history_result.series
            returns = returns_from_price_series(series, lookback_days)
            node_warnings: list[str] = list(history_result.warnings)
            observation_counts[symbol] = int(len(returns))
            if returns.empty:
                missing_symbols.append(symbol)
                node_warnings.append(
                    f"Price history is unavailable for {timeframe}; the node is excluded from returns, beta, and breadth."
                )
            else:
                returns_by_symbol[symbol] = returns
                if len(returns) < lookback_days:
                    thin_history_symbols.append(symbol)
                    node_warnings.append(
                        f"Thin history: {len(returns)}/{lookback_days} return observations available for {timeframe}."
                    )
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
                    source_provider=history_result.source_provider,
                    retrieved_at=retrieved_at,
                    timeframe=timeframe,
                    freshness_label=history_result.freshness_label,
                    warnings=node_warnings,
                )
            )

        source_summary = self._history_results_source_summary(
            history_results,
            source_provider,
            history_source_label,
            freshness_label,
        )
        source_provider = source_summary.source_provider
        history_source_label = source_summary.source_label
        freshness_label = source_summary.freshness_label
        warnings.extend(source_summary.warnings)
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
        min_observations, max_observations = self._overview_observation_range(observation_counts)
        coverage = ResearchOverviewCoverage(
            instrument_count=len(universe.instruments),
            priced_count=len(returns_by_symbol),
            missing_symbols=missing_symbols,
            benchmark_symbol=benchmark_symbol,
            benchmark_available=not benchmark_returns.empty,
            benchmark_observation_count=int(len(benchmark_returns)),
            coverage_ratio=(len(returns_by_symbol) / len(universe.instruments)) if universe.instruments else 0.0,
            missing_count=len(missing_symbols),
            thin_history_symbols=thin_history_symbols,
            min_observation_count=min_observations,
            max_observation_count=max_observations,
            coverage_label=universe.coverage_label,
            history_source_label=history_source_label,
            metadata_source_label=universe.metadata_source_label,
        )
        rankings = self._overview_rankings(instrument_nodes)
        summary = self._overview_summary(group_nodes, coverage)
        coverage_note = summary.coverage_note
        if coverage_note:
            warnings.append(coverage_note)
        if thin_history_symbols:
            preview = ", ".join(thin_history_symbols[:8])
            suffix = f", +{len(thin_history_symbols) - 8} more" if len(thin_history_symbols) > 8 else ""
            warnings.append(
                f"Thin overview history for {len(thin_history_symbols)} instruments over {timeframe}: {preview}{suffix}."
            )

        result = ResearchOverviewResult(
            universe_id=universe.universe_id,
            universe_label=universe.label,
            universe_description=universe.description,
            timeframe=timeframe,
            lookback_days=lookback_days,
            benchmark_symbol=benchmark_symbol,
            available_universes=list(RESEARCH_OVERVIEW_UNIVERSES),
            available_timeframes=list(RESEARCH_OVERVIEW_TIMEFRAMES.keys()),
            metric_options=list(RESEARCH_OVERVIEW_METRIC_OPTIONS),
            sort_options=list(RESEARCH_OVERVIEW_SORT_OPTIONS),
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
                "sizing uses static/reference proxy metadata when available and falls back to universe weights."
            ),
            freshness_label=freshness_label,
            history_source_label=history_source_label,
            metadata_source_label=universe.metadata_source_label,
            coverage_label=universe.coverage_label,
        )
        if cache_seconds > 0:
            with self._overview_lock:
                self._overview_cache[cache_key] = result
        return result

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
        drain_warnings = getattr(self.provider, "drain_history_warnings", None)
        if callable(drain_warnings):
            warnings.extend(drain_warnings())
        if missing:
            warnings.append(
                f"Missing history for {len(missing)} symbol(s) over {request.lookback_days} days: {', '.join(missing)}. "
                "Missing symbols are excluded from the aligned research return stream."
            )
        normalized_prices = normalize_snapshot_price_histories(
            snapshot,
            raw_prices,
            request.lookback_days,
            self.provider.market_data,
        )
        warnings.extend(normalized_prices.warnings)
        prices = normalized_prices.prices
        primary_price = pd.Series(dtype=float)
        primary_price_ohlcv: pd.DataFrame | None = None
        if request.scope_type == ResearchScopeType.SINGLE_TICKER:
            primary_identity = find_identity_by_symbol(snapshot, primary_symbol)
            if primary_identity is not None:
                primary_price = prices.get(primary_identity.instrument_id, pd.Series(dtype=float))
                primary_price_ohlcv = _primary_ohlcv_for_result(
                    self.provider,
                    primary_identity.instrument_id,
                    primary_price,
                )
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
        default_source = self._overview_source_provider()
        source_summary = self._provider_history_source_summary(
            default_source,
            self._overview_history_source_label(default_source),
            FreshnessLabel.MOCKED if default_source == "mock" else FreshnessLabel.HISTORICAL,
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
            primary_price_ohlcv=primary_price_ohlcv,
            available_symbols=self._labels_for_ids(weights.index.tolist(), identity_map),
            missing_symbols=missing,
            benchmark_overlap_count=benchmark_overlap_count,
            constituent_total_returns=constituent_total_returns,
            constituent_annual_vol=constituent_annual_vol,
            constituent_max_drawdown=constituent_max_drawdown,
            warnings=list(dict.fromkeys([*warnings, *source_summary.warnings])),
            source_provider=source_summary.source_provider,
            history_source_label=source_summary.source_label,
            freshness_label=source_summary.freshness_label,
        )

    def analyze_strategy_lab(self, request: ImportedReturnStreamRequest) -> StrategyLabAnalysisResult:
        warnings: list[str] = [
            "Uploaded strategy returns are treated as data inputs only; Gamma does not execute strategy code."
        ]
        retrieved_at = now_utc()
        strategy_returns = self._returns_from_imported_rows(
            request.rows,
            date_column=request.date_column,
            value_column=request.value_column,
            value_kind=request.value_kind,
            label="Strategy",
            min_observations=request.min_observations,
            warnings=warnings,
        )

        benchmark_returns = pd.Series(dtype=float)
        if request.benchmark_column:
            try:
                benchmark_returns = self._returns_from_imported_rows(
                    request.rows,
                    date_column=request.date_column,
                    value_column=request.benchmark_column,
                    value_kind=request.benchmark_value_kind,
                    label="Benchmark",
                    min_observations=2,
                    warnings=warnings,
                )
            except ResearchValidationError as exc:
                warnings.extend(f"Benchmark column ignored: {message}" for message in exc.errors)

        if not benchmark_returns.empty:
            before_count = len(strategy_returns)
            aligned = strategy_returns.to_frame("strategy").join(
                benchmark_returns.to_frame("benchmark"),
                how="inner",
            ).dropna()
            if len(aligned) >= request.min_observations:
                strategy_returns = aligned["strategy"]
                benchmark_returns = aligned["benchmark"]
                if len(aligned) < before_count:
                    warnings.append(
                        f"Strategy and benchmark were aligned to {len(aligned)} shared observations."
                    )
            else:
                warnings.append("Benchmark overlap is too thin; benchmark-relative metrics are unavailable.")
                benchmark_returns = pd.Series(dtype=float)

        try:
            analysis = analyze_return_stream(
                strategy_returns,
                benchmark_returns=benchmark_returns if not benchmark_returns.empty else None,
                min_observations=request.min_observations,
            )
        except ValueError as exc:
            raise ResearchValidationError([str(exc)]) from exc

        return StrategyLabAnalysisResult(
            name=str(request.name or "").strip() or "Imported Strategy",
            value_kind=request.value_kind,
            benchmark_column=request.benchmark_column,
            benchmark_value_kind=request.benchmark_value_kind,
            returns=analysis.returns,
            equity_curve=analysis.equity_curve,
            drawdowns=analysis.drawdowns,
            benchmark_returns=benchmark_returns,
            benchmark_equity_curve=equity_curve_from_returns(benchmark_returns),
            metrics=analysis.metrics,
            rolling_points=analysis.rolling_points,
            monthly_returns=analysis.monthly_returns,
            annual_returns=analysis.annual_returns,
            warnings=list(dict.fromkeys(warnings)),
            source_provider="uploaded_csv",
            retrieved_at=retrieved_at,
            origin="research_service.strategy_lab.analyze",
            transformation_note=(
                "CSV rows are parsed into dated return streams, duplicates keep the last row per date, "
                "levels are converted with pct_change, and analytics assume a zero risk-free rate."
            ),
            freshness_label=FreshnessLabel.DERIVED.value,
        )

    def resolve_strategy_lab_handoff(
        self,
        request: StrategyLabHandoffResolveRequest,
        *,
        prediction_market_service: Any | None = None,
        commodities_service: Any | None = None,
    ) -> StrategyLabResolvedHandoff:
        handoff = request.handoff
        if handoff.intended_target_tab != "strategy_lab":
            raise ResearchValidationError(["Strategy Lab handoff resolver only accepts strategy_lab targets."])
        if handoff.source_tab == "macro":
            return self._resolve_macro_strategy_handoff(handoff)
        if handoff.source_tab in {"equity_research", "fundamentals"}:
            return self._resolve_equity_research_strategy_handoff(handoff)
        if handoff.source_tab == "commodities":
            if commodities_service is None:
                raise ResearchValidationError(["Commodities resolver is unavailable in this runtime."])
            return self._resolve_commodity_strategy_handoff(handoff, commodities_service)
        if handoff.source_tab == "iv":
            return self._resolve_iv_strategy_handoff(handoff)
        if handoff.source_tab != "prediction_markets":
            return StrategyLabResolvedHandoff(
                handoff_id=self._handoff_id(handoff),
                envelope=handoff,
                status="unsupported",
                resolved_capability="reference_only",
                warnings=list(handoff.warnings),
                unsupported_reason=f"No Strategy Lab resolver is available for source tab {handoff.source_tab}.",
            )
        if prediction_market_service is None:
            raise ResearchValidationError(["Prediction market resolver is unavailable in this runtime."])
        return self._resolve_prediction_market_strategy_handoff(handoff, prediction_market_service)

    def _resolve_iv_strategy_handoff(self, handoff) -> StrategyLabResolvedHandoff:
        metadata = dict(handoff.selected_entity.metadata or {})
        option_id = (
            handoff.normalized_ids.get("option_contract_id")
            or handoff.selected_entity.normalized_id
            or handoff.selected_entity.provider_id
            or handoff.selected_entity.native_id
        )
        option_id = str(option_id or "").strip()
        if not option_id:
            raise ResearchValidationError(["Options handoff is missing an option contract id."])

        symbol = str(metadata.get("symbol") or handoff.normalized_ids.get("symbol") or "").strip().upper()
        expiry = str(metadata.get("expiry") or handoff.normalized_ids.get("expiry") or "").strip()
        right = str(metadata.get("right") or handoff.normalized_ids.get("right") or "").strip().upper()
        label = str(handoff.selected_entity.label or option_id).strip() or option_id
        warnings = list(handoff.warnings)
        warnings.extend(
            [
                "Options handoff resolved as a Strategy Lab overlay for read-only volatility context.",
                "The selected option contract is not a weighted return leg because Gamma does not have durable contract price history in the current Options workspace.",
                "This overlay preserves chain row, IV, Greek, surface-quality, provider, and snapshot provenance only; it does not create orders, execution instructions, broker mutations, or rebalance rules.",
            ]
        )
        if handoff.resolver_capability != "overlay":
            return StrategyLabResolvedHandoff(
                handoff_id=self._handoff_id(handoff),
                envelope=handoff,
                status="unsupported",
                resolved_capability="reference_only",
                provider_summary=handoff.provider,
                provenance=self._iv_handoff_provenance(handoff, option_id),
                warnings=list(dict.fromkeys(warnings + ["Options handoffs currently resolve as overlays, not return legs."])),
                unsupported_reason="Options handoffs currently resolve as volatility/context overlays only.",
            )

        overlay = GammaResearchObject(
            object_id=f"iv:{option_id}",
            object_type="options_contract_overlay",
            display_name=label,
            source_tab="iv",
            source_mode=handoff.source_mode,
            resolver_capabilities=["overlay"],
            symbols=[symbol] if symbol else [],
            constituents=[
                {
                    "label": label,
                    "asset_class": "option",
                    "symbol": symbol or None,
                    "expiry": expiry or None,
                    "right": right or None,
                    "strike": metadata.get("strike"),
                    "spot": metadata.get("spot"),
                    "days_to_expiry": metadata.get("days_to_expiry"),
                    "premium": metadata.get("premium"),
                    "price_source": metadata.get("price_source"),
                    "implied_volatility": metadata.get("implied_volatility"),
                    "blended_implied_volatility": metadata.get("blended_implied_volatility"),
                    "delta": metadata.get("delta"),
                    "open_interest": metadata.get("open_interest"),
                    "volume": metadata.get("volume"),
                    "moneyness": metadata.get("moneyness"),
                    "distance_pct": metadata.get("distance_pct"),
                    "implied_move_pct": metadata.get("implied_move_pct"),
                    "snapshot_timestamp": metadata.get("snapshot_timestamp"),
                    "quality": metadata.get("quality"),
                }
            ],
            weights=[],
            available_start=handoff.selected_timeframe.start if handoff.selected_timeframe else None,
            available_end=handoff.selected_timeframe.end if handoff.selected_timeframe else None,
            provider_summary=handoff.provider,
            provenance=self._iv_handoff_provenance(handoff, option_id),
            warnings=list(dict.fromkeys(warnings)),
            return_points=[],
        )
        return StrategyLabResolvedHandoff(
            handoff_id=self._handoff_id(handoff),
            envelope=handoff,
            status="resolved",
            resolved_capability="overlay",
            overlay=overlay,
            date_coverage=handoff.selected_timeframe,
            provider_summary=handoff.provider,
            provenance=overlay.provenance,
            warnings=list(dict.fromkeys(warnings)),
        )

    def _resolve_macro_strategy_handoff(self, handoff) -> StrategyLabResolvedHandoff:
        lens_id = (
            handoff.normalized_ids.get("macro_lens_id")
            or handoff.selected_entity.normalized_id
            or handoff.selected_entity.native_id
        )
        lens_id = str(lens_id or "").strip()
        if not lens_id:
            raise ResearchValidationError(["Macro handoff is missing a lens id."])
        if handoff.resolver_capability != "lens":
            return StrategyLabResolvedHandoff(
                handoff_id=self._handoff_id(handoff),
                envelope=handoff,
                status="unsupported",
                resolved_capability="reference_only",
                provider_summary=handoff.provider,
                provenance=self._macro_handoff_provenance(handoff, lens_id),
                warnings=list(dict.fromkeys(handoff.warnings + ["Macro handoffs are Strategy Lab lenses, not weighted return legs."])),
                unsupported_reason="Macro handoffs currently resolve as lens/context objects only.",
            )

        metadata = dict(handoff.selected_entity.metadata or {})
        region = str(metadata.get("region") or handoff.normalized_ids.get("region") or "").strip()
        timeframe = str(metadata.get("timeframe") or handoff.normalized_ids.get("timeframe") or "").strip()
        theme = str(metadata.get("theme") or handoff.normalized_ids.get("theme") or "").strip()
        mode = str(handoff.source_mode or metadata.get("mode") or "").strip()
        label = str(handoff.selected_entity.label or "Macro lens").strip() or "Macro lens"
        warnings = list(handoff.warnings)
        warnings.extend(
            [
                "Macro handoff resolved as a Strategy Lab lens for read-only research context.",
                "Macro lenses annotate or filter interpretation; they are not weighted portfolio legs or executable strategy rules.",
                "Portfolio return math remains driven by selected return legs; this lens preserves macro regime, region, theme, timeframe, and provenance context.",
            ]
        )
        if region.lower() == "global":
            warnings.append("Global Macro remains a light V1 comparative lens with US-first coverage in some analytics.")
        if region.upper() == "EU":
            warnings.append("EU Macro coverage is structurally compatible but lighter than the US-first Macro implementation.")
        if not timeframe:
            warnings.append("Macro lens timeframe was not provided; Strategy Lab will keep it as context only.")

        provenance = self._macro_handoff_provenance(handoff, lens_id)
        lens = GammaResearchObject(
            object_id=f"macro:{lens_id}",
            object_type="macro_lens",
            display_name=label,
            source_tab="macro",
            source_mode=mode or None,
            resolver_capabilities=["lens"],
            symbols=[],
            constituents=[
                {
                    "label": label,
                    "asset_class": "macro",
                    "region": region or None,
                    "timeframe": timeframe or None,
                    "theme": theme or None,
                    "mode": mode or None,
                    "comparison_region": metadata.get("comparison_region"),
                }
            ],
            weights=[],
            available_start=handoff.selected_timeframe.start if handoff.selected_timeframe else None,
            available_end=handoff.selected_timeframe.end if handoff.selected_timeframe else None,
            provider_summary=handoff.provider,
            provenance=provenance,
            warnings=list(dict.fromkeys(warnings)),
            return_points=[],
        )
        return StrategyLabResolvedHandoff(
            handoff_id=self._handoff_id(handoff),
            envelope=handoff,
            status="resolved",
            resolved_capability="lens",
            lens=lens,
            date_coverage=handoff.selected_timeframe,
            provider_summary=handoff.provider,
            provenance=provenance,
            warnings=list(dict.fromkeys(warnings)),
        )

    def _resolve_equity_research_strategy_handoff(self, handoff) -> StrategyLabResolvedHandoff:
        symbol = (
            handoff.normalized_ids.get("symbol")
            or handoff.selected_entity.normalized_id
            or handoff.selected_entity.provider_id
            or handoff.selected_entity.native_id
        )
        symbol = str(symbol or "").strip().upper()
        if not symbol:
            raise ResearchValidationError(["Listed-equity handoff is missing a ticker symbol."])

        label = str(handoff.selected_entity.label or symbol).strip() or symbol
        warnings = list(handoff.warnings)
        warnings.extend(
            [
                f"{handoff.source_tab.replace('_', ' ').title()} handoff resolved to listed-market return history for read-only Strategy Lab analysis.",
                "Provider prices are converted to percentage returns; Gamma does not create orders or rebalance portfolios.",
            ]
        )
        research_object = self._listed_history_object(
            label=f"{label} equity return stream",
            identifier=symbol,
            asset_class="equity",
            lookback_days=756,
            min_observations=5,
            warnings=warnings,
            capabilities=["return_leg", "benchmark"],
        )
        points = list(research_object.return_points)
        if len(points) < 5:
            return StrategyLabResolvedHandoff(
                handoff_id=self._handoff_id(handoff),
                envelope=handoff,
                status="unsupported",
                resolved_capability="reference_only",
                provider_summary=research_object.provider_summary,
                provenance=self._equity_handoff_provenance(research_object, symbol),
                warnings=list(dict.fromkeys(warnings + ["Listed equity history is too sparse to create a return leg."])),
                unsupported_reason="Equity Research handoff needs at least five listed-market return observations.",
            )

        leg = StrategyLabPortfolioLeg(
            label=research_object.display_name,
            asset_class="equity",
            identifier=symbol,
            weight=float(handoff.default_weight if handoff.default_weight is not None else 0.1),
            value_kind="return",
            return_points=points,
            object=research_object,
        )
        return StrategyLabResolvedHandoff(
            handoff_id=self._handoff_id(handoff),
            envelope=handoff,
            status="resolved",
            resolved_capability="return_leg",
            composer_draft_leg=leg,
            date_coverage=CrossTabHandoffTimeframe(
                label="Listed return history",
                start=research_object.available_start,
                end=research_object.available_end,
            ),
            provider_summary=research_object.provider_summary,
            provenance=self._equity_handoff_provenance(research_object, symbol),
            warnings=list(dict.fromkeys(warnings + research_object.warnings)),
        )

    def _resolve_commodity_strategy_handoff(self, handoff, commodities_service: Any) -> StrategyLabResolvedHandoff:
        instrument_id = (
            handoff.normalized_ids.get("instrument_id")
            or handoff.selected_entity.normalized_id
            or handoff.selected_entity.provider_id
            or handoff.selected_entity.native_id
        )
        instrument_id = str(instrument_id or "").strip().lower()
        if not instrument_id:
            raise ResearchValidationError(["Commodity handoff is missing an instrument id."])

        workspace = commodities_service.get_workspace(
            CommodityWorkspaceRequest(mode="overview", selected_instrument_id=instrument_id)
        )
        resolved_id = str(getattr(workspace, "selected_instrument_id", instrument_id) or instrument_id)
        instrument = next(
            (row for row in getattr(workspace, "instruments", []) if getattr(row, "instrument_id", None) == resolved_id),
            None,
        )
        history = next(
            (row for row in getattr(workspace, "price_histories", []) if getattr(row, "instrument_id", None) == resolved_id),
            None,
        )
        summary = next(
            (
                row
                for row in getattr(workspace, "market_summaries", [])
                if getattr(getattr(row, "instrument", None), "instrument_id", None) == resolved_id
            ),
            None,
        )
        curve = next(
            (row for row in getattr(workspace, "curves", []) if getattr(row, "instrument_id", None) == resolved_id),
            None,
        )
        label = str(
            getattr(instrument, "name", None)
            or getattr(history, "label", None)
            or getattr(handoff.selected_entity, "label", None)
            or resolved_id.upper()
        ).strip()
        provider = (
            getattr(history, "source_provider", None)
            or getattr(instrument, "source_provider", None)
            or getattr(workspace, "source_provider", None)
            or handoff.provider
        )
        warnings = list(handoff.warnings)
        warnings.extend(
            [
                "Commodity handoff resolved for read-only Strategy Lab research only.",
                "Loaded commodity price history is treated as a spot/front-month/proxy level; it is not an executable futures PnL series.",
                "Strategy Lab converts commodity levels to percentage returns and does not claim roll-adjusted strategy performance.",
            ]
        )
        coverage = getattr(workspace, "coverage", None)
        coverage_status = str(getattr(coverage, "coverage_status", "") or "").lower()
        if coverage_status in {"sample", "mock", "official_partial", "partial", "unavailable"}:
            warnings.append(f"Commodity provider coverage is {coverage_status or 'limited'}; review source/proxy limitations.")
        warnings.extend(getattr(workspace, "warnings", []) or [])
        warnings.extend(getattr(summary, "warnings", []) or [])
        warnings.extend(getattr(curve, "warnings", []) or [])

        # The resolver re-reads the provider, which can answer with less than the
        # user was looking at: a cached IBKR curve skips the front-history fetch,
        # and a failed reference series leaves nothing behind it. The originating
        # tab therefore carries the series it had on screen, and whichever of the
        # two covers more of the visible window wins.
        reloaded_prices, reloaded_invalid = self._commodity_price_series(history)
        carried_series = getattr(handoff, "loaded_series", None)
        carried_history = (
            _CarriedSeriesHistory.from_series(carried_series)
            if carried_series is not None and carried_series.points
            else None
        )
        carried_prices, carried_invalid = self._commodity_price_series(carried_history)

        if len(carried_prices) > len(reloaded_prices):
            history_source = "handoff_payload"
            prices = carried_prices
            invalid_points = carried_invalid
            history = carried_history
            provider = carried_series.source_provider or provider
            warnings.append(
                f"Provider reload returned {len(reloaded_prices)} usable observation(s) for the "
                f"{len(carried_prices)} loaded in Commodities; Gamma used the series carried by the handoff."
            )
            if carried_series.contract_symbol:
                warnings.append(
                    f"Carried commodity series is the {carried_series.contract_symbol} basis shown in Commodities; "
                    "it is not roll-adjusted."
                )
        else:
            history_source = "provider_reload"
            prices = reloaded_prices
            invalid_points = reloaded_invalid
        if invalid_points:
            warnings.append(f"Dropped {invalid_points} commodity history point(s) with invalid timestamps or prices.")

        price_series = pd.Series(prices).sort_index().astype(float) if prices else pd.Series(dtype=float)
        returns = clean_return_series(price_series.pct_change().dropna())
        points = [
            ResearchObjectReturnPoint(timestamp=pd.Timestamp(index).isoformat(), value=float(value))
            for index, value in returns.items()
        ]
        if len(points) < 20:
            warnings.append("Commodity history is sparse; Strategy Lab analytics may be unstable.")
        self._append_commodity_staleness_warning(warnings, price_series, history, workspace)

        provenance = self._commodity_handoff_provenance(
            workspace=workspace,
            instrument=instrument,
            history=history,
            curve=curve,
            instrument_id=resolved_id,
            transformation="commodity_price_level_to_return_stream",
            return_points=len(points),
            history_source=history_source,
            carried_series=carried_series if history_source == "handoff_payload" else None,
        )
        if len(points) < 5:
            # A handoff that found nothing and one that found a stub are different
            # problems: the first is a data-availability failure the user can act
            # on, the second is a transformation limit.
            if not prices:
                sparse_warning = (
                    f"No commodity price history was available for {label} from "
                    f"{provider or 'the configured provider'}, and none was carried by the handoff."
                )
                unsupported_reason = (
                    "Commodity handoff found no price history to convert; the provider returned none and the "
                    "originating tab carried none."
                )
            else:
                sparse_warning = (
                    f"Commodity price history for {label} yielded {len(points)} return observation(s); "
                    "at least five are needed to create a return leg."
                )
                unsupported_reason = (
                    "Commodity handoff needs at least five computable return observations from price history."
                )
            return StrategyLabResolvedHandoff(
                handoff_id=self._handoff_id(handoff),
                envelope=handoff,
                status="unsupported",
                resolved_capability="reference_only",
                provider_summary=provider,
                provenance=provenance,
                warnings=list(dict.fromkeys(warnings + [sparse_warning])),
                unsupported_reason=unsupported_reason,
            )

        research_object = GammaResearchObject(
            object_id=f"commodities:{resolved_id}:return_stream:{points[0].timestamp}:{points[-1].timestamp}",
            object_type="commodity_return_stream",
            display_name=f"{label} commodity return stream",
            source_tab="commodities",
            source_mode=handoff.source_mode,
            resolver_capabilities=["return_leg", "benchmark"],
            symbols=[str(getattr(instrument, "symbol", resolved_id.upper()))],
            constituents=[
                {
                    "label": label,
                    "asset_class": "commodity",
                    "instrument_id": resolved_id,
                    "symbol": getattr(instrument, "symbol", None),
                    "family": getattr(instrument, "family", None),
                    "quote_unit": getattr(instrument, "quote_unit", None),
                }
            ],
            weights=[{"label": label, "asset_class": "commodity", "identifier": resolved_id, "weight": 1.0}],
            available_start=points[0].timestamp,
            available_end=points[-1].timestamp,
            provider_summary=provider,
            provenance=provenance,
            warnings=list(dict.fromkeys(warnings)),
            return_points=points,
        )
        leg = StrategyLabPortfolioLeg(
            label=research_object.display_name,
            asset_class="commodity",
            identifier=resolved_id,
            weight=float(handoff.default_weight if handoff.default_weight is not None else 0.1),
            value_kind="return",
            return_points=points,
            object=research_object,
        )
        return StrategyLabResolvedHandoff(
            handoff_id=self._handoff_id(handoff),
            envelope=handoff,
            status="resolved",
            resolved_capability="return_leg",
            composer_draft_leg=leg,
            date_coverage=CrossTabHandoffTimeframe(label="Commodity return history", start=points[0].timestamp, end=points[-1].timestamp),
            provider_summary=provider,
            provenance=provenance,
            warnings=list(dict.fromkeys(warnings)),
        )

    def _resolve_prediction_market_strategy_handoff(
        self,
        handoff,
        prediction_market_service: Any,
    ) -> StrategyLabResolvedHandoff:
        market_id = (
            handoff.normalized_ids.get("market_id")
            or handoff.selected_entity.normalized_id
            or handoff.selected_entity.provider_id
            or handoff.selected_entity.native_id
        )
        market_id = str(market_id or "").strip()
        if not market_id:
            raise ResearchValidationError(["Prediction-market handoff is missing a market id."])

        market = prediction_market_service.get_market_detail(market_id)
        if market is None:
            raise ResearchValidationError([f"Prediction market not found: {market_id}"])
        history = list(prediction_market_service.get_probability_history(market_id) or [])
        side = self._prediction_market_handoff_side(handoff.default_side)
        transformation = f"long_{side.lower()}_probability_return"
        warnings = list(handoff.warnings)
        warnings.extend(
            [
                f"Default Strategy Lab interpretation is {transformation}.",
                f"Prediction-market probability history is a research proxy for mark-to-market {side} exposure, not executable PnL.",
                "The resolver uses venue probability levels and leaves payout-aware contract accounting for a later pass.",
            ]
        )

        points: list[ResearchObjectReturnPoint] = []
        invalid_points = 0
        for point in history:
            probability = float(getattr(point, "probability", float("nan")))
            timestamp = getattr(point, "timestamp", None)
            if timestamp is None or not math.isfinite(probability):
                invalid_points += 1
                continue
            if probability < 0 or probability > 1:
                invalid_points += 1
                continue
            value = probability if side == "YES" else 1.0 - probability
            points.append(ResearchObjectReturnPoint(timestamp=timestamp.isoformat(), value=value))
        if invalid_points:
            warnings.append(f"Dropped {invalid_points} probability history point(s) with invalid timestamps or values.")

        points.sort(key=lambda point: point.timestamp)
        if len(points) < 2:
            return StrategyLabResolvedHandoff(
                handoff_id=self._handoff_id(handoff),
                envelope=handoff,
                status="unsupported",
                resolved_capability="reference_only",
                provider_summary=getattr(market, "source_provider", None),
                provenance=self._prediction_market_handoff_provenance(market, history, transformation=transformation),
                warnings=list(dict.fromkeys(warnings + ["Probability history is too sparse to create a return leg."])),
                unsupported_reason="Prediction-market handoff needs at least two probability history observations.",
            )
        if len(points) < 6:
            warnings.append("Probability history is sparse; Strategy Lab analytics may be unstable.")
        if any(point.value <= 0.02 for point in points[:3]):
            warnings.append(f"Initial {side} probability is near zero; percentage-return conversion can become unstable.")

        freshness = getattr(market, "freshness", None)
        if freshness is not None:
            if getattr(freshness, "is_stale", False) or getattr(freshness, "is_broken", False):
                reason = getattr(freshness, "reason", None)
                warnings.append(f"Market history freshness is {freshness.status}: {reason or 'review source timing.'}")
            elif getattr(freshness, "status", "") == "delayed":
                warnings.append("Market history is delayed relative to the latest venue snapshot.")

        status = str(getattr(market, "status", "") or "").lower()
        if status in {"closed", "resolved"} or any(getattr(outcome, "resolved", False) for outcome in getattr(market, "outcomes", [])):
            warnings.append("Contract is closed or resolved; use the handoff for historical research only.")
        days_to_resolution = self._days_to_resolution(getattr(market, "end_time", None), getattr(market, "retrieved_at", None))
        if days_to_resolution is not None and 0 <= days_to_resolution <= 3:
            warnings.append("Contract is near resolution; probability moves can be path-dependent and discontinuous.")

        start = points[0].timestamp
        end = points[-1].timestamp
        label = f"{getattr(market, 'title', None) or handoff.selected_entity.label} | {side} probability"
        provider = getattr(market, "source_provider", None) or handoff.provider or getattr(market, "venue", None)
        leg = StrategyLabPortfolioLeg(
            label=label,
            asset_class="prediction_contract",
            identifier=market_id,
            weight=float(handoff.default_weight if handoff.default_weight is not None else 0.1),
            value_kind="level",
            return_points=points,
            object=None,
        )
        return StrategyLabResolvedHandoff(
            handoff_id=self._handoff_id(handoff),
            envelope=handoff,
            status="resolved",
            resolved_capability="return_leg",
            composer_draft_leg=leg,
            date_coverage=CrossTabHandoffTimeframe(label="Probability history", start=start, end=end),
            provider_summary=provider,
            provenance=self._prediction_market_handoff_provenance(market, history, transformation=transformation),
            warnings=list(dict.fromkeys(warnings)),
        )

    @staticmethod
    def _prediction_market_handoff_side(default_side: str | None) -> str:
        normalized = str(default_side or "").strip().lower()
        if normalized == "long_no":
            return "NO"
        return "YES"

    @staticmethod
    def _prediction_market_handoff_provenance(market, history, *, transformation: str) -> dict[str, Any]:
        return {
            "source_provider": getattr(market, "source_provider", None),
            "venue": getattr(market, "venue", None),
            "market_id": getattr(market, "market_id", None),
            "provider_market_id": getattr(market, "provider_market_id", None),
            "provider_condition_id": getattr(market, "provider_condition_id", None),
            "retrieved_at": getattr(getattr(market, "retrieved_at", None), "isoformat", lambda: None)(),
            "origin": getattr(market, "origin", None),
            "history_points": len(history or []),
            "transformation": transformation,
        }

    @staticmethod
    def _equity_handoff_provenance(research_object: GammaResearchObject, symbol: str) -> dict[str, Any]:
        provenance = dict(research_object.provenance or {})
        provenance.update(
            {
                "symbol": symbol,
                "history_points": len(research_object.return_points or []),
                "transformation": "listed_equity_return_stream",
                "available_start": research_object.available_start,
                "available_end": research_object.available_end,
            }
        )
        return provenance

    @staticmethod
    def _macro_handoff_provenance(handoff, lens_id: str) -> dict[str, Any]:
        metadata = dict(handoff.selected_entity.metadata or {})
        source = dict(handoff.source or {})
        provenance = {
            "lens_id": lens_id,
            "region": metadata.get("region") or handoff.normalized_ids.get("region"),
            "timeframe": metadata.get("timeframe") or handoff.normalized_ids.get("timeframe"),
            "theme": metadata.get("theme") or handoff.normalized_ids.get("theme"),
            "mode": handoff.source_mode or metadata.get("mode"),
            "comparison_region": metadata.get("comparison_region"),
            "snapshot_focus_count": metadata.get("focus_count"),
            "snapshot_card_count": metadata.get("snapshot_card_count"),
            "divergence_count": metadata.get("divergence_count"),
            "event_count": metadata.get("event_count"),
            "next_event_title": metadata.get("next_event_title"),
            "next_event_at": metadata.get("next_event_at"),
            "source_provider": handoff.provider or source.get("source_provider"),
            "origin": source.get("origin"),
            "retrieved_at": source.get("retrieved_at"),
            "transformation": "macro_context_to_strategy_lab_lens",
            "interpretation": "Macro context is attached as a read-only lens and does not become a weighted return stream.",
        }
        return {key: value for key, value in provenance.items() if value is not None}

    @staticmethod
    def _iv_handoff_provenance(handoff, option_id: str) -> dict[str, Any]:
        metadata = dict(handoff.selected_entity.metadata or {})
        source = dict(handoff.source or {})
        quality = metadata.get("quality") if isinstance(metadata.get("quality"), dict) else {}
        provenance = {
            "source_provider": handoff.provider or source.get("source_provider"),
            "origin": source.get("origin"),
            "retrieved_at": source.get("retrieved_at"),
            "freshness_label": source.get("freshness_label") or metadata.get("freshness_label"),
            "market_data_mode": source.get("market_data_mode"),
            "depth_preset": source.get("depth_preset"),
            "symbol": metadata.get("symbol") or handoff.normalized_ids.get("symbol"),
            "option_contract_id": option_id,
            "provider_contract_id": handoff.normalized_ids.get("provider_contract_id") or handoff.selected_entity.provider_id,
            "expiry": metadata.get("expiry") or handoff.normalized_ids.get("expiry"),
            "right": metadata.get("right") or handoff.normalized_ids.get("right"),
            "strike": metadata.get("strike") or handoff.normalized_ids.get("strike"),
            "snapshot_timestamp": metadata.get("snapshot_timestamp"),
            "surface_model": metadata.get("surface_model"),
            "expected_surface_cells": quality.get("expected_surface_cells"),
            "observed_surface_cells": quality.get("observed_surface_cells"),
            "interpolated_surface_cells": quality.get("interpolated_surface_cells"),
            "interpolation_ratio": quality.get("interpolation_ratio"),
            "transformation": "options_chain_row_to_strategy_lab_overlay",
            "interpretation": "Options chain rows are attached as read-only volatility context; no option-contract return stream or executable order is created.",
        }
        return {key: value for key, value in provenance.items() if value not in (None, "")}

    def _commodity_price_series(self, history: Any) -> tuple[dict[pd.Timestamp, float], int]:
        prices: dict[pd.Timestamp, float] = {}
        invalid_points = 0
        for point in getattr(history, "points", []) if history is not None else []:
            timestamp = pd.to_datetime(getattr(point, "timestamp", None), errors="coerce")
            value = getattr(point, "value", None)
            try:
                price = float(value)
            except (TypeError, ValueError):
                invalid_points += 1
                continue
            if pd.isna(timestamp) or not math.isfinite(price) or price <= 0:
                invalid_points += 1
                continue
            prices[self._normalize_return_point_date(timestamp)] = price
        return prices, invalid_points

    @staticmethod
    def _commodity_handoff_provenance(
        *,
        workspace: Any,
        instrument: Any,
        history: Any,
        curve: Any,
        instrument_id: str,
        transformation: str,
        return_points: int,
        history_source: str = "provider_reload",
        carried_series: CrossTabHandoffSeries | None = None,
    ) -> dict[str, Any]:
        coverage = getattr(workspace, "coverage", None)
        history_points = list(getattr(history, "points", []) or [])
        latest_history_point: pd.Timestamp | None = None
        for point in history_points:
            timestamp = pd.to_datetime(getattr(point, "timestamp", None), errors="coerce")
            if pd.isna(timestamp):
                continue
            candidate = pd.Timestamp(timestamp)
            if latest_history_point is None or candidate > latest_history_point:
                latest_history_point = candidate

        carried_context = (
            {
                "carried_contract_symbol": carried_series.contract_symbol,
                "carried_unit": carried_series.unit,
                "carried_retrieved_at": carried_series.retrieved_at,
                "carried_origin": carried_series.origin,
            }
            if carried_series is not None
            else {}
        )

        return {
            **carried_context,
            "source_provider": getattr(history, "source_provider", None) or getattr(workspace, "source_provider", None),
            "coverage_status": getattr(coverage, "coverage_status", None),
            "provider_label": getattr(coverage, "provider_label", None),
            "instrument_id": instrument_id,
            "symbol": getattr(instrument, "symbol", None),
            "front_symbol": getattr(instrument, "front_symbol", None),
            "exchange": getattr(instrument, "exchange", None),
            "family": getattr(instrument, "family", None),
            "quote_unit": getattr(instrument, "quote_unit", None),
            "history_points": len(history_points),
            "history_source": history_source,
            "return_points": return_points,
            "latest_history_point": latest_history_point.isoformat() if latest_history_point is not None else None,
            "curve_shape": getattr(curve, "shape_label", None),
            "curve_nodes": len(getattr(curve, "nodes", []) or []),
            "origin": getattr(history, "origin", None) or getattr(workspace, "origin", None),
            "transformation": transformation,
            "interpretation": "Loaded commodity proxy levels are converted to returns; roll, storage, collateral, and execution costs are not modeled.",
        }

    @staticmethod
    def _append_commodity_staleness_warning(
        warnings: list[str],
        price_series: pd.Series,
        history: Any,
        workspace: Any,
    ) -> None:
        if price_series.empty:
            return
        latest = ensure_utc(pd.Timestamp(price_series.index[-1]).to_pydatetime())
        reference = (
            ensure_utc(getattr(history, "retrieved_at", None))
            or ensure_utc(getattr(workspace, "retrieved_at", None))
            or now_utc()
        )
        if latest is None:
            return
        age_days = (reference - latest).total_seconds() / 86400.0
        if age_days > 14:
            warnings.append(f"Latest commodity history point is stale by about {age_days:.0f} days versus retrieval time.")

    @staticmethod
    def _days_to_resolution(end_time: datetime | None, retrieved_at: datetime | None) -> float | None:
        normalized_end = ensure_utc(end_time)
        if normalized_end is None:
            return None
        reference = ensure_utc(retrieved_at) or now_utc()
        return (normalized_end - reference).total_seconds() / 86400.0

    @staticmethod
    def _handoff_id(handoff) -> str:
        entity_id = handoff.selected_entity.normalized_id or handoff.selected_entity.native_id or "unknown"
        timestamp = handoff.timestamp or now_utc().isoformat()
        return f"{handoff.source_tab}:{entity_id}:{timestamp}"

    def compose_strategy_lab(self, request: StrategyLabCompositionRequest) -> StrategyLabCompositionResult:
        warnings: list[str] = [
            "Strategy Lab compositions are read-only research runs; Gamma does not rebalance or modify broker portfolios."
        ]
        retrieved_at = now_utc()
        min_observations = max(int(request.min_observations), 2)
        for lens in request.lenses:
            if "lens" not in lens.resolver_capabilities:
                raise ResearchValidationError([f"{lens.display_name} cannot be used as a Strategy Lab lens."])
        for overlay in request.overlays:
            if "overlay" not in overlay.resolver_capabilities:
                raise ResearchValidationError([f"{overlay.display_name} cannot be used as a Strategy Lab overlay."])
        weighted_legs, normalized_weights = self._normalize_composition_weights(request.legs)
        if not weighted_legs:
            raise ResearchValidationError(["Strategy Lab composition requires at least one weighted return leg."])
        leg_series: dict[str, pd.Series] = {}
        leg_weight_map: dict[str, float] = {}
        leg_display_labels: dict[str, str] = {}
        leg_diagnostics: list[dict[str, Any]] = []
        emitted_labels: set[str] = set()
        for index, (leg, normalized_weight) in enumerate(zip(weighted_legs, normalized_weights, strict=True), start=1):
            if "return_leg" not in leg.object.resolver_capabilities:
                raise ResearchValidationError([f"{leg.object.display_name} cannot be used as a weighted return leg."])
            display_label = str(leg.object.display_name or leg.object.object_id or f"Leg {index}")
            contribution_label = self._unique_composition_label(display_label, emitted_labels)
            internal_key = f"{index}:{leg.object.object_id or display_label}"
            returns = self._returns_from_research_object(leg.object, label=display_label, warnings=warnings)
            if returns.empty:
                raise ResearchValidationError([f"{display_label} return stream is empty after cleaning."])
            leg_series[internal_key] = returns
            leg_weight_map[internal_key] = normalized_weight
            leg_display_labels[internal_key] = contribution_label
            leg_diagnostics.append(
                self._composition_leg_diagnostic(
                    leg.object,
                    label=contribution_label,
                    raw_weight=float(leg.weight),
                    normalized_weight=normalized_weight,
                    returns=returns,
                )
            )

        aligned = pd.DataFrame(leg_series).dropna(how="any")
        if len(aligned) < min_observations:
            raise ResearchValidationError(
                self._composition_alignment_failure_errors(
                    leg_diagnostics,
                    aligned_observations=len(aligned),
                    min_observations=min_observations,
                )
            )
        alignment_diagnostics: dict[str, Any] = {
            "min_observations": min_observations,
            "aligned_observation_count": int(len(aligned)),
            "aligned_start": self._series_boundary(aligned.index, first=True),
            "aligned_end": self._series_boundary(aligned.index, first=False),
            "legs": leg_diagnostics,
            "benchmark": None,
            "fail_closed": True,
        }
        weighted_columns = aligned.mul(pd.Series(leg_weight_map), axis="columns")
        composition_returns = weighted_columns.sum(axis="columns").astype(float)
        contribution_columns = weighted_columns
        risk_leg_returns = aligned

        benchmark_returns = pd.Series(dtype=float)
        benchmark_object = request.benchmark_object
        if benchmark_object is not None:
            if {"benchmark", "return_leg"}.isdisjoint(set(benchmark_object.resolver_capabilities)):
                warnings.append(f"{benchmark_object.display_name} is not return-resolvable as a benchmark.")
            else:
                candidate = self._returns_from_research_object(
                    benchmark_object,
                    label=benchmark_object.display_name or "Benchmark",
                    warnings=warnings,
                )
                alignment_diagnostics["benchmark"] = self._composition_leg_diagnostic(
                    benchmark_object,
                    label=benchmark_object.display_name or "Benchmark",
                    raw_weight=0.0,
                    normalized_weight=0.0,
                    returns=candidate,
                )
                benchmark_aligned = composition_returns.to_frame("strategy").join(
                    candidate.to_frame("benchmark"),
                    how="inner",
                ).dropna()
                if len(benchmark_aligned) >= min_observations:
                    composition_returns = benchmark_aligned["strategy"]
                    benchmark_returns = benchmark_aligned["benchmark"]
                    contribution_columns = weighted_columns.reindex(benchmark_aligned.index)
                    risk_leg_returns = aligned.reindex(benchmark_aligned.index)
                    alignment_diagnostics["benchmark_overlap_count"] = int(len(benchmark_aligned))
                    alignment_diagnostics["benchmark_overlap_start"] = self._series_boundary(
                        benchmark_aligned.index,
                        first=True,
                    )
                    alignment_diagnostics["benchmark_overlap_end"] = self._series_boundary(
                        benchmark_aligned.index,
                        first=False,
                    )
                else:
                    alignment_diagnostics["benchmark_overlap_count"] = int(len(benchmark_aligned))
                    warnings.append("Benchmark overlap is too thin; benchmark-relative metrics are unavailable.")

        leg_contributions = {
            leg_display_labels[key]: total_return_from_returns(contribution_columns[key].dropna()) or 0.0
            for key in contribution_columns.columns
        }
        diagnostics_by_key = dict(zip(leg_series, leg_diagnostics, strict=True))
        risk_legs = [
            ResearchBookRiskLeg(
                leg_id=key,
                label=leg_display_labels[key],
                symbol=str(
                    diagnostics_by_key[key].get("identifier")
                    or leg_display_labels[key]
                ).strip().upper(),
                instrument_id=str(
                    diagnostics_by_key[key].get("object_id")
                    or key
                ),
                weight=float(leg_weight_map[key]),
                return_points=[
                    ResearchObjectReturnPoint(timestamp=pd.Timestamp(timestamp).isoformat(), value=float(value))
                    for timestamp, value in risk_leg_returns[key].dropna().items()
                ],
                source_provider=(
                    str(diagnostics_by_key[key].get("source_provider"))
                    if diagnostics_by_key[key].get("source_provider")
                    else None
                ),
                warnings=list(diagnostics_by_key[key].get("warnings") or []),
            )
            for key in risk_leg_returns.columns
        ]

        try:
            analysis = analyze_return_stream(
                composition_returns,
                benchmark_returns=benchmark_returns if not benchmark_returns.empty else None,
                min_observations=min_observations,
            )
        except ValueError as exc:
            raise ResearchValidationError([str(exc)]) from exc

        return StrategyLabCompositionResult(
            name=str(request.name or "").strip() or "Gamma Research Composition",
            value_kind="return",
            benchmark_column=benchmark_object.display_name if benchmark_object is not None else None,
            benchmark_value_kind="return",
            returns=analysis.returns,
            equity_curve=analysis.equity_curve,
            drawdowns=analysis.drawdowns,
            benchmark_returns=benchmark_returns,
            benchmark_equity_curve=equity_curve_from_returns(benchmark_returns),
            metrics=analysis.metrics,
            rolling_points=analysis.rolling_points,
            monthly_returns=analysis.monthly_returns,
            annual_returns=analysis.annual_returns,
            warnings=list(dict.fromkeys(warnings)),
            source_provider="gamma_strategy_lab",
            retrieved_at=retrieved_at,
            origin="research_service.strategy_lab.compose",
            transformation_note=(
                "Weighted Gamma research objects are resolved to return streams, normalized by gross signed exposure, "
                "aligned on shared timestamps, and summed as a read-only research composition."
            ),
            freshness_label=FreshnessLabel.DERIVED.value,
            leg_contributions=leg_contributions,
            risk_legs=risk_legs,
            lenses=list(request.lenses),
            overlays=list(request.overlays),
            alignment_diagnostics=alignment_diagnostics,
        )

    def compose_strategy_lab_portfolio(
        self,
        request: StrategyLabPortfolioCompositionRequest,
    ) -> StrategyLabCompositionResult:
        warnings: list[str] = [
            "Strategy Lab portfolio compositions are read-only research runs; Gamma does not rebalance or modify broker portfolios.",
            "Portfolio leg weights are signed exposures normalized by gross exposure; negative weights represent short research legs.",
        ]
        min_observations = max(int(request.min_observations), 2)
        lookback_days = max(int(request.lookback_days), min_observations)
        composition_legs: list[StrategyLabCompositionLeg] = []
        for index, leg in enumerate(request.legs, start=1):
            weight = float(leg.weight)
            if not math.isfinite(weight):
                raise ResearchValidationError(["Portfolio leg weights must be finite signed values."])
            if weight == 0:
                continue
            research_object = self._research_object_from_portfolio_leg(
                leg,
                index=index,
                lookback_days=lookback_days,
                min_observations=min_observations,
                warnings=warnings,
            )
            composition_legs.append(StrategyLabCompositionLeg(object=research_object, weight=weight))

        if not composition_legs:
            raise ResearchValidationError(["Strategy Lab portfolio composition requires at least one non-zero leg."])

        benchmark_object = request.benchmark_object
        benchmark_symbol = str(request.benchmark_symbol or "").strip().upper()
        if benchmark_object is None and benchmark_symbol:
            benchmark_object = self._listed_history_object(
                label=f"{benchmark_symbol} Benchmark",
                identifier=benchmark_symbol,
                asset_class="benchmark",
                lookback_days=lookback_days,
                min_observations=min_observations,
                warnings=warnings,
                capabilities=["benchmark", "return_leg"],
            )

        result = self.compose_strategy_lab(
            StrategyLabCompositionRequest(
                name=str(request.name or "").strip() or "Strategy Lab Portfolio",
                legs=composition_legs,
                lenses=list(request.lenses),
                overlays=list(request.overlays),
                benchmark_object=benchmark_object,
                min_observations=min_observations,
            )
        )
        return StrategyLabCompositionResult(
            name=result.name,
            value_kind=result.value_kind,
            benchmark_column=result.benchmark_column,
            benchmark_value_kind=result.benchmark_value_kind,
            returns=result.returns,
            equity_curve=result.equity_curve,
            drawdowns=result.drawdowns,
            benchmark_returns=result.benchmark_returns,
            benchmark_equity_curve=result.benchmark_equity_curve,
            metrics=result.metrics,
            rolling_points=result.rolling_points,
            monthly_returns=result.monthly_returns,
            annual_returns=result.annual_returns,
            warnings=list(dict.fromkeys([*warnings, *result.warnings])),
            source_provider="gamma_strategy_lab",
            retrieved_at=result.retrieved_at,
            origin="research_service.strategy_lab.portfolio_compose",
            transformation_note=(
                "Strategy Lab portfolio legs resolve from Gamma objects, inline dated histories, or configured listed-market "
                "history providers. Leg returns are aligned on shared timestamps and combined as signed gross-normalized exposure."
            ),
            freshness_label=result.freshness_label,
            leg_contributions=result.leg_contributions,
            risk_legs=result.risk_legs,
            lenses=result.lenses,
            overlays=result.overlays,
            alignment_diagnostics=result.alignment_diagnostics,
        )

    def validate_strategy_lab_portfolio(
        self,
        request: StrategyLabPortfolioCompositionRequest,
    ) -> StrategyLabBookValidationResult:
        """Dry-run book validation: resolve every leg, report per-leg source/coverage
        diagnostics and shared-window alignment without computing performance metrics.
        Resolution failures are collected per leg instead of failing the whole check."""
        warnings: list[str] = [
            "Validate Book is a read-only pre-run check; it does not compose, persist, or execute anything.",
        ]
        errors: list[str] = []
        retrieved_at = now_utc()
        min_observations = max(int(request.min_observations), 2)
        lookback_days = max(int(request.lookback_days), min_observations)

        usable: list[tuple[str, float, pd.Series, GammaResearchObject]] = []
        leg_diagnostics: list[dict[str, Any]] = []
        emitted_labels: set[str] = set()
        for index, leg in enumerate(request.legs, start=1):
            label = str(leg.label or "").strip() or str(leg.identifier or "").strip() or f"Leg {index}"
            try:
                weight = float(leg.weight)
            except (TypeError, ValueError):
                errors.append(f"{label}: weight is not a number.")
                continue
            if not math.isfinite(weight):
                errors.append(f"{label}: weight must be a finite signed value.")
                continue
            if weight == 0:
                warnings.append(f"{label}: zero weight; the leg is excluded from the book.")
                continue
            try:
                research_object = self._research_object_from_portfolio_leg(
                    leg,
                    index=index,
                    lookback_days=lookback_days,
                    min_observations=min_observations,
                    warnings=warnings,
                )
            except ResearchValidationError as exc:
                errors.extend(f"{label}: {message}" for message in exc.errors)
                continue
            display_label = self._unique_composition_label(
                str(research_object.display_name or label), emitted_labels
            )
            returns = self._returns_from_research_object(research_object, label=display_label, warnings=warnings)
            if returns.empty:
                errors.append(f"{display_label}: return stream is empty after cleaning.")
                continue
            usable.append((display_label, weight, returns, research_object))

        gross_weight = sum(abs(weight) for _, weight, _, _ in usable)
        leg_series: dict[str, pd.Series] = {}
        for position, (display_label, weight, returns, research_object) in enumerate(usable, start=1):
            internal_key = f"{position}:{research_object.object_id or display_label}"
            leg_series[internal_key] = returns
            leg_diagnostics.append(
                self._composition_leg_diagnostic(
                    research_object,
                    label=display_label,
                    raw_weight=weight,
                    normalized_weight=(weight / gross_weight) if gross_weight > 0 else 0.0,
                    returns=returns,
                )
            )

        aligned = pd.DataFrame(leg_series).dropna(how="any") if leg_series else pd.DataFrame()
        aligned_count = int(len(aligned))
        if not usable:
            errors.append("The book has no usable return legs; add at least one non-zero resolvable leg.")
        elif aligned_count < min_observations:
            errors.extend(
                self._composition_alignment_failure_errors(
                    leg_diagnostics,
                    aligned_observations=aligned_count,
                    min_observations=min_observations,
                )
            )

        alignment_diagnostics: dict[str, Any] = {
            "min_observations": min_observations,
            "aligned_observation_count": aligned_count,
            "aligned_start": self._series_boundary(aligned.index, first=True) if aligned_count else None,
            "aligned_end": self._series_boundary(aligned.index, first=False) if aligned_count else None,
            "legs": leg_diagnostics,
            "benchmark": None,
            "fail_closed": True,
        }

        benchmark_object = request.benchmark_object
        benchmark_symbol = str(request.benchmark_symbol or "").strip().upper()
        if benchmark_object is None and benchmark_symbol:
            try:
                benchmark_object = self._listed_history_object(
                    label=f"{benchmark_symbol} Benchmark",
                    identifier=benchmark_symbol,
                    asset_class="benchmark",
                    lookback_days=lookback_days,
                    min_observations=min_observations,
                    warnings=warnings,
                    capabilities=["benchmark", "return_leg"],
                )
            except ResearchValidationError as exc:
                warnings.extend(f"Benchmark {benchmark_symbol}: {message}" for message in exc.errors)
                benchmark_object = None
        if benchmark_object is not None:
            benchmark_returns = self._returns_from_research_object(
                benchmark_object,
                label=benchmark_object.display_name or "Benchmark",
                warnings=warnings,
            )
            alignment_diagnostics["benchmark"] = self._composition_leg_diagnostic(
                benchmark_object,
                label=benchmark_object.display_name or "Benchmark",
                raw_weight=0.0,
                normalized_weight=0.0,
                returns=benchmark_returns,
            )
            if aligned_count:
                overlap = aligned.join(benchmark_returns.to_frame("__benchmark__"), how="inner").dropna()
                alignment_diagnostics["benchmark_overlap_count"] = int(len(overlap))
                if len(overlap) < min_observations:
                    warnings.append(
                        "Benchmark overlap with the aligned book window is too thin; "
                        "benchmark-relative metrics would be unavailable."
                    )

        return StrategyLabBookValidationResult(
            valid=not errors,
            errors=list(dict.fromkeys(errors)),
            warnings=list(dict.fromkeys(warnings)),
            usable_leg_count=len(usable),
            requested_leg_count=len(request.legs),
            aligned_observation_count=aligned_count,
            min_observations=min_observations,
            alignment_diagnostics=alignment_diagnostics,
            retrieved_at=retrieved_at,
        )

    @staticmethod
    def _composition_leg_diagnostic(
        research_object: GammaResearchObject,
        *,
        label: str,
        raw_weight: float,
        normalized_weight: float,
        returns: pd.Series,
    ) -> dict[str, Any]:
        provenance = dict(research_object.provenance)
        source_provider = provenance.get("source_provider") or research_object.provider_summary or research_object.source_tab
        return {
            "label": label,
            "object_id": research_object.object_id,
            "object_type": research_object.object_type,
            "source_provider": source_provider,
            "provider_summary": research_object.provider_summary,
            "origin": provenance.get("origin"),
            "asset_class": provenance.get("asset_class"),
            "identifier": provenance.get("identifier") or (research_object.symbols[0] if research_object.symbols else None),
            "raw_weight": raw_weight,
            "normalized_weight": normalized_weight,
            "observation_count": int(len(returns)),
            "available_start": ResearchService._series_boundary(returns.index, first=True),
            "available_end": ResearchService._series_boundary(returns.index, first=False),
            "warnings": list(research_object.warnings),
        }

    @staticmethod
    def _series_boundary(index: Any, *, first: bool) -> str | None:
        if len(index) == 0:
            return None
        value = index[0] if first else index[-1]
        return pd.Timestamp(value).isoformat()

    @staticmethod
    def _composition_alignment_failure_errors(
        leg_diagnostics: list[dict[str, Any]],
        *,
        aligned_observations: int,
        min_observations: int,
    ) -> list[str]:
        leg_summaries = []
        for diagnostic in leg_diagnostics:
            window = "no usable window"
            if diagnostic.get("available_start") and diagnostic.get("available_end"):
                window = f"{diagnostic['available_start']} to {diagnostic['available_end']}"
            leg_summaries.append(
                f"{diagnostic['label']} [{diagnostic.get('source_provider') or 'unknown'}] "
                f"{diagnostic['observation_count']} obs, {window}"
            )
        return [
            (
                f"Strategy Lab composition needs at least {min_observations} shared return observations; "
                f"only {aligned_observations} overlap after source alignment."
            ),
            "Alignment diagnostics: " + "; ".join(leg_summaries),
        ]

    @staticmethod
    def _normalize_composition_weights(
        legs: list[StrategyLabCompositionLeg],
    ) -> tuple[list[StrategyLabCompositionLeg], list[float]]:
        weighted_legs: list[StrategyLabCompositionLeg] = []
        raw_weights: list[float] = []
        for leg in legs:
            weight = float(leg.weight)
            if not math.isfinite(weight):
                raise ResearchValidationError(["Composition leg weights must be finite signed values."])
            if weight == 0:
                continue
            weighted_legs.append(leg)
            raw_weights.append(weight)
        gross_weight = sum(abs(weight) for weight in raw_weights)
        if gross_weight <= 0:
            return [], []
        return weighted_legs, [weight / gross_weight for weight in raw_weights]

    def _research_object_from_portfolio_leg(
        self,
        leg: StrategyLabPortfolioLeg,
        *,
        index: int,
        lookback_days: int,
        min_observations: int,
        warnings: list[str],
    ) -> GammaResearchObject:
        label = str(leg.label or "").strip() or str(leg.identifier or "").strip() or f"Portfolio Leg {index}"
        if leg.object is not None:
            if "return_leg" not in leg.object.resolver_capabilities:
                raise ResearchValidationError([f"{label} does not provide return-leg capability."])
            return leg.object
        if leg.return_points:
            returns = self._returns_from_portfolio_return_points(
                leg.return_points,
                value_kind=leg.value_kind,
                label=label,
                min_observations=min_observations,
                warnings=warnings,
            )
            return self._portfolio_leg_object_from_returns(
                label=label,
                asset_class=leg.asset_class,
                identifier=leg.identifier,
                returns=returns,
                source_provider="inline_history",
                provider_summary="Inline dated Strategy Lab history",
                origin="research_service.strategy_lab.portfolio.inline_history",
                warnings=[],
            )
        identifier = str(leg.identifier or "").strip().upper()
        if not identifier:
            raise ResearchValidationError([f"{label} needs an identifier or inline history."])
        return self._listed_history_object(
            label=label,
            identifier=identifier,
            asset_class=leg.asset_class,
            lookback_days=lookback_days,
            min_observations=min_observations,
            warnings=warnings,
            capabilities=["return_leg", "benchmark"],
        )

    def _listed_history_object(
        self,
        *,
        label: str,
        identifier: str,
        asset_class: str,
        lookback_days: int,
        min_observations: int,
        warnings: list[str],
        capabilities: list[str],
    ) -> GammaResearchObject:
        normalized_identifier = str(identifier or "").strip().upper()
        instrument = self._portfolio_leg_instrument(normalized_identifier, asset_class)
        result = self.provider.load_instrument_history_result(instrument, lookback_days)
        warnings.extend(result.warnings)
        series = result.series
        if series is None or series.empty:
            raise ResearchValidationError([f"{label} history is unavailable for {normalized_identifier}."])
        returns = compute_returns(align_prices({normalized_identifier: series.astype(float)}))[normalized_identifier]
        returns = clean_return_series(returns)
        if len(returns) < min_observations:
            raise ResearchValidationError(
                [f"{label} needs at least {min_observations} return observations from listed history."]
            )
        return self._portfolio_leg_object_from_returns(
            label=label,
            asset_class=asset_class,
            identifier=normalized_identifier,
            returns=returns,
            source_provider=result.source_provider,
            provider_summary=result.source_label,
            origin=result.origin,
            warnings=result.warnings,
        )

    @staticmethod
    def _portfolio_leg_instrument(identifier: str, asset_class: str) -> InstrumentReference:
        normalized_class = str(asset_class or "").strip().lower()
        sec_type = "FUT" if normalized_class in {"commodity", "future", "futures"} else "STK"
        return InstrumentReference(
            symbol=identifier,
            sec_type=sec_type,
            exchange="SMART",
            currency="USD",
            provider="strategy_lab",
        )

    @staticmethod
    def _returns_from_portfolio_return_points(
        points,
        *,
        value_kind: str,
        label: str,
        min_observations: int,
        warnings: list[str],
    ) -> pd.Series:
        records: list[tuple[pd.Timestamp, float]] = []
        invalid_dates = 0
        non_finite_values = 0
        for point in points:
            timestamp = pd.to_datetime(getattr(point, "timestamp", None), errors="coerce")
            value = float(getattr(point, "value", float("nan")))
            if pd.isna(timestamp):
                invalid_dates += 1
                continue
            if not math.isfinite(value):
                non_finite_values += 1
                continue
            records.append((ResearchService._normalize_return_point_date(timestamp), value))
        if invalid_dates:
            warnings.append(f"{label}: dropped {invalid_dates} inline points with invalid timestamps.")
        if non_finite_values:
            warnings.append(f"{label}: dropped {non_finite_values} inline points with non-finite values.")
        if not records:
            raise ResearchValidationError([f"{label} has no valid inline dated observations."])
        frame = pd.DataFrame(records, columns=["date", "value"]).sort_values("date")
        duplicate_count = int(frame.duplicated("date", keep=False).sum())
        if duplicate_count:
            warnings.append(f"{label}: duplicate inline timestamps detected; keeping the last point per date.")
            frame = frame.drop_duplicates("date", keep="last")
        series = pd.Series(frame["value"].to_numpy(dtype=float), index=pd.to_datetime(frame["date"]))
        if str(value_kind or "return").strip().lower() == "level":
            levels = series
            non_positive = int((levels <= 0).sum())
            if non_positive:
                warnings.append(f"{label}: dropped {non_positive} non-positive level observations before return conversion.")
                levels = levels[levels > 0]
            series = levels.pct_change().dropna()
        elif str(value_kind or "return").strip().lower() != "return":
            raise ResearchValidationError([f"Unsupported {label.lower()} value interpretation: {value_kind}"])
        series = clean_return_series(series)
        if len(series) < min_observations:
            raise ResearchValidationError([f"{label} needs at least {min_observations} inline return observations."])
        return series

    @staticmethod
    def _normalize_return_point_date(timestamp: Any) -> pd.Timestamp:
        normalized = pd.Timestamp(timestamp)
        if normalized.tzinfo is not None:
            normalized = normalized.tz_convert("UTC").tz_localize(None)
        return normalized.normalize()

    @staticmethod
    def _portfolio_leg_object_from_returns(
        *,
        label: str,
        asset_class: str,
        identifier: str,
        returns: pd.Series,
        source_provider: str,
        provider_summary: str,
        origin: str,
        warnings: list[str],
    ) -> GammaResearchObject:
        clean = clean_return_series(returns)
        points = [
            ResearchObjectReturnPoint(timestamp=pd.Timestamp(index).isoformat(), value=float(value))
            for index, value in clean.items()
        ]
        start = points[0].timestamp if points else None
        end = points[-1].timestamp if points else None
        normalized_identifier = str(identifier or label).strip().upper()
        normalized_class = str(asset_class or "custom").strip().lower() or "custom"
        return GammaResearchObject(
            object_id=f"strategy_portfolio_leg:{normalized_class}:{normalized_identifier}:{start}:{end}",
            object_type=f"{normalized_class}_portfolio_leg",
            display_name=label,
            source_tab="strategy_lab",
            source_mode="composer",
            resolver_capabilities=["return_leg", "benchmark"],
            symbols=[normalized_identifier] if normalized_identifier else [],
            constituents=[{"label": label, "asset_class": normalized_class, "identifier": normalized_identifier}],
            weights=[{"label": label, "asset_class": normalized_class, "identifier": normalized_identifier, "weight": 1.0}],
            available_start=start,
            available_end=end,
            provider_summary=provider_summary,
            provenance={
                "source_provider": source_provider,
                "origin": origin,
                "asset_class": normalized_class,
                "identifier": normalized_identifier,
            },
            warnings=list(warnings),
            return_points=points,
        )

    @staticmethod
    def _unique_composition_label(base_label: str, emitted_labels: set[str]) -> str:
        base = str(base_label or "").strip() or "Research Object"
        candidate = base
        suffix = 2
        while candidate in emitted_labels:
            candidate = f"{base} ({suffix})"
            suffix += 1
        emitted_labels.add(candidate)
        return candidate

    def compare_research(self, request: ResearchComparisonRequest) -> ResearchComparisonResult:
        warnings: list[str] = [
            "Compare / Scenario is historical analytics only; it does not rebalance or modify broker portfolios."
        ]
        retrieved_at = now_utc()
        left_label, left_type, left_returns = self._resolve_comparison_leg(request.left, warnings)
        right_label, right_type, right_returns = self._resolve_comparison_leg(request.right, warnings)
        try:
            comparison = compare_return_streams(left_label, left_type, left_returns, right_label, right_type, right_returns)
        except ValueError as exc:
            raise ResearchValidationError([str(exc)]) from exc
        warnings.extend(comparison.warnings)
        return ResearchComparisonResult(
            comparison=comparison,
            warnings=list(dict.fromkeys(warnings)),
            source_provider="gamma_research",
            retrieved_at=retrieved_at,
            origin="research_service.compare_scenario.analyze",
            transformation_note=(
                "Inputs are normalized to return streams, aligned on common timestamps, and rebased to a starting "
                "NAV of 1.0 for comparison. Scenario output is analytical and read-only."
            ),
            freshness_label=FreshnessLabel.DERIVED.value,
        )

    def list_saved_research(self) -> list[SavedResearchItem]:
        return self._saved_store().list_items()

    def load_saved_research(self, item_id: str) -> SavedResearchItem | None:
        return self._saved_store().load_item(item_id)

    def save_research(self, request: SavedResearchCreateRequest) -> SavedResearchItem:
        return self._saved_store().create_item(request)

    def delete_saved_research(self, item_id: str) -> bool:
        return self._saved_store().delete_item(item_id)

    def _overview_benchmark_returns(
        self,
        benchmark_symbol: str,
        lookback_days: int,
        warnings: list[str],
        *,
        provider_policy: str | None = None,
        force_refresh: bool = False,
        cache_seconds: int | None = None,
    ) -> pd.Series:
        base_currency = str(getattr(self.provider, "base_currency", "USD") or "USD").upper()
        try:
            benchmark_history = self.provider.load_benchmark_history(
                benchmark_symbol,
                lookback_days,
                base_currency=base_currency,
                warnings=warnings,
                provider_policy=provider_policy,
                bypass_cache=force_refresh,
                max_age_seconds=cache_seconds,
            )
        except TypeError:
            benchmark_history = self.provider.load_benchmark_history(benchmark_symbol, lookback_days)
        return returns_from_price_series(benchmark_history, lookback_days)

    def _load_overview_history(
        self,
        reference: InstrumentReference,
        lookback_days: int,
        *,
        provider_policy: str | None = None,
        force_refresh: bool = False,
        cache_seconds: int | None = None,
    ) -> ResearchHistoryResult:
        loader = getattr(self.provider, "load_instrument_history_result", None)
        if callable(loader):
            return loader(
                reference,
                lookback_days,
                provider_policy=provider_policy,
                bypass_cache=force_refresh,
                max_age_seconds=cache_seconds,
            )
        series = self.provider.load_instrument_history(reference, lookback_days)
        source_provider = self._overview_source_provider()
        return ResearchHistoryResult(
            series=series,
            source_provider=source_provider,
            source_label=self._overview_history_source_label(source_provider),
            origin="research_service.overview.compat_history_loader",
            freshness_label=FreshnessLabel.MOCKED if source_provider == "mock" else FreshnessLabel.HISTORICAL,
        )

    def _provider_history_source_summary(
        self,
        default_source_provider: str,
        default_source_label: str,
        default_freshness_label: FreshnessLabel,
    ) -> ResearchHistoryResult:
        summary = getattr(self.provider, "history_source_summary", None)
        if callable(summary):
            row = summary()
            if row.source_provider != "unknown":
                return row
        return ResearchHistoryResult(
            series=None,
            source_provider=default_source_provider,
            source_label=default_source_label,
            origin="research_service.history_source_summary",
            freshness_label=default_freshness_label,
        )

    @staticmethod
    def _history_results_source_summary(
        rows: list[ResearchHistoryResult],
        default_source_provider: str,
        default_source_label: str,
        default_freshness_label: FreshnessLabel,
    ) -> ResearchHistoryResult:
        usable = [row for row in rows if row.series is not None and not row.series.empty]
        if not usable:
            return ResearchHistoryResult(
                series=None,
                source_provider=default_source_provider,
                source_label=default_source_label,
                origin="research_service.history_results_summary",
                freshness_label=default_freshness_label,
            )
        providers = sorted({row.source_provider for row in usable})
        if len(providers) == 1:
            representative = usable[0]
            return replace(representative, series=None, warnings=[])
        labels = sorted({row.source_label for row in usable})
        return ResearchHistoryResult(
            series=None,
            source_provider="mixed",
            source_label=f"Mixed listed-market history providers: {', '.join(labels)}",
            origin="research_service.history_results_summary",
            freshness_label=FreshnessLabel.HISTORICAL,
            warnings=["Scope uses more than one listed-market history provider."],
            transformation_note="Gamma selected the first configured provider with usable daily history for each instrument.",
        )

    @staticmethod
    def _overview_provider_policy(value: str | None) -> str:
        normalized = str(value or "").strip().lower().replace("-", "_")
        if normalized in {"sitrep", "situation_report"}:
            return "sitrep"
        return "research_overview"

    def _overview_cache_seconds(self, provider_policy: str) -> int:
        mapping = getattr(self.provider, "history_cache_seconds_by_policy", {}) or {}
        try:
            return max(0, int(mapping.get(provider_policy, 0) or 0))
        except Exception:
            return 0

    def _overview_cache_key(
        self,
        provider_policy: str,
        universe_id: str,
        timeframe: str,
        benchmark_symbol: str,
    ) -> tuple[str, str, str, str, str]:
        base_currency = str(getattr(self.provider, "base_currency", "USD") or "USD").upper()
        return (provider_policy, universe_id, timeframe, benchmark_symbol, base_currency)

    def _get_cached_overview(
        self,
        cache_key: tuple[str, str, str, str, str],
        cache_seconds: int,
        *,
        force_refresh: bool,
    ) -> ResearchOverviewResult | None:
        if force_refresh or cache_seconds <= 0:
            return None
        cached = self._overview_cache.get(cache_key)
        if cached is None:
            return None
        age_seconds = (now_utc() - cached.retrieved_at).total_seconds()
        if age_seconds > cache_seconds:
            self._overview_cache.pop(cache_key, None)
            return None
        return cached

    def _saved_store(self) -> SavedResearchStore:
        if self.saved_store is None:
            self.saved_store = SavedResearchStore()
        return self.saved_store

    def _resolve_comparison_leg(
        self,
        leg: ResearchComparisonLeg,
        warnings: list[str],
    ) -> tuple[str, str, pd.Series]:
        if leg.saved_research_id:
            saved = self.load_saved_research(leg.saved_research_id)
            if saved is None:
                raise ResearchValidationError([f"Saved research item not found: {leg.saved_research_id}"])
            label = leg.label or saved.title
            series = self._return_series_from_saved_payload(saved)
            if series.empty:
                raise ResearchValidationError([f"Saved research item has no reusable return stream: {saved.title}"])
            return label, saved.object_type, series

        series = clean_return_series(leg.returns)
        if series.empty:
            raise ResearchValidationError([f"Comparison leg has no return stream: {leg.label or leg.object_type}"])
        return leg.label or leg.object_type or "Research Object", leg.object_type or "research_object", series

    @staticmethod
    def _return_series_from_saved_payload(saved: SavedResearchItem) -> pd.Series:
        payload = saved.payload or {}
        candidates: list[dict[str, Any]] = [payload]
        for key in ("result", "strategy_result", "analysis", "payload"):
            value = payload.get(key)
            if isinstance(value, dict):
                candidates.append(value)
        for candidate in candidates:
            for key in ("returns_points", "return_points", "performance_points", "portfolio_return_points"):
                points = candidate.get(key)
                series = ResearchService._points_to_return_series(points)
                if not series.empty:
                    return series
        return pd.Series(dtype=float)

    @staticmethod
    def _points_to_return_series(points: Any) -> pd.Series:
        if not isinstance(points, list):
            return pd.Series(dtype=float)
        values: dict[pd.Timestamp, float] = {}
        for point in points:
            if not isinstance(point, dict):
                continue
            timestamp = pd.to_datetime(point.get("timestamp"), errors="coerce")
            value = ResearchService._parse_imported_number(point.get("value"))
            if pd.isna(timestamp) or value is None:
                continue
            values[pd.Timestamp(timestamp).to_pydatetime()] = float(value)
        if not values:
            return pd.Series(dtype=float)
        return pd.Series(values).sort_index().astype(float)

    @staticmethod
    def _returns_from_research_object(
        research_object: GammaResearchObject,
        *,
        label: str,
        warnings: list[str],
    ) -> pd.Series:
        records: list[tuple[pd.Timestamp, float]] = []
        invalid_timestamps = 0
        invalid_values = 0
        non_finite_values = 0
        for point in research_object.return_points:
            timestamp = pd.to_datetime(point.timestamp, errors="coerce")
            value = ResearchService._parse_imported_number(point.value)
            if pd.isna(timestamp):
                invalid_timestamps += 1
                continue
            if value is None:
                invalid_values += 1
                continue
            if not math.isfinite(value):
                non_finite_values += 1
                continue
            records.append((ResearchService._normalize_return_point_date(timestamp), value))
        if invalid_timestamps:
            warnings.append(f"{label}: dropped {invalid_timestamps} return points with invalid timestamps.")
        if invalid_values:
            warnings.append(f"{label}: dropped {invalid_values} return points with missing or invalid values.")
        if non_finite_values:
            if non_finite_values == 1:
                warnings.append(f"{label}: dropped return point with non-finite value.")
            else:
                warnings.append(f"{label}: dropped {non_finite_values} return points with non-finite values.")
        if not records:
            return pd.Series(dtype=float)
        frame = pd.DataFrame(records, columns=["date", "value"]).sort_values("date")
        duplicate_count = int(frame.duplicated("date", keep=False).sum())
        if duplicate_count:
            warnings.append(f"{label}: duplicate return timestamps detected; keeping the last point per date.")
            frame = frame.drop_duplicates("date", keep="last")
        values = pd.Series(frame["value"].to_numpy(dtype=float), index=pd.to_datetime(frame["date"]))
        return clean_return_series(values)

    @staticmethod
    def _returns_from_imported_rows(
        rows: list[dict[str, Any]],
        *,
        date_column: str,
        value_column: str,
        value_kind: str,
        label: str,
        min_observations: int,
        warnings: list[str],
    ) -> pd.Series:
        if not rows:
            raise ResearchValidationError(["CSV import contains no rows."])
        if not str(date_column or "").strip():
            raise ResearchValidationError(["Date column is required."])
        if not str(value_column or "").strip():
            raise ResearchValidationError([f"{label} value column is required."])

        records: list[tuple[pd.Timestamp, float]] = []
        invalid_dates = 0
        missing_values = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            timestamp = pd.to_datetime(row.get(date_column), errors="coerce")
            value = ResearchService._parse_imported_number(row.get(value_column))
            if pd.isna(timestamp):
                invalid_dates += 1
                continue
            if value is None:
                missing_values += 1
                continue
            records.append((ResearchService._normalize_return_point_date(timestamp), value))

        if invalid_dates:
            warnings.append(f"{label}: dropped {invalid_dates} rows with invalid dates.")
        if missing_values:
            warnings.append(f"{label}: dropped {missing_values} rows with missing or invalid values.")
        if not records:
            raise ResearchValidationError([f"{label} has no valid dated observations."])

        frame = pd.DataFrame(records, columns=["date", "value"]).sort_values("date")
        duplicate_count = int(frame.duplicated("date", keep=False).sum())
        if duplicate_count:
            warnings.append(f"{label}: duplicate dates detected; keeping the last row per date.")
            frame = frame.drop_duplicates("date", keep="last")
        values = pd.Series(frame["value"].to_numpy(dtype=float), index=pd.to_datetime(frame["date"]))
        kind = str(value_kind or "return").strip().lower()
        if kind == "level":
            non_positive = int((values <= 0).sum())
            if non_positive:
                warnings.append(f"{label}: dropped {non_positive} non-positive level observations before return conversion.")
                values = values[values > 0]
            returns = values.pct_change().dropna()
        elif kind == "return":
            returns = values
        else:
            raise ResearchValidationError([f"Unsupported {label.lower()} value interpretation: {value_kind}"])

        returns = clean_return_series(returns)
        if returns.empty:
            raise ResearchValidationError([f"{label} return stream is empty after cleaning."])
        if len(returns) < min_observations:
            raise ResearchValidationError([f"{label} needs at least {min_observations} return observations."])

        if kind == "return":
            whole_percent_like = int((returns.abs() > 1.0).sum())
            if whole_percent_like:
                warnings.append(
                    f"{label}: {whole_percent_like} return observations exceed +/-100%; if the CSV uses whole percentages, append % or divide by 100."
                )
            elif float(returns.abs().median()) > 0.20:
                warnings.append(
                    f"{label}: median absolute return exceeds 20%; inspect whether whole percentages were supplied as decimals."
                )

        outlier_count = int((returns.abs() > OUTLIER_ABS_RETURN_THRESHOLD).sum())
        if outlier_count:
            warnings.append(
                f"{label}: {outlier_count} observations exceed +/-{OUTLIER_ABS_RETURN_THRESHOLD:.0%}; inspect for percent/decimal mapping errors."
            )
        return returns

    @staticmethod
    def _parse_imported_number(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            numeric = float(value)
            return numeric if pd.notna(numeric) else None
        raw = str(value).strip()
        if not raw:
            return None
        is_percent = raw.endswith("%")
        raw = raw.rstrip("%").replace(",", "")
        try:
            numeric = float(raw)
        except ValueError:
            return None
        if not pd.notna(numeric):
            return None
        return numeric / 100.0 if is_percent else numeric

    @staticmethod
    def _overview_universe(
        universe_id: str | None,
        warnings: list[str],
    ) -> ResearchOverviewUniverse:
        normalized = str(universe_id or "").strip().lower() or "broad_us_market"
        for universe in RESEARCH_OVERVIEW_UNIVERSES:
            if universe.universe_id == normalized:
                return universe
        warnings.append(f"Unknown Research Overview universe '{universe_id}'; using Broad US Market.")
        return RESEARCH_OVERVIEW_UNIVERSES[0]

    @staticmethod
    def _overview_timeframe(timeframe: str | None, warnings: list[str]) -> str:
        raw = str(timeframe or "").strip()
        if not raw:
            return "DoD"
        if raw in RESEARCH_OVERVIEW_TIMEFRAMES:
            return raw
        normalized = raw.upper()
        if normalized in RESEARCH_OVERVIEW_TIMEFRAMES:
            return normalized
        warnings.append(f"Unknown Research Overview timeframe '{timeframe}'; using Day over day.")
        return "DoD"

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
    def _overview_history_source_label(source_provider: str) -> str:
        if source_provider == "mock":
            return "Mock sample-data daily history"
        if source_provider == "ibkr":
            return "IBKR/TWS daily historical bars"
        if source_provider == "yfinance":
            return "Yahoo Finance/yfinance daily history"
        if source_provider == "mixed":
            return "Mixed listed-market history providers"
        if source_provider == "research_cache":
            return "Research history cache"
        return f"{source_provider} daily history"

    @staticmethod
    def _overview_observation_range(observation_counts: dict[str, int]) -> tuple[int, int]:
        if not observation_counts:
            return 0, 0
        values = list(observation_counts.values())
        return int(min(values)), int(max(values))

    @staticmethod
    def _overview_group_id(group: str) -> str:
        slug = str(group or "Ungrouped").strip().lower().replace("&", "and")
        slug = "_".join(part for part in slug.replace("/", " ").split() if part)
        return f"group:{slug or 'ungrouped'}"

    @staticmethod
    def _overview_node_size(instrument: ResearchOverviewUniverseInstrument) -> float:
        for candidate in (instrument.market_cap_usd, instrument.index_weight, instrument.weight):
            if candidate is not None and float(candidate) > 0:
                return float(candidate)
        return 1.0

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
            market_cap_usd=instrument.market_cap_usd,
            index_weight=instrument.index_weight,
            sort_rank=instrument.sort_rank,
            size=self._overview_node_size(instrument),
            metrics=metrics,
            source_provider=source_provider,
            retrieved_at=retrieved_at,
            origin="research_service.overview.instrument",
            transformation_note=(
                f"Computed from daily close history over {timeframe}. Tile sizing uses static market-cap proxy "
                "metadata when present and falls back to universe weight."
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
            group_market_cap = sum(float(row.market_cap_usd or 0.0) for row in rows) or None
            group_index_weight = sum(float(row.index_weight or 0.0) for row in rows) or None
            priced_count = sum(1 for symbol in symbols if symbol in returns_by_symbol)
            if group_returns.empty:
                warnings = ["No priced constituents are available for this group."]
            elif priced_count < len(rows):
                missing_count = len(rows) - priced_count
                warnings = [
                    f"Group uses {priced_count}/{len(rows)} priced constituents; {missing_count} constituent(s) lack usable history."
                ]
            else:
                warnings = []
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
                    market_cap_usd=group_market_cap,
                    index_weight=group_index_weight,
                    sort_rank=None,
                    size=group_market_cap or group_index_weight or group_weight or float(len(rows) or 1),
                    metrics=metrics,
                    source_provider=source_provider,
                    retrieved_at=retrieved_at,
                    origin="research_service.overview.group",
                    transformation_note=(
                        f"Computed as a weighted return stream from available {group} constituents over {timeframe}. "
                        "This is a seed/watchlist group, not complete market or sector coverage."
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
        primary_price_ohlcv: pd.DataFrame | None = None,
        perf: pd.Series | None = None,
        available_symbols: list[str] | None = None,
        missing_symbols: list[str] | None = None,
        source_provider: str = "unknown",
        history_source_label: str = "Unknown history source",
        freshness_label: FreshnessLabel = FreshnessLabel.UNKNOWN,
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
            primary_price_ohlcv=primary_price_ohlcv,
            available_symbols=list(available_symbols or []),
            missing_symbols=list(missing_symbols or []),
            benchmark_overlap_count=0,
            constituent_total_returns=pd.Series(dtype=float),
            constituent_annual_vol=pd.Series(dtype=float),
            constituent_max_drawdown=pd.Series(dtype=float),
            warnings=warnings,
            source_provider=source_provider,
            history_source_label=history_source_label,
            freshness_label=freshness_label,
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
