from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from types import SimpleNamespace

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


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///tmp/news.html",
        "https://user:password@example.com/news",
        "https:///missing-host",
    ],
)
def test_news_event_item_rejects_unsafe_navigation_urls(url):
    with pytest.raises(ValueError, match="navigable http/https URL"):
        NewsEventItem(
            normalized_id="unsafe",
            title="Unsafe URL",
            url=url,
            source_provider="rss",
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


def test_news_service_dedupes_cross_feed_event_and_preserves_reporting_provenance():
    published_at = datetime(2026, 4, 22, 10, 0)
    first = NewsEventItem(
        normalized_id="feed-a:oil-disruption",
        provider_item_id="a-1",
        title="Oil shipping disruption raises supply concerns",
        url="https://alpha.example.com/oil-disruption",
        source_provider="feed_a",
        source_name="Alpha News",
        published_at=published_at,
        retrieved_at=datetime(2026, 4, 22, 10, 5),
        origin="feed_a.latest",
        tags=["oil"],
        warnings=["Feed A is delayed."],
        freshness_label=FreshnessLabel.DELAYED,
    )
    second = NewsEventItem(
        normalized_id="feed-b:oil-disruption",
        provider_item_id="b-9",
        title="Oil shipping disruption raises supply concerns",
        url="https://beta.example.com/world/oil-disruption",
        source_provider="feed_b",
        source_name="Beta Wire",
        published_at=published_at,
        retrieved_at=datetime(2026, 4, 22, 10, 7),
        origin="feed_b.latest",
        tags=["shipping"],
        warnings=["Feed B metadata is incomplete."],
        freshness_label=FreshnessLabel.DELAYED,
    )
    forward = NewsService(
        [
            _StaticNewsProvider("feed_a", "Alpha News", [first]),
            _StaticNewsProvider("feed_b", "Beta Wire", [second]),
        ],
        cache_ttl_seconds=0,
    ).latest(limit=10)
    reverse = NewsService(
        [
            _StaticNewsProvider("feed_b", "Beta Wire", [second]),
            _StaticNewsProvider("feed_a", "Alpha News", [first]),
        ],
        cache_ttl_seconds=0,
    ).latest(limit=10)

    assert len(forward.items) == 1
    assert len(reverse.items) == 1
    merged = forward.items[0]
    assert merged.normalized_id == reverse.items[0].normalized_id
    assert merged.normalized_id == "feed-b:oil-disruption"
    assert {source.source_provider for source in merged.reporting_sources} == {
        "feed_a",
        "feed_b",
    }
    assert merged.tags == ["shipping", "oil"]
    assert set(merged.warnings) == {
        "Feed A is delayed.",
        "Feed B metadata is incomplete.",
    }
    assert "retained all reporting feed provenance" in merged.transformation_note


class _ChangingNewsProvider:
    provider_id = "counted_news"
    source_name = "Counted News"

    def __init__(self) -> None:
        self.calls = 0

    def latest(self, *, limit: int = 25) -> NewsEventFeed:
        self.calls += 1
        item = _item(
            f"call-{self.calls}",
            f"https://example.com/call-{self.calls}",
            datetime(2026, 4, 22, 12, 0) + timedelta(minutes=self.calls),
            source_provider=self.provider_id,
        )
        return NewsEventFeed(
            items=[item][:limit],
            source_provider=self.provider_id,
            retrieved_at=datetime(2026, 4, 22, 12, self.calls),
            origin="counted.latest",
            freshness_label=FreshnessLabel.DELAYED,
        )


class _RecordingNewsService:
    def __init__(self) -> None:
        self.calls: list[tuple[int, bool]] = []

    def latest(self, *, limit: int = 25, force_refresh: bool = False) -> NewsEventFeed:
        self.calls.append((limit, force_refresh))
        return NewsEventFeed(
            items=[_item("route", "https://example.com/route", datetime(2026, 4, 22, 12, 0))],
            source_provider="recording_news",
            retrieved_at=datetime(2026, 4, 22, 12, 0),
            origin="recording.latest",
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


def test_news_service_force_refresh_bypasses_latest_cache():
    provider = _ChangingNewsProvider()
    service = NewsService([provider], cache_ttl_seconds=300)

    first = service.latest(limit=1)
    cached = service.latest(limit=1)
    refreshed = service.latest(limit=1, force_refresh=True)
    cached_after_refresh = service.latest(limit=1)

    assert provider.calls == 2
    assert first.items[0].normalized_id == "call-1"
    assert cached.items[0].normalized_id == "call-1"
    assert refreshed.items[0].normalized_id == "call-2"
    assert cached_after_refresh.items[0].normalized_id == "call-2"


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


def test_news_latest_api_passes_force_refresh_to_service():
    news_service = _RecordingNewsService()
    runtime = SimpleNamespace(news_service=news_service, shutdown=lambda: None)

    with TestClient(create_app(runtime)) as client:
        response = client.get("/news/latest", params={"limit": 3, "force_refresh": "true"})

    assert response.status_code == 200
    assert news_service.calls == [(3, True)]


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


def test_detect_news_entities_extracts_high_confidence_tickers_and_entities():
    from src.services.news_adapters import detect_news_entities

    text = (
        "Nvidia and Apple rally as the Federal Reserve holds rates; "
        "traders eye $TSLA and (NASDAQ: AMZN) while OPEC+ weighs cuts. $USD stays firm."
    )
    entities = {entity.resolved_id(): entity for entity in detect_news_entities(text)}

    assert entities["NVDA"].entity_type == "company"
    assert entities["AAPL"].symbol == "AAPL"
    assert entities["fed"].entity_type == "central_bank"
    assert entities["opec"].entity_type == "organization"
    assert entities["TSLA"].symbol == "TSLA"
    assert entities["AMZN"].symbol == "AMZN"
    # Currency cashtags are not tickers.
    assert "USD" not in entities

    assert detect_news_entities("Quiet weekend with no market-moving names.") == []


def test_rss_items_carry_reliability_and_detected_entities():
    feed = RssFeedConfig(
        feed_id="test_feed",
        source_name="Test Feed",
        url="https://example.com/feed",
        tier=2,
    )
    xml = b"""<rss version=\"2.0\"><channel><title>Test</title>
    <item>
      <title>Tesla shares jump after earnings ($TSLA)</title>
      <link>https://example.com/tesla-earnings</link>
      <pubDate>Mon, 13 Jul 2026 08:00:00 GMT</pubDate>
      <description>Tesla beat estimates while the Federal Reserve stayed on hold.</description>
    </item>
    </channel></rss>"""

    provider = RssNewsEventProvider(feeds=[feed], fetcher=lambda *_args: xml)
    result = provider.latest(limit=5)

    assert len(result.items) == 1
    item = result.items[0]
    assert item.source_reliability == "major_outlet"
    ids = {entity.resolved_id() for entity in item.detected_entities}
    assert "TSLA" in ids
    assert "fed" in ids


def test_sample_news_items_are_labeled_sample_reliability():
    feed = SampleNewsEventProvider().latest(limit=3)
    assert feed.items
    assert all(item.source_reliability == "sample" for item in feed.items)


def test_news_service_dedupes_identical_cross_feed_headlines():
    shared_title = "Global markets rally as inflation cools further in June"
    early = NewsEventItem(
        normalized_id="rss:feed_a:1",
        provider_item_id="feed_a:1",
        title=shared_title,
        url="https://feed-a.example.com/story-1",
        source_provider="rss",
        source_name="Feed A",
        published_at=datetime(2026, 7, 13, 8, 0),
        retrieved_at=datetime(2026, 7, 13, 9, 0),
        origin="rss.feed:feed_a",
        freshness_label=FreshnessLabel.DELAYED,
    )
    late = NewsEventItem(
        normalized_id="rss:feed_b:9",
        provider_item_id="feed_b:9",
        title=shared_title,
        url="https://feed-b.example.com/story-9",
        source_provider="rss",
        source_name="Feed B",
        published_at=datetime(2026, 7, 13, 8, 30),
        retrieved_at=datetime(2026, 7, 13, 9, 0),
        origin="rss.feed:feed_b",
        freshness_label=FreshnessLabel.DELAYED,
    )
    short_a = _item("Update", "https://feed-a.example.com/u1", datetime(2026, 7, 13, 8, 0))
    short_b = _item("Update", "https://feed-b.example.com/u2", datetime(2026, 7, 13, 8, 5))

    service = NewsService(
        [
            _StaticNewsProvider("rss", "Feed A", [early, short_a]),
            _StaticNewsProvider("rss_b", "Feed B", [late, short_b]),
        ],
        cache_ttl_seconds=0,
    )
    result = service.latest(limit=10)

    titles = [item.title for item in result.items]
    assert titles.count(shared_title) == 1
    kept = next(item for item in result.items if item.title == shared_title)
    assert kept.normalized_id == "rss:feed_b:9"
    # Short/generic titles are not merged across feeds.
    assert titles.count("Update") == 2
