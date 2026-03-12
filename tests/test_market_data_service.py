from __future__ import annotations

import threading
from types import MethodType, SimpleNamespace

import pandas as pd

from src.services.cache import CacheService
from src.services.market_data import MarketDataService
from src.services.throttle import ThrottleQueue


class _ConnectedIB:
    def isConnected(self) -> bool:
        return True


def test_market_data_history_cache_is_lookback_specific(tmp_path):
    cache = CacheService(base_dir=tmp_path / "cache", ttl_hours=24)
    service = MarketDataService(
        ib=_ConnectedIB(),
        cache=cache,
        min_interval_seconds=0.0,
        history_request_timeout_seconds=0.2,
    )
    calls: list[int] = []

    def fake_fetch(self, contract, lookback_days):
        calls.append(int(lookback_days))
        idx = pd.date_range("2026-01-02", periods=3, freq="B")
        return pd.Series([float(lookback_days)] * 3, index=idx)

    service._fetch_history_direct = MethodType(fake_fetch, service)
    contract = SimpleNamespace(
        symbol="AAPL",
        secType="STK",
        currency="USD",
        conId=123,
        exchange="SMART",
        primaryExchange="NASDAQ",
    )

    history_126 = service.fetch_history(contract, 126)
    history_504 = service.fetch_history(contract, 504)
    history_126_again = service.fetch_history(contract, 126)

    assert calls == [126, 504]
    assert history_126 is not None
    assert history_504 is not None
    assert history_126_again is not None
    assert float(history_126.iloc[0]) == 126.0
    assert float(history_504.iloc[0]) == 504.0
    assert float(history_126_again.iloc[0]) == 126.0


def test_throttle_queue_survives_callback_failure():
    queue = ThrottleQueue(min_interval_seconds=0.0)
    callback_error_seen = threading.Event()
    second_task_done = threading.Event()

    queue.submit(
        lambda: 1,
        lambda _result: (_ for _ in ()).throw(RuntimeError("callback failed")),
        lambda _exc: callback_error_seen.set(),
    )
    queue.submit(
        lambda: 2,
        lambda _result: second_task_done.set(),
        lambda _exc: None,
    )

    assert callback_error_seen.wait(1.0)
    assert second_task_done.wait(1.0)


def test_fx_contract_spec_uses_canonical_pair_orientation():
    usd_per_eur = MarketDataService._fx_contract_spec("USD", "EUR")
    eur_per_usd = MarketDataService._fx_contract_spec("EUR", "USD")

    assert usd_per_eur is not None
    usd_contract, usd_invert = usd_per_eur
    assert usd_contract.symbol == "EUR"
    assert usd_contract.currency == "USD"
    assert usd_invert is False

    assert eur_per_usd is not None
    eur_contract, eur_invert = eur_per_usd
    assert eur_contract.symbol == "EUR"
    assert eur_contract.currency == "USD"
    assert eur_invert is True


def test_fetch_fx_history_preserves_or_inverts_series_based_on_target_direction(tmp_path):
    cache = CacheService(base_dir=tmp_path / "cache", ttl_hours=24)
    service = MarketDataService(
        ib=_ConnectedIB(),
        cache=cache,
        min_interval_seconds=0.0,
        history_request_timeout_seconds=0.2,
    )
    idx = pd.date_range("2026-01-02", periods=3, freq="B")
    requested: list[tuple[str, str]] = []

    def fake_fetch_history(contract, lookback_days):
        requested.append((contract.symbol, contract.currency))
        return pd.Series([1.2, 1.25, 1.3], index=idx)

    service.fetch_history = fake_fetch_history  # type: ignore[method-assign]

    usd_per_eur = service.fetch_fx_history("USD", "EUR", 30)
    eur_per_usd = service.fetch_fx_history("EUR", "USD", 30)

    assert requested == [("EUR", "USD"), ("EUR", "USD")]
    assert usd_per_eur is not None
    assert eur_per_usd is not None
    assert float(usd_per_eur.iloc[0]) == 1.2
    assert float(eur_per_usd.iloc[0]) == 1 / 1.2
