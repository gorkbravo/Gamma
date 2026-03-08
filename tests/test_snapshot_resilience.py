from src.services.fx import FXService
from src.services.ibkr_client import IBKRClient
from src.ui.widgets.worker import Worker


def _mock_client() -> IBKRClient:
    return IBKRClient("127.0.0.1", 7496, 9999, account=None, mock=True)


def test_extract_cash_balances_ignores_base_aggregate_when_native_present():
    client = _mock_client()
    summary = {"CashBalance:BASE": "1500.0", "CashBalance:USD": "1000.0"}
    assert client._extract_cash_balances(summary, "EUR") == {"USD": 1000.0}


def test_extract_cash_balances_uses_base_when_only_base_present():
    client = _mock_client()
    summary = {"CashBalance:BASE": "1500.0"}
    assert client._extract_cash_balances(summary, "EUR") == {"EUR": 1500.0}


def test_fetch_snapshot_returns_partial_snapshot_when_totals_fail():
    client = _mock_client()
    original = client._compute_totals
    client._compute_totals = lambda snapshot, fx: (_ for _ in ()).throw(AssertionError())
    try:
        snapshot = client.fetch_snapshot("EUR", FXService(None), market_data=None)
    finally:
        client._compute_totals = original
    assert snapshot is not None
    assert any(w.startswith("Snapshot totals failed: AssertionError") for w in snapshot.warnings)


def test_fetch_snapshot_returns_warning_when_ibkr_disconnected():
    client = _mock_client()
    client.mock = False

    class DisconnectedIB:
        @staticmethod
        def isConnected() -> bool:
            return False

    client.ib = DisconnectedIB()
    snapshot = client._fetch_snapshot_impl("USD", FXService(None), market_data=None)

    assert snapshot.positions == []
    assert snapshot.account_summary == {}
    assert "IBKR not connected" in snapshot.warnings


def test_worker_error_includes_type_and_traceback():
    messages: list[str] = []
    worker = Worker(lambda: (_ for _ in ()).throw(AssertionError()))
    worker.signals.error.connect(messages.append)
    worker.run()
    assert messages
    assert messages[0].splitlines()[0] == "AssertionError"
    assert "Traceback (most recent call last):" in messages[0]
