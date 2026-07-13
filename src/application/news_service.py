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

        deduped = _dedupe_items(items)
        deduped.sort(key=lambda item: item.published_at, reverse=True)
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
        if existing is None or item.published_at > existing.published_at:
            replacement_keys = set(keys)
            if existing is not None:
                replacement_keys.update(key for key, value in by_key.items() if value is existing)
            for key in replacement_keys:
                by_key[key] = item
        elif item.published_at == existing.published_at:
            merged = replace(
                existing,
                warnings=list(dict.fromkeys([*existing.warnings, *item.warnings])),
                tags=list(dict.fromkeys([*existing.tags, *item.tags])),
            )
            merge_keys = set(keys)
            merge_keys.update(key for key, value in by_key.items() if value is existing)
            for key in merge_keys:
                by_key[key] = merged
    unique: dict[tuple[str, str | None, str, str], NewsEventItem] = {}
    for item in by_key.values():
        unique[(item.source_provider, item.provider_item_id, canonical_news_url(item.url), item.normalized_id)] = item
    return list(unique.values())


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
