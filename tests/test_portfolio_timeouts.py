from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient
from ib_insync import Contract

from src.api.main import create_app
from src.application.runtime import build_runtime
from src.models.portfolio import PositionItem
from src.services.fx import FXService
from src.services.ib_thread import IBTaskTimeoutError, IBThreadBusyError, IBThreadRunner
from src.services.ibkr_client import (
    PORTFOLIO_QUOTE_TIMEOUT_MAX_SECONDS,
    PORTFOLIO_SNAPSHOT_WORKER_TIMEOUT_CAP_SECONDS,
    IBKRClient,
    derive_portfolio_snapshot_worker_timeout,
)


def test_maximum_public_quote_timeout_fits_derived_worker_budget():
    delayed_budget = derive_portfolio_snapshot_worker_timeout(
        PORTFOLIO_QUOTE_TIMEOUT_MAX_SECONDS,
        "delayed",
    )
    auto_budget = derive_portfolio_snapshot_worker_timeout(
        PORTFOLIO_QUOTE_TIMEOUT_MAX_SECONDS,
        "auto",
    )

    assert delayed_budget == pytest.approx(28.0)
    assert auto_budget == pytest.approx(38.0)
    assert auto_budget <= PORTFOLIO_SNAPSHOT_WORKER_TIMEOUT_CAP_SECONDS
    with pytest.raises(ValueError, match="must be between"):
        derive_portfolio_snapshot_worker_timeout(
            PORTFOLIO_QUOTE_TIMEOUT_MAX_SECONDS + 0.1,
            "auto",
        )


def test_portfolio_snapshot_api_accepts_maximum_and_rejects_unsupported_timeout(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        accepted = client.get(
            f"/portfolio/snapshot?quote_timeout_seconds={PORTFOLIO_QUOTE_TIMEOUT_MAX_SECONDS}"
        )
        rejected = client.get(
            f"/portfolio/snapshot?quote_timeout_seconds={PORTFOLIO_QUOTE_TIMEOUT_MAX_SECONDS + 0.1}"
        )

        assert accepted.status_code == 200
        assert accepted.json()["positions"]
        assert rejected.status_code == 422
    finally:
        runtime.shutdown()


def test_timed_out_inflight_ib_task_exposes_still_finishing_and_rejects_follow_up():
    runner = IBThreadRunner()
    started = threading.Event()
    release = threading.Event()

    def blocked_snapshot():
        started.set()
        release.wait(timeout=2.0)
        return "complete"

    try:
        with pytest.raises(IBTaskTimeoutError) as timeout:
            runner.run(blocked_snapshot, timeout=0.05)
        assert started.is_set()
        assert timeout.value.still_finishing is True
        assert runner.busy_state() == {
            "busy": True,
            "still_finishing": True,
            "operation": "blocked_snapshot",
        }

        with pytest.raises(IBThreadBusyError, match="still_finishing"):
            runner.run(lambda: "follow-up", timeout=0.05)

        release.set()
        deadline = time.time() + 1.0
        while runner.busy_state()["busy"] and time.time() < deadline:
            threading.Event().wait(0.01)
        assert runner.run(lambda: "follow-up", timeout=1.0) == "follow-up"
        assert runner.busy_state()["busy"] is False
    finally:
        release.set()
        runner.stop()


def test_quote_timeout_retains_partial_account_and_position_snapshot():
    client = IBKRClient("127.0.0.1", 7496, 9911, account=None, mock=True)
    client.ib.isConnected = lambda: True
    client._ensure_account_subscription = lambda: []
    client._snapshot_account_summary = lambda: {"NetLiquidation:USD": "1000"}
    position = PositionItem(
        symbol="LMT",
        sec_type="STK",
        currency="USD",
        quantity=2,
        avg_cost=480.0,
        market_price=None,
        market_value=None,
        unrealized_pnl=None,
    )
    contract = Contract(
        conId=1001,
        symbol="LMT",
        secType="STK",
        exchange="SMART",
        currency="USD",
    )
    client._snapshot_positions = lambda: [(position, contract)]

    class TimedOutMarketData:
        @staticmethod
        def fetch_snapshot_quotes_batch(*args, **kwargs):
            del args, kwargs
            raise TimeoutError("quote budget exhausted")

    snapshot = client._fetch_snapshot_impl(
        "USD",
        FXService(None),
        market_data=TimedOutMarketData(),
        quote_timeout_seconds=2.0,
    )

    assert snapshot.account_summary == {"NetLiquidation:USD": "1000"}
    assert [row.symbol for row in snapshot.positions] == ["LMT"]
    assert any(
        "account and position data were retained (TimeoutError)" in warning
        for warning in snapshot.warnings
    )
