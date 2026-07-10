import pytest

from src.models.portfolio import PortfolioSnapshot
from src.services.fx import FXService
from src.services.ibkr_client import IBKRClient
from src.ui.widgets.worker import Worker
from src.utils.time import now_utc


def _mock_client() -> IBKRClient:
    return IBKRClient("127.0.0.1", 7496, 9999, account=None, mock=True)


class _StubFX:
    def __init__(self, rates: dict[tuple[str, str], float]) -> None:
        self._rates = rates

    def get_rate(self, base: str, currency: str):
        if base == currency:
            return 1.0
        return self._rates.get((base, currency))


def _snapshot(summary: dict[str, str], base_currency: str = "USD") -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=now_utc(),
        base_currency=base_currency,
        account_summary=summary,
        positions=[],
        warnings=[],
    )


def test_extract_cash_balances_ignores_base_aggregate_when_native_present():
    client = _mock_client()
    summary = {"CashBalance:BASE": "1500.0", "CashBalance:USD": "1000.0"}
    assert client._extract_cash_balances(summary, "EUR") == {"USD": 1000.0}


def test_extract_cash_balances_uses_base_when_only_base_present():
    client = _mock_client()
    summary = {"CashBalance:BASE": "1500.0"}
    assert client._extract_cash_balances(summary, "EUR") == {"EUR": 1500.0}


def test_summary_amount_reads_account_currency_and_ignores_similar_tags():
    summary = {
        "NetLiquidationUncertainty:EUR": "0.00",
        "NetLiquidationByCurrency:USD": "41588.03",
        "NetLiquidation:EUR": "37012.05",
    }
    assert IBKRClient._summary_amount(summary, "NetLiquidation", "USD") == (37012.05, "EUR")


def test_summary_amount_prefers_app_base_currency_when_present():
    summary = {"NetLiquidation:EUR": "900.0", "NetLiquidation:USD": "1000.0"}
    assert IBKRClient._summary_amount(summary, "NetLiquidation", "USD") == (1000.0, "USD")


def test_summary_amount_infers_account_currency_for_base_suffix():
    summary = {"NetLiquidation:BASE": "1000.0", "EquityWithLoanValue:EUR": "1000.0"}
    assert IBKRClient._summary_amount(summary, "NetLiquidation", "USD") == (1000.0, "EUR")


def test_compute_totals_converts_net_liquidation_to_app_base_currency():
    client = _mock_client()
    snapshot = _snapshot(
        {
            "NetLiquidation:EUR": "1000.0",
            "NetLiquidationUncertainty:EUR": "0.00",
            "PreviousDayEquityWithLoanValue:EUR": "900.0",
        }
    )
    client._compute_totals(snapshot, _StubFX({("USD", "EUR"): 1.1}))
    assert snapshot.net_liquidation == pytest.approx(1100.0)
    assert snapshot.day_pnl == pytest.approx(110.0)
    assert snapshot.day_pnl_source == "account_summary"


def test_compute_totals_drops_net_liquidation_when_fx_missing():
    client = _mock_client()
    snapshot = _snapshot({"NetLiquidation:EUR": "1000.0"})
    client._compute_totals(snapshot, _StubFX({}))
    assert snapshot.net_liquidation is None
    assert any("FX unavailable for EUR->USD" in w for w in snapshot.warnings)


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
