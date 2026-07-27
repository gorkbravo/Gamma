from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.runtime import build_runtime
from src.models.portfolio import PortfolioSnapshot, PositionItem
from src.utils.time import now_utc


def _build_client(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    return TestClient(create_app(runtime)), runtime


def _live_snapshot(
    *,
    summary: dict[str, str] | None = None,
    positions: list[PositionItem] | None = None,
    warnings: list[str] | None = None,
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=now_utc(),
        base_currency="USD",
        account_summary=dict(summary or {}),
        positions=list(positions or []),
        total_market_value=100.0 if positions else None,
        total_cash=25.0 if summary else None,
        net_liquidation=125.0 if summary else None,
        warnings=list(warnings or []),
    )


def _position(symbol: str = "LMT") -> PositionItem:
    return PositionItem(
        symbol=symbol,
        sec_type="STK",
        currency="USD",
        quantity=1.0,
        avg_cost=90.0,
        market_price=100.0,
        market_value=100.0,
        unrealized_pnl=10.0,
        base_market_value=100.0,
        provider="ibkr",
    )


def test_portfolio_api_exposes_snapshot_history_performance_provenance_and_coverage(
    tmp_path,
):
    client, runtime = _build_client(tmp_path)
    try:
        snapshot_response = client.get("/portfolio/snapshot")
        assert snapshot_response.status_code == 200
        snapshot = snapshot_response.json()
        assert snapshot["state"] == "ready"
        assert snapshot["source_provider"] == "mock"
        assert snapshot["freshness_label"] == "mocked"
        assert snapshot["retrieved_at"]
        assert snapshot["origin"] == "gamma.portfolio.snapshot"
        assert snapshot["quote_mode"] == "Snapshot"
        priced_position_count = sum(
            1 for position in snapshot["positions"] if position["sec_type"] != "CASH"
        )
        assert snapshot["requested_position_count"] == priced_position_count
        assert snapshot["quoted_position_count"] == priced_position_count
        assert snapshot["missing_quote_count"] == 0
        assert snapshot["history_store_health"]["status"] == "ready"

        history_response = client.get("/portfolio/history")
        assert history_response.status_code == 200
        history = history_response.json()
        assert history["state"] == "ready"
        assert history["source_provider"] == "local_history_store"
        assert history["freshness_label"] == "historical"
        assert history["health"]["point_count"] == 1
        assert history["health"]["base_currency"] == runtime.base_currency
        assert "not a broker backfill" in history["transformation_note"].lower()

        performance_response = client.post(
            "/portfolio/performance",
            json={
                "snapshot": snapshot,
                "benchmark_symbol": "SPY",
                "lookback_days": 252,
            },
        )
        assert performance_response.status_code == 200
        performance = performance_response.json()
        assert performance["state"] in {"ready", "partial"}
        assert performance["source_provider"] == "gamma"
        assert performance["freshness_label"] == "derived"
        assert performance["history_source"] == "constituent_history"
        assert performance["history_source_provider"] == "mock"
        assert performance["history_freshness_label"] == "mocked"
        assert performance["requested_position_count"] == priced_position_count
        assert performance["covered_position_count"] == priced_position_count
        assert performance["history_coverage_ratio"] == pytest.approx(1.0)
        assert performance["history_point_count"] == len(performance["performance_points"])
        assert performance["benchmark_source_provider"] == "mock"
        assert performance["benchmark_freshness_label"] == "historical"
        assert performance["transformation_note"]
    finally:
        runtime.shutdown()


@pytest.mark.parametrize(
    ("summary", "positions", "warnings", "expected_state"),
    [
        ({}, [], ["IBKR not connected"], "unavailable"),
        ({}, [], ["Account summary unavailable", "No positions returned from IBKR"], "unavailable"),
        ({"NetLiquidation:USD": "125"}, [], ["No positions in account"], "empty"),
        (
            {"NetLiquidation:USD": "125"},
            [_position()],
            ["Snapshot quote missing for LMT"],
            "partial",
        ),
    ],
)
def test_snapshot_api_distinguishes_disconnected_subscription_empty_and_partial_states(
    tmp_path,
    summary,
    positions,
    warnings,
    expected_state,
):
    client, runtime = _build_client(tmp_path)
    try:
        runtime.client.mock = False
        runtime.client.is_connected = lambda: "IBKR not connected" not in warnings
        runtime.client.account_subscription_usable = lambda: bool(summary)
        runtime.client.fetch_snapshot = lambda *args, **kwargs: _live_snapshot(
            summary=summary,
            positions=positions,
            warnings=warnings,
        )

        response = client.get("/portfolio/snapshot")
        assert response.status_code == 200
        payload = response.json()
        assert payload["state"] == expected_state
        assert payload["source_provider"] == "ibkr"
        if expected_state == "partial":
            assert payload["complete"] is False
            assert payload["requested_position_count"] == 1
            assert payload["quoted_position_count"] == 0
            assert payload["missing_quote_count"] == 1
            assert payload["missing_quote_symbols"] == ["LMT"]
        if expected_state == "empty":
            assert payload["account_summary_available"] is True
            assert payload["account_subscription_usable"] is True
    finally:
        runtime.shutdown()


def test_performance_benchmark_failure_uses_explicit_cash_fallback_without_losing_positions(
    tmp_path,
):
    client, runtime = _build_client(tmp_path)
    try:
        snapshot = client.get("/portfolio/snapshot").json()

        def cash_benchmark(*, target_index, **kwargs):
            del kwargs
            return (
                pd.Series(1.0, index=target_index),
                "cash_0",
                ["No benchmark data for BROKEN; using Cash (0%) benchmark"],
            )

        runtime.portfolio_service.build_benchmark = cash_benchmark
        response = client.post(
            "/portfolio/performance",
            json={
                "snapshot": snapshot,
                "benchmark_symbol": "BROKEN",
                "lookback_days": 252,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["state"] == "partial"
        assert payload["performance_points"]
        assert payload["benchmark_points"]
        assert payload["benchmark_source"] == "cash_0"
        assert payload["benchmark_source_provider"] == "gamma_cash_0"
        assert payload["benchmark_freshness_label"] == "derived"
        assert "zero-return fallback" in payload["benchmark_transformation_note"]
    finally:
        runtime.shutdown()


def test_snapshot_cached_quote_is_separate_from_truly_missing_quote_coverage(tmp_path):
    client, runtime = _build_client(tmp_path)
    try:
        runtime.client.mock = False
        runtime.client.is_connected = lambda: True
        runtime.client.account_subscription_usable = lambda: True
        runtime.client.fetch_snapshot = lambda *args, **kwargs: _live_snapshot(
            summary={"NetLiquidation:USD": "125"},
            positions=[_position()],
            warnings=["Snapshot quote missing for LMT; using cached value"],
        )

        response = client.get("/portfolio/snapshot")
        assert response.status_code == 200
        payload = response.json()
        assert payload["state"] == "partial"
        assert payload["freshness_label"] == "stale"
        assert payload["requested_position_count"] == 1
        assert payload["quoted_position_count"] == 0
        assert payload["cached_quote_count"] == 1
        assert payload["cached_quote_symbols"] == ["LMT"]
        assert payload["missing_quote_count"] == 0
        assert payload["missing_quote_symbols"] == []
        assert (
            payload["quoted_position_count"]
            + payload["cached_quote_count"]
            + payload["missing_quote_count"]
            == payload["requested_position_count"]
        )
    finally:
        runtime.shutdown()


def test_performance_drains_provider_cache_warnings_and_labels_stale_history(tmp_path):
    client, runtime = _build_client(tmp_path)
    try:
        snapshot = client.get("/portfolio/snapshot").json()
        provider = runtime.portfolio_service.data_provider
        runtime.client.mock = False

        def load_with_stale_warning(loaded_snapshot, lookback_days):
            del lookback_days
            prices = {}
            missing = []
            for position in loaded_snapshot.positions:
                history = runtime.client.mock_service.load_history(position.symbol)
                if history is None:
                    missing.append(position.resolved_display_symbol())
                else:
                    prices[position.resolved_instrument_id()] = history
            provider._last_history_warnings.append(
                "Using stale cached constituent history after provider timeout."
            )
            return prices, missing

        provider.load_prices = load_with_stale_warning
        response = client.post(
            "/portfolio/performance",
            json={
                "snapshot": snapshot,
                "benchmark_symbol": "SPY",
                "lookback_days": 252,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["history_source_provider"] == "configured_provider_chain"
        assert payload["history_freshness_label"] == "stale"
        assert any("stale cached constituent history" in warning for warning in payload["warnings"])
    finally:
        runtime.shutdown()


def test_performance_reports_missing_constituent_and_fx_coverage_without_losing_series(
    tmp_path,
):
    client, runtime = _build_client(tmp_path)
    try:
        snapshot = client.get("/portfolio/snapshot").json()
        provider = runtime.portfolio_service.data_provider

        def load_partial_history(loaded_snapshot, lookback_days):
            del lookback_days
            prices = {}
            missing = []
            for position in loaded_snapshot.positions:
                if position.sec_type == "CASH":
                    continue
                if position.symbol == "SAP":
                    missing.append(position.resolved_display_symbol())
                    continue
                history = runtime.client.mock_service.load_history(position.symbol)
                if history is not None:
                    prices[position.resolved_instrument_id()] = history
            provider._last_history_warnings.append(
                "FX history unavailable for SAP EUR conversion."
            )
            return prices, missing

        provider.load_prices = load_partial_history
        response = client.post(
            "/portfolio/performance",
            json={
                "snapshot": snapshot,
                "benchmark_symbol": "SPY",
                "lookback_days": 252,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["state"] == "partial"
        assert payload["performance_points"]
        assert payload["requested_position_count"] == 3
        assert payload["covered_position_count"] == 2
        assert payload["history_coverage_ratio"] == pytest.approx(2 / 3)
        assert payload["missing_history_symbols"] == ["SAP"]
        assert payload["missing_symbols"] == ["SAP"]
        assert payload["missing_fx_symbols"] == ["SAP"]
    finally:
        runtime.shutdown()


def test_history_api_reports_degraded_rows_and_clear_returns_recoverable_archive(tmp_path):
    client, runtime = _build_client(tmp_path)
    try:
        runtime.portfolio_history.path.write_text(
            "\n".join(
                [
                    "date,timestamp,netliq,market_value,cash,portfolio_value,base_ccy",
                    "2026-07-20,2026-07-20T12:00:00+00:00,100,90,10,100,USD",
                    "2026-07-21,not-a-date,broken,90,10,broken,USD",
                ]
            ),
            encoding="utf-8",
        )
        response = client.get("/portfolio/history")
        assert response.status_code == 200
        payload = response.json()
        assert payload["state"] == "degraded"
        assert payload["health"]["malformed_row_count"] == 1
        assert len(payload["points"]) == 1
        assert payload["warnings"]

        clear_response = client.post("/portfolio/history/clear")
        assert clear_response.status_code == 200
        clear_payload = clear_response.json()
        assert clear_payload["success"] is True
        assert clear_payload["archived"] is True
        assert clear_payload["archive_name"]
        assert (runtime.portfolio_history.archive_dir / clear_payload["archive_name"]).exists()
        assert not runtime.portfolio_history.path.exists()
    finally:
        runtime.shutdown()


def test_history_and_performance_api_validation_and_typed_unexpected_failure(tmp_path):
    client, runtime = _build_client(tmp_path)
    try:
        snapshot = client.get("/portfolio/snapshot").json()
        assert client.get("/portfolio/snapshot?quote_mode=Unknown").status_code == 422
        assert (
            client.get(
                "/portfolio/history",
                params={
                    "start": datetime(2026, 7, 22, tzinfo=timezone.utc).isoformat(),
                    "end": datetime(2026, 7, 20, tzinfo=timezone.utc).isoformat(),
                },
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/portfolio/performance",
                json={
                    "snapshot": snapshot,
                    "benchmark_symbol": "SPY?",
                    "lookback_days": 252,
                },
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/portfolio/performance",
                json={
                    "snapshot": snapshot,
                    "benchmark_symbol": "SPY",
                    "lookback_days": 5001,
                },
            ).status_code
            == 422
        )
        invalid_snapshot = dict(snapshot)
        invalid_snapshot["state"] = "mystery"
        assert (
            client.post(
                "/portfolio/performance",
                json={
                    "snapshot": invalid_snapshot,
                    "benchmark_symbol": "SPY",
                    "lookback_days": 252,
                },
            ).status_code
            == 422
        )

        runtime.portfolio_service.compute_performance = lambda request: (
            (_ for _ in ()).throw(RuntimeError("provider secret must not escape"))
        )
        failed_response = client.post(
            "/portfolio/performance",
            json={
                "snapshot": snapshot,
                "benchmark_symbol": "SPY",
                "lookback_days": 252,
            },
        )
        assert failed_response.status_code == 200
        failed = failed_response.json()
        assert failed["state"] == "failed"
        assert failed["complete"] is False
        assert failed["performance_points"] == []
        assert failed["benchmark_points"] == []
        assert "provider secret" not in str(failed)
        assert "RuntimeError" in failed["warnings"][0]
    finally:
        runtime.shutdown()
