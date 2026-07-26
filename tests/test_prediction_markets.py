from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.prediction_market_service import PredictionMarketService, PredictionMarketScreenerRequest
from src.application.runtime import build_runtime
from src.models.prediction_markets import (
    CalibrationSummary,
    PredictionHistoryWindow,
    PredictionMarketOutcome,
    PredictionMarketRecord,
    PredictionProbabilityPoint,
    RelatedMarketRecord,
    WalletActivityRecord,
    WalletSummary,
)
from src.services.cache import CacheService
from src.services.prediction_market_adapters import KalshiAdapter, PolymarketAdapter


def test_polymarket_adapter_normalizes_and_caches_screener_results(tmp_path):
    calls: defaultdict[str, int] = defaultdict(int)

    def fake_fetch(url: str, params: dict | None = None):
        calls[f"{url}|{params}"] += 1
        return [
            {
                "id": "123",
                "conditionId": "0xabc",
                "question": "Will rates fall?",
                "description": "Fed decision contract",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.6100", "0.3900"]',
                "clobTokenIds": '["yes-token", "no-token"]',
                "slug": "will-rates-fall",
                "category": "Economy",
                "active": True,
                "closed": False,
                "volumeNum": 125000.0,
                "volume24hr": 1200.0,
                "liquidityNum": 7500.0,
                "bestBid": 0.6,
                "bestAsk": 0.62,
                "spread": 0.02,
                "lastTradePrice": 0.61,
                "startDate": "2026-03-01T00:00:00Z",
                "endDate": "2026-03-18T00:00:00Z",
                "events": [
                    {
                        "id": "event-1",
                        "title": "Fed decision in March?",
                        "category": "Economy",
                        "openInterest": 1000.0,
                        "series": [{"id": "series-1", "title": "FOMC"}],
                    }
                ],
                "tags": [{"label": "Fed Rates"}],
            }
        ]

    adapter = PolymarketAdapter(CacheService(base_dir=tmp_path / "cache"), fetch_json=fake_fetch)

    first = adapter.list_markets(status="open", limit=10)
    second = adapter.list_markets(status="open", limit=10)
    refreshed = adapter.list_markets(status="open", limit=10, force_refresh=True)

    assert len(first) == 1
    assert len(second) == 1
    assert len(refreshed) == 1
    assert sum(calls.values()) == 2
    market = first[0]
    assert market.market_id == "polymarket:123"
    assert market.provider_condition_id == "0xabc"
    assert market.current_probability == 0.61
    assert market.outcomes[0].token_id == "yes-token"
    assert market.event_title == "Fed decision in March?"
    assert market.series_title == "FOMC"
    assert market.tags == ["Fed Rates"]


def test_polymarket_adapter_uses_public_search_for_query_and_category_discovery(tmp_path):
    calls: defaultdict[str, int] = defaultdict(int)

    def fake_fetch(url: str, params: dict | None = None):
        calls[f"{url}|{params}"] += 1
        if url.endswith("/public-search"):
            return {
                "events": [
                    {
                        "id": "event-1",
                        "title": "Fed decision in March?",
                        "description": "Macro event",
                        "openInterest": 2500.0,
                        "tags": [{"label": "Economy"}, {"label": "Fed Rates"}],
                        "markets": [
                            {
                                "id": "search-1",
                                "conditionId": "0xsearch",
                                "question": "Will the Fed cut rates in March?",
                                "description": "Fed decision contract",
                                "outcomes": '["Yes", "No"]',
                                "outcomePrices": '["0.5700", "0.4300"]',
                                "clobTokenIds": '["yes-token", "no-token"]',
                                "slug": "will-the-fed-cut-rates-in-march",
                                "active": True,
                                "closed": False,
                                "volumeNum": 225000.0,
                                "volume24hr": 4200.0,
                                "liquidityNum": 12500.0,
                                "bestBid": 0.56,
                                "bestAsk": 0.58,
                                "spread": 0.02,
                                "lastTradePrice": 0.57,
                                "startDate": "2026-03-01T00:00:00Z",
                                "endDate": "2026-03-18T00:00:00Z",
                            }
                        ],
                    }
                ]
            }
        return []

    adapter = PolymarketAdapter(CacheService(base_dir=tmp_path / "cache"), fetch_json=fake_fetch)

    query_rows = adapter.list_markets(status="open", limit=20, query="fed")
    category_rows = adapter.list_markets(status="open", limit=20, category="Economy")

    assert [row.market_id for row in query_rows] == ["polymarket:search-1"]
    assert [row.market_id for row in category_rows] == ["polymarket:search-1"]
    assert query_rows[0].event_title == "Fed decision in March?"
    assert query_rows[0].tags == ["Economy", "Fed Rates"]
    assert query_rows[0].current_probability == 0.57
    assert sum(1 for key in calls if "/public-search|" in key) >= 2
    assert not any("/markets|" in key for key in calls)


def test_polymarket_calibration_excludes_resolved_settlement_prices_without_last_trade(tmp_path):
    def fake_fetch(url: str, params: dict | None = None):
        assert url.endswith("/markets")
        return [
            {
                "id": "resolved-settlement-only",
                "conditionId": "0xresolved1",
                "question": "Resolved without trade proxy?",
                "description": "Settlement-only record",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["1.0000", "0.0000"]',
                "clobTokenIds": '["yes-token", "no-token"]',
                "slug": "resolved-settlement-only",
                "category": "Politics",
                "active": False,
                "closed": True,
                "volumeNum": 1500.0,
                "volume24hr": 0.0,
                "liquidityNum": 0.0,
                "endDate": "2026-03-10T00:00:00Z",
                "closedTime": "2026-03-10T01:00:00Z",
                "events": [{"id": "event-1", "title": "Resolved event", "category": "Politics"}],
            },
            {
                "id": "resolved-with-trade",
                "conditionId": "0xresolved2",
                "question": "Resolved with last trade?",
                "description": "Resolved market with valid proxy",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.0000", "1.0000"]',
                "clobTokenIds": '["yes-token-2", "no-token-2"]',
                "slug": "resolved-with-trade",
                "category": "Politics",
                "active": False,
                "closed": True,
                "lastTradePrice": 0.24,
                "volumeNum": 2200.0,
                "volume24hr": 0.0,
                "liquidityNum": 0.0,
                "endDate": "2026-03-11T00:00:00Z",
                "closedTime": "2026-03-11T01:00:00Z",
                "events": [{"id": "event-2", "title": "Resolved trade event", "category": "Politics"}],
            },
        ]

    adapter = PolymarketAdapter(CacheService(base_dir=tmp_path / "cache"), fetch_json=fake_fetch)

    markets = adapter.list_markets(status="closed", limit=10)
    settlement_only = next(market for market in markets if market.market_id == "polymarket:resolved-settlement-only")
    trade_proxy = next(market for market in markets if market.market_id == "polymarket:resolved-with-trade")
    summary = adapter.build_calibration_summary(sample_size=10)

    assert settlement_only.status == "resolved"
    assert settlement_only.current_probability is None
    assert settlement_only.resolved_probability == 1.0
    assert settlement_only.resolution_outcome is True

    assert trade_proxy.current_probability == 0.24
    assert trade_proxy.resolved_probability == 0.0
    assert trade_proxy.resolution_outcome is False

    assert summary.sample_size == 1
    assert [bucket.label for bucket in summary.buckets] == ["10-25%"]
    assert summary.buckets[0].average_probability == pytest.approx(0.24)
    assert summary.buckets[0].realized_frequency == 0.0
    assert [observation.market_id for observation in summary.observations] == ["polymarket:resolved-with-trade"]


def test_polymarket_wallet_summary_uses_selected_outcome_probability_for_edge(tmp_path):
    def fake_fetch(url: str, params: dict | None = None):
        if url.endswith("/trades"):
            return [
                {
                    "proxyWallet": "0xwallet-no",
                    "name": "No Desk",
                    "side": "buy",
                    "outcome": "No",
                    "size": "100",
                    "price": "0.97",
                    "timestamp": 1_710_000_000,
                }
            ]
        if url.endswith("/holders"):
            return []
        return []

    adapter = PolymarketAdapter(CacheService(base_dir=tmp_path / "cache"), fetch_json=fake_fetch)
    market = PredictionMarketRecord(
        market_id="polymarket:test-no-edge",
        venue="polymarket",
        title="Will X happen?",
        subtitle=None,
        description=None,
        status="open",
        category="Politics",
        event_id="polymarket:event:test",
        event_title="Will X happen?",
        series_id=None,
        series_title=None,
        provider_market_id="test-no-edge",
        provider_condition_id="condition-1",
        provider_event_id="event-1",
        provider_series_id=None,
        slug="test-no-edge",
        end_time=datetime(2026, 3, 31, 0, 0, 0),
        open_time=datetime(2026, 3, 1, 0, 0, 0),
        close_time=None,
        current_probability=0.02,
        probability_label="Yes",
        volume=1000.0,
        volume_24h=50.0,
        liquidity=500.0,
        open_interest=200.0,
        best_bid=0.02,
        best_ask=0.03,
        spread=0.01,
        recent_price_change=0.0,
        resolved_probability=None,
        resolution_outcome=None,
        image_url=None,
        resolution_source=None,
        outcomes=[
            PredictionMarketOutcome(outcome_id="yes", label="Yes", probability=0.02),
            PredictionMarketOutcome(outcome_id="no", label="No", probability=0.98),
        ],
        tags=["Politics"],
        source_provider="polymarket",
        retrieved_at=datetime(2026, 3, 18, 17, 0, 0),
        origin="test",
    )

    wallet = adapter.get_wallet_summary(market)

    assert len(wallet.participants) == 1
    assert wallet.participants[0].outcome_label == "No"
    assert wallet.participants[0].current_edge == pytest.approx(0.01)


def test_polymarket_history_points_use_utc_timestamps(tmp_path):
    def fake_fetch(url: str, params: dict | None = None):
        if url.endswith("/prices-history"):
            return {
                "history": [
                    {"t": 1_711_958_435, "p": 0.64},
                    {"t": 1_711_962_034, "p": 0.66},
                ]
            }
        raise AssertionError(f"Unexpected request: {url} {params}")

    adapter = PolymarketAdapter(CacheService(base_dir=tmp_path / "cache"), fetch_json=fake_fetch)
    market = PredictionMarketRecord(
        market_id="polymarket:test-history",
        venue="polymarket",
        title="Will X happen?",
        subtitle=None,
        description=None,
        status="open",
        category="Politics",
        event_id="polymarket:event:test",
        event_title="Will X happen?",
        series_id=None,
        series_title=None,
        provider_market_id="test-history",
        provider_condition_id="condition-1",
        provider_event_id="event-1",
        provider_series_id=None,
        slug="test-history",
        end_time=datetime(2026, 3, 31, 0, 0, 0),
        open_time=datetime(2026, 3, 1, 0, 0, 0),
        close_time=None,
        current_probability=0.66,
        probability_label="Yes",
        volume=1000.0,
        volume_24h=50.0,
        liquidity=500.0,
        open_interest=200.0,
        best_bid=0.65,
        best_ask=0.67,
        spread=0.02,
        recent_price_change=0.02,
        resolved_probability=None,
        resolution_outcome=None,
        image_url=None,
        resolution_source=None,
        outcomes=[
            PredictionMarketOutcome(outcome_id="yes", label="Yes", probability=0.66, token_id="yes-token"),
        ],
        tags=["Politics"],
        source_provider="polymarket",
        retrieved_at=datetime(2026, 3, 18, 17, 0, 0),
        origin="test",
    )

    history = adapter.get_history(market)

    assert [point.probability for point in history] == [0.64, 0.66]
    assert all(point.timestamp.tzinfo is not None for point in history)


def test_kalshi_adapter_normalizes_closed_markets_and_flow_summary(tmp_path):
    calls: defaultdict[str, int] = defaultdict(int)

    def fake_fetch(url: str, params: dict | None = None):
        key = f"{url}|{params}"
        calls[key] += 1
        if url.endswith("/events") and params == {"limit": 50, "status": "closed", "with_nested_markets": "true"}:
            return {
                "events": [
                    {
                        "event_ticker": "KXEVENT-1",
                        "title": "Will X happen?",
                        "category": "Politics",
                        "series_ticker": "KXSERIES",
                        "markets": [
                            {
                                "ticker": "KXTEST-YES",
                                "event_ticker": "KXEVENT-1",
                                "title": "Will X happen?",
                                "yes_sub_title": "Yes",
                                "status": "determined",
                                "result": "yes",
                                "last_price_dollars": "0.83",
                                "previous_price_dollars": "0.80",
                                "yes_bid_dollars": "0.82",
                                "yes_ask_dollars": "0.84",
                                "volume_fp": "1200",
                                "volume_24h_fp": "400",
                                "liquidity_dollars": "2500",
                                "open_interest_fp": "600",
                                "expiration_time": "2026-03-15T00:00:00Z",
                                "close_time": "2026-03-14T23:00:00Z",
                                "open_time": "2026-03-10T00:00:00Z",
                                "rules_primary": "Primary rules",
                            },
                            {
                                "ticker": "KXOPEN-YES",
                                "event_ticker": "KXEVENT-1",
                                "title": "Still open",
                                "yes_sub_title": "Yes",
                                "status": "active",
                                "last_price_dollars": "0.40",
                                "yes_bid_dollars": "0.39",
                                "yes_ask_dollars": "0.41",
                                "volume_fp": "200",
                                "volume_24h_fp": "25",
                                "liquidity_dollars": "500",
                                "open_interest_fp": "150",
                                "expiration_time": "2026-04-15T00:00:00Z",
                                "close_time": "2026-04-14T23:00:00Z",
                                "open_time": "2026-03-10T00:00:00Z",
                                "rules_primary": "Secondary rules",
                            },
                        ],
                    }
                ]
            }
        if url.endswith("/events") and params == {"limit": 50, "status": "settled", "with_nested_markets": "true"}:
            return {"events": []}
        if url.endswith("/markets/trades"):
            return {
                "trades": [
                    {"taker_side": "yes", "count_fp": "15", "yes_price_dollars": "0.80"},
                    {"taker_side": "yes", "count_fp": "5", "yes_price_dollars": "0.84"},
                    {"taker_side": "no", "count_fp": "10", "no_price_dollars": "0.22"},
                ]
            }
        return {"event": {"title": "Will X happen?", "category": "Politics", "series_ticker": "KXSERIES"}, "markets": []}

    adapter = KalshiAdapter(CacheService(base_dir=tmp_path / "cache"), fetch_json=fake_fetch)

    markets = adapter.list_markets(status="closed", limit=40)
    wallet = adapter.get_wallet_summary(markets[0])

    assert len(markets) == 1
    market = markets[0]
    assert market.market_id == "kalshi:KXTEST-YES"
    assert market.status == "resolved"
    assert market.resolution_outcome is True
    assert market.current_probability == 0.83
    assert wallet.transformation_note is not None
    assert {row.participant_id for row in wallet.participants} == {"kalshi:flow:yes", "kalshi:flow:no"}
    assert wallet.total_trades == 3


def test_kalshi_adapter_closed_discovery_merges_archived_historical_markets(tmp_path):
    def fake_fetch(url: str, params: dict | None = None):
        if url.endswith("/events") and params == {"limit": 50, "status": "closed", "with_nested_markets": "true"}:
            return {
                "events": [
                    {
                        "event_ticker": "KXEVENT-RECENT",
                        "title": "Will Congress pass the bill?",
                        "category": "Politics",
                        "series_ticker": "KXPOL",
                        "markets": [
                            {
                                "ticker": "KXRECENT-YES",
                                "event_ticker": "KXEVENT-RECENT",
                                "title": "Will Congress pass the bill?",
                                "yes_sub_title": "Yes",
                                "status": "determined",
                                "result": "yes",
                                "last_price_dollars": "0.74",
                                "previous_price_dollars": "0.70",
                                "yes_bid_dollars": "0.73",
                                "yes_ask_dollars": "0.75",
                                "volume_fp": "500",
                                "volume_24h_fp": "0",
                                "liquidity_dollars": "0",
                                "open_interest_fp": "0",
                                "expiration_time": "2026-03-10T00:00:00Z",
                                "close_time": "2026-03-09T23:00:00Z",
                                "open_time": "2026-03-01T00:00:00Z",
                                "rules_primary": "Recent rules",
                            }
                        ],
                    }
                ]
            }
        if url.endswith("/events") and params == {"limit": 50, "status": "settled", "with_nested_markets": "true"}:
            return {"events": []}
        if url.endswith("/historical/markets") and params == {"limit": 50}:
            return {
                "markets": [
                    {
                        "ticker": "KXARCHIVE-YES",
                        "event_ticker": "KXEVENT-ARCHIVE",
                        "title": "Will the Fed cut rates by June?",
                        "yes_sub_title": "Yes",
                        "status": "determined",
                        "result": "no",
                        "last_price_dollars": "0.12",
                        "previous_price_dollars": "0.15",
                        "yes_bid_dollars": "0.11",
                        "yes_ask_dollars": "0.13",
                        "volume_fp": "900",
                        "volume_24h_fp": "0",
                        "liquidity_dollars": "0",
                        "open_interest_fp": "0",
                        "expiration_time": "2025-06-30T00:00:00Z",
                        "close_time": "2025-06-29T23:00:00Z",
                        "open_time": "2025-05-01T00:00:00Z",
                        "rules_primary": "Archived rules",
                    }
                ],
                "cursor": "",
            }
        if url.endswith("/events/KXEVENT-ARCHIVE"):
            return {
                "event": {
                    "title": "Fed June decision",
                    "category": "Economy",
                    "series_ticker": "KXMACRO",
                },
                "markets": [],
            }
        if url.endswith("/events/KXEVENT-RECENT"):
            return {
                "event": {
                    "title": "Will Congress pass the bill?",
                    "category": "Politics",
                    "series_ticker": "KXPOL",
                },
                "markets": [],
            }
        raise AssertionError(f"Unexpected request: {url} {params}")

    adapter = KalshiAdapter(CacheService(base_dir=tmp_path / "cache"), fetch_json=fake_fetch)

    markets = adapter.list_markets(status="closed", limit=40)

    assert {market.market_id for market in markets} == {"kalshi:KXRECENT-YES", "kalshi:KXARCHIVE-YES"}
    archived = next(market for market in markets if market.market_id == "kalshi:KXARCHIVE-YES")
    assert archived.category == "Economy"
    assert archived.event_title == "Fed June decision"
    assert archived.series_id == "kalshi:series:KXMACRO"
    assert archived.resolution_outcome is False


def test_kalshi_adapter_uses_historical_endpoint_for_archived_market_history(tmp_path):
    calls: list[tuple[str, dict | None]] = []

    def fake_fetch(url: str, params: dict | None = None):
        calls.append((url, params))
        if url.endswith("/historical/cutoff"):
            return {"market_settled_ts": "2026-01-01T00:00:00Z"}
        if url.endswith("/historical/markets/KXOLD-YES/candlesticks"):
            assert params == {
                "period_interval": 60,
                "start_ts": int(datetime(2025, 12, 20, 0, 0, 0, tzinfo=timezone.utc).timestamp()),
                "end_ts": int(datetime(2025, 12, 31, 23, 0, 0, tzinfo=timezone.utc).timestamp()),
            }
            return {
                "ticker": "KXOLD-YES",
                "candlesticks": [
                    {
                        "end_period_ts": int(datetime(2025, 12, 30, 22, 0, 0, tzinfo=timezone.utc).timestamp()),
                        "yes_bid": {"close": "0.41"},
                        "yes_ask": {"close": "0.43"},
                        "price": {"close": "0.42"},
                        "volume": "25.00",
                        "open_interest": "100.00",
                    },
                    {
                        "end_period_ts": int(datetime(2025, 12, 31, 23, 0, 0, tzinfo=timezone.utc).timestamp()),
                        "yes_bid": {"close": "0.58"},
                        "yes_ask": {"close": "0.60"},
                        "price": {"close": "0.59"},
                        "volume": "40.00",
                        "open_interest": "150.00",
                    },
                ],
            }
        raise AssertionError(f"Unexpected request: {url} {params}")

    adapter = KalshiAdapter(CacheService(base_dir=tmp_path / "cache"), fetch_json=fake_fetch)
    market = PredictionMarketRecord(
        market_id="kalshi:KXOLD-YES",
        venue="kalshi",
        title="Will X happen?",
        subtitle=None,
        description=None,
        status="resolved",
        category="Politics",
        event_id="kalshi:event:KXEVENT-1",
        event_title="Will X happen?",
        series_id="kalshi:series:KXSERIES",
        series_title="KXSERIES",
        provider_market_id="KXOLD-YES",
        provider_condition_id=None,
        provider_event_id="KXEVENT-1",
        provider_series_id="KXSERIES",
        slug="KXOLD-YES",
        end_time=datetime(2025, 12, 31, 23, 0, 0),
        open_time=datetime(2025, 12, 20, 0, 0, 0),
        close_time=datetime(2025, 12, 31, 23, 0, 0),
        current_probability=0.59,
        probability_label="Yes",
        volume=500.0,
        volume_24h=0.0,
        liquidity=100.0,
        open_interest=150.0,
        best_bid=0.58,
        best_ask=0.60,
        spread=0.02,
        recent_price_change=0.01,
        resolved_probability=1.0,
        resolution_outcome=True,
        image_url=None,
        resolution_source=None,
        outcomes=[],
        tags=["Politics"],
        source_provider="kalshi",
        retrieved_at=datetime(2026, 3, 18, 18, 0, 0),
        origin="test",
    )

    history = adapter.get_history(market)

    assert [point.probability for point in history] == [0.42, 0.59]
    assert all(point.timestamp.tzinfo is not None for point in history)
    assert history[0].volume == 25.0
    assert history[0].open_interest == 100.0
    assert history[0].spread == pytest.approx(0.02)
    assert all(point.origin == "kalshi.historical_candlesticks" for point in history)
    assert any(url.endswith("/historical/cutoff") for url, _ in calls)
    assert any(url.endswith("/historical/markets/KXOLD-YES/candlesticks") for url, _ in calls)
    assert not any(url.endswith("/series/KXSERIES/markets/KXOLD-YES/candlesticks") for url, _ in calls)


def test_kalshi_adapter_caps_open_market_history_at_current_time(tmp_path, monkeypatch):
    fixed_now = datetime(2026, 4, 5, 12, 0, 0)
    calls: list[tuple[str, dict | None]] = []

    def fake_fetch(url: str, params: dict | None = None):
        calls.append((url, params))
        if url.endswith("/series/KXLONG/markets/KXLONG-YES/candlesticks"):
            assert params == {
                "period_interval": 1440,
                "start_ts": int(datetime(2025, 9, 24, 14, 0, 0, tzinfo=timezone.utc).timestamp()),
                "end_ts": int(fixed_now.replace(tzinfo=timezone.utc).timestamp()),
            }
            return {
                "ticker": "KXLONG-YES",
                "candlesticks": [
                    {
                        "end_period_ts": int(datetime(2026, 4, 5, 0, 0, 0, tzinfo=timezone.utc).timestamp()),
                        "yes_bid": {"close": "0.20"},
                        "yes_ask": {"close": "0.22"},
                        "price": {"close": "0.21"},
                        "volume": "10.0",
                    }
                ],
            }
        raise AssertionError(f"Unexpected request: {url} {params}")

    monkeypatch.setattr("src.services.prediction_market_adapters.now_utc", lambda: fixed_now)
    adapter = KalshiAdapter(CacheService(base_dir=tmp_path / "cache"), fetch_json=fake_fetch)
    market = PredictionMarketRecord(
        market_id="kalshi:KXLONG-YES",
        venue="kalshi",
        title="Will X happen before 2045?",
        subtitle=None,
        description=None,
        status="open",
        category="Politics",
        event_id="kalshi:event:KXLONG-45",
        event_title="Will X happen before 2045?",
        series_id="kalshi:series:KXLONG",
        series_title="KXLONG",
        provider_market_id="KXLONG-YES",
        provider_condition_id=None,
        provider_event_id="KXLONG-45",
        provider_series_id="KXLONG",
        slug="KXLONG-YES",
        end_time=datetime(2045, 1, 8, 15, 0, 0),
        open_time=datetime(2025, 9, 24, 14, 0, 0),
        close_time=datetime(2045, 1, 1, 4, 59, 0),
        current_probability=0.21,
        probability_label="Yes",
        volume=1000.0,
        volume_24h=10.0,
        liquidity=500.0,
        open_interest=200.0,
        best_bid=0.20,
        best_ask=0.22,
        spread=0.02,
        recent_price_change=0.01,
        resolved_probability=None,
        resolution_outcome=None,
        image_url=None,
        resolution_source=None,
        outcomes=[],
        tags=["Politics"],
        source_provider="kalshi",
        retrieved_at=fixed_now,
        origin="test",
    )

    history = adapter.get_history(market)

    assert [point.probability for point in history] == [0.21]
    assert history[0].timestamp.tzinfo is not None
    assert any(url.endswith("/series/KXLONG/markets/KXLONG-YES/candlesticks") for url, _ in calls)


def test_kalshi_adapter_falls_back_to_historical_market_detail(tmp_path):
    calls: list[str] = []

    def fake_fetch(url: str, params: dict | None = None):
        calls.append(url)
        if url.endswith("/historical/markets/KXOLD-YES"):
            return {
                "market": {
                    "ticker": "KXOLD-YES",
                    "event_ticker": "KXEVENT-1",
                    "title": "Will X happen?",
                    "yes_sub_title": "Yes",
                    "status": "determined",
                    "result": "yes",
                    "last_price_dollars": "0.91",
                    "yes_bid_dollars": "0.90",
                    "yes_ask_dollars": "0.92",
                    "volume_fp": "1200",
                    "volume_24h_fp": "0",
                    "liquidity_dollars": "0",
                    "open_interest_fp": "0",
                    "expiration_time": "2025-12-31T23:00:00Z",
                    "close_time": "2025-12-31T23:00:00Z",
                    "open_time": "2025-12-20T00:00:00Z",
                    "rules_primary": "Primary rules",
                }
            }
        if url.endswith("/markets/KXOLD-YES"):
            raise RuntimeError("live market not found")
        if url.endswith("/events/KXEVENT-1"):
            return {
                "event": {
                    "title": "Will X happen?",
                    "category": "Politics",
                    "series_ticker": "KXSERIES",
                },
                "markets": [],
            }
        raise AssertionError(f"Unexpected request: {url} {params}")

    adapter = KalshiAdapter(CacheService(base_dir=tmp_path / "cache"), fetch_json=fake_fetch)

    market = adapter.get_market("KXOLD-YES")

    assert market is not None
    assert market.market_id == "kalshi:KXOLD-YES"
    assert market.status == "resolved"
    assert market.current_probability == 0.91
    assert market.category == "Politics"
    assert market.provider_series_id == "KXSERIES"
    assert calls[0].endswith("/markets/KXOLD-YES")
    assert any(url.endswith("/historical/markets/KXOLD-YES") for url in calls)


def test_prediction_market_service_and_api_routes(tmp_path):
    base_time = datetime(2026, 3, 14, 20, 0, 0)

    class FakeAdapter:
        def __init__(self, provider: str, records: list[PredictionMarketRecord]) -> None:
            self.provider = provider
            self.records = records

        def list_markets(
            self,
            *,
            status: str = "open",
            limit: int = 50,
            force_refresh: bool = False,
            query: str = "",
            category: str | None = None,
        ):
            rows = self.records if status == "all" else [row for row in self.records if row.status == status or (status == "closed" and row.status == "resolved")]
            return rows[:limit]

        def get_market(self, provider_market_id: str):
            for record in self.records:
                if record.provider_market_id == provider_market_id:
                    return record
            return None

        def get_history(self, market: PredictionMarketRecord):
            return [
                PredictionProbabilityPoint(
                    timestamp=base_time - timedelta(hours=1),
                    probability=0.47,
                    source_provider=self.provider,
                    retrieved_at=base_time,
                    origin=f"{self.provider}.history",
                ),
                PredictionProbabilityPoint(
                    timestamp=base_time,
                    probability=market.current_probability or 0.5,
                    source_provider=self.provider,
                    retrieved_at=base_time,
                    origin=f"{self.provider}.history",
                ),
            ]

        def get_wallet_summary(self, market: PredictionMarketRecord):
            return WalletSummary(
                market_id=market.market_id,
                venue=self.provider,
                concentration_hhi=0.42,
                top_participant_share=0.55,
                total_trades=3,
                total_notional=1500.0,
                participants=[
                    WalletActivityRecord(
                        participant_id=f"{self.provider}:wallet:1",
                        display_name="Desk One",
                        venue=self.provider,
                        side="buy",
                        outcome_label=market.probability_label,
                        trade_count=3,
                        total_size=250.0,
                        average_price=0.48,
                        first_seen=base_time - timedelta(hours=6),
                        last_seen=base_time,
                        current_edge=0.04,
                        source_provider=self.provider,
                        retrieved_at=base_time,
                        origin=f"{self.provider}.wallets",
                    )
                ],
                source_provider=self.provider,
                retrieved_at=base_time,
                origin=f"{self.provider}.wallets",
            )

        def list_event_markets(self, market: PredictionMarketRecord, *, limit: int = 12):
            return [row for row in self.records if row.market_id != market.market_id][:limit]

        def build_calibration_summary(self, *, sample_size: int = 30):
            return CalibrationSummary(
                venue=self.provider,
                sample_size=2,
                warnings=[],
                source_provider=self.provider,
                retrieved_at=base_time,
                origin=f"{self.provider}.calibration",
                transformation_note="Calibration uses last traded probabilities as a first-pass proxy.",
            )

    polymarket_record = _build_market(
        market_id="polymarket:fed-cut",
        venue="polymarket",
        provider_market_id="fed-cut",
        title="Will the Fed cut rates in March?",
        event_title="Fed decision in March?",
        category="Economics",
        current_probability=0.52,
        retrieved_at=base_time,
    )
    polymarket_sibling = _build_market(
        market_id="polymarket:fed-hold",
        venue="polymarket",
        provider_market_id="fed-hold",
        title="Will the Fed hold rates in March?",
        event_title="Fed decision in March?",
        category="Economics",
        current_probability=0.41,
        retrieved_at=base_time,
    )
    kalshi_match = _build_market(
        market_id="kalshi:KXFED-MARCH-CUT",
        venue="kalshi",
        provider_market_id="KXFED-MARCH-CUT",
        title="Will the Fed cut rates in March?",
        event_title="Fed March decision",
        category="Economy",
        current_probability=0.49,
        retrieved_at=base_time,
    )
    sports_record = _build_market(
        market_id="polymarket:ukraine-world-cup",
        venue="polymarket",
        provider_market_id="ukraine-world-cup",
        title="Will Ukraine qualify for the 2026 FIFA World Cup?",
        event_title="2026 FIFA World Cup qualification",
        category="Sports",
        series_title="Sports",
        current_probability=0.37,
        retrieved_at=base_time,
    )
    service = PredictionMarketService(
        adapters={
            "polymarket": FakeAdapter("polymarket", [polymarket_record, polymarket_sibling, sports_record]),
            "kalshi": FakeAdapter("kalshi", [kalshi_match]),
        }
    )

    screener_result = service.screener(PredictionMarketScreenerRequest(status="open", limit=10))
    assert {row.market_id for row in screener_result.markets} == {
        "polymarket:fed-cut",
        "polymarket:fed-hold",
        "kalshi:KXFED-MARCH-CUT",
    }
    assert {row.category for row in screener_result.markets} == {"Economy"}
    assert {row.status for row in screener_result.venues} == {"active"}

    related = service.get_related_markets("polymarket:fed-cut")
    assert any(row.relationship in {"same_event", "conditional_consistency", "adjacent_threshold"} for row in related)
    assert any(row.relationship == "cross_venue_analog" for row in related)
    assert all(row.relationship != "weak_venue_link" for row in related)

    unrelated_sibling = _build_market(
        market_id="polymarket:argentina-dollarize",
        venue="polymarket",
        provider_market_id="argentina-dollarize",
        title="Will Argentina dollarize by 2027?",
        event_title="Venue catch-all grouping",
        category="Economics",
        current_probability=0.18,
        retrieved_at=base_time,
    )
    # Venue-metadata-only siblings must not be presented as semantically related
    # when real matches exist (the audited GTA VI failure mode).
    contaminated_service = PredictionMarketService(
        adapters={
            "polymarket": FakeAdapter("polymarket", [polymarket_record, polymarket_sibling, unrelated_sibling]),
            "kalshi": FakeAdapter("kalshi", [kalshi_match]),
        }
    )
    contaminated_related = contaminated_service.get_related_markets("polymarket:fed-cut")
    assert all(row.market_id != "polymarket:argentina-dollarize" for row in contaminated_related)
    assert any(row.relationship == "cross_venue_analog" for row in contaminated_related)

    # When nothing semantically related exists, the venue-only link is still shown
    # but clearly labeled as a weak match instead of pretending to be same-event.
    weak_only_service = PredictionMarketService(
        adapters={"polymarket": FakeAdapter("polymarket", [polymarket_record, unrelated_sibling])}
    )
    weak_related = weak_only_service.get_related_markets("polymarket:fed-cut")
    assert [row.relationship for row in weak_related] == ["weak_venue_link"]
    assert "Likely unrelated" in weak_related[0].note

    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    runtime.prediction_market_service = service
    client = TestClient(create_app(runtime))
    try:
        screener_response = client.post(
            "/prediction-markets/screener",
            json={"query": "fed", "venues": ["polymarket", "kalshi"], "status": "open", "limit": 10},
        )
        assert screener_response.status_code == 200
        assert len(screener_response.json()["markets"]) == 3

        detail_response = client.get("/prediction-markets/markets/polymarket:fed-cut")
        assert detail_response.status_code == 200
        assert detail_response.json()["provider_market_id"] == "fed-cut"

        history_response = client.get("/prediction-markets/markets/polymarket:fed-cut/history")
        assert history_response.status_code == 200
        assert len(history_response.json()["points"]) == 2

        wallet_response = client.get("/prediction-markets/markets/polymarket:fed-cut/wallet-summary")
        assert wallet_response.status_code == 200
        assert wallet_response.json()["participants"][0]["display_name"] == "Desk One"

        related_response = client.get("/prediction-markets/markets/polymarket:fed-cut/related")
        assert related_response.status_code == 200
        assert len(related_response.json()["related"]) >= 2

        calibration_response = client.get("/prediction-markets/markets/polymarket:fed-cut/calibration")
        assert calibration_response.status_code == 200
        assert calibration_response.json()["transformation_note"]
    finally:
        runtime.shutdown()


def test_prediction_market_service_screener_overfetches_for_relevance():
    base_time = datetime(2026, 3, 14, 20, 0, 0)
    buried_research_rows = [
        _build_market(
            market_id=f"polymarket:fed-cut-{index}",
            venue="polymarket",
            provider_market_id=f"fed-cut-{index}",
            title=f"Will the Fed cut rates in meeting {index}?",
            event_title="Fed decisions",
            category="Economics",
            current_probability=0.45 + (index * 0.01),
            retrieved_at=base_time,
        )
        for index in range(5)
    ]
    filler_rows = [
        _build_market(
            market_id=f"polymarket:sports-{index}",
            venue="polymarket",
            provider_market_id=f"sports-{index}",
            title=f"Will Team {index} win the football final?",
            event_title="Sports weekly specials",
            category="Sports",
            series_title="Sports",
            current_probability=0.5,
            retrieved_at=base_time,
        )
        for index in range(180)
    ]
    records = filler_rows + buried_research_rows

    class DeepCatalogAdapter:
        provider = "polymarket"

        def list_markets(
            self,
            *,
            status: str = "open",
            limit: int = 50,
            force_refresh: bool = False,
            query: str = "",
            category: str | None = None,
        ):
            return records[:limit]

        def get_market(self, provider_market_id: str):
            return next((row for row in records if row.provider_market_id == provider_market_id), None)

        def get_history(self, market: PredictionMarketRecord):
            return []

        def get_wallet_summary(self, market: PredictionMarketRecord):
            return WalletSummary(
                market_id=market.market_id,
                venue=self.provider,
                concentration_hhi=None,
                top_participant_share=None,
                total_trades=0,
                total_notional=0.0,
                source_provider=self.provider,
                retrieved_at=base_time,
                origin=f"{self.provider}.wallets",
            )

        def list_event_markets(self, market: PredictionMarketRecord, *, limit: int = 12):
            return []

        def build_calibration_summary(self, *, sample_size: int = 30):
            return CalibrationSummary(
                venue=self.provider,
                sample_size=0,
                source_provider=self.provider,
                retrieved_at=base_time,
                origin=f"{self.provider}.calibration",
            )

    service = PredictionMarketService(adapters={"polymarket": DeepCatalogAdapter()})

    rows = service.screener(PredictionMarketScreenerRequest(status="open", limit=5)).markets

    assert [row.market_id for row in rows] == [row.market_id for row in buried_research_rows]


def test_prediction_market_service_query_ignores_description_only_false_positives():
    base_time = datetime(2026, 3, 14, 20, 0, 0)

    senate_record = _build_market(
        market_id="polymarket:senate-control",
        venue="polymarket",
        provider_market_id="senate-control",
        title="Will the Republican Party control the Senate after the 2026 Midterm elections?",
        event_title="Which party will win the Senate in 2026?",
        category="Politics",
        current_probability=0.49,
        retrieved_at=base_time,
    )
    senate_record = senate_record.__class__(
        **{
            **senate_record.__dict__,
            "description": "Determination uses final federal and state election certification."
        }
    )
    fed_record = _build_market(
        market_id="polymarket:fed-cut",
        venue="polymarket",
        provider_market_id="fed-cut",
        title="Will the Fed cut rates in March?",
        event_title="Fed decision in March?",
        category="Economics",
        current_probability=0.52,
        retrieved_at=base_time,
    )

    class QueryAdapter:
        provider = "polymarket"

        def list_markets(
            self,
            *,
            status: str = "open",
            limit: int = 50,
            force_refresh: bool = False,
            query: str = "",
            category: str | None = None,
        ):
            return [senate_record, fed_record][:limit]

        def get_market(self, provider_market_id: str):
            return next((row for row in [senate_record, fed_record] if row.provider_market_id == provider_market_id), None)

        def get_history(self, market: PredictionMarketRecord):
            return []

        def get_wallet_summary(self, market: PredictionMarketRecord):
            return WalletSummary(
                market_id=market.market_id,
                venue=self.provider,
                concentration_hhi=None,
                top_participant_share=None,
                total_trades=0,
                total_notional=0.0,
                source_provider=self.provider,
                retrieved_at=base_time,
                origin=f"{self.provider}.wallets",
            )

        def list_event_markets(self, market: PredictionMarketRecord, *, limit: int = 12):
            return []

        def build_calibration_summary(self, *, sample_size: int = 30):
            return CalibrationSummary(
                venue=self.provider,
                sample_size=0,
                source_provider=self.provider,
                retrieved_at=base_time,
                origin=f"{self.provider}.calibration",
            )

    service = PredictionMarketService(adapters={"polymarket": QueryAdapter()})

    rows = service.screener(PredictionMarketScreenerRequest(query="fed", status="open", limit=10)).markets

    assert [row.market_id for row in rows] == ["polymarket:fed-cut"]


def test_prediction_market_service_prefers_macro_headline_over_generic_tags():
    base_time = datetime(2026, 3, 14, 20, 0, 0)
    inflation_record = _build_market(
        market_id="polymarket:inflation-2025",
        venue="polymarket",
        provider_market_id="inflation-2025",
        title="Will inflation reach more than 3% in 2025?",
        event_title="How high will inflation get in 2025?",
        category="Politics",
        current_probability=0.44,
        retrieved_at=base_time,
    )
    inflation_record = inflation_record.__class__(
        **{
            **inflation_record.__dict__,
            "tags": ["Politics", "Economy", "Inflation", "Macro Indicators"],
        }
    )

    class CategoryAdapter:
        provider = "polymarket"

        def list_markets(
            self,
            *,
            status: str = "open",
            limit: int = 50,
            force_refresh: bool = False,
            query: str = "",
            category: str | None = None,
        ):
            return [inflation_record][:limit]

        def get_market(self, provider_market_id: str):
            return inflation_record if provider_market_id == inflation_record.provider_market_id else None

        def get_history(self, market: PredictionMarketRecord):
            return []

        def get_wallet_summary(self, market: PredictionMarketRecord):
            return WalletSummary(
                market_id=market.market_id,
                venue=self.provider,
                concentration_hhi=None,
                top_participant_share=None,
                total_trades=0,
                total_notional=0.0,
                source_provider=self.provider,
                retrieved_at=base_time,
                origin=f"{self.provider}.wallets",
            )

        def list_event_markets(self, market: PredictionMarketRecord, *, limit: int = 12):
            return []

        def build_calibration_summary(self, *, sample_size: int = 30):
            return CalibrationSummary(
                venue=self.provider,
                sample_size=0,
                source_provider=self.provider,
                retrieved_at=base_time,
                origin=f"{self.provider}.calibration",
            )

    service = PredictionMarketService(adapters={"polymarket": CategoryAdapter()})

    rows = service.screener(PredictionMarketScreenerRequest(category="Economy", status="open", limit=10)).markets

    assert [row.category for row in rows] == ["Economy"]


def test_prediction_market_service_canonicalizes_ai_markets_to_tech_ai_category():
    base_time = datetime(2026, 6, 10, 20, 0, 0)
    ai_record = _build_market(
        market_id="polymarket:openai-top-model",
        venue="polymarket",
        provider_market_id="openai-top-model",
        title="Will OpenAI have a #1 AI model by June 30?",
        event_title="Which company has the top AI model?",
        category="AI",
        series_title="AI Models",
        current_probability=0.62,
        retrieved_at=base_time,
    )
    geopolitics_record = _build_market(
        market_id="polymarket:china-ai-chips",
        venue="polymarket",
        provider_market_id="china-ai-chips",
        title="Will China restrict AI chip exports this year?",
        event_title="China AI chip export controls",
        category="AI",
        series_title="Export Controls",
        current_probability=0.31,
        retrieved_at=base_time,
    )

    class TechAdapter:
        provider = "polymarket"

        def list_markets(
            self,
            *,
            status: str = "open",
            limit: int = 50,
            force_refresh: bool = False,
            query: str = "",
            category: str | None = None,
        ):
            return [ai_record, geopolitics_record][:limit]

        def get_market(self, provider_market_id: str):
            for record in (ai_record, geopolitics_record):
                if record.provider_market_id == provider_market_id:
                    return record
            return None

        def get_history(self, market: PredictionMarketRecord):
            return []

        def get_wallet_summary(self, market: PredictionMarketRecord):
            return WalletSummary(
                market_id=market.market_id,
                venue=self.provider,
                concentration_hhi=None,
                top_participant_share=None,
                total_trades=0,
                total_notional=0.0,
                source_provider=self.provider,
                retrieved_at=base_time,
                origin=f"{self.provider}.wallets",
            )

        def list_event_markets(self, market: PredictionMarketRecord, *, limit: int = 12):
            return []

        def build_calibration_summary(self, *, sample_size: int = 30):
            return CalibrationSummary(
                venue=self.provider,
                sample_size=0,
                source_provider=self.provider,
                retrieved_at=base_time,
                origin=f"{self.provider}.calibration",
            )

    service = PredictionMarketService(adapters={"polymarket": TechAdapter()})

    # The AI-model market previously canonicalized to category None and was
    # unreachable through the screener category filter.
    tech_rows = service.screener(
        PredictionMarketScreenerRequest(category="Tech/AI", status="open", limit=10)
    ).markets
    assert [row.market_id for row in tech_rows] == ["polymarket:openai-top-model"]
    assert [row.category for row in tech_rows] == ["Tech/AI"]

    # Markets that already canonicalize to an existing research category keep
    # their label; Tech/AI keywords are matched last.
    geo_rows = service.screener(
        PredictionMarketScreenerRequest(category="Geopolitics", status="open", limit=10)
    ).markets
    assert [row.market_id for row in geo_rows] == ["polymarket:china-ai-chips"]
    assert [row.category for row in geo_rows] == ["Geopolitics"]


def test_prediction_market_service_filters_expired_open_markets_and_marks_detail_broken():
    base_time = datetime(2026, 3, 15, 12, 0, 0)
    expired_open = _build_market(
        market_id="polymarket:expired-iran",
        venue="polymarket",
        provider_market_id="expired-iran",
        title="Will Iran resume uranium enrichment above 60% by March 10?",
        event_title="Iran enrichment escalation",
        category="Geopolitics",
        current_probability=0.61,
        retrieved_at=base_time - timedelta(hours=2),
    )
    expired_open = expired_open.__class__(
        **{
            **expired_open.__dict__,
            "end_time": base_time - timedelta(days=1),
            "status": "open",
        }
    )
    current_market = _build_market(
        market_id="polymarket:iran-current",
        venue="polymarket",
        provider_market_id="iran-current",
        title="Will Iran restart formal nuclear talks before April?",
        event_title="Iran diplomacy",
        category="Geopolitics",
        current_probability=0.46,
        retrieved_at=base_time - timedelta(hours=1),
    )

    class ExpiredAdapter:
        provider = "polymarket"

        def list_markets(self, **kwargs):
            return [expired_open, current_market]

        def get_market(self, provider_market_id: str):
            return next((row for row in [expired_open, current_market] if row.provider_market_id == provider_market_id), None)

        def get_history(self, market: PredictionMarketRecord):
            if market.provider_market_id == "expired-iran":
                return [
                    PredictionProbabilityPoint(
                        timestamp=base_time - timedelta(hours=12),
                        probability=0.58,
                        source_provider=self.provider,
                        retrieved_at=base_time - timedelta(hours=2),
                        origin="polymarket.history",
                    )
                ]
            return []

        def get_wallet_summary(self, market: PredictionMarketRecord):
            return WalletSummary(
                market_id=market.market_id,
                venue=self.provider,
                concentration_hhi=None,
                top_participant_share=None,
                total_trades=0,
                total_notional=0.0,
                source_provider=self.provider,
                retrieved_at=base_time,
                origin="polymarket.wallets",
            )

        def list_event_markets(self, market: PredictionMarketRecord, *, limit: int = 12):
            return []

        def build_calibration_summary(self, *, sample_size: int = 30):
            return CalibrationSummary(
                venue=self.provider,
                sample_size=0,
                source_provider=self.provider,
                retrieved_at=base_time,
                origin="polymarket.calibration",
            )

    service = PredictionMarketService(adapters={"polymarket": ExpiredAdapter()})

    result = service.screener(PredictionMarketScreenerRequest(status="open", limit=10))

    assert [row.market_id for row in result.markets] == ["polymarket:iran-current"]
    assert result.venues[0].broken_markets == 1

    detail = service.get_market_detail("polymarket:expired-iran")

    assert detail is not None
    assert detail.freshness is not None
    assert detail.freshness.status == "broken"
    assert "end_time" in str(detail.freshness.reason)


def test_prediction_market_service_handles_mixed_naive_and_aware_history_timestamps():
    base_time = datetime(2026, 3, 15, 12, 0, 0)
    market = _build_market(
        market_id="polymarket:fed-cut",
        venue="polymarket",
        provider_market_id="fed-cut",
        title="Will the Fed cut rates by June?",
        event_title="Fed policy outlook",
        category="Economy",
        current_probability=0.52,
        retrieved_at=base_time,
    )

    class MixedTimeAdapter:
        provider = "polymarket"

        def list_markets(self, **kwargs):
            return [market]

        def get_market(self, provider_market_id: str):
            return market if provider_market_id == market.provider_market_id else None

        def get_history(self, market: PredictionMarketRecord):
            return [
                PredictionProbabilityPoint(
                    timestamp=(base_time - timedelta(hours=1)).replace(tzinfo=timezone.utc),
                    probability=0.5,
                    source_provider=self.provider,
                    retrieved_at=base_time,
                    origin="polymarket.history",
                )
            ]

        def get_wallet_summary(self, market: PredictionMarketRecord):
            return WalletSummary(
                market_id=market.market_id,
                venue=self.provider,
                concentration_hhi=None,
                top_participant_share=None,
                total_trades=0,
                total_notional=0.0,
                source_provider=self.provider,
                retrieved_at=base_time,
                origin="polymarket.wallets",
            )

        def list_event_markets(self, market: PredictionMarketRecord, *, limit: int = 12):
            return []

        def build_calibration_summary(self, *, sample_size: int = 30):
            return CalibrationSummary(
                venue=self.provider,
                sample_size=0,
                source_provider=self.provider,
                retrieved_at=base_time,
                origin="polymarket.calibration",
            )

    service = PredictionMarketService(adapters={"polymarket": MixedTimeAdapter()})

    detail = service.get_market_detail("polymarket:fed-cut")
    related = service.get_related_markets("polymarket:fed-cut")

    assert detail is not None
    assert detail.freshness is not None
    assert detail.freshness.status != "broken"
    assert detail.freshness.history_lag_seconds == pytest.approx(3600.0)
    assert related == []


def test_prediction_market_service_research_rank_prefers_current_liquid_contracts():
    base_time = datetime(2026, 3, 15, 12, 0, 0)
    fed_current = _build_market(
        market_id="polymarket:fed-june-cut",
        venue="polymarket",
        provider_market_id="fed-june-cut",
        title="Will the Fed cut rates by June?",
        event_title="Fed policy outlook",
        category="Economy",
        current_probability=0.54,
        retrieved_at=base_time - timedelta(minutes=20),
    )
    fed_current = fed_current.__class__(
        **{
            **fed_current.__dict__,
            "volume": 400_000.0,
            "volume_24h": 50_000.0,
            "liquidity": 80_000.0,
            "open_interest": 25_000.0,
            "end_time": base_time + timedelta(days=30),
        }
    )
    fed_long_tail = _build_market(
        market_id="polymarket:fed-2027-meeting",
        venue="polymarket",
        provider_market_id="fed-2027-meeting",
        title="Will the Fed cut rates at the first 2027 meeting?",
        event_title="Fed policy outlook",
        category="Economy",
        current_probability=0.49,
        retrieved_at=base_time - timedelta(minutes=15),
    )
    fed_long_tail = fed_long_tail.__class__(
        **{
            **fed_long_tail.__dict__,
            "volume": 3_000.0,
            "volume_24h": 45.0,
            "liquidity": 600.0,
            "open_interest": 10.0,
            "end_time": base_time + timedelta(days=660),
        }
    )
    bitcoin_current = _build_market(
        market_id="polymarket:btc-100k",
        venue="polymarket",
        provider_market_id="btc-100k",
        title="Will Bitcoin reach $100k by June 30?",
        event_title="Bitcoin milestones",
        category="Crypto",
        current_probability=0.48,
        retrieved_at=base_time - timedelta(minutes=10),
    )
    bitcoin_current = bitcoin_current.__class__(
        **{
            **bitcoin_current.__dict__,
            "volume": 320_000.0,
            "volume_24h": 35_000.0,
            "liquidity": 45_000.0,
            "open_interest": 12_000.0,
            "end_time": base_time + timedelta(days=90),
        }
    )

    class RankingAdapter:
        provider = "polymarket"

        def list_markets(self, **kwargs):
            return [fed_long_tail, bitcoin_current, fed_current]

        def get_market(self, provider_market_id: str):
            return next((row for row in [fed_long_tail, bitcoin_current, fed_current] if row.provider_market_id == provider_market_id), None)

        def get_history(self, market: PredictionMarketRecord):
            return []

        def get_wallet_summary(self, market: PredictionMarketRecord):
            return WalletSummary(
                market_id=market.market_id,
                venue=self.provider,
                concentration_hhi=None,
                top_participant_share=None,
                total_trades=0,
                total_notional=0.0,
                source_provider=self.provider,
                retrieved_at=base_time,
                origin="polymarket.wallets",
            )

        def list_event_markets(self, market: PredictionMarketRecord, *, limit: int = 12):
            return []

        def build_calibration_summary(self, *, sample_size: int = 30):
            return CalibrationSummary(
                venue=self.provider,
                sample_size=0,
                source_provider=self.provider,
                retrieved_at=base_time,
                origin="polymarket.calibration",
            )

    service = PredictionMarketService(adapters={"polymarket": RankingAdapter()})

    fed_rows = service.screener(PredictionMarketScreenerRequest(query="fed", status="open", limit=5)).markets
    bitcoin_rows = service.screener(PredictionMarketScreenerRequest(query="bitcoin", status="open", limit=5)).markets

    assert [row.market_id for row in fed_rows[:2]] == ["polymarket:fed-june-cut", "polymarket:fed-2027-meeting"]
    assert bitcoin_rows[0].market_id == "polymarket:btc-100k"
    assert fed_rows[0].research_score > fed_rows[1].research_score


def test_prediction_market_service_reports_venue_status_when_one_venue_has_no_results():
    base_time = datetime(2026, 3, 15, 12, 0, 0)
    kalshi_market = _build_market(
        market_id="kalshi:fed-cut",
        venue="kalshi",
        provider_market_id="fed-cut",
        title="Will the Fed cut rates by June?",
        event_title="Fed policy outlook",
        category="Economy",
        current_probability=0.52,
        retrieved_at=base_time,
    )
    kalshi_market = kalshi_market.__class__(**{**kalshi_market.__dict__, "volume_24h": 8_000.0, "liquidity": 20_000.0})

    class VenueAdapter:
        def __init__(self, provider: str, rows: list[PredictionMarketRecord]) -> None:
            self.provider = provider
            self.rows = rows

        def list_markets(self, **kwargs):
            return list(self.rows)

        def get_market(self, provider_market_id: str):
            return next((row for row in self.rows if row.provider_market_id == provider_market_id), None)

        def get_history(self, market: PredictionMarketRecord):
            return []

        def get_wallet_summary(self, market: PredictionMarketRecord):
            return WalletSummary(
                market_id=market.market_id,
                venue=self.provider,
                concentration_hhi=None,
                top_participant_share=None,
                total_trades=0,
                total_notional=0.0,
                source_provider=self.provider,
                retrieved_at=base_time,
                origin=f"{self.provider}.wallets",
            )

        def list_event_markets(self, market: PredictionMarketRecord, *, limit: int = 12):
            return []

        def build_calibration_summary(self, *, sample_size: int = 30):
            return CalibrationSummary(
                venue=self.provider,
                sample_size=0,
                source_provider=self.provider,
                retrieved_at=base_time,
                origin=f"{self.provider}.calibration",
            )

    service = PredictionMarketService(
        adapters={
            "polymarket": VenueAdapter("polymarket", []),
            "kalshi": VenueAdapter("kalshi", [kalshi_market]),
        }
    )

    result = service.screener(PredictionMarketScreenerRequest(query="fed", status="open", limit=5))

    venue_statuses = {venue.venue: venue for venue in result.venues}

    assert venue_statuses["polymarket"].status == "no_results"
    assert venue_statuses["kalshi"].status == "active"
    assert "returned no markets" in str(venue_statuses["polymarket"].message)
    assert result.markets[0].market_id == "kalshi:fed-cut"


def _build_market(
    *,
    market_id: str,
    venue: str,
    provider_market_id: str,
    title: str,
    event_title: str,
    category: str,
    series_title: str = "Rates",
    current_probability: float,
    retrieved_at: datetime,
) -> PredictionMarketRecord:
    return PredictionMarketRecord(
        market_id=market_id,
        venue=venue,
        title=title,
        subtitle=None,
        description=title,
        status="open",
        category=category,
        event_id=f"{venue}:event:1",
        event_title=event_title,
        series_id=f"{venue}:series:1",
        series_title=series_title,
        provider_market_id=provider_market_id,
        provider_condition_id="condition-1" if venue == "polymarket" else None,
        provider_event_id="1",
        provider_series_id="series-1",
        slug=provider_market_id.lower(),
        end_time=retrieved_at + timedelta(days=4),
        open_time=retrieved_at - timedelta(days=7),
        close_time=None,
        current_probability=current_probability,
        probability_label="Yes",
        volume=1000.0,
        volume_24h=100.0,
        liquidity=500.0,
        open_interest=250.0,
        best_bid=current_probability - 0.01,
        best_ask=current_probability + 0.01,
        spread=0.02,
        recent_price_change=0.03,
        resolved_probability=None,
        resolution_outcome=None,
        image_url=None,
        resolution_source="Rulebook",
        outcomes=[
            PredictionMarketOutcome(
                outcome_id=f"{market_id}:yes",
                label="Yes",
                probability=current_probability,
                token_id="yes-token" if venue == "polymarket" else None,
                source_provider=venue,
                retrieved_at=retrieved_at,
                origin=f"{venue}.seed",
            ),
            PredictionMarketOutcome(
                outcome_id=f"{market_id}:no",
                label="No",
                probability=1 - current_probability,
                token_id="no-token" if venue == "polymarket" else None,
                source_provider=venue,
                retrieved_at=retrieved_at,
                origin=f"{venue}.seed",
                transformation_note="Derived as one minus the normalized Yes probability.",
            ),
        ],
        tags=[category],
        source_provider=venue,
        retrieved_at=retrieved_at,
        origin=f"{venue}.seed",
        transformation_note="Seed test market.",
    )


class _WindowRecordingFetcher:
    """Captures every provider call so window plumbing can be asserted."""

    def __init__(self, history_by_scope: dict[str, list[dict]] | None = None) -> None:
        self.calls: list[tuple[str, dict | None]] = []
        self.history_by_scope = history_by_scope or {}

    def __call__(self, url: str, params: dict | None = None):
        self.calls.append((url, dict(params or {})))
        if "prices-history" in url:
            scope = "max" if (params or {}).get("interval") else "window"
            return {"history": self.history_by_scope.get(scope, [])}
        return {}


def _history_market(*, venue: str = "polymarket") -> PredictionMarketRecord:
    return _build_market(
        market_id=f"{venue}:fed-cut",
        venue=venue,
        provider_market_id="fed-cut",
        title="Will the Fed cut rates?",
        event_title="Fed decisions",
        category="Economy",
        current_probability=0.6,
        retrieved_at=datetime(2026, 3, 18, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_polymarket_history_window_requests_bounded_timestamps_and_fidelity(tmp_path):
    points = [
        {"t": int(datetime(2026, 3, 17, 12, tzinfo=timezone.utc).timestamp()), "p": 0.55},
        {"t": int(datetime(2026, 3, 18, 12, tzinfo=timezone.utc).timestamp()), "p": 0.61},
    ]
    fetcher = _WindowRecordingFetcher({"window": points})
    adapter = PolymarketAdapter(CacheService(tmp_path / "cache"), fetch_json=fetcher)
    market = _history_market()

    window = PredictionHistoryWindow(
        range_key="1w",
        start=datetime(2026, 3, 11, 12, tzinfo=timezone.utc),
        end=datetime(2026, 3, 18, 12, tzinfo=timezone.utc),
        resolution_minutes=60,
        outcome_token_id="yes-token",
    )
    fetch = adapter.get_history_window(market, window)

    assert [point.probability for point in fetch.points] == [0.55, 0.61]
    assert fetch.effective_resolution_minutes == 60
    assert fetch.windowing == "provider_window"
    _, params = fetcher.calls[0]
    assert params["startTs"] == int(window.start.timestamp())
    assert params["endTs"] == int(window.end.timestamp())
    assert params["fidelity"] == 60
    assert "interval" not in params


def test_polymarket_history_window_falls_back_to_full_series_when_window_is_empty(tmp_path):
    max_points = [{"t": int(datetime(2026, 1, 5, tzinfo=timezone.utc).timestamp()), "p": 0.4}]
    fetcher = _WindowRecordingFetcher({"window": [], "max": max_points})
    adapter = PolymarketAdapter(CacheService(tmp_path / "cache"), fetch_json=fetcher)

    fetch = adapter.get_history_window(
        _history_market(),
        PredictionHistoryWindow(
            range_key="1d",
            start=datetime(2026, 3, 17, 12, tzinfo=timezone.utc),
            end=datetime(2026, 3, 18, 12, tzinfo=timezone.utc),
            resolution_minutes=5,
            outcome_token_id="yes-token",
        ),
    )

    assert fetch.windowing == "provider_full"
    assert [point.probability for point in fetch.points] == [0.4]
    assert any("full available series" in warning for warning in fetch.warnings)
    assert fetcher.calls[-1][1]["interval"] == "max"


def test_polymarket_history_cache_key_separates_resolutions(tmp_path):
    fetcher = _WindowRecordingFetcher({"window": [{"t": 1773835200, "p": 0.5}]})
    adapter = PolymarketAdapter(CacheService(tmp_path / "cache"), fetch_json=fetcher)
    market = _history_market()
    bounds = {
        "start": datetime(2026, 3, 11, 12, tzinfo=timezone.utc),
        "end": datetime(2026, 3, 18, 12, tzinfo=timezone.utc),
    }

    adapter.get_history_window(market, PredictionHistoryWindow(range_key="1w", resolution_minutes=60, outcome_token_id="yes-token", **bounds))
    adapter.get_history_window(market, PredictionHistoryWindow(range_key="1w", resolution_minutes=60, outcome_token_id="yes-token", **bounds))
    adapter.get_history_window(market, PredictionHistoryWindow(range_key="1w", resolution_minutes=5, outcome_token_id="yes-token", **bounds))

    fidelities = [params["fidelity"] for _, params in fetcher.calls]
    # The repeat at 60 is served from cache; the 5-minute request is a real miss.
    assert fidelities == [60, 5]


def test_polymarket_history_window_uses_the_requested_outcome_token(tmp_path):
    fetcher = _WindowRecordingFetcher({"max": [{"t": 1773835200, "p": 0.31}]})
    adapter = PolymarketAdapter(CacheService(tmp_path / "cache"), fetch_json=fetcher)

    adapter.get_history_window(
        _history_market(),
        PredictionHistoryWindow(range_key="max", outcome_id="no", outcome_token_id="no-token"),
    )

    assert fetcher.calls[0][1]["market"] == "no-token"


def test_kalshi_history_window_clamps_resolution_and_reports_the_downgrade(tmp_path):
    def fake_fetch(url: str, params: dict | None = None):
        return {"candlesticks": []}

    adapter = KalshiAdapter(CacheService(tmp_path / "cache"), fetch_json=fake_fetch)
    market = _build_market(
        market_id="kalshi:KXFED",
        venue="kalshi",
        provider_market_id="KXFED",
        title="Fed cut?",
        event_title="Fed",
        category="Economy",
        current_probability=0.5,
        retrieved_at=datetime(2026, 3, 18, 12, tzinfo=timezone.utc),
    )

    fetch = adapter.get_history_window(market, PredictionHistoryWindow(range_key="1w", resolution_minutes=5))

    assert fetch.effective_resolution_minutes == 60
    assert any("5-minute request was served at 60" in warning for warning in fetch.warnings)


def test_kalshi_history_window_rejects_a_window_outside_the_market_life(tmp_path):
    adapter = KalshiAdapter(CacheService(tmp_path / "cache"), fetch_json=lambda url, params=None: {"candlesticks": []})
    market = _build_market(
        market_id="kalshi:KXFED",
        venue="kalshi",
        provider_market_id="KXFED",
        title="Fed cut?",
        event_title="Fed",
        category="Economy",
        current_probability=0.5,
        retrieved_at=datetime(2026, 3, 18, 12, tzinfo=timezone.utc),
    )

    fetch = adapter.get_history_window(
        market,
        PredictionHistoryWindow(
            range_key="1d",
            start=datetime(2020, 1, 1, tzinfo=timezone.utc),
            end=datetime(2020, 1, 2, tzinfo=timezone.utc),
        ),
    )

    assert fetch.points == []
    assert any("outside the Kalshi market's trading life" in warning for warning in fetch.warnings)


class _SeriesAdapter:
    """Legacy-shaped adapter: no windowing capability, full series only."""

    def __init__(self, provider: str, records, series_by_market: dict[str, list[tuple[datetime, float]]]):
        self.provider = provider
        self.records = records
        self.series_by_market = series_by_market

    def list_markets(self, *, status="open", limit=50, force_refresh=False, query="", category=None):
        return self.records[:limit]

    def get_market(self, provider_market_id: str):
        for record in self.records:
            if record.provider_market_id == provider_market_id:
                return record
        return None

    def get_history(self, market: PredictionMarketRecord):
        return [
            PredictionProbabilityPoint(
                timestamp=stamp,
                probability=value,
                source_provider=self.provider,
                retrieved_at=stamp,
                origin=f"{self.provider}.history",
            )
            for stamp, value in self.series_by_market.get(market.market_id, [])
        ]

    def get_wallet_summary(self, market: PredictionMarketRecord):
        return WalletSummary(
            market_id=market.market_id,
            venue=self.provider,
            concentration_hhi=None,
            top_participant_share=None,
            total_trades=0,
            total_notional=0.0,
        )

    def list_event_markets(self, market: PredictionMarketRecord, *, limit: int = 12):
        return []

    def build_calibration_summary(self, *, sample_size: int = 30):
        return CalibrationSummary(venue=self.provider, sample_size=0)


def _hourly_series(start: datetime, values: list[float]) -> list[tuple[datetime, float]]:
    return [(start + timedelta(hours=index), value) for index, value in enumerate(values)]


def _service_with_series(series_by_market) -> PredictionMarketService:
    base = datetime(2026, 3, 18, 12, tzinfo=timezone.utc)
    records = []
    for market_id, series in series_by_market.items():
        venue, provider_id = market_id.split(":", 1)
        records.append(
            _build_market(
                market_id=market_id,
                venue=venue,
                provider_market_id=provider_id,
                title=f"Contract {provider_id}",
                event_title="Fed decisions",
                category="Economy",
                current_probability=series[-1][1],
                retrieved_at=base,
            )
        )
    by_venue: dict[str, list[PredictionMarketRecord]] = {}
    for record in records:
        by_venue.setdefault(record.venue, []).append(record)
    return PredictionMarketService(
        adapters={
            venue: _SeriesAdapter(venue, venue_records, series_by_market)
            for venue, venue_records in by_venue.items()
        }
    )


def test_history_series_clips_a_legacy_adapter_series_to_the_requested_window():
    start = datetime(2026, 3, 1, tzinfo=timezone.utc)
    service = _service_with_series(
        {"polymarket:fed-cut": [(start + timedelta(days=index), 0.4 + index * 0.01) for index in range(18)]}
    )

    full = service.get_history_series("polymarket:fed-cut", range_key="max")
    windowed = service.get_history_series("polymarket:fed-cut", range_key="1w")

    assert full.windowing == "client_clipped"
    assert len(windowed.points) < len(full.points)
    assert all(point.timestamp >= windowed.window_start for point in windowed.points)
    assert windowed.requested_range == "1w"
    assert windowed.coverage_start is not None and windowed.coverage_end is not None


def test_history_series_reports_stats_over_the_window():
    start = datetime(2026, 3, 10, tzinfo=timezone.utc)
    service = _service_with_series(
        {"polymarket:fed-cut": _hourly_series(start, [0.40, 0.44, 0.60, 0.52, 0.55])}
    )

    stats = service.get_history_series("polymarket:fed-cut", range_key="max").stats

    assert stats.point_count == 5
    assert stats.high == pytest.approx(0.60)
    assert stats.low == pytest.approx(0.40)
    assert stats.change == pytest.approx(0.15)
    assert stats.range_width == pytest.approx(0.20)
    assert stats.percentile_of_range == pytest.approx(0.75)
    assert stats.max_move == pytest.approx(0.16)
    assert stats.share_above_half == pytest.approx(0.6)
    assert stats.median_gap_seconds == pytest.approx(3600)
    assert stats.daily_volatility is not None


def test_history_series_warns_when_the_window_predates_available_history():
    service = _service_with_series(
        {"polymarket:fed-cut": _hourly_series(datetime(2026, 3, 17, tzinfo=timezone.utc), [0.5, 0.51])}
    )

    history = service.get_history_series("polymarket:fed-cut", range_key="1y")

    assert any("days of history" in warning for warning in history.warnings)


def test_history_series_reports_an_unknown_range_instead_of_failing():
    service = _service_with_series(
        {"polymarket:fed-cut": _hourly_series(datetime(2026, 3, 17, tzinfo=timezone.utc), [0.5, 0.52])}
    )

    history = service.get_history_series("polymarket:fed-cut", range_key="10y")

    assert history.requested_range == "max"
    assert any("Unsupported range" in warning for warning in history.warnings)


def test_compare_markets_aligns_series_and_reports_spread_and_correlation():
    start = datetime(2026, 3, 10, tzinfo=timezone.utc)
    service = _service_with_series(
        {
            "polymarket:fed-cut": _hourly_series(start, [0.50, 0.54, 0.58, 0.60, 0.62, 0.64]),
            "kalshi:KXFED": _hourly_series(start, [0.46, 0.50, 0.53, 0.56, 0.57, 0.60]),
        }
    )

    comparison = service.compare_markets(["polymarket:fed-cut", "kalshi:KXFED"], range_key="max")

    assert len(comparison.legs) == 2
    assert len(comparison.pairs) == 1
    pair = comparison.pairs[0]
    assert pair.overlap_points > 0
    assert pair.current_spread == pytest.approx(0.04, abs=0.01)
    assert pair.mean_spread is not None
    assert pair.max_spread >= pair.min_spread
    # Both contracts drift up together, so change correlation should be strongly positive.
    assert pair.correlation is not None and pair.correlation > 0.5
    assert comparison.basket.leg_count == 2
    assert comparison.basket.probability_sum == pytest.approx(1.24)
    assert comparison.basket.same_venue is False
    assert "mutually exclusive" in comparison.basket.note


def test_compare_markets_flags_non_overlapping_contracts():
    service = _service_with_series(
        {
            "polymarket:fed-cut": _hourly_series(datetime(2026, 3, 1, tzinfo=timezone.utc), [0.5, 0.52, 0.54]),
            "kalshi:KXFED": _hourly_series(datetime(2026, 3, 17, tzinfo=timezone.utc), [0.4, 0.42, 0.44]),
        }
    )

    pair = service.compare_markets(["polymarket:fed-cut", "kalshi:KXFED"], range_key="max").pairs[0]

    assert pair.overlap_points == 0
    assert any("no overlapping history" in warning for warning in pair.warnings)
    # The live probability gap is still reported even without an aligned window.
    assert pair.current_spread is not None


def test_compare_markets_deduplicates_and_caps_requested_contracts():
    series = {
        f"polymarket:c{index}": _hourly_series(datetime(2026, 3, 10, tzinfo=timezone.utc), [0.4, 0.45, 0.5])
        for index in range(8)
    }
    service = _service_with_series(series)

    comparison = service.compare_markets(
        ["polymarket:c0", "polymarket:c0", *[f"polymarket:c{index}" for index in range(1, 8)]],
        range_key="max",
    )

    assert len(comparison.legs) == 6
    assert any("Duplicate contracts" in warning for warning in comparison.warnings)
    assert any("capped at 6" in warning for warning in comparison.warnings)


def test_compare_markets_needs_two_loadable_legs():
    service = _service_with_series(
        {"polymarket:fed-cut": _hourly_series(datetime(2026, 3, 10, tzinfo=timezone.utc), [0.5, 0.55])}
    )

    comparison = service.compare_markets(["polymarket:fed-cut", "polymarket:missing"], range_key="max")

    assert len(comparison.legs) == 1
    assert comparison.pairs == []
    assert any("could not be loaded" in warning for warning in comparison.warnings)
    assert any("At least two loadable contracts" in warning for warning in comparison.warnings)


def test_history_and_compare_routes_expose_windowed_context(tmp_path):
    start = datetime(2026, 3, 10, tzinfo=timezone.utc)
    service = _service_with_series(
        {
            "polymarket:fed-cut": _hourly_series(start, [0.50, 0.54, 0.58, 0.60]),
            "kalshi:KXFED": _hourly_series(start, [0.46, 0.50, 0.53, 0.56]),
        }
    )
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    runtime.prediction_market_service = service
    client = TestClient(create_app(runtime))
    try:
        history_response = client.get(
            "/prediction-markets/markets/polymarket:fed-cut/history",
            params={"range": "1w", "resolution": 60},
        )
        assert history_response.status_code == 200
        history = history_response.json()
        assert history["requested_range"] == "1w"
        assert history["requested_resolution_minutes"] == 60
        assert history["stats"]["point_count"] == len(history["points"])
        assert history["window_start"] and history["window_end"]

        rejected = client.get(
            "/prediction-markets/markets/polymarket:fed-cut/history",
            params={"range": "decade"},
        )
        assert rejected.status_code == 422

        missing = client.get("/prediction-markets/markets/polymarket:nope/history")
        assert missing.status_code == 404

        outcome_response = client.get(
            "/prediction-markets/markets/polymarket:fed-cut/outcome-history",
            params={"range": "max"},
        )
        assert outcome_response.status_code == 200
        assert outcome_response.json()["series"][0]["label"] == "Yes"

        compare_response = client.post(
            "/prediction-markets/compare",
            json={"market_ids": ["polymarket:fed-cut", "kalshi:KXFED"], "range_key": "max"},
        )
        assert compare_response.status_code == 200
        compare = compare_response.json()
        assert len(compare["legs"]) == 2
        assert compare["pairs"][0]["overlap_points"] > 0
        assert compare["basket"]["leg_count"] == 2
        assert compare["transformation_note"]

        too_many = client.post(
            "/prediction-markets/compare",
            json={"market_ids": [f"polymarket:c{index}" for index in range(9)], "range_key": "max"},
        )
        assert too_many.status_code == 422
    finally:
        runtime.shutdown()


def test_polymarket_long_windows_use_a_named_interval_instead_of_timestamps(tmp_path):
    """The CLOB returns HTTP 400 for an explicit span beyond ~2 weeks."""
    fetcher = _WindowRecordingFetcher({"max": [{"t": 1773835200, "p": 0.5}]})
    adapter = PolymarketAdapter(CacheService(tmp_path / "cache"), fetch_json=fetcher)
    end = datetime(2026, 3, 18, 12, tzinfo=timezone.utc)

    fetch = adapter.get_history_window(
        _history_market(),
        PredictionHistoryWindow(
            range_key="3m",
            start=end - timedelta(days=90),
            end=end,
            resolution_minutes=1440,
            resolution_is_auto=False,
            outcome_token_id="yes-token",
        ),
    )

    _, params = fetcher.calls[0]
    assert params["interval"] == "max"
    assert "startTs" not in params
    assert fetch.windowing == "provider_full"
    assert any("explicit windows up to 14 days" in warning for warning in fetch.warnings)


def test_polymarket_month_window_uses_the_smallest_covering_interval(tmp_path):
    fetcher = _WindowRecordingFetcher({"max": [{"t": 1773835200, "p": 0.5}]})
    adapter = PolymarketAdapter(CacheService(tmp_path / "cache"), fetch_json=fetcher)
    end = datetime(2026, 3, 18, 12, tzinfo=timezone.utc)

    adapter.get_history_window(
        _history_market(),
        PredictionHistoryWindow(
            range_key="1m",
            start=end - timedelta(days=30),
            end=end,
            resolution_minutes=60,
            resolution_is_auto=False,
            outcome_token_id="yes-token",
        ),
    )

    assert fetcher.calls[0][1]["interval"] == "1m"


def test_polymarket_short_windows_still_use_exact_timestamps(tmp_path):
    fetcher = _WindowRecordingFetcher({"window": [{"t": 1773835200, "p": 0.5}]})
    adapter = PolymarketAdapter(CacheService(tmp_path / "cache"), fetch_json=fetcher)
    end = datetime(2026, 3, 18, 12, tzinfo=timezone.utc)

    fetch = adapter.get_history_window(
        _history_market(),
        PredictionHistoryWindow(
            range_key="1w",
            start=end - timedelta(days=7),
            end=end,
            resolution_minutes=15,
            resolution_is_auto=False,
            outcome_token_id="yes-token",
        ),
    )

    assert "startTs" in fetcher.calls[0][1]
    assert fetch.windowing == "provider_window"


def test_polymarket_max_range_widens_an_automatic_fidelity_to_reach_further_back(tmp_path):
    """The CLOB caps bars per full-history response, so coarse bars reach back further."""
    fetcher = _WindowRecordingFetcher({"max": [{"t": 1773835200, "p": 0.5}]})
    adapter = PolymarketAdapter(CacheService(tmp_path / "cache"), fetch_json=fetcher)

    fetch = adapter.get_history_window(
        _history_market(),
        PredictionHistoryWindow(range_key="max", resolution_minutes=360, resolution_is_auto=True, outcome_token_id="yes-token"),
    )

    assert fetcher.calls[0][1]["fidelity"] == 1440
    assert fetch.effective_resolution_minutes == 1440
    assert any("reach further back" in warning for warning in fetch.warnings)


def test_polymarket_max_range_honors_an_explicit_fidelity(tmp_path):
    fetcher = _WindowRecordingFetcher({"max": [{"t": 1773835200, "p": 0.5}]})
    adapter = PolymarketAdapter(CacheService(tmp_path / "cache"), fetch_json=fetcher)

    fetch = adapter.get_history_window(
        _history_market(),
        PredictionHistoryWindow(
            range_key="max",
            resolution_minutes=360,
            resolution_is_auto=False,
            outcome_token_id="yes-token",
        ),
    )

    assert fetcher.calls[0][1]["fidelity"] == 360
    assert fetch.effective_resolution_minutes == 360
    assert fetch.warnings == []
