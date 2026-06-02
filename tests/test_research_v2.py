from __future__ import annotations

import json
import math
from types import SimpleNamespace
from datetime import datetime, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.research_service import ResearchService
from src.application.runtime import build_runtime
from src.application.research_validation import ResearchValidationError
from src.api.schemas.research import GammaResearchObjectModel
from src.models.research_lab import (
    GammaResearchObject,
    CrossTabHandoffEntity,
    ImportedReturnStreamRequest,
    ResearchComparisonLeg,
    ResearchComparisonRequest,
    ResearchObjectReturnPoint,
    SavedResearchCreateRequest,
    StrategyLabCompositionLeg,
    StrategyLabCompositionRequest,
    StrategyLabHandoffEnvelope,
    StrategyLabHandoffResolveRequest,
    StrategyLabPortfolioCompositionRequest,
    StrategyLabPortfolioLeg,
)
from src.models.prediction_markets import PredictionMarketFreshness, PredictionMarketRecord, PredictionProbabilityPoint
from src.models.provenance import FreshnessLabel
from src.services.research_market_data import ResearchHistoryResult
from src.services.saved_research_store import SavedResearchStore


def _service(tmp_path) -> ResearchService:
    return ResearchService(SimpleNamespace(), saved_store=SavedResearchStore(tmp_path / "research"))


class StubListedHistoryProvider:
    def load_instrument_history_result(self, instrument, lookback_days: int) -> ResearchHistoryResult:
        assert instrument.symbol == "MSFT"
        assert lookback_days == 756
        prices = pd.Series(
            [100.0, 101.0, 100.5, 102.0, 103.0, 104.0],
            index=pd.date_range("2026-01-02", periods=6, freq="B"),
        )
        return ResearchHistoryResult(
            series=prices,
            source_provider="fixture",
            source_label="Fixture listed history",
            origin="tests.equity_handoff",
            freshness_label=FreshnessLabel.HISTORICAL,
            warnings=["Fixture history is local test data."],
        )


def test_strategy_lab_analyzes_imported_return_stream_with_benchmark(tmp_path):
    service = _service(tmp_path)
    rows = [
        {"date": "2026-01-02", "strategy": 0.010, "benchmark": 0.004},
        {"date": "2026-01-05", "strategy": -0.004, "benchmark": -0.002},
        {"date": "2026-01-06", "strategy": 0.006, "benchmark": 0.003},
        {"date": "2026-01-07", "strategy": 0.002, "benchmark": 0.001},
        {"date": "2026-01-08", "strategy": -0.003, "benchmark": -0.004},
        {"date": "2026-01-09", "strategy": 0.008, "benchmark": 0.005},
        {"date": "2026-01-12", "strategy": 0.004, "benchmark": 0.002},
        {"date": "2026-01-13", "strategy": 0.001, "benchmark": -0.001},
    ]

    result = service.analyze_strategy_lab(
        ImportedReturnStreamRequest(
            rows=rows,
            date_column="date",
            value_column="strategy",
            benchmark_column="benchmark",
            name="CSV Strategy",
        )
    )

    assert result.name == "CSV Strategy"
    assert result.source_provider == "uploaded_csv"
    assert result.freshness_label == "derived"
    assert result.metrics.observation_count == 8
    assert result.metrics.total_return is not None
    assert result.metrics.annual_volatility is not None
    assert result.metrics.benchmark_correlation is not None
    assert result.benchmark_returns.size == 8
    assert result.monthly_returns[0].period == "2026-01"
    assert any("data inputs only" in warning for warning in result.warnings)


def test_strategy_lab_converts_level_stream_to_returns(tmp_path):
    service = _service(tmp_path)
    rows = [
        {"date": "2026-01-02", "nav": 100.0},
        {"date": "2026-01-05", "nav": 101.0},
        {"date": "2026-01-06", "nav": 102.0},
        {"date": "2026-01-07", "nav": 101.5},
        {"date": "2026-01-08", "nav": 103.0},
        {"date": "2026-01-09", "nav": 104.0},
    ]

    result = service.analyze_strategy_lab(
        ImportedReturnStreamRequest(
            rows=rows,
            date_column="date",
            value_column="nav",
            value_kind="level",
            name="NAV Strategy",
        )
    )

    expected_returns = pd.Series([100.0, 101.0, 102.0, 101.5, 103.0, 104.0]).pct_change().dropna()
    assert result.metrics.observation_count == 5
    assert result.metrics.total_return == pytest.approx(float((1.0 + expected_returns).prod() - 1.0))
    assert result.value_kind == "level"


def test_strategy_lab_warns_on_duplicates_missing_values_and_outliers(tmp_path):
    service = _service(tmp_path)
    rows = [
        {"date": "2026-01-02", "return": "1%"},
        {"date": "2026-01-05", "return": ""},
        {"date": "2026-01-06", "return": "2%"},
        {"date": "2026-01-06", "return": "3%"},
        {"date": "2026-01-07", "return": "75%"},
        {"date": "2026-01-08", "return": "-1%"},
        {"date": "2026-01-09", "return": "0%"},
        {"date": "2026-01-12", "return": "2%"},
        {"date": "2026-01-13", "return": "1%"},
    ]

    result = service.analyze_strategy_lab(
        ImportedReturnStreamRequest(rows=rows, date_column="date", value_column="return")
    )

    joined_warnings = " ".join(result.warnings).lower()
    assert "missing or invalid values" in joined_warnings
    assert "duplicate dates" in joined_warnings
    assert "exceed +/-50%" in joined_warnings
    assert result.metrics.observation_count == 7


def test_strategy_lab_warns_on_whole_percent_decimal_mistake(tmp_path):
    service = _service(tmp_path)
    rows = [
        {"date": "2026-01-02", "return": 1.0},
        {"date": "2026-01-05", "return": -0.5},
        {"date": "2026-01-06", "return": 0.75},
        {"date": "2026-01-07", "return": 0.4},
        {"date": "2026-01-08", "return": -0.3},
        {"date": "2026-01-09", "return": 0.2},
    ]

    result = service.analyze_strategy_lab(
        ImportedReturnStreamRequest(rows=rows, date_column="date", value_column="return")
    )

    joined_warnings = " ".join(result.warnings).lower()
    assert "whole percentages" in joined_warnings


def test_strategy_lab_rejects_too_few_observations(tmp_path):
    service = _service(tmp_path)

    with pytest.raises(ResearchValidationError) as exc_info:
        service.analyze_strategy_lab(
            ImportedReturnStreamRequest(
                rows=[
                    {"date": "2026-01-02", "return": 0.01},
                    {"date": "2026-01-05", "return": 0.02},
                ],
                date_column="date",
                value_column="return",
            )
        )

    assert "needs at least 5 return observations" in exc_info.value.errors[0]


def test_strategy_lab_composes_weighted_return_objects(tmp_path):
    service = _service(tmp_path)
    result = service.compose_strategy_lab(
        StrategyLabCompositionRequest(
            name="Live Gamma Composition",
            legs=[
                StrategyLabCompositionLeg(
                    object=GammaResearchObject(
                        object_id="strategy:a",
                        object_type="strategy_return_stream",
                        display_name="Strategy A",
                        source_tab="strategy_lab",
                        source_mode="imports",
                        resolver_capabilities=["return_leg"],
                        return_points=[
                            ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.02),
                            ResearchObjectReturnPoint(timestamp="bad-date", value=0.99),
                            ResearchObjectReturnPoint(timestamp="2026-01-04", value=-0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.03),
                            ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.01),
                        ],
                    ),
                    weight=6.0,
                ),
                StrategyLabCompositionLeg(
                    object=GammaResearchObject(
                        object_id="strategy:b",
                        object_type="strategy_return_stream",
                        display_name="Strategy B",
                        source_tab="strategy_lab",
                        source_mode="imports",
                        resolver_capabilities=["return_leg"],
                        return_points=[
                            ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.00),
                            ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-04", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.00),
                            ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.02),
                        ],
                    ),
                    weight=4.0,
                ),
            ],
            lenses=[
                GammaResearchObject(
                    object_id="macro:lens",
                    object_type="macro_regime",
                    display_name="Macro Lens",
                    source_tab="macro",
                    resolver_capabilities=["lens"],
                )
            ],
            overlays=[
                GammaResearchObject(
                    object_id="crypto:overlay",
                    object_type="crypto_flow",
                    display_name="Flow Overlay",
                    source_tab="crypto",
                    resolver_capabilities=["overlay"],
                )
            ],
            benchmark_object=GammaResearchObject(
                object_id="benchmark:spy",
                object_type="benchmark_return_stream",
                display_name="SPY Benchmark",
                source_tab="equity_research",
                resolver_capabilities=["benchmark"],
                return_points=[
                    ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.004),
                    ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.003),
                    ResearchObjectReturnPoint(timestamp="2026-01-04", value=-0.002),
                    ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.005),
                    ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.001),
                ],
            ),
            min_observations=5,
        )
    )

    expected_returns = pd.Series([0.006, 0.016, -0.002, 0.018, 0.014], index=pd.date_range("2026-01-02", periods=5))
    expected_strategy_a_contribution = pd.Series([0.006, 0.012, -0.006, 0.018, 0.006])
    assert result.name == "Live Gamma Composition"
    assert list(result.leg_contributions.keys()) == ["Strategy A", "Strategy B"]
    assert result.leg_contributions["Strategy A"] == pytest.approx(
        float((1.0 + expected_strategy_a_contribution).prod() - 1.0)
    )
    assert result.returns.tolist() == pytest.approx(expected_returns.tolist())
    assert len(result.returns) == 5
    assert result.metrics.observation_count == 5
    assert result.benchmark_returns.size == 5
    assert result.source_provider == "gamma_strategy_lab"
    assert result.origin == "research_service.strategy_lab.compose"
    assert result.freshness_label == "derived"
    assert result.lenses[0].display_name == "Macro Lens"
    assert result.overlays[0].display_name == "Flow Overlay"
    assert result.warnings[0].startswith("Strategy Lab compositions are read-only research")
    assert any("Strategy A: dropped 1 return points with invalid timestamps" in warning for warning in result.warnings)


def test_strategy_lab_portfolio_compose_normalizes_timezone_aware_inline_dates(tmp_path):
    service = _service(tmp_path)

    result = service.compose_strategy_lab_portfolio(
        StrategyLabPortfolioCompositionRequest(
            name="Prediction Proxy Portfolio",
            benchmark_symbol=None,
            min_observations=3,
            legs=[
                StrategyLabPortfolioLeg(
                    label="Date-only probability proxy",
                    asset_class="prediction_contract",
                    weight=0.5,
                    value_kind="level",
                    return_points=[
                        ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.50),
                        ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.52),
                        ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.51),
                        ResearchObjectReturnPoint(timestamp="2026-01-07", value=0.54),
                    ],
                ),
                StrategyLabPortfolioLeg(
                    label="UTC probability proxy",
                    asset_class="prediction_contract",
                    weight=0.5,
                    value_kind="level",
                    return_points=[
                        ResearchObjectReturnPoint(timestamp="2026-01-02T16:00:00Z", value=0.20),
                        ResearchObjectReturnPoint(timestamp="2026-01-05T16:00:00Z", value=0.22),
                        ResearchObjectReturnPoint(timestamp="2026-01-06T16:00:00Z", value=0.21),
                        ResearchObjectReturnPoint(timestamp="2026-01-07T16:00:00Z", value=0.23),
                    ],
                ),
            ],
        )
    )

    assert result.metrics.observation_count == 3
    assert result.returns.index.tz is None
    assert result.name == "Prediction Proxy Portfolio"
    assert any("read-only research runs" in warning for warning in result.warnings)


def test_strategy_lab_resolves_prediction_market_handoff_to_draft_leg(tmp_path):
    service = _service(tmp_path)
    market = _prediction_market_record()

    class StubPredictionMarketService:
        def get_market_detail(self, market_id: str):
            return market if market_id == "polymarket:fed-cut" else None

        def get_probability_history(self, market_id: str):
            assert market_id == "polymarket:fed-cut"
            return [
                PredictionProbabilityPoint(timestamp=datetime(2026, 3, day, tzinfo=timezone.utc), probability=probability)
                for day, probability in enumerate([0.51, 0.52, 0.5, 0.54, 0.55, 0.56], start=1)
            ]

    result = service.resolve_strategy_lab_handoff(
        StrategyLabHandoffResolveRequest(
            handoff=StrategyLabHandoffEnvelope(
                source_tab="prediction_markets",
                source_mode="detail",
                intended_target_tab="strategy_lab",
                intended_target_mode="composer",
                selected_entity=CrossTabHandoffEntity(
                    entity_type="prediction_market_contract",
                    label=market.title,
                    normalized_id=market.market_id,
                    provider_id=market.provider_market_id,
                    native_id=market.provider_condition_id,
                ),
                resolver_capability="return_leg",
                asset_class="prediction_market",
                value_kind="probability",
                default_side="long_yes",
                default_weight=0.1,
                provider="polymarket",
                normalized_ids={"market_id": market.market_id},
                timestamp="2026-03-01T00:00:00Z",
            )
        ),
        prediction_market_service=StubPredictionMarketService(),
    )

    assert result.status == "resolved"
    assert result.resolved_capability == "return_leg"
    assert result.composer_draft_leg is not None
    assert result.composer_draft_leg.asset_class == "prediction_contract"
    assert result.composer_draft_leg.value_kind == "level"
    assert result.composer_draft_leg.identifier == "polymarket:fed-cut"
    assert len(result.composer_draft_leg.return_points) == 6
    assert result.date_coverage is not None
    assert result.provenance["transformation"] == "long_yes_probability_return"
    assert any("research proxy" in warning for warning in result.warnings)


def test_strategy_lab_resolves_prediction_market_no_handoff_to_draft_leg(tmp_path):
    service = _service(tmp_path)
    market = _prediction_market_record()

    class StubPredictionMarketService:
        def get_market_detail(self, market_id: str):
            return market if market_id == "polymarket:fed-cut" else None

        def get_probability_history(self, market_id: str):
            assert market_id == "polymarket:fed-cut"
            return [
                PredictionProbabilityPoint(timestamp=datetime(2026, 3, day, tzinfo=timezone.utc), probability=probability)
                for day, probability in enumerate([0.51, 0.52, 0.5, 0.54, 0.55, 0.56], start=1)
            ]

    result = service.resolve_strategy_lab_handoff(
        StrategyLabHandoffResolveRequest(
            handoff=StrategyLabHandoffEnvelope(
                source_tab="prediction_markets",
                source_mode="detail",
                intended_target_tab="strategy_lab",
                intended_target_mode="composer",
                selected_entity=CrossTabHandoffEntity(
                    entity_type="prediction_market_contract",
                    label=market.title,
                    normalized_id=market.market_id,
                    provider_id=market.provider_market_id,
                    native_id=market.provider_condition_id,
                ),
                resolver_capability="return_leg",
                asset_class="prediction_market",
                value_kind="probability",
                default_side="long_no",
                default_weight=0.1,
                provider="polymarket",
                normalized_ids={"market_id": market.market_id},
                timestamp="2026-03-01T00:00:00Z",
            )
        ),
        prediction_market_service=StubPredictionMarketService(),
    )

    assert result.status == "resolved"
    assert result.composer_draft_leg is not None
    assert result.composer_draft_leg.label.endswith("| NO probability")
    assert result.composer_draft_leg.return_points[0].value == pytest.approx(0.49)
    assert result.composer_draft_leg.return_points[-1].value == pytest.approx(0.44)
    assert result.provenance["transformation"] == "long_no_probability_return"
    assert any("NO exposure" in warning for warning in result.warnings)


def test_strategy_lab_resolves_equity_research_handoff_to_draft_leg(tmp_path):
    service = ResearchService(StubListedHistoryProvider(), saved_store=SavedResearchStore(tmp_path / "research"))

    result = service.resolve_strategy_lab_handoff(
        StrategyLabHandoffResolveRequest(
            handoff=StrategyLabHandoffEnvelope(
                source_tab="equity_research",
                source_mode="scope_analysis",
                intended_target_tab="strategy_lab",
                intended_target_mode="composer",
                selected_entity=CrossTabHandoffEntity(
                    entity_type="equity_symbol",
                    label="Microsoft",
                    normalized_id="MSFT",
                    provider_id="MSFT",
                    native_id="MSFT",
                ),
                resolver_capability="return_leg",
                asset_class="equity",
                value_kind="return",
                default_side="long",
                default_weight=0.1,
                provider="fixture",
                normalized_ids={"symbol": "MSFT"},
                timestamp="2026-03-01T00:00:00Z",
            )
        )
    )

    assert result.status == "resolved"
    assert result.resolved_capability == "return_leg"
    assert result.composer_draft_leg is not None
    assert result.composer_draft_leg.asset_class == "equity"
    assert result.composer_draft_leg.identifier == "MSFT"
    assert result.composer_draft_leg.value_kind == "return"
    assert len(result.composer_draft_leg.return_points) == 5
    assert result.date_coverage is not None
    assert result.provider_summary == "Fixture listed history"
    assert result.provenance["transformation"] == "listed_equity_return_stream"
    assert result.provenance["history_points"] == 5
    assert any("read-only Strategy Lab analysis" in warning for warning in result.warnings)


def test_strategy_lab_ignores_thin_optional_benchmark_overlap(tmp_path):
    service = _service(tmp_path)

    result = service.compose_strategy_lab(
        StrategyLabCompositionRequest(
            name="Thin Benchmark Composition",
            legs=[
                StrategyLabCompositionLeg(
                    object=GammaResearchObject(
                        object_id="strategy:thin-benchmark",
                        object_type="strategy_return_stream",
                        display_name="Strategy With Thin Benchmark",
                        source_tab="strategy_lab",
                        source_mode="imports",
                        resolver_capabilities=["return_leg"],
                        return_points=[
                            ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.02),
                            ResearchObjectReturnPoint(timestamp="2026-01-04", value=-0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.03),
                            ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.01),
                        ],
                    ),
                    weight=1.0,
                )
            ],
            lenses=[],
            overlays=[],
            benchmark_object=GammaResearchObject(
                object_id="benchmark:thin",
                object_type="benchmark_return_stream",
                display_name="Thin Benchmark",
                source_tab="equity_research",
                resolver_capabilities=["benchmark"],
                return_points=[
                    ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.004),
                    ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.003),
                ],
            ),
            min_observations=5,
        )
    )

    assert result.metrics.observation_count == 5
    assert len(result.returns) == 5
    assert result.benchmark_returns.empty
    assert result.metrics.benchmark_beta is None
    assert result.metrics.benchmark_correlation is None
    assert any("Benchmark overlap is too thin" in warning for warning in result.warnings)


def test_strategy_lab_preserves_valid_lenses_and_overlays_without_return_contributions(tmp_path):
    service = _service(tmp_path)

    result = service.compose_strategy_lab(
        StrategyLabCompositionRequest(
            name="Lens Overlay Composition",
            legs=[
                StrategyLabCompositionLeg(
                    object=GammaResearchObject(
                        object_id="strategy:base",
                        object_type="strategy_return_stream",
                        display_name="Base Strategy",
                        source_tab="strategy_lab",
                        resolver_capabilities=["return_leg"],
                        return_points=[
                            ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.02),
                            ResearchObjectReturnPoint(timestamp="2026-01-04", value=-0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.03),
                            ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.01),
                        ],
                    ),
                    weight=1.0,
                )
            ],
            lenses=[
                GammaResearchObject(
                    object_id="macro:valid-lens",
                    object_type="macro_regime",
                    display_name="Valid Macro Lens",
                    source_tab="macro",
                    resolver_capabilities=["lens"],
                )
            ],
            overlays=[
                GammaResearchObject(
                    object_id="crypto:valid-overlay",
                    object_type="crypto_flow",
                    display_name="Valid Flow Overlay",
                    source_tab="crypto",
                    resolver_capabilities=["overlay"],
                )
            ],
            benchmark_object=None,
            min_observations=5,
        )
    )

    assert [item.display_name for item in result.lenses] == ["Valid Macro Lens"]
    assert [item.display_name for item in result.overlays] == ["Valid Flow Overlay"]
    assert list(result.leg_contributions.keys()) == ["Base Strategy"]
    assert result.metrics.observation_count == 5


def test_strategy_lab_rejects_invalid_lens_object(tmp_path):
    service = _service(tmp_path)

    with pytest.raises(ResearchValidationError) as exc_info:
        service.compose_strategy_lab(
            StrategyLabCompositionRequest(
                name="Invalid Lens Composition",
                legs=[
                    StrategyLabCompositionLeg(
                        object=GammaResearchObject(
                            object_id="strategy:base",
                            object_type="strategy_return_stream",
                            display_name="Base Strategy",
                            source_tab="strategy_lab",
                            resolver_capabilities=["return_leg"],
                            return_points=[
                                ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.01),
                                ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.02),
                                ResearchObjectReturnPoint(timestamp="2026-01-04", value=-0.01),
                                ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.03),
                                ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.01),
                            ],
                        ),
                        weight=1.0,
                    )
                ],
                lenses=[
                    GammaResearchObject(
                        object_id="macro:not-lens",
                        object_type="macro_regime",
                        display_name="Invalid Lens",
                        source_tab="macro",
                        resolver_capabilities=["reference_only"],
                    )
                ],
                overlays=[],
                benchmark_object=None,
                min_observations=5,
            )
        )

    assert exc_info.value.errors == ["Invalid Lens cannot be used as a Strategy Lab lens."]


def test_strategy_lab_rejects_invalid_overlay_object(tmp_path):
    service = _service(tmp_path)

    with pytest.raises(ResearchValidationError) as exc_info:
        service.compose_strategy_lab(
            StrategyLabCompositionRequest(
                name="Invalid Overlay Composition",
                legs=[
                    StrategyLabCompositionLeg(
                        object=GammaResearchObject(
                            object_id="strategy:base",
                            object_type="strategy_return_stream",
                            display_name="Base Strategy",
                            source_tab="strategy_lab",
                            resolver_capabilities=["return_leg"],
                            return_points=[
                                ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.01),
                                ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.02),
                                ResearchObjectReturnPoint(timestamp="2026-01-04", value=-0.01),
                                ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.03),
                                ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.01),
                            ],
                        ),
                        weight=1.0,
                    )
                ],
                lenses=[],
                overlays=[
                    GammaResearchObject(
                        object_id="crypto:not-overlay",
                        object_type="crypto_flow",
                        display_name="Invalid Overlay",
                        source_tab="crypto",
                        resolver_capabilities=["reference_only"],
                    )
                ],
                benchmark_object=None,
                min_observations=5,
            )
        )

    assert exc_info.value.errors == ["Invalid Overlay cannot be used as a Strategy Lab overlay."]


def test_strategy_lab_rejects_lens_as_weighted_leg(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(ResearchValidationError) as exc_info:
        service.compose_strategy_lab(
            StrategyLabCompositionRequest(
                name="Bad Composition",
                legs=[
                    StrategyLabCompositionLeg(
                        object=GammaResearchObject(
                            object_id="macro:inflation-shock",
                            object_type="macro_regime",
                            display_name="Inflation Shock",
                            source_tab="macro",
                            source_mode="events_regimes",
                            resolver_capabilities=["lens"],
                        ),
                        weight=1.0,
                    )
                ],
                lenses=[],
                overlays=[],
                benchmark_object=None,
                min_observations=5,
            )
        )

    assert "Inflation Shock cannot be used as a weighted return leg." in exc_info.value.errors[0]


def test_strategy_lab_rejects_non_finite_leg_weight(tmp_path):
    service = _service(tmp_path)

    with pytest.raises(ResearchValidationError) as exc_info:
        service.compose_strategy_lab(
            StrategyLabCompositionRequest(
                name="Bad Weight Composition",
                legs=[
                    StrategyLabCompositionLeg(
                        object=GammaResearchObject(
                            object_id="strategy:bad-weight",
                            object_type="strategy_return_stream",
                            display_name="Bad Weight Strategy",
                            source_tab="strategy_lab",
                            resolver_capabilities=["return_leg"],
                            return_points=[
                                ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.01),
                                ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.02),
                                ResearchObjectReturnPoint(timestamp="2026-01-04", value=-0.01),
                                ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.03),
                                ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.01),
                            ],
                        ),
                        weight=float("nan"),
                    )
                ],
                lenses=[],
                overlays=[],
                benchmark_object=None,
                min_observations=5,
            )
        )

    assert exc_info.value.errors == ["Composition leg weights must be finite signed values."]


def test_strategy_lab_composes_signed_long_short_weights(tmp_path):
    service = _service(tmp_path)

    result = service.compose_strategy_lab(
        StrategyLabCompositionRequest(
            name="Long Short Composition",
            legs=[
                StrategyLabCompositionLeg(
                    object=GammaResearchObject(
                        object_id="strategy:long",
                        object_type="strategy_return_stream",
                        display_name="Long Leg",
                        source_tab="strategy_lab",
                        resolver_capabilities=["return_leg"],
                        return_points=[
                            ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.02),
                            ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.02),
                            ResearchObjectReturnPoint(timestamp="2026-01-04", value=0.02),
                            ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.02),
                            ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.02),
                        ],
                    ),
                    weight=0.6,
                ),
                StrategyLabCompositionLeg(
                    object=GammaResearchObject(
                        object_id="strategy:short",
                        object_type="strategy_return_stream",
                        display_name="Short Leg",
                        source_tab="strategy_lab",
                        resolver_capabilities=["return_leg"],
                        return_points=[
                            ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-04", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.01),
                        ],
                    ),
                    weight=-0.4,
                ),
            ],
            min_observations=5,
        )
    )

    assert result.returns.tolist() == pytest.approx([0.008, 0.008, 0.008, 0.008, 0.008])
    assert result.leg_contributions["Long Leg"] > 0
    assert result.leg_contributions["Short Leg"] < 0


def test_strategy_lab_drops_non_finite_return_point_values(tmp_path):
    service = _service(tmp_path)

    result = service.compose_strategy_lab(
        StrategyLabCompositionRequest(
            name="Finite Return Composition",
            legs=[
                StrategyLabCompositionLeg(
                    object=GammaResearchObject(
                        object_id="strategy:non-finite-return",
                        object_type="strategy_return_stream",
                        display_name="Non-Finite Return Strategy",
                        source_tab="strategy_lab",
                        resolver_capabilities=["return_leg"],
                        return_points=[
                            ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-03", value=float("inf")),
                            ResearchObjectReturnPoint(timestamp="2026-01-04", value=-0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.03),
                            ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-07", value=0.02),
                        ],
                    ),
                    weight=1.0,
                )
            ],
            lenses=[],
            overlays=[],
            benchmark_object=None,
            min_observations=5,
        )
    )

    assert result.metrics.observation_count == 5
    assert result.metrics.total_return is not None
    assert math.isfinite(result.metrics.total_return)
    assert all(math.isfinite(float(value)) for value in result.returns)
    assert any(
        "Non-Finite Return Strategy: dropped return point with non-finite value." in warning
        for warning in result.warnings
    )


def test_strategy_lab_composes_duplicate_display_name_legs_without_overwrite(tmp_path):
    service = _service(tmp_path)

    result = service.compose_strategy_lab(
        StrategyLabCompositionRequest(
            name="Duplicate Display Names",
            legs=[
                StrategyLabCompositionLeg(
                    object=GammaResearchObject(
                        object_id="strategy:same-name-a",
                        object_type="strategy_return_stream",
                        display_name="Same Name",
                        source_tab="strategy_lab",
                        resolver_capabilities=["return_leg"],
                        return_points=[
                            ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-04", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.01),
                        ],
                    ),
                    weight=0.5,
                ),
                StrategyLabCompositionLeg(
                    object=GammaResearchObject(
                        object_id="strategy:same-name-b",
                        object_type="strategy_return_stream",
                        display_name="Same Name",
                        source_tab="strategy_lab",
                        resolver_capabilities=["return_leg"],
                        return_points=[
                            ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.03),
                            ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.03),
                            ResearchObjectReturnPoint(timestamp="2026-01-04", value=0.03),
                            ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.03),
                            ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.03),
                        ],
                    ),
                    weight=0.5,
                ),
            ],
            lenses=[],
            overlays=[],
            benchmark_object=None,
            min_observations=5,
        )
    )

    assert result.returns.tolist() == pytest.approx([0.02, 0.02, 0.02, 0.02, 0.02])
    assert list(result.leg_contributions.keys()) == ["Same Name", "Same Name (2)"]
    assert len(result.leg_contributions) == 2


def test_strategy_lab_disambiguates_explicit_duplicate_contribution_suffixes(tmp_path):
    service = _service(tmp_path)

    result = service.compose_strategy_lab(
        StrategyLabCompositionRequest(
            name="Duplicate Explicit Suffixes",
            legs=[
                StrategyLabCompositionLeg(
                    object=GammaResearchObject(
                        object_id="strategy:same-name-a",
                        object_type="strategy_return_stream",
                        display_name="Same Name",
                        source_tab="strategy_lab",
                        resolver_capabilities=["return_leg"],
                        return_points=[
                            ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-04", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.01),
                        ],
                    ),
                    weight=1.0,
                ),
                StrategyLabCompositionLeg(
                    object=GammaResearchObject(
                        object_id="strategy:same-name-b",
                        object_type="strategy_return_stream",
                        display_name="Same Name (2)",
                        source_tab="strategy_lab",
                        resolver_capabilities=["return_leg"],
                        return_points=[
                            ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.02),
                            ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.02),
                            ResearchObjectReturnPoint(timestamp="2026-01-04", value=0.02),
                            ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.02),
                            ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.02),
                        ],
                    ),
                    weight=1.0,
                ),
                StrategyLabCompositionLeg(
                    object=GammaResearchObject(
                        object_id="strategy:same-name-c",
                        object_type="strategy_return_stream",
                        display_name="Same Name",
                        source_tab="strategy_lab",
                        resolver_capabilities=["return_leg"],
                        return_points=[
                            ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.03),
                            ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.03),
                            ResearchObjectReturnPoint(timestamp="2026-01-04", value=0.03),
                            ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.03),
                            ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.03),
                        ],
                    ),
                    weight=1.0,
                ),
            ],
            lenses=[],
            overlays=[],
            benchmark_object=None,
            min_observations=5,
        )
    )

    assert list(result.leg_contributions.keys()) == ["Same Name", "Same Name (2)", "Same Name (3)"]
    assert len(result.leg_contributions) == 3


def test_strategy_lab_contributions_use_benchmark_trimmed_window(tmp_path):
    service = _service(tmp_path)

    result = service.compose_strategy_lab(
        StrategyLabCompositionRequest(
            name="Benchmark Trimmed Contributions",
            legs=[
                StrategyLabCompositionLeg(
                    object=GammaResearchObject(
                        object_id="strategy:trimmed-a",
                        object_type="strategy_return_stream",
                        display_name="Trimmed A",
                        source_tab="strategy_lab",
                        resolver_capabilities=["return_leg"],
                        return_points=[
                            ResearchObjectReturnPoint(timestamp="2026-01-01", value=0.50),
                            ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.01),
                            ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.012),
                            ResearchObjectReturnPoint(timestamp="2026-01-04", value=0.008),
                            ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.014),
                            ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.01),
                        ],
                    ),
                    weight=0.5,
                ),
                StrategyLabCompositionLeg(
                    object=GammaResearchObject(
                        object_id="strategy:trimmed-b",
                        object_type="strategy_return_stream",
                        display_name="Trimmed B",
                        source_tab="strategy_lab",
                        resolver_capabilities=["return_leg"],
                        return_points=[
                            ResearchObjectReturnPoint(timestamp="2026-01-01", value=0.10),
                            ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.03),
                            ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.03),
                            ResearchObjectReturnPoint(timestamp="2026-01-04", value=0.032),
                            ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.026),
                            ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.034),
                        ],
                    ),
                    weight=0.5,
                ),
            ],
            lenses=[],
            overlays=[],
            benchmark_object=GammaResearchObject(
                object_id="benchmark:trimmed",
                object_type="benchmark_return_stream",
                display_name="Trimmed Benchmark",
                source_tab="equity_research",
                resolver_capabilities=["benchmark"],
                return_points=[
                    ResearchObjectReturnPoint(timestamp="2026-01-02", value=0.004),
                    ResearchObjectReturnPoint(timestamp="2026-01-03", value=0.005),
                    ResearchObjectReturnPoint(timestamp="2026-01-04", value=0.003),
                    ResearchObjectReturnPoint(timestamp="2026-01-05", value=0.006),
                    ResearchObjectReturnPoint(timestamp="2026-01-06", value=0.002),
                ],
            ),
            min_observations=5,
        )
    )

    assert result.metrics.observation_count == 5
    assert result.returns.tolist() == pytest.approx([0.02, 0.021, 0.02, 0.02, 0.022])
    assert result.leg_contributions["Trimmed A"] == pytest.approx(
        float((1.0 + pd.Series([0.005, 0.006, 0.004, 0.007, 0.005])).prod() - 1.0)
    )
    assert result.leg_contributions["Trimmed B"] == pytest.approx(
        float((1.0 + pd.Series([0.015, 0.015, 0.016, 0.013, 0.017])).prod() - 1.0)
    )


def test_research_object_schema_serializes_nested_return_points():
    research_object = GammaResearchObject(
        object_id="strategy:api",
        object_type="strategy_return_stream",
        display_name="API Strategy",
        source_tab="strategy_lab",
        source_mode="imports",
        resolver_capabilities=["return_leg"],
        return_points=[
            ResearchObjectReturnPoint(timestamp="2026-01-02T00:00:00", value=0.01),
            ResearchObjectReturnPoint(timestamp="2026-01-03T00:00:00", value=-0.02),
        ],
    )

    model = GammaResearchObjectModel.from_domain(research_object)
    round_trip = model.to_domain()

    assert model.return_points[0].timestamp.year == 2026
    assert round_trip.return_points[0] == ResearchObjectReturnPoint(timestamp="2026-01-02T00:00:00", value=0.01)


def test_strategy_lab_compose_route_serializes_nested_return_points(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        response = client.post(
            "/research/strategy-lab/compose",
            json={
                "name": "API Composition",
                "legs": [
                    {
                        "object": {
                            "object_id": "strategy:api-a",
                            "object_type": "strategy_return_stream",
                            "display_name": "API Strategy A",
                            "source_tab": "strategy_lab",
                            "resolver_capabilities": ["return_leg"],
                            "return_points": [
                                {"timestamp": "2026-01-02T00:00:00", "value": 0.01},
                                {"timestamp": "2026-01-03T00:00:00", "value": 0.02},
                                {"timestamp": "2026-01-04T00:00:00", "value": -0.01},
                                {"timestamp": "2026-01-05T00:00:00", "value": 0.03},
                                {"timestamp": "2026-01-06T00:00:00", "value": 0.01},
                            ],
                        },
                        "weight": 1.0,
                    }
                ],
                "lenses": [
                    {
                        "object_id": "macro:lens",
                        "object_type": "macro_regime",
                        "display_name": "Macro Lens",
                        "source_tab": "macro",
                        "resolver_capabilities": ["lens"],
                        "return_points": [],
                    }
                ],
                "overlays": [],
                "benchmark_object": None,
                "min_observations": 5,
            },
        )

        payload = response.json()
        assert response.status_code == 200
        assert payload["name"] == "API Composition"
        assert payload["metrics"]["observation_count"] == 5
        assert payload["lenses"][0]["return_points"] == []
        assert payload["returns_points"][0]["timestamp"].startswith("2026-01-02")
    finally:
        runtime.shutdown()


def test_compare_scenario_aligns_direct_and_saved_return_streams(tmp_path):
    service = _service(tmp_path)
    idx = pd.date_range("2026-01-02", periods=8, freq="B")
    strategy_returns = pd.Series([0.01, -0.004, 0.006, 0.002, -0.003, 0.008, 0.004, 0.001], index=idx)
    benchmark_returns = pd.Series([0.004, -0.002, 0.003, 0.001, -0.004, 0.005, 0.002, -0.001], index=idx)
    saved = service.save_research(
        SavedResearchCreateRequest(
            object_type="strategy_lab",
            title="Saved Strategy",
            payload={
                "returns_points": [
                    {"timestamp": timestamp.isoformat(), "value": float(value)}
                    for timestamp, value in strategy_returns.items()
                ]
            },
            warnings=["Uploaded CSV source retained as normalized returns only."],
        )
    )

    result = service.compare_research(
        ResearchComparisonRequest(
            left=ResearchComparisonLeg(
                label="Saved Strategy",
                object_type="strategy_lab",
                saved_research_id=saved.id,
            ),
            right=ResearchComparisonLeg(
                label="Benchmark",
                object_type="benchmark",
                returns=benchmark_returns,
            ),
        )
    )

    assert result.comparison.aligned_observation_count == 8
    assert result.comparison.left_observation_count == 8
    assert result.comparison.right_observation_count == 8
    assert result.comparison.overlap_start is not None
    assert result.comparison.overlap_end is not None
    assert result.comparison.left.label == "Saved Strategy"
    assert result.comparison.relative_return is not None
    assert result.comparison.correlation is not None
    assert any("historical analytics only" in warning for warning in result.warnings)


def test_saved_research_create_list_load_and_delete(tmp_path):
    service = _service(tmp_path)

    saved = service.save_research(
        SavedResearchCreateRequest(
            object_type="scope_analysis",
            title="AAPL Scope",
            notes="First-pass saved scope.",
            payload={"performance_points": [{"timestamp": "2026-01-02T00:00:00", "value": 0.01}]},
            warnings=["Sample warning"],
        )
    )

    assert saved.id
    assert service.list_saved_research()[0].title == "AAPL Scope"
    loaded = service.load_saved_research(saved.id)
    assert loaded is not None
    assert loaded.title == "AAPL Scope"
    assert service.delete_saved_research(saved.id) is True
    assert service.load_saved_research(saved.id) is None


def test_saved_research_keeps_legacy_scope_and_strategy_objects(tmp_path):
    store = SavedResearchStore(tmp_path / "research")
    scope = store.create_item(SavedResearchCreateRequest(object_type="scope_analysis", title="AAPL Scope"))
    strategy = store.create_item(SavedResearchCreateRequest(object_type="strategy_lab", title="CSV Strategy"))

    loaded = store.list_items()

    assert {item.id for item in loaded} == {scope.id, strategy.id}
    assert store.load_item(scope.id).object_type == "scope_analysis"
    assert store.load_item(strategy.id).object_type == "strategy_lab"


def test_saved_research_loads_future_schema_best_effort(tmp_path):
    store = SavedResearchStore(tmp_path / "research")
    item_path = store.items_dir / "future-schema.json"
    item_path.write_text(
        json.dumps(
            {
                "id": "future-schema",
                "schema_version": 99,
                "object_type": "strategy_lab",
                "title": "Future Schema",
                "notes": "",
                "payload": {"returns_points": [{"timestamp": "2026-01-02T00:00:00", "value": 0.01}]},
                "created_at": "2026-01-02T00:00:00",
                "updated_at": "2026-01-02T00:00:00",
                "warnings": [],
                "source_provider": "uploaded_csv",
                "retrieved_at": "2026-01-02T00:00:00",
                "origin": "test",
                "transformation_note": None,
            }
        ),
        encoding="utf-8",
    )

    loaded = store.load_item("future-schema")

    assert loaded is not None
    assert loaded.schema_version == 99
    assert any("loaded best-effort" in warning for warning in loaded.warnings)


def _prediction_market_record() -> PredictionMarketRecord:
    return PredictionMarketRecord(
        market_id="polymarket:fed-cut",
        venue="polymarket",
        title="Will the Fed cut rates in March?",
        subtitle=None,
        description="Fed decision contract",
        status="open",
        category="Economy",
        event_id="event-1",
        event_title="Fed decision",
        series_id="series-1",
        series_title="FOMC",
        provider_market_id="fed-cut",
        provider_condition_id="0xabc",
        provider_event_id="event-1",
        provider_series_id="series-1",
        slug="fed-cut",
        end_time=datetime(2026, 3, 18, tzinfo=timezone.utc),
        open_time=datetime(2026, 3, 1, tzinfo=timezone.utc),
        close_time=None,
        current_probability=0.56,
        probability_label="Yes",
        volume=100_000,
        volume_24h=5_000,
        liquidity=25_000,
        open_interest=4_000,
        best_bid=0.55,
        best_ask=0.57,
        spread=0.02,
        recent_price_change=0.03,
        resolved_probability=None,
        resolution_outcome=None,
        image_url=None,
        resolution_source="Federal Reserve statement",
        freshness=PredictionMarketFreshness(
            status="fresh",
            is_stale=False,
            is_broken=False,
            reason="Venue metadata is recent.",
            last_history_point_at=datetime(2026, 3, 6, tzinfo=timezone.utc),
            retrieval_age_seconds=120,
            history_lag_seconds=120,
        ),
        source_provider="polymarket",
        retrieved_at=datetime(2026, 3, 6, 0, 5, tzinfo=timezone.utc),
        origin="polymarket.fixture",
        transformation_note="Fixture market.",
    )
