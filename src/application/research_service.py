from __future__ import annotations

from dataclasses import dataclass, field
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
from src.application.instrument_identity import find_identity_by_symbol, snapshot_identity_map
from src.application.research_validation import ResearchValidationError, ensure_valid_research_scope
from src.models.app_mode import ResearchScopeType, SyntheticPosition
from src.models.instruments import InstrumentDefaults, InstrumentReference
from src.models.portfolio import PortfolioSnapshot
from src.models.provenance import FreshnessLabel
from src.models.research_lab import (
    ImportedReturnStreamRequest,
    ResearchComparisonLeg,
    ResearchComparisonRequest,
    ResearchComparisonResult,
    SavedResearchCreateRequest,
    SavedResearchItem,
    StrategyLabAnalysisResult,
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
from src.services.saved_research_store import SavedResearchStore
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
    def __init__(self, provider: ResearchDataProvider, saved_store: SavedResearchStore | None = None) -> None:
        self.provider = provider
        self.saved_store = saved_store

    def overview(self, request: ResearchOverviewRequest) -> ResearchOverviewResult:
        warnings: list[str] = []
        retrieved_at = now_utc()
        universe = self._overview_universe(request.universe_id, warnings)
        timeframe = self._overview_timeframe(request.timeframe, warnings)
        lookback_days = RESEARCH_OVERVIEW_TIMEFRAMES[timeframe]
        benchmark_symbol = str(request.benchmark_symbol or "").strip().upper() or "SPY"
        source_provider = self._overview_source_provider()
        history_source_label = self._overview_history_source_label(source_provider)
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
        thin_history_symbols: list[str] = []
        observation_counts: dict[str, int] = {}

        for instrument in universe.instruments:
            reference = self._overview_reference(instrument)
            symbol = instrument.normalized_symbol()
            series = self.provider.load_instrument_history(reference, lookback_days)
            returns = returns_from_price_series(series, lookback_days)
            node_warnings: list[str] = []
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
            records.append((pd.Timestamp(timestamp).normalize(), value))

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
