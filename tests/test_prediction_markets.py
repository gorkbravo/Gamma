from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.prediction_market_service import PredictionMarketService, PredictionMarketScreenerRequest
from src.application.runtime import build_runtime
from src.models.prediction_markets import (
    CalibrationSummary,
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


def test_kalshi_adapter_normalizes_closed_markets_and_flow_summary(tmp_path):
    calls: defaultdict[str, int] = defaultdict(int)

    def fake_fetch(url: str, params: dict | None = None):
        key = f"{url}|{params}"
        calls[key] += 1
        if url.endswith("/markets") and params == {"limit": 40, "status": "closed"}:
            return {
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
                    }
                ]
            }
        if url.endswith("/markets") and params == {"limit": 40, "status": "settled"}:
            return {"markets": []}
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
