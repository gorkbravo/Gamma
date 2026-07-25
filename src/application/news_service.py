from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from src.models.news import NewsEventFeed, NewsEventItem, canonical_news_url
from src.models.provenance import FreshnessLabel
from src.services.news_adapters import NewsEventProvider
from src.utils.time import now_utc


class NewsService:
    def __init__(
        self,
        providers: list[NewsEventProvider] | tuple[NewsEventProvider, ...],
        *,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self.providers = tuple(providers)
        self.cache_ttl = timedelta(seconds=max(0, int(cache_ttl_seconds or 0)))
        self._latest_cache: dict[int, tuple[datetime, NewsEventFeed]] = {}

    def latest(self, *, limit: int = 25, force_refresh: bool = False) -> NewsEventFeed:
        requested_limit = max(int(limit or 0), 0)
        retrieved_at = now_utc()
        cache_key = requested_limit
        if not force_refresh and self.cache_ttl.total_seconds() > 0:
            cached = self._latest_cache.get(cache_key)
            if cached is not None:
                cached_at, cached_feed = cached
                if retrieved_at - cached_at <= self.cache_ttl:
                    return cached_feed
                self._latest_cache.pop(cache_key, None)

        warnings: list[str] = []
        items: list[NewsEventItem] = []

        for provider in self.providers:
            try:
                feed = provider.latest(limit=requested_limit or 25)
            except Exception as exc:
                warnings.append(f"{provider.provider_id} news provider failed: {exc}")
                continue
            warnings.extend(feed.warnings)
            items.extend(feed.items)
        if not self.providers:
            warnings.append("No news/event providers are configured; item-level news context is unavailable.")
        elif not items:
            warnings.append(
                "Configured news/event providers returned no usable items; the feed is unavailable rather than neutral."
            )

        deduped = _dedupe_items(items)
        deduped.sort(
            key=lambda item: (
                item.published_at,
                item.normalized_id,
                item.source_provider,
            ),
            reverse=True,
        )
        if requested_limit:
            deduped = deduped[:requested_limit]
        source_provider = _source_provider_label(deduped)
        freshness_label = _feed_freshness(deduped)
        result = NewsEventFeed(
            items=deduped,
            source_provider=source_provider,
            retrieved_at=retrieved_at,
            origin="news_service.latest",
            freshness_label=freshness_label,
            warnings=list(dict.fromkeys(warnings)),
            transformation_note=(
                "Gamma merges normalized news/event provider feeds, dedupes by provider item id, canonical URL, "
                "or identical cross-feed headline, sorts by publication time, and applies the requested item limit."
            ),
        )
        if self.cache_ttl.total_seconds() > 0:
            self._latest_cache[cache_key] = (retrieved_at, result)
        return result


def _dedupe_items(items: list[NewsEventItem]) -> list[NewsEventItem]:
    by_key: dict[str, NewsEventItem] = {}
    for item in items:
        keys = _dedupe_keys(item)
        existing = next((by_key[key] for key in keys if key in by_key), None)
        if existing is None:
            for key in keys:
                by_key[key] = item
            continue
        winner, alternate = _deterministic_news_winner(existing, item)
        merged = replace(
            winner,
            warnings=list(dict.fromkeys([*winner.warnings, *alternate.warnings])),
            tags=list(dict.fromkeys([*winner.tags, *alternate.tags])),
            detected_entities=_merge_entities(winner.detected_entities, alternate.detected_entities),
            reporting_sources=[
                *winner.reporting_sources,
                *alternate.reporting_sources,
            ],
            transformation_note=(
                "Gamma deterministically deduplicated matching normalized news items and retained "
                "all reporting feed provenance."
            ),
        )
        merge_keys = set(keys)
        merge_keys.update(key for key, value in by_key.items() if value is existing)
        merge_keys.update(_dedupe_keys(merged))
        for key in merge_keys:
            by_key[key] = merged
    unique: dict[tuple[str, str | None, str, str], NewsEventItem] = {}
    for item in by_key.values():
        unique[(item.source_provider, item.provider_item_id, canonical_news_url(item.url), item.normalized_id)] = item
    return list(unique.values())


def _deterministic_news_winner(
    left: NewsEventItem,
    right: NewsEventItem,
) -> tuple[NewsEventItem, NewsEventItem]:
    left_key = (
        left.published_at,
        left.retrieved_at,
        left.normalized_id,
        left.source_provider,
        canonical_news_url(left.url),
    )
    right_key = (
        right.published_at,
        right.retrieved_at,
        right.normalized_id,
        right.source_provider,
        canonical_news_url(right.url),
    )
    return (left, right) if left_key >= right_key else (right, left)


def _merge_entities(left: list, right: list) -> list:
    merged = {
        (
            entity.entity_type,
            entity.resolved_id(),
            entity.label,
        ): entity
        for entity in [*left, *right]
    }
    return [merged[key] for key in sorted(merged)]


def _dedupe_keys(item: NewsEventItem) -> list[str]:
    keys = [item.dedupe_key()]
    if item.url:
        keys.append(canonical_news_url(item.url))
    # Same headline syndicated by two feeds dedupes cross-feed; short/generic
    # titles are excluded so unrelated brief items are not merged.
    title_key = item.title_dedupe_key()
    if len(title_key) >= len("title:") + 20:
        keys.append(title_key)
    return list(dict.fromkeys(keys))


def _source_provider_label(items: list[NewsEventItem]) -> str:
    providers = sorted({item.source_provider for item in items})
    if not providers:
        return "unavailable"
    if len(providers) == 1:
        return providers[0]
    return "mixed"


def _feed_freshness(items: list[NewsEventItem]) -> FreshnessLabel:
    labels = {item.freshness_label for item in items}
    if not labels:
        return FreshnessLabel.UNAVAILABLE
    if labels == {FreshnessLabel.MOCKED}:
        return FreshnessLabel.MOCKED
    if FreshnessLabel.LIVE in labels:
        return FreshnessLabel.LIVE
    if FreshnessLabel.DELAYED in labels:
        return FreshnessLabel.DELAYED
    if FreshnessLabel.HISTORICAL in labels:
        return FreshnessLabel.HISTORICAL
    return FreshnessLabel.UNKNOWN
