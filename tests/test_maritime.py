from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.maritime_service import MaritimeService
from src.application.provider_capability_registry import build_default_provider_capability_registry
from src.application.runtime import build_runtime
from src.models.maritime import MaritimeCoverageMetadata
from src.services.maritime_adapters import (
    AISSTREAM_DEFAULT_MESSAGE_TYPES,
    AisstreamMaritimeDataProvider,
    SampleMaritimeDataProvider,
    normalize_aisstream_live_message,
)


def test_maritime_coverage_model_rejects_unknown_status():
    with pytest.raises(ValueError):
        MaritimeCoverageMetadata(
            coverage_status="complete_global",
            provider_id="bad",
            provider_label="Bad",
            freshness_label="live",
        )


def test_maritime_service_builds_sample_workspace_with_caveats():
    service = MaritimeService(provider=SampleMaritimeDataProvider())

    result = service.get_workspace(mode="trade_flows")

    assert result.mode == "trade_flows"
    assert result.coverage.coverage_status == "sample"
    assert result.coverage.supports_live is False
    assert result.coverage.supports_historical is True
    assert result.vessels
    assert result.positions
    assert result.chokepoint_summaries
    assert result.flow_summaries
    assert all(summary.coverage_status == "sample" for summary in result.chokepoint_summaries)
    assert any(summary.total_vessel_count > 0 for summary in result.chokepoint_summaries)
    assert all(flow.inference_caveat and "AIS does not report cargo" in flow.inference_caveat for flow in result.flow_summaries)
    assert any("not live global AIS" in warning for warning in result.warnings)
    assert any("Risk Signals are not enabled" in warning for warning in result.warnings)


def test_maritime_service_normalizes_unknown_mode_and_loads_track():
    service = MaritimeService(provider=SampleMaritimeDataProvider())

    result = service.get_workspace(mode="risk signals")
    track = service.get_vessel_track("vessel-gulf-horizon")

    assert result.mode == "live_map"
    assert track is not None
    assert track.vessel_id == "vessel-gulf-horizon"
    assert len(track.points) >= 2
    assert track.points[-1].source_provider == "sample_data"


def test_maritime_api_routes_return_sample_workspace_and_track(tmp_path, monkeypatch):
    monkeypatch.setenv("MARITIME_PROVIDER", "sample")
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        workspace = client.get("/maritime/workspace", params={"mode": "chokepoints"})
        track = client.get("/maritime/vessels/vessel-gulf-horizon/track")
        missing = client.get("/maritime/vessels/not-a-vessel/track")

        assert workspace.status_code == 200
        payload = workspace.json()
        assert payload["mode"] == "chokepoints"
        assert payload["coverage"]["coverage_status"] == "sample"
        assert payload["source_provider"] == "gamma"
        assert payload["chokepoint_summaries"]
        assert payload["flow_summaries"]
        assert any("AIS does not identify cargo" in warning for warning in payload["warnings"])

        assert track.status_code == 200
        track_payload = track.json()
        assert track_payload["track"]["vessel_id"] == "vessel-gulf-horizon"
        assert len(track_payload["track"]["points"]) >= 2

        assert missing.status_code == 404
    finally:
        runtime.shutdown()


def test_maritime_live_ws_without_key_reports_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("MARITIME_PROVIDER", "sample")
    monkeypatch.setenv("AISSTREAM_API_KEY", "")
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        with client.websocket_connect("/maritime/live/ws") as websocket:
            payload = websocket.receive_json()

        assert payload["type"] == "status"
        assert payload["status"] == "unavailable"
        assert "AISSTREAM_API_KEY" in payload["message"]
    finally:
        runtime.shutdown()


def test_aisstream_provider_without_key_returns_unavailable_reference_snapshot():
    provider = AisstreamMaritimeDataProvider(api_key="", reference_provider=SampleMaritimeDataProvider())

    snapshot = provider.get_snapshot()

    assert snapshot.coverage.provider_id == "aisstream"
    assert snapshot.coverage.coverage_status == "unavailable"
    assert snapshot.coverage.supports_live is True
    assert snapshot.coverage.supports_historical is False
    assert "AISSTREAM_API_KEY" in snapshot.coverage.credential_env_vars
    assert snapshot.positions == []
    assert snapshot.vessels == []
    assert snapshot.chokepoints
    assert any("AISSTREAM_API_KEY" in warning for warning in snapshot.warnings)


def test_aisstream_provider_maps_position_messages(monkeypatch):
    provider = AisstreamMaritimeDataProvider(
        api_key="test-key",
        reference_provider=SampleMaritimeDataProvider(),
        sample_seconds=1,
    )
    message = {
        "MessageType": "PositionReport",
        "MetaData": {
            "MMSI": 538009991,
            "ShipName": "GULF HORIZON",
            "latitude": 26.33,
            "longitude": 56.35,
            "time_utc": "2026-04-18 11:20:00.000000 +0000 UTC",
        },
        "Message": {
            "PositionReport": {
                "UserID": 538009991,
                "Latitude": 26.33,
                "Longitude": 56.35,
                "Sog": 12.1,
                "Cog": 105.0,
                "TrueHeading": 108,
                "NavigationalStatus": 0,
            }
        },
    }
    monkeypatch.setattr(provider, "_collect_messages_sync", lambda reference: [message])

    snapshot = provider.get_snapshot(force_refresh=True)

    assert snapshot.coverage.coverage_status == "partial"
    assert snapshot.coverage.freshness_label == "live_stream_sample"
    assert snapshot.positions[0].source_provider == "aisstream"
    assert snapshot.positions[0].vessel_id == "mmsi:538009991"
    assert snapshot.positions[0].speed_knots == 12.1
    assert snapshot.positions[0].heading_degrees == 108
    assert snapshot.vessels[0].name == "GULF HORIZON"
    assert snapshot.vessels[0].cargo_inference is None
    assert any("partial live AIS coverage" in warning for warning in snapshot.warnings)


def test_aisstream_live_normalizer_maps_static_vessel_type_and_dimensions():
    message = {
        "MessageType": "ShipStaticData",
        "MetaData": {
            "MMSI": 538009991,
            "ShipName": "GULF HORIZON",
            "time_utc": "2026-04-18 11:20:00.000000 +0000 UTC",
        },
        "Message": {
            "ShipStaticData": {
                "UserID": 538009991,
                "ImoNumber": 9876543,
                "CallSign": "V7GH9",
                "Name": "GULF HORIZON",
                "Type": 84,
                "Dimension": {"A": 280, "B": 53, "C": 30, "D": 30},
                "MaximumStaticDraught": 18.2,
                "Destination": "FUJAIRAH",
            }
        },
    }

    normalized = normalize_aisstream_live_message(message, index=0, retrieved_at=datetime(2026, 4, 18, 11, 20))

    assert normalized is not None
    position, vessel = normalized
    assert position is None
    assert vessel is not None
    assert vessel.vessel_type == "tanker"
    assert vessel.vessel_class == "AIS tanker class 84"
    assert vessel.identity.imo == "9876543"
    assert vessel.identity.callsign == "V7GH9"
    assert vessel.length_m == 333
    assert vessel.beam_m == 60
    assert vessel.cargo_inference is None
    assert "does not infer commodity cargo" in (vessel.cargo_inference_caveat or "")


def test_aisstream_live_normalizer_maps_static_data_report_ship_type():
    message = {
        "MessageType": "StaticDataReport",
        "MetaData": {
            "MMSI": 257702970,
            "latitude": 59.1,
            "longitude": 10.7,
            "time_utc": "2026-04-18 11:20:00.000000 +0000 UTC",
        },
        "Message": {
            "StaticDataReport": {
                "UserID": 257702970,
                "ReportA": {"Name": "OSLO CARGO", "Valid": True},
                "ReportB": {
                    "CallSign": "LESW",
                    "ShipType": 70,
                    "Dimension": {"A": 120, "B": 28, "C": 16, "D": 16},
                    "Valid": True,
                },
            }
        },
    }

    normalized = normalize_aisstream_live_message(message, index=0, retrieved_at=datetime(2026, 4, 18, 11, 20))

    assert normalized is not None
    position, vessel = normalized
    assert position is not None
    assert position.heading_degrees is None
    assert vessel is not None
    assert vessel.name == "OSLO CARGO"
    assert vessel.vessel_type == "cargo"
    assert vessel.length_m == 148
    assert vessel.beam_m == 32


def test_aisstream_provider_preserves_static_type_after_position_only_messages(monkeypatch):
    provider = AisstreamMaritimeDataProvider(
        api_key="test-key",
        reference_provider=SampleMaritimeDataProvider(),
        sample_seconds=1,
    )
    static_message = {
        "MessageType": "ShipStaticData",
        "MetaData": {"MMSI": 538009991, "ShipName": "GULF HORIZON"},
        "Message": {
            "ShipStaticData": {
                "UserID": 538009991,
                "Name": "GULF HORIZON",
                "Type": 84,
                "Dimension": {"A": 280, "B": 53, "C": 30, "D": 30},
            }
        },
    }
    position_message = {
        "MessageType": "PositionReport",
        "MetaData": {
            "MMSI": 538009991,
            "latitude": 26.33,
            "longitude": 56.35,
            "time_utc": "2026-04-18 11:20:00.000000 +0000 UTC",
        },
        "Message": {
            "PositionReport": {
                "UserID": 538009991,
                "Latitude": 26.33,
                "Longitude": 56.35,
                "Sog": 12.1,
                "Cog": 105.0,
                "TrueHeading": 511,
            }
        },
    }
    monkeypatch.setattr(provider, "_collect_messages_sync", lambda reference: [static_message, position_message])

    snapshot = provider.get_snapshot(force_refresh=True)

    assert snapshot.positions[0].heading_degrees is None
    assert snapshot.vessels[0].vessel_type == "tanker"
    assert snapshot.vessels[0].length_m == 333


def test_aisstream_live_message_types_include_static_data_for_vessel_coloring():
    assert "PositionReport" in AISSTREAM_DEFAULT_MESSAGE_TYPES
    assert "ShipStaticData" in AISSTREAM_DEFAULT_MESSAGE_TYPES
    assert "StaticDataReport" in AISSTREAM_DEFAULT_MESSAGE_TYPES


def test_runtime_can_select_aisstream_provider_without_key(tmp_path, monkeypatch):
    monkeypatch.setenv("MARITIME_PROVIDER", "aisstream")
    monkeypatch.setenv("AISSTREAM_API_KEY", "")
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    try:
        workspace = runtime.maritime_service.get_workspace(mode="live_map")

        assert workspace.coverage.provider_id == "aisstream"
        assert workspace.coverage.coverage_status == "unavailable"
        assert workspace.positions == []
        assert workspace.chokepoints
    finally:
        runtime.shutdown()


def test_provider_registry_exposes_sample_and_planned_maritime_providers():
    registry = build_default_provider_capability_registry()

    maritime_ids = {row.provider_id for row in registry.providers_for_domain("maritime_intelligence")}
    active_maritime_ids = {
        row.provider_id
        for row in registry.providers_for_domain("maritime_intelligence", include_planned=False)
    }

    assert {"sample_data", "aisstream", "noaa_marinecadastre", "aishub", "global_fishing_watch", "paid_ais_vendors"}.issubset(
        maritime_ids
    )
    assert active_maritime_ids == {"sample_data", "aisstream"}
