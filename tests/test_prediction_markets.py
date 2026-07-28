from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.prediction_market_service import (
    MAX_EVENT_BOOK_LEGS,
    PredictionMarketService,
    PredictionMarketScreenerRequest,
)
from src.application.prediction_market_taxonomy import build_cross_domain_handoffs
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
from src.services.prediction_research_store import PREDICTION_WATCHLIST_LIMIT, PredictionResearchStore


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


def test_polymarket_settlement_summary_is_a_convergence_diagnostic_not_a_curve(tmp_path):
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

    # The settlement path never produces a curve: the print it would bucket was
    # made after the outcome was effectively known.
    assert summary.sample_size == 1
    assert summary.method == "settlement_last_trade_deprecated"
    assert summary.is_validated is False
    assert summary.curves == []
    assert any("convergence diagnostic" in warning for warning in summary.warnings)
    assert summary.convergence is not None
    assert summary.convergence.sample_size == 1
    assert summary.convergence.average_distance_to_outcome == pytest.approx(0.24)
    assert [observation.market_id for observation in summary.observations] == ["polymarket:resolved-with-trade"]
    assert summary.observations[0].settlement_probability == pytest.approx(0.24)


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


# ── Outward cross-domain handoffs ────────────────────────────────────────


def _themed_market(*, title: str, category: str, description: str = "", end_offset_days: int = 40):
    retrieved_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    base = _build_market(
        market_id="polymarket:themed",
        venue="polymarket",
        provider_market_id="themed",
        title=title,
        event_title=title,
        category=category,
        current_probability=0.4,
        retrieved_at=retrieved_at,
    )
    return replace(
        base,
        description=description or title,
        end_time=retrieved_at + timedelta(days=end_offset_days),
    )


def test_cross_domain_handoffs_resolve_commodity_and_chokepoint_targets():
    market = _themed_market(
        title="Will Iran close the Strait of Hormuz to oil tankers before September?",
        category="Geopolitics",
    )

    handoffs = build_cross_domain_handoffs(market)
    by_tab = {envelope.intended_target_tab: envelope for envelope in handoffs}

    assert set(by_tab) == {"macro", "commodities", "maritime"}
    assert by_tab["commodities"].intended_target_mode == "events_cross_domain"
    assert by_tab["commodities"].selected_entity.normalized_id == "wti"
    assert by_tab["maritime"].intended_target_mode == "chokepoints"
    assert by_tab["maritime"].selected_entity.normalized_id == "hormuz"
    # Every envelope carries the contract's own event window as the lens.
    for envelope in handoffs:
        assert envelope.source_tab == "prediction_markets"
        assert envelope.source_mode == "contract"
        assert envelope.selected_timeframe is not None
        assert envelope.selected_timeframe.end == market.end_time
        assert envelope.normalized_ids["market_id"] == "polymarket:themed"
        assert envelope.source is not None


def test_cross_domain_macro_handoff_carries_region_theme_and_timeframe():
    market = _themed_market(
        title="Will the Fed cut rates at the September FOMC meeting?",
        category="Economy",
        end_offset_days=20,
    )

    macro = next(row for row in build_cross_domain_handoffs(market) if row.intended_target_tab == "macro")

    assert macro.intended_target_mode == "events_regimes"
    assert macro.selected_entity.normalized_id == "US"
    assert macro.normalized_ids["theme"] == "policy"
    assert macro.normalized_ids["timeframe"] == "1M"
    assert macro.selected_entity.metadata["matched_terms"]


def test_cross_domain_handoffs_do_not_invent_a_target_for_an_unmatched_contract():
    market = _themed_market(
        title="Will the new stadium open before the end of the year?",
        category="Politics",
    )

    handoffs = build_cross_domain_handoffs(market)

    # Macro still resolves (Politics is a macro-adjacent category) but there is
    # no commodity or maritime target to fabricate.
    assert [row.intended_target_tab for row in handoffs] == ["macro"]
    assert handoffs[0].selected_entity.normalized_id == "Global"
    assert any("Global region" in warning for warning in handoffs[0].warnings)


def test_cross_domain_handoff_flags_a_body_only_match():
    market = _themed_market(
        title="Will the shipping disruption index exceed 40?",
        category="Geopolitics",
        description="Resolves based on transits through the Suez Canal reported by the authority.",
    )

    maritime = next(row for row in build_cross_domain_handoffs(market) if row.intended_target_tab == "maritime")

    assert maritime.selected_entity.normalized_id == "suez"
    assert any("only in the contract's resolution text" in warning for warning in maritime.warnings)


def test_cross_domain_handoff_route_serializes_envelopes(tmp_path):
    market = _themed_market(
        title="Will OPEC cut production before December?",
        category="Geopolitics",
    )

    class HandoffAdapter(_EventBookAdapter):
        def list_event_markets(self, market, *, limit: int = 12):
            return []

    service = PredictionMarketService(adapters={"polymarket": HandoffAdapter([market])})
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    runtime.prediction_market_service = service

    with TestClient(create_app(runtime)) as client:
        response = client.get("/prediction-markets/markets/polymarket:themed/handoffs")
        assert response.status_code == 200
        payload = response.json()
        targets = {row["intended_target_tab"]: row for row in payload["handoffs"]}
        assert "commodities" in targets
        assert targets["commodities"]["selected_entity"]["normalized_id"] == "wti"
        assert targets["commodities"]["source_tab"] == "prediction_markets"
        assert targets["commodities"]["selected_timeframe"]["end"]

        assert client.get("/prediction-markets/markets/polymarket:nope/handoffs").status_code == 404


# ── Order-book depth ─────────────────────────────────────────────────────


def test_polymarket_depth_ranks_levels_and_prices_a_reference_clip(tmp_path):
    def fake_fetch(url: str, params: dict | None = None):
        assert url.endswith("/book")
        assert params == {"token_id": "yes-token"}
        return {
            "bids": [
                {"price": "0.44", "size": "500"},
                {"price": "0.46", "size": "1000"},
                {"price": "0.45", "size": "800"},
            ],
            "asks": [
                {"price": "0.52", "size": "400"},
                {"price": "0.50", "size": "1200"},
            ],
        }

    adapter = PolymarketAdapter(CacheService(base_dir=tmp_path / "cache"), fetch_json=fake_fetch)
    depth = adapter.get_order_book(_history_market())

    assert [level.price for level in depth.bids] == [0.46, 0.45, 0.44]
    assert [level.price for level in depth.asks] == [0.50, 0.52]
    assert depth.best_bid == 0.46
    assert depth.best_ask == 0.50
    assert depth.spread == pytest.approx(0.04)
    assert depth.mid == pytest.approx(0.48)
    # Every level sits within 5 probability points of its touch.
    assert depth.bid_notional_within_band == pytest.approx(460.0 + 360.0 + 220.0)
    assert depth.ask_notional_within_band == pytest.approx(600.0 + 208.0)
    # A $1,000 sale clears 460 at 0.46, 360 at 0.45, and 180 at 0.44, averaging
    # 0.4527 against a 0.46 touch.
    assert depth.bid_slippage_reference == pytest.approx(0.00732, abs=1e-4)
    # The ask ladder only holds $808, so the reference clip cannot be filled and
    # the quoted spread does not describe it.
    assert depth.ask_slippage_reference is None


def test_kalshi_depth_derives_the_yes_ask_side_from_the_no_book(tmp_path):
    def fake_fetch(url: str, params: dict | None = None):
        assert url.endswith("/orderbook")
        return {"orderbook": {"yes": [[46, 1000], [45, 500]], "no": [[48, 900], [47, 300]]}}

    adapter = KalshiAdapter(CacheService(base_dir=tmp_path / "cache"), fetch_json=fake_fetch)
    depth = adapter.get_order_book(_history_market(venue="kalshi"))

    assert depth.best_bid == pytest.approx(0.46)
    # A 0.48 bid for NO is a 0.52 offer for YES.
    assert depth.best_ask == pytest.approx(0.52)
    assert [level.price for level in depth.asks] == [pytest.approx(0.52), pytest.approx(0.53)]
    assert "converted as one minus its price" in (depth.transformation_note or "")


def test_depth_service_warns_when_the_book_cannot_absorb_the_reference_clip(tmp_path):
    def fake_fetch(url: str, params: dict | None = None):
        if url.endswith("/book"):
            return {"bids": [{"price": "0.40", "size": "10"}], "asks": [{"price": "0.60", "size": "10"}]}
        return {}

    class ThinBookAdapter(PolymarketAdapter):
        def get_market(self, provider_market_id: str):
            return _history_market()

    adapter = ThinBookAdapter(CacheService(base_dir=tmp_path / "cache"), fetch_json=fake_fetch)
    service = PredictionMarketService(adapters={"polymarket": adapter})

    depth = service.get_order_book_depth("polymarket:fed-cut")

    assert depth is not None
    assert depth.spread == pytest.approx(0.2)
    assert any("only applies to smaller size" in warning for warning in depth.warnings)


def test_depth_service_labels_an_adapter_without_a_book_endpoint():
    records = [
        _build_market(
            market_id="polymarket:fed-cut",
            venue="polymarket",
            provider_market_id="fed-cut",
            title="Will the Fed cut rates?",
            event_title="Fed decisions",
            category="Economy",
            current_probability=0.5,
            retrieved_at=datetime(2026, 3, 18, 12, tzinfo=timezone.utc),
        )
    ]
    service = PredictionMarketService(adapters={"polymarket": _SeriesAdapter("polymarket", records, {})})

    depth = service.get_order_book_depth("polymarket:fed-cut")

    assert depth is not None
    assert depth.bids == []
    assert any("does not expose order-book depth" in warning for warning in depth.warnings)


def test_depth_route_returns_ladders(tmp_path):
    def fake_fetch(url: str, params: dict | None = None):
        if url.endswith("/book"):
            return {"bids": [{"price": "0.46", "size": "1000"}], "asks": [{"price": "0.50", "size": "1200"}]}
        return {}

    class BookAdapter(PolymarketAdapter):
        def get_market(self, provider_market_id: str):
            return _history_market()

    service = PredictionMarketService(
        adapters={"polymarket": BookAdapter(CacheService(base_dir=tmp_path / "cache"), fetch_json=fake_fetch)}
    )
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "runtime-cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    runtime.prediction_market_service = service

    with TestClient(create_app(runtime)) as client:
        response = client.get("/prediction-markets/markets/polymarket:fed-cut/depth")
        assert response.status_code == 200
        payload = response.json()
        assert payload["best_bid"] == pytest.approx(0.46)
        assert payload["bids"][0]["notional"] == pytest.approx(460.0)
        assert payload["total_ask_notional"] == pytest.approx(600.0)
        assert payload["transformation_note"]


# ── Saved research sets ──────────────────────────────────────────────────


def test_saved_research_store_round_trips_watchlist_and_named_sets(tmp_path):
    store = PredictionResearchStore(base_dir=tmp_path / "prediction_markets")

    store.add_watchlist_entry(market_id="polymarket:a", venue="polymarket", title="A", probability=0.4)
    # Re-adding the same contract updates it instead of duplicating.
    store.add_watchlist_entry(market_id="polymarket:a", venue="polymarket", title="A revised", probability=0.5)
    store.add_watchlist_entry(market_id="kalshi:b", venue="kalshi", title="B", probability=0.6)
    store.save_comparison_set(name="Fed vs Fed", market_ids=["polymarket:a", "kalshi:b"], range_key="1m")

    saved = store.get_saved_research()
    assert saved.schema_version == 1
    assert [row.market_id for row in saved.watchlist] == ["kalshi:b", "polymarket:a"]
    assert next(row for row in saved.watchlist if row.market_id == "polymarket:a").title == "A revised"
    assert [row.name for row in saved.comparison_sets] == ["Fed vs Fed"]
    assert saved.comparison_sets[0].market_ids == ["polymarket:a", "kalshi:b"]
    assert saved.warnings == []

    # A second store over the same directory sees the same records, which is
    # what "survives a browser change" means.
    reopened = PredictionResearchStore(base_dir=tmp_path / "prediction_markets").get_saved_research()
    assert len(reopened.watchlist) == 2
    assert len(reopened.comparison_sets) == 1

    assert store.remove_watchlist_entry("polymarket:a") is True
    assert store.remove_watchlist_entry("polymarket:a") is False
    assert store.delete_comparison_set(saved.comparison_sets[0].id) is True


def test_saved_research_store_caps_and_reports_unreadable_records(tmp_path):
    store = PredictionResearchStore(base_dir=tmp_path / "prediction_markets")
    for index in range(PREDICTION_WATCHLIST_LIMIT + 5):
        store.add_watchlist_entry(market_id=f"polymarket:{index}", venue="polymarket", title=f"M{index}")

    saved = store.get_saved_research()
    assert len(saved.watchlist) == PREDICTION_WATCHLIST_LIMIT
    assert saved.watchlist_limit == PREDICTION_WATCHLIST_LIMIT

    (store.watchlist_dir / "corrupt.json").write_text("{not json", encoding="utf-8")
    (store.watchlist_dir / "future.json").write_text(
        json.dumps({"schema_version": 99, "id": "future", "market_id": "polymarket:future"}),
        encoding="utf-8",
    )
    degraded = store.get_saved_research()
    assert any("unreadable watchlist record" in warning for warning in degraded.warnings)
    assert any("newer than" in warning for warning in degraded.warnings)
    assert all(row.market_id != "polymarket:future" for row in degraded.watchlist)


def test_saved_research_routes_migrate_legacy_local_records(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    with TestClient(create_app(runtime)) as client:
        empty = client.get("/prediction-markets/saved")
        assert empty.status_code == 200
        assert empty.json()["watchlist"] == []

        migrated = client.post(
            "/prediction-markets/saved/import",
            json={
                "watchlist": [
                    {"market_id": "polymarket:a", "venue": "polymarket", "title": "A", "probability": 0.4},
                    {"market_id": "kalshi:b", "venue": "kalshi", "title": "B", "probability": 0.6},
                ],
                "comparison_basket": ["polymarket:a", "kalshi:b"],
                "basket_name": "Migrated basket",
            },
        )
        assert migrated.status_code == 200
        payload = migrated.json()
        assert {row["market_id"] for row in payload["watchlist"]} == {"polymarket:a", "kalshi:b"}
        assert payload["comparison_sets"][0]["name"] == "Migrated basket"

        # Re-running the migration is idempotent per market.
        again = client.post(
            "/prediction-markets/saved/import",
            json={
                "watchlist": [{"market_id": "polymarket:a", "venue": "polymarket", "title": "A"}],
                "comparison_basket": ["polymarket:a", "kalshi:b"],
                "basket_name": "Migrated basket",
            },
        )
        assert len(again.json()["watchlist"]) == 2
        assert len(again.json()["comparison_sets"]) == 1

        set_id = again.json()["comparison_sets"][0]["id"]
        deleted = client.delete(f"/prediction-markets/saved/comparison-sets/{set_id}")
        assert deleted.status_code == 200
        assert deleted.json()["comparison_sets"] == []
        assert client.delete(f"/prediction-markets/saved/comparison-sets/{set_id}").status_code == 404

        removed = client.delete("/prediction-markets/saved/watchlist/kalshi:b")
        assert removed.status_code == 200
        assert {row["market_id"] for row in removed.json()["watchlist"]} == {"polymarket:a"}
        assert client.delete("/prediction-markets/saved/watchlist/kalshi:b").status_code == 404


# ── Event book ───────────────────────────────────────────────────────────


class _EventBookAdapter:
    provider = "polymarket"

    def __init__(self, records: list[PredictionMarketRecord]) -> None:
        self.records = records
        self.requested_limits: list[int] = []

    def list_markets(self, *, status="open", limit=50, force_refresh=False, query="", category=None):
        return self.records[:limit]

    def get_market(self, provider_market_id: str):
        return next((row for row in self.records if row.provider_market_id == provider_market_id), None)

    def get_history(self, market: PredictionMarketRecord):
        return []

    def get_wallet_summary(self, market: PredictionMarketRecord):
        return WalletSummary(market_id=market.market_id, venue=self.provider, concentration_hhi=None, top_participant_share=None, total_trades=0, total_notional=0.0)

    def list_event_markets(self, market: PredictionMarketRecord, *, limit: int = 12):
        self.requested_limits.append(limit)
        return [row for row in self.records if row.market_id != market.market_id][:limit]

    def build_calibration_summary(self, *, sample_size: int = 30):
        return CalibrationSummary(venue=self.provider, sample_size=0)


def _candidate_market(
    *,
    index: int,
    probability: float,
    subtitle: str,
    end_time: datetime,
    resolution_source: str = "Resolves to the candidate certified as the winner by the national election board.",
) -> PredictionMarketRecord:
    base = _build_market(
        market_id=f"polymarket:race-{index}",
        venue="polymarket",
        provider_market_id=f"race-{index}",
        title=f"Will {subtitle} win the election?",
        event_title="Presidential election winner",
        category="Politics",
        current_probability=probability,
        retrieved_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    return replace(
        base,
        subtitle=subtitle,
        end_time=end_time,
        resolution_source=resolution_source,
        description=resolution_source,
    )


def _event_book_service(records: list[PredictionMarketRecord]) -> tuple[PredictionMarketService, _EventBookAdapter]:
    adapter = _EventBookAdapter(records)
    return PredictionMarketService(adapters={"polymarket": adapter}), adapter


def test_event_book_sums_a_complete_venue_grouped_race():
    end_time = datetime(2026, 11, 4, tzinfo=timezone.utc)
    records = [
        _candidate_market(index=0, probability=0.55, subtitle="Alvarez", end_time=end_time),
        _candidate_market(index=1, probability=0.3, subtitle="Baker", end_time=end_time),
        _candidate_market(index=2, probability=0.18, subtitle="Chen", end_time=end_time),
    ]
    service, adapter = _event_book_service(records)

    book = service.get_event_book("polymarket:race-0")

    assert book is not None
    assert [leg.market_id for leg in book.legs] == ["polymarket:race-0", "polymarket:race-1", "polymarket:race-2"]
    assert book.legs[0].is_anchor is True
    assert book.probability_sum == pytest.approx(1.03)
    assert book.implied_overround == pytest.approx(0.03)
    assert book.exclusivity_signal == "venue_grouped_candidates"
    assert book.overround_is_meaningful is True
    assert book.completeness.status == "complete"
    assert book.completeness.legs_returned == 3
    assert book.favorite_market_id == "polymarket:race-0"
    assert book.warnings == []
    # Asking one past the cap is how truncation stays detectable.
    assert adapter.requested_limits[0] == MAX_EVENT_BOOK_LEGS + 1


def test_event_book_refuses_the_overround_claim_when_the_book_is_truncated():
    end_time = datetime(2026, 11, 4, tzinfo=timezone.utc)
    records = [
        _candidate_market(index=index, probability=0.02, subtitle=f"Candidate {index}", end_time=end_time)
        for index in range(6)
    ]
    service, _ = _event_book_service(records)

    book = service.get_event_book("polymarket:race-0", limit=4)

    assert book is not None
    assert book.completeness.status == "truncated"
    assert book.completeness.truncated is True
    assert len(book.legs) == 4
    assert book.overround_is_meaningful is False
    assert any("descriptive here, not an overround" in warning for warning in book.warnings)


def test_event_book_flags_a_sibling_that_resolves_on_different_terms():
    end_time = datetime(2026, 11, 4, tzinfo=timezone.utc)
    records = [
        _candidate_market(index=0, probability=0.5, subtitle="Alvarez", end_time=end_time),
        _candidate_market(index=1, probability=0.3, subtitle="Baker", end_time=end_time),
        _candidate_market(index=2, probability=0.2, subtitle="Chen", end_time=end_time),
        _candidate_market(
            index=3,
            probability=0.2,
            subtitle="Chen concedes",
            end_time=end_time + timedelta(days=30),
            resolution_source="Resolves yes if a formal concession statement is published by the campaign press office.",
        ),
    ]
    service, _ = _event_book_service(records)

    book = service.get_event_book("polymarket:race-0")

    divergent = next(leg for leg in book.legs if leg.market_id == "polymarket:race-3")
    assert divergent.divergence_flags
    assert any("Resolves 30.0 days later" in flag for flag in divergent.divergence_flags)
    assert any("materially different terms" in warning for warning in book.warnings)


def test_event_book_reports_a_standalone_contract_instead_of_an_empty_sum():
    base = _build_market(
        market_id="polymarket:solo",
        venue="polymarket",
        provider_market_id="solo",
        title="Standalone contract",
        event_title="Standalone",
        category="Economy",
        current_probability=0.4,
        retrieved_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    records = [replace(base, provider_event_id=None, event_id=None)]
    service, _ = _event_book_service(records)

    book = service.get_event_book("polymarket:solo")

    assert book is not None
    assert book.completeness.status == "unavailable"
    assert book.probability_sum is None
    assert book.overround_is_meaningful is False
    assert any("standalone" in warning for warning in book.warnings)


def test_event_book_route_returns_completeness(tmp_path):
    end_time = datetime(2026, 11, 4, tzinfo=timezone.utc)
    records = [
        _candidate_market(index=0, probability=0.6, subtitle="Alvarez", end_time=end_time),
        _candidate_market(index=1, probability=0.25, subtitle="Baker", end_time=end_time),
        _candidate_market(index=2, probability=0.1, subtitle="Chen", end_time=end_time),
    ]
    service, _ = _event_book_service(records)
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    runtime.prediction_market_service = service

    with TestClient(create_app(runtime)) as client:
        response = client.get("/prediction-markets/markets/polymarket:race-0/event-book")
        assert response.status_code == 200
        payload = response.json()
        assert payload["completeness"]["status"] == "complete"
        assert payload["overround_is_meaningful"] is True
        assert payload["probability_sum"] == pytest.approx(0.95)
        assert payload["implied_overround"] == pytest.approx(-0.05)
        assert len(payload["legs"]) == 3

        missing = client.get("/prediction-markets/markets/polymarket:nope/event-book")
        assert missing.status_code == 404


# ── Calibration ──────────────────────────────────────────────────────────


CALIBRATION_BASE_TIME = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)


def _resolved_market(
    *,
    index: int,
    outcome: bool,
    settlement_probability: float,
    resolved_at: datetime,
    life_days: float = 30.0,
    venue: str = "polymarket",
) -> PredictionMarketRecord:
    base = _build_market(
        market_id=f"{venue}:settled-{index}",
        venue=venue,
        provider_market_id=f"settled-{index}",
        title=f"Settled contract {index}",
        event_title="Settled event",
        category="Economy",
        current_probability=settlement_probability,
        retrieved_at=resolved_at,
    )
    return replace(
        base,
        status="resolved",
        open_time=resolved_at - timedelta(days=life_days),
        end_time=resolved_at,
        close_time=resolved_at,
        resolved_probability=1.0 if outcome else 0.0,
        resolution_outcome=outcome,
    )


def _converged_series(
    *,
    resolved_at: datetime,
    lead_probability: float,
    settlement_probability: float,
    life_days: float = 30.0,
) -> list[tuple[datetime, float]]:
    """Hourly quotes that sit at `lead_probability` until the last 12 hours.

    This is the shape that makes the old measurement look flawless: the final
    print already knows the answer while every earlier quote does not.
    """
    points: list[tuple[datetime, float]] = []
    hours = int(life_days * 24)
    for offset in range(hours, -1, -1):
        stamp = resolved_at - timedelta(hours=offset)
        points.append((stamp, settlement_probability if offset <= 12 else lead_probability))
    return points


class _CalibrationAdapter:
    """Resolved-market adapter without the optional windowing capability."""

    provider = "polymarket"

    def __init__(self, records, series_by_market):
        self.records = records
        self.series_by_market = series_by_market
        self.history_calls: list[str] = []

    def list_markets(self, *, status="open", limit=50, force_refresh=False, query="", category=None):
        if status == "closed":
            return [row for row in self.records if row.status in {"closed", "resolved"}][:limit]
        return self.records[:limit]

    def get_market(self, provider_market_id: str):
        return next((row for row in self.records if row.provider_market_id == provider_market_id), None)

    def get_history(self, market: PredictionMarketRecord):
        self.history_calls.append(market.market_id)
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
        return WalletSummary(market_id=market.market_id, venue=self.provider, concentration_hhi=None, top_participant_share=None, total_trades=0, total_notional=0.0)

    def list_event_markets(self, market: PredictionMarketRecord, *, limit: int = 12):
        return []

    def build_calibration_summary(self, *, sample_size: int = 30):
        return CalibrationSummary(
            venue=self.provider,
            sample_size=len(self.records),
            warnings=["settlement fallback"],
            source_provider=self.provider,
            origin="polymarket.gamma.settlement_convergence",
            transformation_note="Non-predictive settlement print.",
        )


def _calibration_service(*, count: int, lead_probability: float, hit_rate: float, life_days: float = 30.0):
    records = []
    series: dict[str, list[tuple[datetime, float]]] = {}
    hits = round(count * hit_rate)
    for index in range(count):
        outcome = index < hits
        resolved_at = CALIBRATION_BASE_TIME - timedelta(days=index + 1)
        settlement = 0.99 if outcome else 0.01
        record = _resolved_market(
            index=index,
            outcome=outcome,
            settlement_probability=settlement,
            resolved_at=resolved_at,
            life_days=life_days,
        )
        records.append(record)
        series[record.market_id] = _converged_series(
            resolved_at=resolved_at,
            lead_probability=lead_probability,
            settlement_probability=settlement,
            life_days=life_days,
        )
    adapter = _CalibrationAdapter(records, series)
    return PredictionMarketService(adapters={"polymarket": adapter}), adapter


def test_calibration_buckets_the_lead_time_price_not_the_settlement_print():
    """The regression this rebuild exists for.

    Every contract settles at 0.99/0.01 but was quoted at 0.60 a day earlier.
    Bucketing the settlement print would report perfect calibration; bucketing
    the lead-time quote reports the 60% band against its real 70% hit rate.
    """
    service, _ = _calibration_service(count=24, lead_probability=0.6, hit_rate=0.75)

    summary = service.get_calibration_summary("polymarket:settled-0", lead_times_hours=[24])

    assert summary is not None
    assert summary.method == "lead_time_history"
    assert summary.lead_times_hours == [24]
    curve = summary.curves[0]
    assert curve.label == "T-1d"
    assert curve.sample_size == 24
    assert [bucket.label for bucket in curve.buckets] == ["50-75%"]
    assert curve.buckets[0].average_probability == pytest.approx(0.6)
    assert curve.buckets[0].realized_frequency == pytest.approx(0.75)
    assert curve.buckets[0].lead_time_hours == 24
    assert curve.buckets[0].meets_minimum is True
    # No settlement price reached a bucket.
    assert all(bucket.average_probability < 0.9 for bucket in curve.buckets)
    # The settlement print survives only as the diagnostic that explains why.
    assert summary.convergence is not None
    assert summary.convergence.share_within_five_points == pytest.approx(1.0)
    assert summary.observations[0].settlement_probability in {0.99, 0.01}
    assert summary.observations[0].probability == pytest.approx(0.6)


def test_calibration_refuses_to_draw_a_curve_below_the_stated_minimum():
    service, _ = _calibration_service(count=4, lead_probability=0.6, hit_rate=0.5)

    summary = service.get_calibration_summary("polymarket:settled-0", lead_times_hours=[24])

    assert summary is not None
    assert summary.sample_size == 4
    assert summary.minimum_curve_sample == 20
    assert summary.minimum_bucket_sample == 5
    assert summary.curves[0].is_plottable is False
    assert summary.is_validated is False
    assert any("no curve is drawn" in warning for warning in summary.curves[0].warnings)


def test_calibration_withholds_a_curve_built_from_one_settlement_batch():
    """Forty contracts settling in the same minute are one market state, not a sample."""
    records = []
    series: dict[str, list[tuple[datetime, float]]] = {}
    for index in range(30):
        outcome = index % 2 == 0
        settlement = 0.99 if outcome else 0.01
        # Every contract settles inside the same five minutes.
        resolved_at = CALIBRATION_BASE_TIME - timedelta(seconds=index * 10)
        record = _resolved_market(
            index=index,
            outcome=outcome,
            settlement_probability=settlement,
            resolved_at=resolved_at,
        )
        records.append(record)
        series[record.market_id] = _converged_series(
            resolved_at=resolved_at,
            lead_probability=0.3 if index % 3 else 0.7,
            settlement_probability=settlement,
        )
    service = PredictionMarketService(adapters={"polymarket": _CalibrationAdapter(records, series)})

    summary = service.get_calibration_summary("polymarket:settled-0", lead_times_hours=[24])

    assert summary is not None
    assert summary.curves[0].sample_size == 30
    assert summary.curves[0].is_plottable is False
    assert summary.is_validated is False
    assert any("settlement batch" in warning for warning in summary.warnings)
    assert any("settlement span" in warning for warning in summary.curves[0].warnings)


def test_calibration_reports_both_lead_times_with_separate_samples():
    service, adapter = _calibration_service(count=22, lead_probability=0.4, hit_rate=0.5)

    summary = service.get_calibration_summary("polymarket:settled-0", lead_times_hours=[168, 24])

    assert summary is not None
    assert summary.lead_times_hours == [24, 168]
    assert [curve.label for curve in summary.curves] == ["T-1d", "T-7d"]
    assert all(curve.sample_size == 22 for curve in summary.curves)
    # One history request per contract serves every lead time.
    assert len(adapter.history_calls) == 22
    assert summary.curves[0].brier_score == pytest.approx(0.5 * (0.4**2) + 0.5 * (0.6**2), abs=1e-6)


def test_calibration_skips_contracts_that_were_not_listed_at_the_lead_time():
    """A contract that only lived six hours has no T-1d probability."""
    service, _ = _calibration_service(count=6, lead_probability=0.6, hit_rate=0.5, life_days=0.25)

    summary = service.get_calibration_summary("polymarket:settled-0", lead_times_hours=[24])

    assert summary is not None
    assert summary.method == "settlement_last_trade_deprecated"
    assert summary.is_validated is False
    assert summary.curves == []
    assert any("no calibration could be measured" in warning for warning in summary.warnings)


def test_calibration_falls_back_to_a_labeled_settlement_summary_without_history():
    records = [
        _resolved_market(
            index=index,
            outcome=index % 2 == 0,
            settlement_probability=0.99 if index % 2 == 0 else 0.01,
            resolved_at=CALIBRATION_BASE_TIME - timedelta(days=index + 1),
        )
        for index in range(5)
    ]
    service = PredictionMarketService(adapters={"polymarket": _CalibrationAdapter(records, {})})

    summary = service.get_calibration_summary("polymarket:settled-0")

    assert summary is not None
    assert summary.method == "settlement_last_trade_deprecated"
    assert summary.is_validated is False
    assert summary.curves == []
    assert summary.markets_without_history == 5
    assert summary.convergence is not None
    assert any("not predictive" in warning for warning in summary.warnings)


def test_calibration_route_exposes_lead_times_and_rejects_unsupported_ones(tmp_path):
    service, _ = _calibration_service(count=22, lead_probability=0.6, hit_rate=0.5)
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    runtime.prediction_market_service = service

    with TestClient(create_app(runtime)) as client:
        response = client.get(
            "/prediction-markets/markets/polymarket:settled-0/calibration?lead=24&lead=168&sample=25"
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["method"] == "lead_time_history"
        assert payload["lead_times_hours"] == [24, 168]
        assert payload["minimum_curve_sample"] == 20
        assert payload["curves"][0]["label"] == "T-1d"
        assert payload["curves"][0]["buckets"][0]["lead_time_hours"] == 24
        assert payload["convergence"]["note"]
        assert payload["transformation_note"]

        rejected = client.get("/prediction-markets/markets/polymarket:settled-0/calibration?lead=999")
        assert rejected.status_code == 422
