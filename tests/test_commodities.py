from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.commodities_service import CommoditiesService, CommodityWorkspaceRequest
from src.application.runtime import build_runtime
from src.models.commodities import CommodityCoverageMetadata
from src.services.commodities_adapters import EiaCommoditiesDataProvider, SampleCommoditiesDataProvider


def test_commodity_coverage_rejects_unknown_status():
    with pytest.raises(ValueError, match="Unsupported commodities coverage status"):
        CommodityCoverageMetadata(
            coverage_status="tradable",
            provider_id="bad",
            provider_label="Bad",
            freshness_label="bad",
        )


def test_sample_commodities_workspace_contains_research_analytics():
    service = CommoditiesService(provider=SampleCommoditiesDataProvider())

    workspace = service.get_workspace(CommodityWorkspaceRequest(mode="energy", selected_instrument_id="CL"))

    assert workspace.mode == "energy"
    assert workspace.selected_instrument_id == "wti"
    assert workspace.coverage.coverage_status == "sample"
    assert workspace.coverage.supports_prices is True
    assert workspace.coverage.supports_curves is True
    assert workspace.coverage.supports_inventories is True
    assert {instrument.family for instrument in workspace.instruments} == {"energy", "metals"}
    assert len(workspace.market_summaries) == 8
    assert len(workspace.price_histories) == 8
    assert len(workspace.curves) == 8
    assert len(workspace.spreads) >= 6
    assert len(workspace.inventories) >= 6
    assert len(workspace.events) >= 2
    assert len(workspace.cross_domain_links) >= 3
    assert any("read-only research" in warning for warning in workspace.warnings)

    wti_curve = next(curve for curve in workspace.curves if curve.instrument_id == "wti")
    assert wti_curve.shape_label == "backwardation"
    assert wti_curve.front_spread is not None
    assert wti_curve.m1_m6_spread is not None
    assert wti_curve.roll_yield_proxy_pct is not None
    assert any("Roll-yield proxy" in warning for warning in wti_curve.warnings)

    crude_inventory = next(
        series for series in workspace.inventories if series.metadata.series_id == "us-commercial-crude-stocks"
    )
    assert crude_inventory.latest_value is not None
    assert crude_inventory.latest_change is not None
    assert crude_inventory.seasonal_percentile is not None
    assert crude_inventory.interpretation

    rich_spread = next(spread for spread in workspace.spreads if spread.definition.spread_id == "gold-silver-ratio")
    assert rich_spread.value is not None
    assert rich_spread.z_score is not None
    assert rich_spread.percentile is not None
    assert rich_spread.history


def test_eia_provider_without_key_degrades_to_sample_with_warning():
    provider = EiaCommoditiesDataProvider(api_key="", reference_provider=SampleCommoditiesDataProvider())

    snapshot = provider.get_snapshot()

    assert snapshot.coverage.coverage_status == "sample"
    assert "EIA_API_KEY" in snapshot.coverage.credential_env_vars
    assert any("EIA_API_KEY is not configured" in warning for warning in snapshot.warnings)
    assert snapshot.instruments
    assert snapshot.price_histories
    assert snapshot.curve_snapshots


def test_eia_provider_enriches_energy_inventory_with_official_series():
    def fake_fetch_json(url: str, params: dict[str, object] | None):
        del url, params
        return {
            "response": {
                "data": [
                    {"period": "2026-01-03", "value": 420000},
                    {"period": "2026-01-10", "value": 421500},
                    {"period": "2026-01-17", "value": 419750},
                ]
            }
        }

    provider = EiaCommoditiesDataProvider(
        api_key="test-key",
        reference_provider=SampleCommoditiesDataProvider(),
        fetch_json=fake_fetch_json,
    )

    snapshot = provider.get_snapshot(force_refresh=True)

    assert snapshot.coverage.coverage_status == "official_partial"
    assert snapshot.source_provider == "eia"
    assert any("EIA" in caveat for caveat in snapshot.coverage.caveats)
    crude = next(series for series in snapshot.inventory_series if series.metadata.series_id == "us-commercial-crude-stocks")
    assert crude.source_provider == "eia"
    assert crude.metadata.provider_series_id == "PET.WCESTUS1.W"
    assert [point.value for point in crude.points] == [420.0, 421.5, 419.75]
    assert crude.points[-1].change == -1.75


def test_commodities_api_routes_return_workspace_and_slices(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMODITIES_PROVIDER", "sample")
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        workspace_response = client.post(
            "/commodities/workspace",
            json={
                "mode": "curves_spreads",
                "selected_instrument_id": "wti",
                "force_refresh": False,
            },
        )
        assert workspace_response.status_code == 200
        workspace_payload = workspace_response.json()
        assert workspace_payload["mode"] == "curves_spreads"
        assert workspace_payload["coverage"]["coverage_status"] == "sample"
        assert len(workspace_payload["market_summaries"]) == 8
        assert len(workspace_payload["spreads"]) >= 6
        assert workspace_payload["cross_domain_links"]

        overview_response = client.get("/commodities/overview")
        assert overview_response.status_code == 200
        assert overview_response.json()["mode"] == "overview"

        curve_response = client.get("/commodities/curve", params={"instrument_id": "wti"})
        assert curve_response.status_code == 200
        assert curve_response.json()["curve"]["shape_label"] == "backwardation"

        spreads_response = client.get("/commodities/spreads")
        assert spreads_response.status_code == 200
        assert spreads_response.json()["spreads"]

        history_response = client.get("/commodities/price-history", params={"instrument_id": "gold"})
        assert history_response.status_code == 200
        assert history_response.json()["history"]["points"]

        missing_response = client.get("/commodities/curve", params={"instrument_id": "missing"})
        assert missing_response.status_code == 404
    finally:
        runtime.shutdown()


def test_commodities_copilot_context_uses_loaded_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMODITIES_PROVIDER", "sample")
    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        workspace = client.post(
            "/commodities/workspace",
            json={"mode": "overview", "selected_instrument_id": "wti", "force_refresh": False},
        ).json()
        response = client.post(
            "/copilot/research-card",
            json={
                "domain": "commodities",
                "prompt": "Frame the selected energy setup.",
                "context": {
                    "current_tab": "commodities",
                    "workspace_mode": "research",
                    "commodities_state": {"workspace": workspace},
                },
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["provider"] == "mock"
        assert payload["domain"] == "commodities"
        assert payload["response_id"].startswith("mock_commodities_")
        assert payload["card"]["title"].startswith("Commodities:")
        assert any(trace["tool_name"] == "get_commodities_workspace_summary" for trace in payload["tool_traces"])
        assert any(source["source_id"] == "commodities.workspace" for source in payload["sources"])
        assert any(source["source_id"] == "commodities.workspace.drilldown" for source in payload["sources"])
    finally:
        runtime.shutdown()
