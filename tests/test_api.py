from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.runtime import build_runtime
from src.models.app_mode import ResearchScopeType


def _build_test_client(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    app = create_app(runtime)
    return TestClient(app), runtime


def test_health_and_system_status_endpoints(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        health = client.get("/health")
        status = client.get("/system/status")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert status.status_code == 200
        payload = status.json()
        assert payload["healthy"] is True
        assert payload["mock_mode"] is True
        assert payload["connection"]["connected"] is True
        assert payload["base_currency"] == runtime.base_currency
    finally:
        runtime.shutdown()


def test_portfolio_snapshot_and_history_endpoints(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        snapshot_response = client.get("/portfolio/snapshot")
        assert snapshot_response.status_code == 200
        snapshot_payload = snapshot_response.json()
        assert len(snapshot_payload["positions"]) >= 1

        history_response = client.get("/portfolio/history")
        assert history_response.status_code == 200
        history_payload = history_response.json()
        assert history_payload["source"] == "local_history_store"
        assert len(history_payload["points"]) >= 1
    finally:
        runtime.shutdown()


def test_research_analyze_endpoint(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/research/analyze",
            json={
                "scope_type": ResearchScopeType.SINGLE_TICKER.value,
                "primary_symbol": "AAPL",
                "benchmark_symbol": "MSFT",
                "lookback_days": 252,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["scope_type"] == ResearchScopeType.SINGLE_TICKER.value
        assert payload["observations_count"] > 0
        assert payload["summary"]["total_return"] is not None
        assert payload["snapshot"]["positions"][0]["symbol"] == "AAPL"
    finally:
        runtime.shutdown()


def test_risk_compute_endpoint(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        snapshot = client.get("/portfolio/snapshot").json()
        response = client.post(
            "/risk/compute",
            json={
                "snapshot": snapshot,
                "alpha": 0.95,
                "lookback_days": 252,
                "horizon_days": 1,
                "mc_horizon_days": 10,
                "mc_simulation_model": "Gaussian",
                "mc_num_simulations": 500,
                "beta_window": 63,
                "benchmark_symbol": "AAPL",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["metrics"]["historical_var"] is not None
        assert payload["metrics"]["portfolio_value"] > 0
        assert len(payload["contributions"]) >= 1
    finally:
        runtime.shutdown()


def test_iv_surface_and_diagnostics_endpoints(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        iv_response = client.get("/iv/surface", params={"symbol": "SPY"})
        diagnostics_response = client.get("/diagnostics")
        assert iv_response.status_code == 200
        iv_payload = iv_response.json()
        assert iv_payload["snapshot_available"] is True
        assert iv_payload["points"] > 0
        assert len(iv_payload["expiries"]) > 0

        assert diagnostics_response.status_code == 200
        diagnostics_payload = diagnostics_response.json()
        assert diagnostics_payload["mock_mode"] is True
        assert "history_cache" in diagnostics_payload
        assert diagnostics_payload["local_history_path"]
    finally:
        runtime.shutdown()
