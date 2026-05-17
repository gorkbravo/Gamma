from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.runtime import build_runtime
from src.services.provider_usage import ProviderUsageLedger, trace_provider


class FakeProvider:
    provider_id = "fake_provider"
    source_label = "Fake Provider"

    def load(self, value: str) -> str:
        return f"loaded:{value}"

    def fail(self) -> None:
        raise RuntimeError("provider broke")


def test_provider_usage_ledger_summarizes_recent_calls():
    ledger = ProviderUsageLedger(clock=lambda: datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc))

    ledger.record(
        provider_id="yfinance",
        endpoint="history",
        status="success",
        cache_status="miss",
        duration_ms=12.4,
    )
    ledger.record(
        provider_id="yfinance",
        endpoint="history",
        status="unavailable",
        cache_status="miss",
        duration_ms=4.1,
        message="No history returned",
    )
    ledger.record(
        provider_id="fred",
        endpoint="series",
        status="success",
        cache_status="hit",
        duration_ms=1.3,
    )

    snapshot = ledger.snapshot()

    assert snapshot.generated_at.isoformat() == "2026-05-16T12:00:00+00:00"
    assert snapshot.total_calls == 3
    assert [row.provider_id for row in snapshot.providers] == ["yfinance", "fred"]
    yfinance = snapshot.providers[0]
    assert yfinance.call_count == 2
    assert yfinance.success_count == 1
    assert yfinance.unavailable_count == 1
    assert yfinance.cache_miss_count == 2
    assert yfinance.last_message == "No history returned"
    assert len(snapshot.recent_calls) == 3


def test_trace_provider_records_success_and_failure_without_swallowing_errors():
    ledger = ProviderUsageLedger(clock=lambda: datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc))
    provider = trace_provider(FakeProvider(), ledger, endpoint_prefix="fake")

    assert provider.load("x") == "loaded:x"
    with pytest.raises(RuntimeError, match="provider broke"):
        provider.fail()

    snapshot = ledger.snapshot()
    assert snapshot.total_calls == 2
    assert [call.status for call in snapshot.recent_calls] == ["error", "success"]
    assert snapshot.providers[0].error_count == 1
    assert snapshot.providers[0].last_error == "provider broke"


def test_provider_usage_system_api_returns_runtime_ledger(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        runtime.provider_usage.record(
            provider_id="mock",
            endpoint="research_history.load_history",
            status="success",
            cache_status="miss",
            duration_ms=2.0,
        )

        response = client.get("/system/provider-usage")

        assert response.status_code == 200
        payload = response.json()
        assert payload["source_provider"] == "gamma"
        assert payload["total_calls"] == 1
        assert payload["providers"][0]["provider_id"] == "mock"
        assert payload["providers"][0]["success_count"] == 1
        assert payload["recent_calls"][0]["endpoint"] == "research_history.load_history"
    finally:
        runtime.shutdown()
