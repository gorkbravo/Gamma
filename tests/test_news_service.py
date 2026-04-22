from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from src.application.news_service import NewsService
from src.models.news import NewsEventFeed, NewsEventItem, canonical_news_url, source_domain_from_url
from src.models.provenance import FreshnessLabel
from src.services.news_adapters import SampleNewsEventProvider


def test_news_event_item_normalizes_domain_tags_warnings_and_dedupe_key():
    item = NewsEventItem(
        normalized_id="rss:test",
        title="Test item",
        url="https://www.example.com/news/item/?utm_source=x",
        source_provider="rss",
        source_name="Example",
        published_at=datetime(2026, 4, 22, 9, 0),
        retrieved_at=datetime(2026, 4, 22, 9, 5),
        origin="rss.feed.item",
        tags=["Macro", "Macro", ""],
        warnings=["Delayed feed", "Delayed feed"],
        freshness_label="delayed",
    )

    assert item.source_domain == "example.com"
    assert item.tags == ["Macro"]
    assert item.warnings == ["Delayed feed"]
    assert item.freshness_label == FreshnessLabel.DELAYED
    assert item.dedupe_key() == canonical_news_url(item.url)
    assert source_domain_from_url(item.url) == "example.com"


def test_news_event_item_requires_core_provenance_fields():
    with pytest.raises(ValueError, match="source_provider is required"):
        NewsEventItem(
            normalized_id="bad",
            title="Missing source",
            url="https://example.com/news",
            source_provider="",
            source_name="Example",
            published_at=datetime(2026, 4, 22),
            retrieved_at=datetime(2026, 4, 22),
            origin="test",
        )


@dataclass
class _StaticNewsProvider:
    provider_id: str
    source_name: str
    items: list[NewsEventItem]

    def latest(self, *, limit: int = 25) -> NewsEventFeed:
        return NewsEventFeed(
            items=self.items[:limit],
            source_provider=self.provider_id,
            retrieved_at=datetime(2026, 4, 22, 12, 0),
            origin=f"{self.provider_id}.latest",
            freshness_label=FreshnessLabel.DELAYED,
            warnings=[f"{self.provider_id} warning"],
        )


def _item(
    normalized_id: str,
    url: str,
    published_at: datetime,
    *,
    source_provider: str = "rss",
    provider_item_id: str | None = None,
) -> NewsEventItem:
    return NewsEventItem(
        normalized_id=normalized_id,
        provider_item_id=provider_item_id,
        title=normalized_id,
        url=url,
        source_provider=source_provider,
        source_name="Example",
        published_at=published_at,
        retrieved_at=datetime(2026, 4, 22, 12, 0),
        origin="test.provider",
        freshness_label=FreshnessLabel.DELAYED,
    )


def test_news_service_dedupes_sorts_and_limits_items():
    base_time = datetime(2026, 4, 22, 12, 0)
    older_duplicate = _item("old", "https://example.com/a?utm=x", base_time - timedelta(hours=2))
    newer_duplicate = _item("new", "https://www.example.com/a", base_time - timedelta(minutes=5))
    separate = _item("separate", "https://example.com/b", base_time - timedelta(minutes=30))
    service = NewsService(
        [
            _StaticNewsProvider("rss", "RSS", [older_duplicate, separate]),
            _StaticNewsProvider("rss", "RSS", [newer_duplicate]),
        ]
    )

    feed = service.latest(limit=2)

    assert [item.normalized_id for item in feed.items] == ["new", "separate"]
    assert feed.source_provider == "rss"
    assert feed.freshness_label == FreshnessLabel.DELAYED
    assert feed.warnings == ["rss warning"]
    assert "dedupes" in (feed.transformation_note or "")


def test_news_service_dedupes_same_url_even_with_different_provider_item_ids():
    base_time = datetime(2026, 4, 22, 12, 0)
    first = _item(
        "first",
        "https://example.com/same-story?utm_source=feed",
        base_time - timedelta(minutes=20),
        provider_item_id="provider-a-1",
    )
    second = _item(
        "second",
        "https://www.example.com/same-story",
        base_time - timedelta(minutes=5),
        provider_item_id="provider-b-9",
    )
    service = NewsService([_StaticNewsProvider("rss", "RSS", [first, second])])

    feed = service.latest(limit=10)

    assert [item.normalized_id for item in feed.items] == ["second"]


def test_sample_news_provider_returns_mocked_normalized_contract_items():
    feed = SampleNewsEventProvider().latest(limit=2)

    assert feed.source_provider == "sample_news"
    assert feed.freshness_label == FreshnessLabel.MOCKED
    assert len(feed.items) == 2
    assert all(item.source_provider == "sample_news" for item in feed.items)
    assert all(item.detected_entities for item in feed.items)
    assert any("static" in warning.lower() for warning in feed.warnings)
