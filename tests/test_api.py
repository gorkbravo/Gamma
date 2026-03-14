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
        assert runtime.app_context is None
        assert runtime.research_provider.context is None
        health = client.get("/health")
        status = client.get("/system/status")
        mode_change = client.post("/system/market-data-mode", json={"market_data_mode": "live"})
        connection_toggle = client.post("/system/connection/toggle", json={})
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert status.status_code == 200
        payload = status.json()
        assert payload["healthy"] is True
        assert payload["mock_mode"] is True
        assert payload["connection"]["connected"] is True
        assert payload["base_currency"] == runtime.base_currency
        assert mode_change.status_code == 200
        assert mode_change.json()["market_data_mode"] == "live"
        next_currency = "EUR" if runtime.base_currency != "EUR" else "USD"
        base_currency_change = client.post("/system/base-currency", json={"base_currency": next_currency})
        assert base_currency_change.status_code == 200
        base_currency_payload = base_currency_change.json()
        assert base_currency_payload["base_currency"] == next_currency
        assert any("Local portfolio history was cleared" in line for line in base_currency_payload["lines"])
        assert connection_toggle.status_code == 200
        assert connection_toggle.json()["connection"]["status_text"] == "Status: Mock"
    finally:
        runtime.shutdown()


def test_portfolio_snapshot_and_history_endpoints(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        snapshot_response = client.get("/portfolio/snapshot")
        assert snapshot_response.status_code == 200
        snapshot_payload = snapshot_response.json()
        assert len(snapshot_payload["positions"]) >= 1

        performance_response = client.post(
            "/portfolio/performance",
            json={
                "snapshot": snapshot_payload,
                "benchmark_symbol": "SPY",
                "lookback_days": 252,
            },
        )
        assert performance_response.status_code == 200
        performance_payload = performance_response.json()
        assert performance_payload["benchmark_symbol"] == "SPY"
        assert "performance_points" in performance_payload

        history_response = client.get("/portfolio/history")
        assert history_response.status_code == 200
        history_payload = history_response.json()
        assert history_payload["source"] == "local_history_store"
        assert len(history_payload["points"]) >= 1

        clear_response = client.post("/portfolio/history/clear")
        assert clear_response.status_code == 200
        assert clear_response.json()["success"] is True
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
        assert payload["primary_symbol"] == "AAPL"
        assert payload["summary"]["total_return"] is not None
        assert payload["structure"]["aligned_symbol_count"] == 1
        assert payload["structure"]["top_weight"] == 1.0
        assert payload["coverage"]["available_symbols"] == ["AAPL"]
        assert payload["coverage"]["benchmark_overlap_count"] > 0
        assert payload["constituents"][0]["symbol"] == "AAPL"
        assert payload["constituents"][0]["instrument_id"] is not None
        assert payload["weights"][0]["display_symbol"] == "AAPL"
        assert payload["snapshot"]["positions"][0]["symbol"] == "AAPL"
        assert payload["snapshot"]["positions"][0]["instrument_id"] is not None
    finally:
        runtime.shutdown()


def test_research_context_replaces_scope_after_mode_switch(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        single_response = client.post(
            "/research/analyze",
            json={
                "scope_type": ResearchScopeType.SINGLE_TICKER.value,
                "primary_symbol": "AAPL",
                "benchmark_symbol": "MSFT",
                "lookback_days": 252,
            },
        )
        assert single_response.status_code == 200

        diagnostics_after_single = client.get("/diagnostics")
        assert diagnostics_after_single.status_code == 200
        assert "AAPL" in diagnostics_after_single.json()["cached_symbols"]
        assert diagnostics_after_single.json()["research_scope_type"] == ResearchScopeType.NONE.value
        assert diagnostics_after_single.json()["research_primary_symbol"] is None
        assert diagnostics_after_single.json()["research_synthetic_count"] == 0

        synthetic_response = client.post(
            "/research/analyze",
            json={
                "scope_type": ResearchScopeType.SYNTHETIC_PORTFOLIO.value,
                "synthetic_positions": [
                    {"symbol": "AAPL", "weight": 0.5},
                    {"symbol": "MSFT", "weight": 0.3},
                    {"symbol": "SAP", "weight": 0.2},
                ],
                "benchmark_symbol": "SPY",
                "lookback_days": 252,
            },
        )
        assert synthetic_response.status_code == 200
        synthetic_payload = synthetic_response.json()
        assert synthetic_payload["scope_type"] == ResearchScopeType.SYNTHETIC_PORTFOLIO.value
        assert synthetic_payload["primary_symbol"] is None
        assert [row["symbol"] for row in synthetic_payload["weights"]] == ["AAPL", "MSFT", "SAP"]
        assert len(synthetic_payload["snapshot"]["positions"]) == 3

        diagnostics_after_synthetic = client.get("/diagnostics")
        assert diagnostics_after_synthetic.status_code == 200
        assert set(diagnostics_after_synthetic.json()["cached_symbols"]) >= {"AAPL", "MSFT", "SAP"}
        assert diagnostics_after_synthetic.json()["research_scope_type"] == ResearchScopeType.NONE.value
        assert diagnostics_after_synthetic.json()["research_primary_symbol"] is None
        assert diagnostics_after_synthetic.json()["research_synthetic_count"] == 0
    finally:
        runtime.shutdown()


def test_research_analyze_rejects_invalid_synthetic_payloads(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        duplicate_response = client.post(
            "/research/analyze",
            json={
                "scope_type": ResearchScopeType.SYNTHETIC_PORTFOLIO.value,
                "synthetic_positions": [
                    {"symbol": "AAPL", "weight": 0.5},
                    {"symbol": "AAPL", "weight": 0.5},
                ],
            },
        )
        assert duplicate_response.status_code == 422
        assert "Duplicate symbol in synthetic portfolio: AAPL" in duplicate_response.json()["detail"]

        negative_response = client.post(
            "/research/analyze",
            json={
                "scope_type": ResearchScopeType.SYNTHETIC_PORTFOLIO.value,
                "synthetic_positions": [
                    {"symbol": "AAPL", "weight": -1},
                ],
            },
        )
        assert negative_response.status_code == 422
        assert "Synthetic weight must be positive for AAPL" in negative_response.json()["detail"]
    finally:
        runtime.shutdown()


def test_research_analyze_accepts_distinct_instruments_with_same_symbol(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/research/analyze",
            json={
                "scope_type": ResearchScopeType.SYNTHETIC_PORTFOLIO.value,
                "synthetic_positions": [
                    {
                        "symbol": "AAPL",
                        "weight": 0.6,
                        "instrument_id": "research:aapl-us",
                        "provider": "research",
                        "provider_id": "aapl-us",
                        "exchange": "SMART",
                        "currency": "USD",
                    },
                    {
                        "symbol": "AAPL",
                        "weight": 0.4,
                        "instrument_id": "research:aapl-eu",
                        "provider": "research",
                        "provider_id": "aapl-eu",
                        "exchange": "AEB",
                        "currency": "EUR",
                    },
                ],
                "benchmark_symbol": "SPY",
                "lookback_days": 252,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert [row["instrument_id"] for row in payload["weights"]] == ["research:aapl-us", "research:aapl-eu"]
        assert [row["symbol"] for row in payload["weights"]] == ["AAPL", "AAPL"]
        assert len(payload["constituents"]) == 2
        assert len(payload["snapshot"]["positions"]) == 2
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
        assert "monte_carlo" in payload
        assert "fan_percentiles" in payload["monte_carlo"]
    finally:
        runtime.shutdown()


def test_iv_surface_and_diagnostics_endpoints(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        iv_response = client.get("/iv/surface", params={"symbol": "SPY"})
        iv_session_start = client.post("/iv/session/start", json={"symbol": "SPY", "market_data_mode": "delayed"})
        iv_session_status = client.get("/iv/session")
        iv_session_stop = client.post("/iv/session/stop")
        diagnostics_response = client.get("/diagnostics")
        diagnostics_run = client.post("/diagnostics/run")
        subscribe_response = client.post("/system/account-subscribe")
        assert iv_response.status_code == 200
        iv_payload = iv_response.json()
        assert iv_payload["snapshot_available"] is True
        assert iv_payload["points"] > 0
        assert len(iv_payload["expiries"]) > 0

        assert iv_session_start.status_code == 200
        assert iv_session_start.json()["active_symbol"] == "SPY"
        assert iv_session_status.status_code == 200
        assert "surface" in iv_session_status.json()
        assert iv_session_stop.status_code == 200
        assert iv_session_stop.json()["running"] is False

        assert diagnostics_response.status_code == 200
        diagnostics_payload = diagnostics_response.json()
        assert diagnostics_payload["mock_mode"] is True
        assert "history_cache" in diagnostics_payload
        assert diagnostics_payload["local_history_path"]
        assert diagnostics_payload["research_scope_type"] == ResearchScopeType.NONE.value

        assert diagnostics_run.status_code == 200
        assert diagnostics_run.json()["success"] is True
        assert subscribe_response.status_code == 200
        assert subscribe_response.json()["success"] is True
    finally:
        runtime.shutdown()
