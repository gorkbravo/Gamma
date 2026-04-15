from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.runtime import build_runtime
from src.models.cache_policy import CacheFreshnessPolicy, StaleBehavior, default_cache_freshness_policies
from src.models.copilot import CopilotContextBundle
from src.models.copilot_context import (
    CopilotContextContract,
    CopilotDrilldownTool,
    CopilotHeadlineMetric,
)
from src.models.handoff import CrossTabHandoffEnvelope, HandoffEntity, HandoffTimeframe
from src.models.provenance import (
    FreshnessLabel,
    FreshnessRecord,
    ProvenanceRecord,
    ProvenanceSummary,
    normalize_freshness_label,
    requires_transformation_note,
)


def test_provenance_and_freshness_primitives_normalize_expected_labels():
    retrieved_at = datetime(2026, 4, 15, 10, 0, 0)
    provenance = ProvenanceRecord(
        source_provider="fred",
        retrieved_at=retrieved_at,
        origin="fred.series.observations:CPIAUCSL",
        transformation_note="Gamma derives YoY inflation from the official index level.",
    )
    freshness = FreshnessRecord(
        label=FreshnessLabel.DERIVED,
        retrieved_at=retrieved_at,
        source_timestamp=datetime(2026, 4, 14, 12, 30, 0),
        evaluated_at=datetime(2026, 4, 15, 10, 5, 0),
        age_seconds=300.0,
        ttl_seconds=86400.0,
        is_stale=False,
        warnings=[],
    )

    assert provenance.to_dict()["retrieved_at"] == "2026-04-15T10:00:00"
    assert freshness.to_dict()["label"] == "derived"
    assert normalize_freshness_label("fresh") == FreshnessLabel.LIVE
    assert normalize_freshness_label("model-generated") == FreshnessLabel.MODEL_GENERATED
    assert normalize_freshness_label("not-a-known-label") == FreshnessLabel.UNKNOWN
    assert requires_transformation_note(FreshnessLabel.DERIVED) is True
    assert requires_transformation_note(FreshnessLabel.MODEL_GENERATED) is True
    assert requires_transformation_note(FreshnessLabel.LIVE) is False

    with pytest.raises(ValueError, match="source_provider"):
        ProvenanceRecord(source_provider="", retrieved_at=retrieved_at, origin="gamma.test")


def test_cache_freshness_policy_tracks_ttl_stale_behavior_and_source_time():
    evaluated_at = datetime(2026, 4, 15, 12, 0, 0)
    retrieved_at = evaluated_at - timedelta(minutes=10)
    source_timestamp = evaluated_at - timedelta(minutes=12)
    policy = CacheFreshnessPolicy(
        policy_id="test_snapshot",
        description="Test short-lived snapshot policy.",
        ttl=timedelta(minutes=5),
        fresh_label=FreshnessLabel.LIVE,
        stale_behavior=StaleBehavior.SERVE_WITH_WARNING,
    )

    assessment = policy.evaluate(
        retrieved_at=retrieved_at,
        source_timestamp=source_timestamp,
        evaluated_at=evaluated_at,
    )

    assert assessment.label == FreshnessLabel.STALE
    assert assessment.is_stale is True
    assert assessment.usable is True
    assert assessment.should_refresh is True
    assert assessment.source_timestamp == source_timestamp
    assert assessment.to_freshness_record().to_dict()["ttl_seconds"] == 300.0
    assert assessment.warnings == ["Cached value for test_snapshot is stale."]

    strict_policy = CacheFreshnessPolicy(
        policy_id="strict_snapshot",
        description="Test stale cache rejection.",
        ttl=timedelta(minutes=5),
        fresh_label=FreshnessLabel.LIVE,
        stale_behavior=StaleBehavior.REFETCH_REQUIRED,
    )
    strict_assessment = strict_policy.evaluate(retrieved_at=retrieved_at, evaluated_at=evaluated_at)
    assert strict_assessment.usable is False
    assert strict_assessment.should_refresh is True

    missing_assessment = policy.evaluate(retrieved_at=None, evaluated_at=evaluated_at, value_available=False)
    assert missing_assessment.label == FreshnessLabel.UNAVAILABLE
    assert missing_assessment.usable is False
    assert missing_assessment.should_refresh is True


def test_default_cache_freshness_policies_are_provider_agnostic():
    policies = {policy.policy_id: policy for policy in default_cache_freshness_policies()}

    assert {
        "live_or_delayed_market_snapshot",
        "daily_research_series",
        "historical_reference_dataset",
        "generated_or_mocked_context",
    }.issubset(policies)
    assert all(policy.description for policy in policies.values())
    assert policies["generated_or_mocked_context"].ttl is None


def test_cross_tab_handoff_envelope_round_trips_and_validates():
    retrieved_at = datetime(2026, 4, 15, 9, 30, 0)
    envelope = CrossTabHandoffEnvelope(
        source_tab="research",
        source_mode="scope_analysis",
        intended_target_tab="risk",
        intended_target_mode="portfolio_risk",
        selected_entity=HandoffEntity(
            entity_type="instrument",
            label="AAPL",
            normalized_id="research:AAPL:STK:SMART:USD",
            provider_id="AAPL",
            native_id="AAPL",
        ),
        selected_timeframe=HandoffTimeframe(
            label="1Y",
            start=datetime(2025, 4, 15),
            end=datetime(2026, 4, 15),
        ),
        provider="ibkr",
        source=ProvenanceRecord(
            source_provider="gamma",
            retrieved_at=retrieved_at,
            origin="gamma.research.analyze",
            transformation_note="Synthetic single-name research scope forwarded to Risk.",
        ),
        warnings=["History coverage is incomplete."],
        normalized_ids={"instrument_id": "research:AAPL:STK:SMART:USD"},
        timestamp=datetime(2026, 4, 15, 10, 0, 0),
    )

    payload = envelope.to_dict()
    restored = CrossTabHandoffEnvelope.from_dict(payload)

    assert payload["source_tab"] == "research"
    assert payload["selected_entity"]["normalized_id"] == "research:AAPL:STK:SMART:USD"
    assert restored == envelope

    with pytest.raises(ValueError, match="source_tab"):
        CrossTabHandoffEnvelope(source_tab="", intended_target_tab="risk")
    with pytest.raises(ValueError, match="start cannot be after end"):
        HandoffTimeframe(label="bad", start=datetime(2026, 4, 16), end=datetime(2026, 4, 15))


def test_copilot_context_contract_serializes_compact_read_only_context():
    provenance = ProvenanceSummary.from_record(
        ProvenanceRecord(
            source_provider="ibkr",
            retrieved_at=datetime(2026, 4, 15, 9, 0, 0),
            origin="gamma.iv.surface",
        ),
        freshness_label="delayed",
    )
    contract = CopilotContextContract(
        tab_id="iv",
        active_mode="surface",
        selected_entity=HandoffEntity(
            entity_type="instrument",
            label="SPY",
            normalized_id="ibkr:SPY:STK:SMART:USD",
        ),
        selected_timeframe=HandoffTimeframe(label="current"),
        headline_metrics=[
            CopilotHeadlineMetric(
                metric_id="atm_iv",
                label="ATM IV",
                value=0.21,
                display_value="21.0%",
                unit="percent",
            )
        ],
        provenance_summaries=[provenance],
        warnings=["Delayed market data mode."],
        available_drilldown_tools=[
            CopilotDrilldownTool(
                tool_id="get_iv_surface_context",
                label="IV surface",
                description="Read-only IV surface summary.",
            )
        ],
    )

    payload = contract.to_dict()
    bundle = CopilotContextBundle(domain="iv", current_tab="iv", summary_data={})

    assert payload["read_only_safety"]["read_only"] is True
    assert payload["read_only_safety"]["execution_allowed"] is False
    assert payload["available_drilldown_tools"][0]["read_only"] is True
    assert payload["provenance_summaries"][0]["freshness_label"] == "delayed"
    assert bundle.read_only_safety["mutation_allowed"] is False
    assert bundle.read_only_safety["execution_allowed"] is False


def test_read_only_boundary_system_api_exposes_no_execution_contract(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        response = client.get("/system/read-only-boundary")
        assert response.status_code == 200
        payload = response.json()

        assert payload["read_only"] is True
        assert "order_placement" in payload["prohibits"]
        assert "account_modification" in payload["prohibits"]
        assert "market_data_retrieval" in payload["allows"]
        assert any("TWS API read-only" in note for note in payload["hard_operator_locks"])
        assert any("no backend route or Copilot tool is an execution path" in note for note in payload["app_boundary_notes"])
        assert payload["source_provider"] == "gamma"
        assert payload["retrieved_at"] is not None
    finally:
        runtime.shutdown()

