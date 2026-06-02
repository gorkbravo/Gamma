from __future__ import annotations

from fastapi.testclient import TestClient
from datetime import datetime, timezone

import pandas as pd

from src.api.main import create_app
from src.api.session_auth import GAMMA_SESSION_HEADER
from src.api.schemas.crypto import CryptoWorkspaceRequestModel
from src.api.schemas.prediction_markets import PredictionMarketScreenerRequestModel
from src.api.schemas.research import StrategyLabAnalyzeRequestModel
from src.api.schemas.risk import RiskComputeRequestModel
from src.application.request_limits import (
    MAX_CRYPTO_WORKSPACE_LIMIT,
    MAX_PREDICTION_MARKET_LIMIT,
    MAX_PREDICTION_MARKET_VENUES,
    MAX_REQUEST_TEXT_CHARS,
    MAX_RISK_HORIZON_DAYS,
    MAX_RISK_MC_SIMULATIONS,
    MAX_STRATEGY_LAB_ROWS,
)
from src.application.runtime import build_runtime
from src.models.app_mode import ResearchScopeType
from src.models.prediction_markets import PredictionMarketFreshness, PredictionMarketRecord, PredictionProbabilityPoint
from src.models.provenance import FreshnessLabel
from src.services.research_market_data import ResearchHistoryResult
from src.models.crypto import (
    CryptoComparisonRecord,
    CryptoDexLiquiditySummary,
    CryptoFlowSummaryRecord,
    CryptoPricePoint,
    CryptoSyntheticPortfolioRecord,
    CryptoTokenRecord,
    CryptoWorkspaceResult,
)


def _build_test_client(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    app = create_app(runtime)
    return TestClient(app), runtime


class StubListedHistoryProvider:
    def load_instrument_history_result(self, instrument, lookback_days: int) -> ResearchHistoryResult:
        assert instrument.symbol == "MSFT"
        prices = pd.Series(
            [100.0, 101.0, 100.5, 102.0, 103.0, 104.0],
            index=pd.date_range("2026-01-02", periods=6, freq="B"),
        )
        return ResearchHistoryResult(
            series=prices,
            source_provider="fixture",
            source_label="Fixture listed history",
            origin="tests.api.equity_handoff",
            freshness_label=FreshnessLabel.HISTORICAL,
            warnings=[],
        )


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


def test_gamma_session_boundary_rejects_missing_or_invalid_tokens(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    app = create_app(runtime, session_token="expected-session")
    client = TestClient(app, headers={"X-Test-No-Gamma-Session": "1"})
    try:
        assert client.get("/health").status_code == 200

        status_response = client.get("/system/status")
        mutating_response = client.post("/system/market-data-mode", json={"market_data_mode": "live"})
        refresh_response = client.get("/news/latest", params={"force_refresh": "true"})
        invalid_response = client.get("/system/status", headers={GAMMA_SESSION_HEADER: "wrong-session"})
        valid_response = client.get("/system/status", headers={GAMMA_SESSION_HEADER: "expected-session"})

        assert status_response.status_code == 401
        assert status_response.json()["detail"] == "Missing or invalid Gamma session token."
        assert mutating_response.status_code == 401
        assert refresh_response.status_code == 401
        assert invalid_response.status_code == 401
        assert valid_response.status_code == 200
    finally:
        runtime.shutdown()


def test_gamma_cors_rejects_unknown_localhost_origin(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.options(
            "/system/status",
            headers={
                "Origin": "http://localhost:9999",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": GAMMA_SESSION_HEADER,
            },
        )
        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers
    finally:
        runtime.shutdown()


def test_research_v2_strategy_saved_and_compare_endpoints(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        strategy_response = client.post(
            "/research/strategy-lab/analyze",
            json={
                "name": "API Strategy",
                "date_column": "date",
                "value_column": "strategy",
                "benchmark_column": "benchmark",
                "rows": [
                    {"date": "2026-01-02", "strategy": 0.010, "benchmark": 0.004},
                    {"date": "2026-01-05", "strategy": -0.004, "benchmark": -0.002},
                    {"date": "2026-01-06", "strategy": 0.006, "benchmark": 0.003},
                    {"date": "2026-01-07", "strategy": 0.002, "benchmark": 0.001},
                    {"date": "2026-01-08", "strategy": -0.003, "benchmark": -0.004},
                    {"date": "2026-01-09", "strategy": 0.008, "benchmark": 0.005},
                    {"date": "2026-01-12", "strategy": 0.004, "benchmark": 0.002},
                    {"date": "2026-01-13", "strategy": 0.001, "benchmark": -0.001},
                ],
            },
        )
        assert strategy_response.status_code == 200
        strategy_payload = strategy_response.json()
        assert strategy_payload["source_provider"] == "uploaded_csv"
        assert strategy_payload["metrics"]["observation_count"] == 8
        assert strategy_payload["benchmark_points"]

        saved_response = client.post(
            "/research/saved",
            json={
                "object_type": "strategy_lab",
                "title": "Saved API Strategy",
                "payload": strategy_payload,
                "warnings": strategy_payload["warnings"],
                "source_provider": "uploaded_csv",
            },
        )
        assert saved_response.status_code == 200
        saved_payload = saved_response.json()
        saved_id = saved_payload["id"]

        list_response = client.get("/research/saved")
        assert list_response.status_code == 200
        assert [item["id"] for item in list_response.json()["items"]] == [saved_id]

        load_response = client.get(f"/research/saved/{saved_id}")
        assert load_response.status_code == 200
        assert load_response.json()["title"] == "Saved API Strategy"

        compare_response = client.post(
            "/research/compare-scenario/analyze",
            json={
                "left": {
                    "label": "Saved API Strategy",
                    "object_type": "strategy_lab",
                    "saved_research_id": saved_id,
                },
                "right": {
                    "label": "Benchmark",
                    "object_type": "benchmark",
                    "return_points": strategy_payload["benchmark_points"],
                },
            },
        )
        assert compare_response.status_code == 200
        compare_payload = compare_response.json()
        assert compare_payload["aligned_observation_count"] == 8
        assert compare_payload["left_observation_count"] == 8
        assert compare_payload["right_observation_count"] == 8
        assert compare_payload["overlap_start"]
        assert compare_payload["overlap_end"]
        assert compare_payload["relative_return"] is not None
        assert "historical analytics only" in " ".join(compare_payload["warnings"])

        delete_response = client.delete(f"/research/saved/{saved_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["success"] is True
        assert client.get(f"/research/saved/{saved_id}").status_code == 404
    finally:
        runtime.shutdown()


def test_strategy_lab_portfolio_compose_endpoint_accepts_signed_inline_legs(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        response = client.post(
            "/research/strategy-lab/portfolio-compose",
            json={
                "name": "Mixed Research Book",
                "benchmark_symbol": None,
                "lookback_days": 252,
                "legs": [
                    {
                        "label": "Long probability contract",
                        "asset_class": "prediction_contract",
                        "identifier": "PM:TEST-LONG",
                        "weight": 0.7,
                        "value_kind": "level",
                        "return_points": [
                            {"timestamp": "2026-01-02T00:00:00Z", "value": 0.50},
                            {"timestamp": "2026-01-05T00:00:00Z", "value": 0.52},
                            {"timestamp": "2026-01-06T00:00:00Z", "value": 0.51},
                            {"timestamp": "2026-01-07T00:00:00Z", "value": 0.55},
                            {"timestamp": "2026-01-08T00:00:00Z", "value": 0.57},
                            {"timestamp": "2026-01-09T00:00:00Z", "value": 0.58},
                        ],
                    },
                    {
                        "label": "Short hedge stream",
                        "asset_class": "custom_stream",
                        "identifier": "HEDGE",
                        "weight": -0.3,
                        "value_kind": "return",
                        "return_points": [
                            {"timestamp": "2026-01-05T00:00:00Z", "value": 0.01},
                            {"timestamp": "2026-01-06T00:00:00Z", "value": 0.01},
                            {"timestamp": "2026-01-07T00:00:00Z", "value": -0.01},
                            {"timestamp": "2026-01-08T00:00:00Z", "value": 0.00},
                            {"timestamp": "2026-01-09T00:00:00Z", "value": 0.02},
                        ],
                    },
                ],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["origin"] == "research_service.strategy_lab.portfolio_compose"
        assert payload["metrics"]["observation_count"] == 5
        assert payload["leg_contributions"]["Long probability contract"] is not None
        assert payload["leg_contributions"]["Short hedge stream"] < 0
        assert "read-only research" in " ".join(payload["warnings"])
    finally:
        runtime.shutdown()


def test_strategy_lab_resolve_handoff_endpoint_returns_prediction_market_draft(tmp_path):
    client, runtime = _build_test_client(tmp_path)

    class StubPredictionMarketService:
        def get_market_detail(self, market_id: str):
            return _prediction_market_record() if market_id == "polymarket:fed-cut" else None

        def get_probability_history(self, market_id: str):
            assert market_id == "polymarket:fed-cut"
            return [
                PredictionProbabilityPoint(timestamp=datetime(2026, 3, day, tzinfo=timezone.utc), probability=probability)
                for day, probability in enumerate([0.51, 0.52, 0.5, 0.54, 0.55, 0.56], start=1)
            ]

    runtime.prediction_market_service = StubPredictionMarketService()
    try:
        request_body = {
            "handoff": {
                "source_tab": "prediction_markets",
                "source_mode": "detail",
                "intended_target_tab": "strategy_lab",
                "intended_target_mode": "composer",
                "selected_entity": {
                    "entity_type": "prediction_market_contract",
                    "label": "Will the Fed cut rates in March?",
                    "normalized_id": "polymarket:fed-cut",
                    "provider_id": "fed-cut",
                    "native_id": "0xabc",
                    "metadata": {"venue": "polymarket"},
                },
                "resolver_capability": "return_leg",
                "asset_class": "prediction_market",
                "value_kind": "probability",
                "default_side": "long_yes",
                "default_weight": 0.1,
                "selected_timeframe": None,
                "provider": "polymarket",
                "source": {"origin": "fixture"},
                "warnings": [],
                "normalized_ids": {"market_id": "polymarket:fed-cut"},
                "timestamp": "2026-03-01T00:00:00Z",
            }
        }
        response = client.post(
            "/research/strategy-lab/resolve-handoff",
            json=request_body,
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "resolved"
        assert payload["composer_draft_leg"]["asset_class"] == "prediction_contract"
        assert payload["composer_draft_leg"]["value_kind"] == "level"
        assert payload["composer_draft_leg"]["return_points"][0]["value"] == 0.51
        assert payload["provenance"]["transformation"] == "long_yes_probability_return"
        assert "research proxy" in " ".join(payload["warnings"])

        no_request = {"handoff": {**request_body["handoff"], "default_side": "long_no"}}
        no_response = client.post("/research/strategy-lab/resolve-handoff", json=no_request)
        assert no_response.status_code == 200
        no_result = no_response.json()
        assert no_result["composer_draft_leg"]["label"].endswith("| NO probability")
        assert abs(no_result["composer_draft_leg"]["return_points"][0]["value"] - 0.49) < 1e-9
        assert no_result["provenance"]["transformation"] == "long_no_probability_return"
    finally:
        runtime.shutdown()


def test_strategy_lab_resolve_handoff_endpoint_returns_equity_draft(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    runtime.research_service.provider = StubListedHistoryProvider()
    try:
        response = client.post(
            "/research/strategy-lab/resolve-handoff",
            json={
                "handoff": {
                    "source_tab": "equity_research",
                    "source_mode": "scope_analysis",
                    "intended_target_tab": "strategy_lab",
                    "intended_target_mode": "composer",
                    "selected_entity": {
                        "entity_type": "equity_symbol",
                        "label": "Microsoft",
                        "normalized_id": "MSFT",
                        "provider_id": "MSFT",
                        "native_id": "MSFT",
                        "metadata": {"symbol": "MSFT"},
                    },
                    "resolver_capability": "return_leg",
                    "asset_class": "equity",
                    "value_kind": "return",
                    "default_side": "long",
                    "default_weight": 0.1,
                    "selected_timeframe": None,
                    "provider": "fixture",
                    "source": {"origin": "fixture"},
                    "warnings": [],
                    "normalized_ids": {"symbol": "MSFT"},
                    "timestamp": "2026-03-01T00:00:00Z",
                }
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "resolved"
        assert payload["composer_draft_leg"]["asset_class"] == "equity"
        assert payload["composer_draft_leg"]["identifier"] == "MSFT"
        assert payload["composer_draft_leg"]["value_kind"] == "return"
        assert len(payload["composer_draft_leg"]["return_points"]) == 5
        assert payload["provider_summary"] == "Fixture listed history"
        assert payload["provenance"]["transformation"] == "listed_equity_return_stream"
        assert "read-only Strategy Lab analysis" in " ".join(payload["warnings"])
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
        assert "correlation_matrix" in payload
        assert "assets" in payload["correlation_matrix"]
    finally:
        runtime.shutdown()


def test_expensive_request_models_reject_oversized_payloads(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        snapshot = client.get("/portfolio/snapshot").json()
        risk_response = client.post(
            "/risk/compute",
            json={
                "snapshot": snapshot,
                "mc_num_simulations": MAX_RISK_MC_SIMULATIONS + 1,
            },
        )
        horizon_response = client.post(
            "/risk/compute",
            json={
                "snapshot": snapshot,
                "horizon_days": MAX_RISK_HORIZON_DAYS + 1,
            },
        )
        strategy_response = client.post(
            "/research/strategy-lab/analyze",
            json={
                "rows": [{"date": "2026-01-02", "return": 0.01}]
                * (MAX_STRATEGY_LAB_ROWS + 1),
            },
        )
        crypto_response = client.post(
            "/crypto/workspace",
            json={"query": "x" * (MAX_REQUEST_TEXT_CHARS + 1)},
        )
        prediction_response = client.post(
            "/prediction-markets/screener",
            json={"limit": MAX_PREDICTION_MARKET_LIMIT + 1},
        )

        assert RiskComputeRequestModel(
            snapshot=snapshot,
            mc_num_simulations=MAX_RISK_MC_SIMULATIONS,
            horizon_days=MAX_RISK_HORIZON_DAYS,
        )
        assert StrategyLabAnalyzeRequestModel(
            rows=[{"date": "2026-01-02", "return": 0.01}] * MAX_STRATEGY_LAB_ROWS
        )
        assert CryptoWorkspaceRequestModel(query="x" * 128, limit=MAX_CRYPTO_WORKSPACE_LIMIT)
        assert PredictionMarketScreenerRequestModel(
            query="x" * MAX_REQUEST_TEXT_CHARS,
            venues=["polymarket"] * MAX_PREDICTION_MARKET_VENUES,
            limit=MAX_PREDICTION_MARKET_LIMIT,
        )

        assert risk_response.status_code == 422
        assert horizon_response.status_code == 422
        assert strategy_response.status_code == 422
        assert crypto_response.status_code == 422
        assert prediction_response.status_code == 422
    finally:
        runtime.shutdown()


def test_iv_surface_and_diagnostics_endpoints(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    try:
        iv_response = client.get("/iv/surface", params={"symbol": "SPY"})
        iv_session_start = client.post("/iv/session/start", json={"symbol": "SPY", "market_data_mode": "delayed"})
        if runtime.iv_service._engine is not None:
            runtime.iv_service._engine._add_message("Option subscription failed SPY test contract")
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
        assert iv_payload["contracts"]
        assert iv_payload["pairs"]
        assert {row["right"] for row in iv_payload["contracts"]} == {"C", "P"}
        assert iv_payload["collection"]["configured_market_data_line_budget"] >= 10
        assert iv_payload["collection"]["option_market_data_line_budget"] >= 1
        assert iv_payload["quality"]["pairs_with_both_sides"] > 0
        assert iv_payload["quality"]["call_contract_count"] > 0
        assert iv_payload["quality"]["put_contract_count"] > 0
        assert iv_payload["pricing_assumptions"]["fallback_greeks_methodology"]
        assert iv_payload["expiry_analytics"]
        assert iv_payload["contracts"][0]["derived_greeks"] is not None

        assert iv_session_start.status_code == 200
        assert iv_session_start.json()["active_symbol"] == "SPY"
        assert iv_session_status.status_code == 200
        assert "surface" in iv_session_status.json()
        assert "Option subscription failed SPY test contract" in iv_session_status.json()["messages"]
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


def test_crypto_workspace_and_token_endpoints(tmp_path):
    client, runtime = _build_test_client(tmp_path)

    class StubCryptoService:
        def get_workspace(self, request):
            del request
            return CryptoWorkspaceResult(tokens=[_crypto_token()], narratives=[], warnings=[])

        def get_token_detail(self, token_id: str, *, force_refresh: bool = False):
            del force_refresh
            return _crypto_token() if token_id == "solana" else None

        def get_price_history(self, token_id: str, *, days: int = 30, force_refresh: bool = False):
            del force_refresh
            if token_id != "solana":
                return []
            return [
                CryptoPricePoint(
                    timestamp=_crypto_token().retrieved_at,
                    price=150.0,
                    market_cap=75_000_000_000.0,
                    total_volume=4_500_000_000.0,
                    source_provider="coingecko",
                    retrieved_at=_crypto_token().retrieved_at,
                    origin=f"coingecko.market_chart.{days}",
                )
            ]

        def get_dex_liquidity(self, token_id: str, *, force_refresh: bool = False):
            del force_refresh
            if token_id != "solana":
                return None
            return CryptoDexLiquiditySummary(
                token_id="solana",
                lookup_strategy="contract_lookup",
                matched_networks=["solana"],
                total_reserve_usd=180_000_000.0,
                total_volume_24h=45_000_000.0,
                total_buys_24h=9_000,
                total_sells_24h=8_700,
                total_buyers_24h=5_200,
                total_sellers_24h=5_100,
                dominant_dex="raydium",
                warnings=[],
                source_provider="geckoterminal",
                retrieved_at=_crypto_token().retrieved_at,
                origin="geckoterminal.liquidity_summary",
            )

        def get_comparison(
            self,
            token_id: str,
            *,
            target_token_id: str | None = None,
            basket_id: str | None = None,
            force_refresh: bool = False,
        ):
            del target_token_id, basket_id, force_refresh
            if token_id != "solana":
                return None
            return CryptoComparisonRecord(
                subject_token_id="solana",
                target_kind="basket",
                target_id="layer-1",
                target_label="Layer 1",
                shared_categories=["Layer 1"],
                subject_price_change_pct_24h=4.2,
                target_price_change_pct_24h=2.1,
                price_gap_pct_24h=2.1,
                subject_price_change_pct_7d=10.5,
                target_price_change_pct_7d=5.2,
                price_gap_pct_7d=5.3,
                subject_price_change_pct_30d=18.2,
                target_price_change_pct_30d=11.4,
                price_gap_pct_30d=6.8,
                subject_market_cap=75_000_000_000.0,
                target_market_cap=900_000_000_000.0,
                market_cap_ratio=0.083,
                subject_turnover_ratio_24h=0.09,
                target_turnover_ratio_24h=0.06,
                turnover_gap=0.03,
                summary="Solana is outperforming the Layer 1 basket with hotter turnover.",
                source_provider="gamma",
                retrieved_at=_crypto_token().retrieved_at,
                origin="gamma.crypto.comparison.basket",
            )

        def get_flow_summary(self, token_id: str, *, force_refresh: bool = False):
            del force_refresh
            if token_id != "solana":
                return None
            return CryptoFlowSummaryRecord(
                token_id="solana",
                pool_count=2,
                matched_networks=["solana"],
                total_reserve_usd=180_000_000.0,
                total_volume_24h=45_000_000.0,
                dex_volume_share_of_total_volume=0.35,
                reserve_to_market_cap_ratio=0.0024,
                top_pool_reserve_share=0.62,
                top_pool_volume_share=0.58,
                buy_pressure_pct=57.3,
                active_trader_proxy_24h=10_300,
                buy_sell_ratio=1.03,
                participant_balance_ratio=1.02,
                reserve_volume_ratio_24h=4.0,
                slippage_proxy_label="deep",
                liquidity_concentration_label="moderately concentrated",
                flow_signal_label="accumulation",
                summary="Solana flow is constructive with deep pool support.",
                warnings=[],
                source_provider="gamma",
                retrieved_at=_crypto_token().retrieved_at,
                origin="gamma.crypto.flow_summary",
            )

        def analyze_synthetic_portfolio(self, request):
            del request
            return CryptoSyntheticPortfolioRecord(
                lookback_days=30,
                benchmark_token_id="bitcoin",
                benchmark_label="Bitcoin",
                constituents=[],
                narrative_exposures=[],
                portfolio_points=[],
                benchmark_points=[],
                cumulative_return_pct=7.5,
                benchmark_return_pct=5.1,
                relative_return_pct=2.4,
                annualized_volatility_pct=62.0,
                weighted_turnover_ratio_24h=0.08,
                weighted_market_cap=40_000_000_000.0,
                concentration_hhi=0.5,
                effective_positions=2.0,
                summary="Synthetic basket stub.",
                warnings=[],
                source_provider="gamma",
                retrieved_at=_crypto_token().retrieved_at,
                origin="gamma.crypto.synthetic_portfolio",
            )

    runtime.crypto_service = StubCryptoService()
    try:
        workspace = client.post("/crypto/workspace", json={"query": "sol", "sort_by": "screen_score_desc"})
        detail = client.get("/crypto/tokens/solana")
        history = client.get("/crypto/tokens/solana/history", params={"days": 30})
        liquidity = client.get("/crypto/tokens/solana/liquidity")
        flow = client.get("/crypto/tokens/solana/flow")
        comparison = client.get("/crypto/tokens/solana/comparison")
        synthetic = client.post(
            "/crypto/portfolio",
            json={"positions": [{"identifier": "SOL", "weight": 0.6}, {"identifier": "UNI", "weight": 0.4}]},
        )

        assert workspace.status_code == 200
        assert workspace.json()["tokens"][0]["token_id"] == "solana"
        assert detail.status_code == 200
        assert detail.json()["name"] == "Solana"
        assert history.status_code == 200
        assert history.json()["points"][0]["price"] == 150.0
        assert liquidity.status_code == 200
        assert liquidity.json()["dominant_dex"] == "raydium"
        assert flow.status_code == 200
        assert flow.json()["flow_signal_label"] == "accumulation"
        assert comparison.status_code == 200
        assert comparison.json()["target_kind"] == "basket"
        assert synthetic.status_code == 200
        assert synthetic.json()["benchmark_token_id"] == "bitcoin"
    finally:
        runtime.shutdown()


def _crypto_token() -> CryptoTokenRecord:
    from datetime import datetime, timezone

    return CryptoTokenRecord(
        token_id="solana",
        symbol="sol",
        name="Solana",
        image_url=None,
        chain="Solana",
        asset_platform_id="solana",
        geckoterminal_network="solana",
        contract_address=None,
        market_cap_rank=6,
        current_price=150.0,
        market_cap=75_000_000_000.0,
        fully_diluted_valuation=90_000_000_000.0,
        total_volume=4_500_000_000.0,
        circulating_supply=500_000_000.0,
        total_supply=600_000_000.0,
        max_supply=None,
        price_change_pct_24h=4.2,
        price_change_pct_7d=10.5,
        price_change_pct_30d=18.2,
        market_cap_change_pct_24h=4.0,
        high_24h=155.0,
        low_24h=143.0,
        homepage_url="https://solana.com",
        description="High-throughput smart-contract network.",
        categories=["Layer 1"],
        turnover_ratio_24h=0.09,
        fdv_premium_ratio=0.2,
        screen_score=77.4,
        screen_rationale="turnover 0.09x | 24H volume $4.5B",
        source_provider="coingecko",
        retrieved_at=datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc),
        origin="coingecko.markets",
        transformation_note="Gamma screen score combines size, liquidity, turnover, momentum, and FDV premium heuristics.",
    )


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
