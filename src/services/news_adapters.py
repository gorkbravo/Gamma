from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from src.models.news import NewsEventEntity, NewsEventFeed, NewsEventItem
from src.models.provenance import FreshnessLabel
from src.utils.time import now_utc


class NewsEventProvider(Protocol):
    provider_id: str
    source_name: str

    def latest(self, *, limit: int = 25) -> NewsEventFeed:
        ...


@dataclass
class SampleNewsEventProvider:
    provider_id: str = "sample_news"
    source_name: str = "Gamma sample news"

    def latest(self, *, limit: int = 25) -> NewsEventFeed:
        retrieved_at = now_utc()
        items = [
            NewsEventItem(
                normalized_id="sample_news:macro-policy-path",
                provider_item_id="macro-policy-path",
                title="Policy path debate remains the main cross-asset driver",
                summary=(
                    "Sample research item linking rates, equity duration, dollar strength, and prediction-market "
                    "policy expectations for SITREP contract testing."
                ),
                url="https://example.com/gamma/sample/macro-policy-path",
                source_provider=self.provider_id,
                source_name=self.source_name,
                published_at=retrieved_at - timedelta(minutes=35),
                retrieved_at=retrieved_at,
                origin="sample_news.static_feed",
                detected_entities=[
                    NewsEventEntity(label="Federal Reserve", entity_type="central_bank", normalized_id="fed"),
                    NewsEventEntity(label="S&P 500", entity_type="index", symbol="SPY"),
                ],
                tags=["macro", "policy", "rates"],
                freshness_label=FreshnessLabel.MOCKED,
                transformation_note="Static sample item used to validate Gamma's normalized news/event contract.",
            ),
            NewsEventItem(
                normalized_id="sample_news:energy-shipping-risk",
                provider_item_id="energy-shipping-risk",
                title="Energy shipping risk stays on the commodity watchlist",
                summary=(
                    "Sample research item connecting crude curves, product spreads, chokepoint monitoring, "
                    "and maritime handoff candidates."
                ),
                url="https://example.com/gamma/sample/energy-shipping-risk",
                source_provider=self.provider_id,
                source_name=self.source_name,
                published_at=retrieved_at - timedelta(hours=2),
                retrieved_at=retrieved_at,
                origin="sample_news.static_feed",
                detected_entities=[
                    NewsEventEntity(label="WTI crude", entity_type="commodity", normalized_id="wti"),
                    NewsEventEntity(label="Hormuz", entity_type="chokepoint", normalized_id="hormuz"),
                ],
                tags=["commodities", "energy", "maritime"],
                freshness_label=FreshnessLabel.MOCKED,
                transformation_note="Static sample item used to validate Gamma's normalized news/event contract.",
            ),
            NewsEventItem(
                normalized_id="sample_news:crypto-liquidity",
                provider_item_id="crypto-liquidity",
                title="Crypto liquidity screen highlights turnover dispersion",
                summary=(
                    "Sample research item for future crypto-flow and liquidity-news correlation surfaces."
                ),
                url="https://example.com/gamma/sample/crypto-liquidity",
                source_provider=self.provider_id,
                source_name=self.source_name,
                published_at=retrieved_at - timedelta(hours=4),
                retrieved_at=retrieved_at,
                origin="sample_news.static_feed",
                detected_entities=[
                    NewsEventEntity(label="Bitcoin", entity_type="crypto_asset", symbol="BTC"),
                    NewsEventEntity(label="Ethereum", entity_type="crypto_asset", symbol="ETH"),
                ],
                tags=["crypto", "liquidity"],
                freshness_label=FreshnessLabel.MOCKED,
                transformation_note="Static sample item used to validate Gamma's normalized news/event contract.",
            ),
        ]
        return NewsEventFeed(
            items=items[: max(int(limit or 0), 0)],
            source_provider=self.provider_id,
            retrieved_at=retrieved_at,
            origin="sample_news.latest",
            freshness_label=FreshnessLabel.MOCKED,
            warnings=["Sample news items are static contract fixtures, not live news coverage."],
            transformation_note="Sample provider emits deterministic normalized news/event items for backend and UI integration.",
        )

