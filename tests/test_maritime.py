from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.maritime_service import MaritimeService
from src.application.provider_capability_registry import build_default_provider_capability_registry
from src.application.runtime import build_runtime
from src.models.maritime import MaritimeCoverageMetadata
from src.services.maritime_adapters import AisstreamMaritimeDataProvider, SampleMaritimeDataProvider


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
    assert snapshot.vessels[0].name == "GULF HORIZON"
    assert snapshot.vessels[0].cargo_inference is None
    assert any("partial live AIS coverage" in warning for warning in snapshot.warnings)


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
