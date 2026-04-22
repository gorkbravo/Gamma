from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import Callable, Protocol
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from src.models.news import NewsEventEntity, NewsEventFeed, NewsEventItem, canonical_news_url
from src.models.provenance import FreshnessLabel
from src.utils.time import now_utc


class NewsEventProvider(Protocol):
    provider_id: str
    source_name: str

    def latest(self, *, limit: int = 25) -> NewsEventFeed:
        ...


@dataclass(frozen=True)
class RssFeedConfig:
    feed_id: str
    source_name: str
    url: str
    tags: tuple[str, ...] = field(default_factory=tuple)
    region: str = "Global"
    tier: int = 2
    detected_entities: tuple[NewsEventEntity, ...] = field(default_factory=tuple)


FeedFetcher = Callable[[RssFeedConfig, float, str], bytes]

RSS_USER_AGENT = "GammaResearch/0.1 read-only RSS news adapter"
MAX_RSS_FEED_BYTES = 5 * 1024 * 1024
SUMMARY_MAX_CHARS = 420

DEFAULT_RSS_FEEDS: tuple[RssFeedConfig, ...] = (
    RssFeedConfig(
        feed_id="sec_press_releases",
        source_name="SEC Press Releases",
        url="https://www.sec.gov/news/pressreleases.rss",
        tags=("official", "regulatory", "sec", "fundamentals", "us"),
        region="US",
        tier=1,
        detected_entities=(
            NewsEventEntity(
                label="U.S. Securities and Exchange Commission",
                entity_type="regulator",
                normalized_id="sec",
            ),
        ),
    ),
    RssFeedConfig(
        feed_id="federal_reserve",
        source_name="Federal Reserve",
        url="https://www.federalreserve.gov/feeds/press_all.xml",
        tags=("official", "macro", "policy", "rates", "us"),
        region="US",
        tier=1,
        detected_entities=(
            NewsEventEntity(label="Federal Reserve", entity_type="central_bank", normalized_id="fed"),
        ),
    ),
    RssFeedConfig(
        feed_id="bloomberg_markets",
        source_name="Bloomberg Markets",
        url="https://feeds.bloomberg.com/markets/news.rss",
        tags=("markets", "cross_asset", "macro"),
        region="Global",
        tier=2,
    ),
    RssFeedConfig(
        feed_id="wsj_markets",
        source_name="WSJ Markets",
        url="https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        tags=("markets", "equities", "macro"),
        region="Global",
        tier=2,
    ),
    RssFeedConfig(
        feed_id="marketwatch_top_stories",
        source_name="MarketWatch Top Stories",
        url="https://feeds.marketwatch.com/marketwatch/topstories/",
        tags=("markets", "equities", "macro"),
        region="US",
        tier=2,
    ),
    RssFeedConfig(
        feed_id="bbc_business",
        source_name="BBC Business",
        url="http://feeds.bbci.co.uk/news/business/rss.xml",
        tags=("business", "macro", "global"),
        region="Global",
        tier=2,
    ),
    RssFeedConfig(
        feed_id="al_jazeera",
        source_name="Al Jazeera",
        url="https://www.aljazeera.com/xml/rss/all.xml",
        tags=("geopolitics", "global"),
        region="Global",
        tier=3,
    ),
    RssFeedConfig(
        feed_id="coindesk",
        source_name="CoinDesk",
        url="https://www.coindesk.com/arc/outboundfeeds/rss/",
        tags=("crypto", "digital_assets"),
        region="Global",
        tier=2,
    ),
    RssFeedConfig(
        feed_id="oilprice",
        source_name="OilPrice",
        url="https://oilprice.com/rss/main",
        tags=("commodities", "energy", "oil"),
        region="Global",
        tier=2,
    ),
)


class RssNewsEventProvider:
    provider_id = "rss"
    source_name = "RSS news feeds"

    def __init__(
        self,
        *,
        feeds: tuple[RssFeedConfig, ...] | list[RssFeedConfig] = DEFAULT_RSS_FEEDS,
        timeout_seconds: float = 6.0,
        user_agent: str = RSS_USER_AGENT,
        fetcher: FeedFetcher | None = None,
    ) -> None:
        self.feeds = tuple(feeds)
        self.timeout_seconds = max(0.5, float(timeout_seconds))
        self.user_agent = str(user_agent or RSS_USER_AGENT).strip() or RSS_USER_AGENT
        self.fetcher = fetcher or _default_feed_fetcher

    def latest(self, *, limit: int = 25) -> NewsEventFeed:
        requested_limit = max(int(limit or 0), 0)
        retrieved_at = now_utc()
        warnings: list[str] = []
        items: list[NewsEventItem] = []

        for feed in self.feeds:
            try:
                content = self.fetcher(feed, self.timeout_seconds, self.user_agent)
                parsed_items, feed_warnings = _parse_feed_items(feed, content, retrieved_at)
                items.extend(parsed_items)
                warnings.extend(feed_warnings)
            except Exception as exc:
                warnings.append(f"RSS feed {feed.feed_id} ({feed.source_name}) failed: {exc}")

        items.sort(key=lambda item: item.published_at, reverse=True)
        items = items[:requested_limit]
        return NewsEventFeed(
            items=items,
            source_provider=self.provider_id,
            retrieved_at=retrieved_at,
            origin="rss.latest",
            freshness_label=FreshnessLabel.DELAYED if items else FreshnessLabel.UNAVAILABLE,
            warnings=warnings,
            transformation_note=(
                "Gamma fetches curated source-owned RSS/Atom feeds, parses public XML, strips HTML from snippets, "
                "adds curated feed tags/source category labels, and emits delayed normalized news/event records."
            ),
        )


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


def _default_feed_fetcher(feed: RssFeedConfig, timeout_seconds: float, user_agent: str) -> bytes:
    request = Request(
        feed.url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/rss+xml,application/atom+xml,application/xml;q=0.9,text/xml;q=0.8,*/*;q=0.5",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        content = response.read(MAX_RSS_FEED_BYTES + 1)
    if len(content) > MAX_RSS_FEED_BYTES:
        raise ValueError(f"feed response exceeded {MAX_RSS_FEED_BYTES} bytes")
    return content


def _parse_feed_items(
    feed: RssFeedConfig,
    content: bytes,
    retrieved_at: datetime,
) -> tuple[list[NewsEventItem], list[str]]:
    root = _parse_xml(content)
    feed_timestamp = _feed_timestamp(root)
    entries = _feed_entries(root)
    warnings: list[str] = []
    items: list[NewsEventItem] = []

    for index, entry in enumerate(entries, start=1):
        try:
            item = _entry_to_item(feed, entry, index, retrieved_at, feed_timestamp)
        except ValueError as exc:
            warnings.append(f"RSS feed {feed.feed_id} skipped item {index}: {exc}")
            continue
        warnings.extend(item.warnings)
        items.append(item)

    if not entries:
        warnings.append(f"RSS feed {feed.feed_id} returned no item/entry records.")
    return items, warnings


def _parse_xml(content: bytes) -> ET.Element:
    if len(content) > MAX_RSS_FEED_BYTES:
        raise ValueError(f"feed response exceeded {MAX_RSS_FEED_BYTES} bytes")
    lower_head = content[:4096].lower()
    if b"<!doctype" in lower_head or b"<!entity" in lower_head:
        raise ValueError("RSS/XML with DTD or entity declarations is not supported")
    try:
        return ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"invalid RSS/XML: {exc}") from exc


def _feed_entries(root: ET.Element) -> list[ET.Element]:
    root_name = _local_name(root.tag)
    if root_name == "feed":
        return [child for child in list(root) if _local_name(child.tag) == "entry"]

    channel = next((child for child in list(root) if _local_name(child.tag) == "channel"), root)
    direct_items = [child for child in list(channel) if _local_name(child.tag) == "item"]
    if direct_items:
        return direct_items
    return [element for element in root.iter() if _local_name(element.tag) in {"item", "entry"}]


def _feed_timestamp(root: ET.Element) -> datetime | None:
    channel = next((child for child in list(root) if _local_name(child.tag) == "channel"), root)
    return _parse_datetime(
        _first_child_text(channel, ("lastBuildDate", "pubDate", "published", "updated", "date"))
    )


def _entry_to_item(
    feed: RssFeedConfig,
    entry: ET.Element,
    index: int,
    retrieved_at: datetime,
    feed_timestamp: datetime | None,
) -> NewsEventItem:
    entry_name = _local_name(entry.tag)
    is_atom = entry_name == "entry"
    title = _clean_text(_first_child_text(entry, ("title",)))
    url = _entry_link(entry)
    if not title:
        raise ValueError("title is missing")
    if not url:
        raise ValueError("link URL is missing")

    raw_provider_id = _first_child_text(entry, ("guid", "id")) or url
    provider_item_id = _provider_item_id(feed.feed_id, raw_provider_id)
    published_text = _first_child_text(
        entry,
        ("published", "updated", "pubDate", "date", "dc:date"),
    )
    published_at = _parse_datetime(published_text)
    item_warnings: list[str] = []
    if published_at is None:
        published_at = feed_timestamp or retrieved_at
        if feed_timestamp is None:
            item_warnings.append(
                f"RSS feed {feed.feed_id} item missing publication timestamp; using retrieval time."
            )
        else:
            item_warnings.append(
                f"RSS feed {feed.feed_id} item missing publication timestamp; using feed timestamp."
            )

    summary_fields = ("summary", "content") if is_atom else ("description", "encoded", "content", "summary")
    summary = _clean_summary(_first_child_text(entry, summary_fields))
    tags = _entry_tags(feed, entry)
    normalized_id = _normalized_item_id(feed.feed_id, provider_item_id, url, title, index)
    return NewsEventItem(
        normalized_id=normalized_id,
        provider_item_id=provider_item_id,
        title=title,
        summary=summary,
        url=url,
        source_provider="rss",
        source_name=feed.source_name,
        published_at=published_at,
        retrieved_at=retrieved_at,
        origin=f"rss.feed:{feed.feed_id}",
        detected_entities=list(feed.detected_entities),
        tags=tags,
        freshness_label=FreshnessLabel.DELAYED,
        warnings=item_warnings,
        transformation_note=(
            "Parsed from a curated source-owned RSS/Atom feed; Gamma strips HTML from snippets, normalizes URLs and "
            "timestamps, and combines curated feed tags with source category labels."
        ),
    )


def _entry_link(entry: ET.Element) -> str:
    for child in list(entry):
        if _local_name(child.tag) != "link":
            continue
        href = str(child.attrib.get("href") or "").strip()
        if href:
            return href
        text = _element_text(child)
        if text:
            return text
    return ""


def _entry_tags(feed: RssFeedConfig, entry: ET.Element) -> list[str]:
    tags = [*_normalize_tags(feed.tags)]
    for category in _children(entry, ("category",)):
        value = category.attrib.get("term") or _element_text(category)
        normalized = _normalize_tag(value)
        if normalized:
            tags.append(normalized)
    return list(dict.fromkeys(tags))


def _normalized_item_id(
    feed_id: str,
    provider_item_id: str | None,
    url: str,
    title: str,
    index: int,
) -> str:
    raw = provider_item_id or canonical_news_url(url) or f"{title}:{index}"
    digest = hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()[:16]
    return f"rss:{feed_id}:{digest}"


def _provider_item_id(feed_id: str, raw_value: str | None) -> str | None:
    value = _clean_text(raw_value)
    if not value:
        return None
    if value.lower().startswith(("http://", "https://")):
        return canonical_news_url(value)
    return f"{feed_id}:{value}"


def _first_child_text(element: ET.Element, names: tuple[str, ...]) -> str:
    name_set = {_normalize_xml_name(name) for name in names}
    for child in list(element):
        child_name = _normalize_xml_name(_local_name(child.tag))
        if child_name in name_set:
            return _element_text(child)
    return ""


def _children(element: ET.Element, names: tuple[str, ...]) -> list[ET.Element]:
    name_set = {_normalize_xml_name(name) for name in names}
    return [child for child in list(element) if _normalize_xml_name(_local_name(child.tag)) in name_set]


def _element_text(element: ET.Element) -> str:
    return "".join(element.itertext()).strip()


def _local_name(tag: str) -> str:
    text = str(tag or "")
    if "}" in text:
        text = text.rsplit("}", 1)[-1]
    return text


def _normalize_xml_name(value: str) -> str:
    return str(value or "").strip().split(":", 1)[-1]


def _parse_datetime(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return _to_utc_naive(parsedate_to_datetime(raw))
    except (TypeError, ValueError, IndexError):
        pass
    iso_value = raw.replace("Z", "+00:00")
    try:
        return _to_utc_naive(datetime.fromisoformat(iso_value))
    except ValueError:
        return None


def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _clean_summary(value: str | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    if len(text) <= SUMMARY_MAX_CHARS:
        return text
    clipped = text[: SUMMARY_MAX_CHARS - 3].rsplit(" ", 1)[0].strip()
    return f"{clipped or text[: SUMMARY_MAX_CHARS - 3]}..."


def _clean_text(value: str | None) -> str:
    raw = str(value or "")
    if not raw.strip():
        return ""
    parser = _HTMLTextExtractor()
    parser.feed(raw)
    parser.close()
    text = parser.text or raw
    return " ".join(unescape(text).split())


def _normalize_tags(values: tuple[str, ...]) -> list[str]:
    return [tag for tag in (_normalize_tag(value) for value in values) if tag]


def _normalize_tag(value: str | None) -> str:
    normalized = " ".join(str(value or "").strip().lower().split())
    if not normalized or len(normalized) > 60:
        return ""
    return normalized.replace(" ", "_")


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    @property
    def text(self) -> str:
        return " ".join(" ".join(self._parts).split())

    def handle_data(self, data: str) -> None:
        if data:
            self._parts.append(data)
