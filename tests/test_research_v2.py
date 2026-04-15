from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from src.application.research_service import ResearchService
from src.application.research_validation import ResearchValidationError
from src.models.research_lab import (
    ImportedReturnStreamRequest,
    ResearchComparisonLeg,
    ResearchComparisonRequest,
    SavedResearchCreateRequest,
)
from src.services.saved_research_store import SavedResearchStore


def _service(tmp_path) -> ResearchService:
    return ResearchService(SimpleNamespace(), saved_store=SavedResearchStore(tmp_path / "research"))


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
