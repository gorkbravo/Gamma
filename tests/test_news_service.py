from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.news_service import NewsService
from src.application.runtime import build_runtime
from src.models.news import NewsEventFeed, NewsEventItem, canonical_news_url, source_domain_from_url
from src.models.provenance import FreshnessLabel
from src.services.news_adapters import RssFeedConfig, RssNewsEventProvider, SampleNewsEventProvider


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


def test_rss_news_provider_parses_rss_items_and_strips_html_description():
    config = RssFeedConfig(
        feed_id="test_feed",
        source_name="Example Feed",
        url="https://example.com/rss.xml",
        tags=("Macro", "Markets"),
        region="US",
        tier=1,
    )
    fixture = b"""<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
      <channel>
        <title>Example Feed</title>
        <lastBuildDate>Wed, 22 Apr 2026 11:30:00 GMT</lastBuildDate>
        <item>
          <guid>story-1</guid>
          <title>Fed &amp; markets react</title>
          <link>https://example.com/news/fed-markets?utm_source=rss</link>
          <pubDate>Wed, 22 Apr 2026 10:30:00 GMT</pubDate>
          <description><![CDATA[<p>Stocks <b>rallied</b> &amp; yields fell.</p>]]></description>
          <category>Macro Policy</category>
        </item>
        <item>
          <title>Second story</title>
          <link>https://example.com/news/second</link>
          <dc:date>2026-04-22T09:15:00Z</dc:date>
          <description>Plain summary</description>
        </item>
      </channel>
    </rss>
    """
    provider = RssNewsEventProvider(feeds=(config,), fetcher=lambda feed, timeout, user_agent: fixture)

    feed = provider.latest(limit=10)

    assert feed.source_provider == "rss"
    assert feed.freshness_label == FreshnessLabel.DELAYED
    assert len(feed.items) == 2
    first = feed.items[0]
    assert first.title == "Fed & markets react"
    assert first.published_at == datetime(2026, 4, 22, 10, 30)
    assert first.summary == "Stocks rallied & yields fell."
    assert first.source_domain == "example.com"
    assert first.provider_item_id == "test_feed:story-1"
    assert first.origin == "rss.feed:test_feed"
    assert first.tags == ["macro", "markets", "macro_policy"]
    assert "RSS/Atom" in (first.transformation_note or "")
    assert feed.items[1].published_at == datetime(2026, 4, 22, 9, 15)


def test_rss_news_provider_parses_atomish_dates_and_links():
    config = RssFeedConfig(
        feed_id="atom_feed",
        source_name="Atom Feed",
        url="https://example.com/atom.xml",
        tags=("Crypto",),
    )
    fixture = b"""<?xml version="1.0" encoding="utf-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>Atom Feed</title>
      <updated>2026-04-22T08:00:00+00:00</updated>
      <entry>
        <id>tag:example.com,2026:atom-1</id>
        <title>Atom story</title>
        <link href="https://example.com/atom/story" />
        <updated>2026-04-22T08:45:00+00:00</updated>
        <summary>Atom <em>summary</em></summary>
        <category term="Digital Assets" />
      </entry>
    </feed>
    """
    provider = RssNewsEventProvider(feeds=(config,), fetcher=lambda feed, timeout, user_agent: fixture)

    feed = provider.latest(limit=10)

    assert len(feed.items) == 1
    item = feed.items[0]
    assert item.url == "https://example.com/atom/story"
    assert item.published_at == datetime(2026, 4, 22, 8, 45)
    assert item.summary == "Atom summary"
    assert item.provider_item_id == "atom_feed:tag:example.com,2026:atom-1"
    assert item.tags == ["crypto", "digital_assets"]


def test_rss_news_provider_keeps_successful_feeds_when_one_feed_fails():
    good = RssFeedConfig(feed_id="good_feed", source_name="Good", url="https://example.com/good.xml")
    bad = RssFeedConfig(feed_id="bad_feed", source_name="Bad", url="https://example.com/bad.xml")
    fixture = b"""<rss><channel><item><title>Good item</title><link>https://example.com/good</link><pubDate>Wed, 22 Apr 2026 10:30:00 GMT</pubDate></item></channel></rss>"""

    def fetcher(feed: RssFeedConfig, timeout: float, user_agent: str) -> bytes:
        if feed.feed_id == "bad_feed":
            raise TimeoutError("timed out")
        return fixture

    provider = RssNewsEventProvider(feeds=(good, bad), fetcher=fetcher)

    feed = provider.latest(limit=10)

    assert [item.title for item in feed.items] == ["Good item"]
    assert any("bad_feed" in warning and "timed out" in warning for warning in feed.warnings)


def test_news_service_dedupes_rss_items_by_canonical_url():
    old_config = RssFeedConfig(feed_id="old_feed", source_name="Old", url="https://example.com/old.xml")
    new_config = RssFeedConfig(feed_id="new_feed", source_name="New", url="https://example.com/new.xml")
    old_fixture = b"""<rss><channel><item><guid>old-id</guid><title>Old duplicate</title><link>https://example.com/same?utm_source=rss</link><pubDate>Wed, 22 Apr 2026 09:00:00 GMT</pubDate></item></channel></rss>"""
    new_fixture = b"""<rss><channel><item><guid>new-id</guid><title>New duplicate</title><link>https://www.example.com/same</link><pubDate>Wed, 22 Apr 2026 10:00:00 GMT</pubDate></item></channel></rss>"""
    old_provider = RssNewsEventProvider(feeds=(old_config,), fetcher=lambda feed, timeout, user_agent: old_fixture)
    new_provider = RssNewsEventProvider(feeds=(new_config,), fetcher=lambda feed, timeout, user_agent: new_fixture)
    service = NewsService([old_provider, new_provider])

    feed = service.latest(limit=10)

    assert [item.title for item in feed.items] == ["New duplicate"]


def test_news_latest_api_returns_normalized_sample_feed(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_PROVIDER", "sample")
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    client = TestClient(create_app(runtime))
    try:
        response = client.get("/news/latest", params={"limit": 2})
        assert response.status_code == 200
        payload = response.json()
        assert payload["source_provider"] == "sample_news"
        assert payload["freshness_label"] == "mocked"
        assert len(payload["items"]) == 2
        assert payload["items"][0]["normalized_id"]
        assert payload["items"][0]["source_provider"] == "sample_news"
        assert payload["items"][0]["origin"]
    finally:
        runtime.shutdown()


def test_runtime_can_select_rss_news_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_PROVIDER", "rss")
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    try:
        assert len(runtime.news_service.providers) == 1
        assert isinstance(runtime.news_service.providers[0], RssNewsEventProvider)
    finally:
        runtime.shutdown()
