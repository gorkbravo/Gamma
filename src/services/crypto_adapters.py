from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.models.crypto import (
    CryptoBasketConstituent,
    CryptoDexLiquiditySummary,
    CryptoDexPoolRecord,
    CryptoNarrativeBasketRecord,
    CryptoPricePoint,
    CryptoTokenRecord,
)
from src.services.cache import CacheService
from src.utils.time import ensure_utc, now_utc


JsonFetcher = Callable[[str, dict[str, Any] | None, dict[str, str] | None], Any]

_STALE_FALLBACK_AGE = timedelta(days=30)
_MARKET_CACHE_AGE = timedelta(minutes=20)
_DETAIL_CACHE_AGE = timedelta(minutes=20)
_HISTORY_CACHE_AGE = timedelta(hours=6)
_NARRATIVE_CACHE_AGE = timedelta(hours=4)
_NETWORK_CACHE_AGE = timedelta(days=30)

_PREFERRED_NARRATIVES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Layer 1", ("layer 1", "layer-1", "l1")),
    ("Layer 2", ("layer 2", "layer-2", "l2")),
    ("Layer 3", ("layer 3", "layer-3", "l3")),
    ("DeFi", ("decentralized finance", "defi")),
    ("AI", ("artificial intelligence", "ai")),
    ("DePIN", ("depin",)),
    ("Gaming", ("gaming", "gamefi")),
    ("Meme", ("meme", "memecoin")),
)


def default_json_fetcher(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    cleaned = {
        key: value
        for key, value in (params or {}).items()
        if value is not None and value != "" and value != []
    }
    target_url = url
    if cleaned:
        target_url = f"{url}?{urlencode(cleaned, doseq=True)}"
    request = Request(
        target_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Gamma/0.1 crypto-research",
            **(headers or {}),
        },
    )
    with urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


class CoinGeckoAdapter:
    provider = "coingecko"
    _base_url = "https://api.coingecko.com/api/v3"

    def __init__(
        self,
        cache: CacheService,
        fetch_json: JsonFetcher | None = None,
        api_key: str | None = None,
    ) -> None:
        self.cache = cache
        self.fetch_json = fetch_json or default_json_fetcher
        self.api_key = str(api_key or os.getenv("COINGECKO_API_KEY", "")).strip() or None

    def list_tokens(
        self,
        *,
        limit: int = 40,
        force_refresh: bool = False,
    ) -> list[CryptoTokenRecord]:
        target = min(max(limit * 4, 100), 250)
        return self._load_market_rows(
            cache_key=self.cache.make_key("crypto", self.provider, "markets", str(target)),
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": target,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "24h,7d,30d",
            },
            force_refresh=force_refresh,
            origin="coingecko.coins.markets",
            max_age=_MARKET_CACHE_AGE,
        )

    def search_tokens(
        self,
        query: str,
        *,
        limit: int = 40,
        force_refresh: bool = False,
    ) -> list[CryptoTokenRecord]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return self.list_tokens(limit=limit, force_refresh=force_refresh)

        cache_key = self.cache.make_key("crypto", self.provider, "search", normalized_query.lower())
        payload, _ = self._fetch_cached_json(
            cache_key,
            f"{self._base_url}/search",
            {"query": normalized_query},
            force_refresh=force_refresh,
            max_age=_MARKET_CACHE_AGE,
        )
        coins = payload.get("coins", []) if isinstance(payload, dict) else []
        ranked_ids = [
            str(item.get("id") or "").strip()
            for item in coins
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ]
        ranked_ids = ranked_ids[: max(limit * 2, 20)]
        if not ranked_ids:
            return self._filter_query(self.list_tokens(limit=limit, force_refresh=force_refresh), normalized_query)[:limit]

        try:
            rows = self._load_market_rows(
                cache_key=self.cache.make_key(
                    "crypto",
                    self.provider,
                    "markets_by_ids",
                    str(len(ranked_ids)),
                    normalized_query.lower(),
                ),
                params={
                    "vs_currency": "usd",
                    "ids": ",".join(ranked_ids),
                    "order": "market_cap_desc",
                    "sparkline": "false",
                    "price_change_percentage": "24h,7d,30d",
                },
                force_refresh=force_refresh,
                origin="coingecko.coins.markets",
                max_age=_MARKET_CACHE_AGE,
            )
        except Exception:
            return self._filter_query(self.list_tokens(limit=limit, force_refresh=force_refresh), normalized_query)[:limit]

        order_lookup = {token_id: index for index, token_id in enumerate(ranked_ids)}
        rows.sort(key=lambda row: (order_lookup.get(row.token_id, len(order_lookup)), row.market_cap_rank or 9_999_999))
        return rows[:limit]

    def get_token(self, token_id: str, *, force_refresh: bool = False) -> CryptoTokenRecord | None:
        normalized_id = str(token_id or "").strip()
        if not normalized_id:
            return None
        cache_key = self.cache.make_key("crypto", self.provider, "detail", normalized_id)
        payload, retrieved_at = self._fetch_cached_json(
            cache_key,
            f"{self._base_url}/coins/{normalized_id}",
            {
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "false",
                "developer_data": "false",
                "sparkline": "false",
            },
            force_refresh=force_refresh,
            max_age=_DETAIL_CACHE_AGE,
        )
        if not isinstance(payload, dict) or not payload:
            return None
        return self._normalize_detail(payload, retrieved_at=retrieved_at, origin="coingecko.coins.detail")

    def get_price_history(
        self,
        token_id: str,
        *,
        days: int = 30,
        force_refresh: bool = False,
    ) -> list[CryptoPricePoint]:
        normalized_id = str(token_id or "").strip()
        if not normalized_id:
            return []
        requested_days = min(max(int(days), 1), 365)
        cache_key = self.cache.make_key("crypto", self.provider, "history", normalized_id, str(requested_days))
        payload, retrieved_at = self._fetch_cached_json(
            cache_key,
            f"{self._base_url}/coins/{normalized_id}/market_chart",
            {
                "vs_currency": "usd",
                "days": requested_days,
                "interval": "daily" if requested_days > 2 else None,
            },
            force_refresh=force_refresh,
            max_age=_HISTORY_CACHE_AGE,
        )
        prices = payload.get("prices", []) if isinstance(payload, dict) else []
        market_caps = {
            int(item[0]): _to_float(item[1])
            for item in payload.get("market_caps", [])
            if isinstance(item, list) and len(item) >= 2
        } if isinstance(payload, dict) else {}
        volumes = {
            int(item[0]): _to_float(item[1])
            for item in payload.get("total_volumes", [])
            if isinstance(item, list) and len(item) >= 2
        } if isinstance(payload, dict) else {}
        points: list[CryptoPricePoint] = []
        for item in prices:
            if not isinstance(item, list) or len(item) < 2:
                continue
            millis = _to_float(item[0])
            price = _to_float(item[1])
            if millis is None or price is None:
                continue
            timestamp = datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)
            key = int(millis)
            points.append(
                CryptoPricePoint(
                    timestamp=timestamp,
                    price=price,
                    market_cap=market_caps.get(key),
                    total_volume=volumes.get(key),
                    source_provider=self.provider,
                    retrieved_at=retrieved_at,
                    origin="coingecko.coins.market_chart",
                )
            )
        points.sort(key=lambda point: point.timestamp)
        return points

    def get_narrative_baskets(
        self,
        *,
        force_refresh: bool = False,
        token_index: dict[str, CryptoTokenRecord] | None = None,
    ) -> list[CryptoNarrativeBasketRecord]:
        cache_key = self.cache.make_key("crypto", self.provider, "categories")
        payload, retrieved_at = self._fetch_cached_json(
            cache_key,
            f"{self._base_url}/coins/categories",
            {"order": "market_cap_desc"},
            force_refresh=force_refresh,
            max_age=_NARRATIVE_CACHE_AGE,
        )
        categories = payload if isinstance(payload, list) else []
        selected: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for label, keywords in _PREFERRED_NARRATIVES:
            match = _match_category(categories, keywords)
            if not match:
                continue
            category_id = str(match.get("id") or "").strip()
            if not category_id or category_id in seen_ids:
                continue
            seen_ids.add(category_id)
            selected.append({"label": label, "payload": match})

        rows: list[CryptoNarrativeBasketRecord] = []
        for item in selected:
            category = item["payload"]
            top_ids = [
                str(token_id or "").strip()
                for token_id in category.get("top_3_coins_id", []) or []
                if str(token_id or "").strip()
            ]
            top_images = list(category.get("top_3_coins", []) or [])
            top_tokens: list[CryptoBasketConstituent] = []
            for index, top_id in enumerate(top_ids):
                token = (token_index or {}).get(top_id)
                top_tokens.append(
                    CryptoBasketConstituent(
                        token_id=top_id,
                        name=token.name if token is not None else _prettify_identifier(top_id),
                        symbol=token.symbol.upper() if token is not None else None,
                        image_url=token.image_url if token is not None else str(top_images[index] or "") or None,
                    )
                )
            rows.append(
                CryptoNarrativeBasketRecord(
                    basket_id=str(category.get("id") or ""),
                    label=str(item["label"]),
                    description=_compact_description(category.get("content")),
                    market_cap=_to_float(category.get("market_cap")),
                    market_cap_change_pct_24h=_to_float(category.get("market_cap_change_24h")),
                    volume_24h=_to_float(category.get("volume_24h")),
                    top_tokens=top_tokens,
                    source_provider=self.provider,
                    retrieved_at=retrieved_at,
                    origin="coingecko.coins.categories",
                    transformation_note=(
                        "Gamma-selected narrative baskets map broad research labels onto CoinGecko category records via keyword matching."
                    ),
                )
            )
        return rows

    def _load_market_rows(
        self,
        *,
        cache_key: str,
        params: dict[str, Any],
        force_refresh: bool,
        origin: str,
        max_age: timedelta,
    ) -> list[CryptoTokenRecord]:
        payload, retrieved_at = self._fetch_cached_json(
            cache_key,
            f"{self._base_url}/coins/markets",
            params,
            force_refresh=force_refresh,
            max_age=max_age,
        )
        rows = payload if isinstance(payload, list) else []
        return [
            self._normalize_market(item, retrieved_at=retrieved_at, origin=origin)
            for item in rows
            if isinstance(item, dict)
        ]

    def _fetch_cached_json(
        self,
        cache_key: str,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        force_refresh: bool,
        max_age: timedelta,
    ) -> tuple[Any, datetime]:
        if not force_refresh:
            cached = self.cache.get_json_entry(cache_key, max_age=max_age)
            if isinstance(cached, dict) and isinstance(cached.get("value"), dict):
                value = cached["value"]
                if "payload" in value and "retrieved_at" in value:
                    retrieved_at = _parse_datetime(value.get("retrieved_at")) or ensure_utc(now_utc())
                    return value.get("payload"), retrieved_at
        try:
            payload = self.fetch_json(url, params, self._headers())
        except Exception:
            cached = self.cache.get_json_entry(cache_key, max_age=_STALE_FALLBACK_AGE)
            if isinstance(cached, dict) and isinstance(cached.get("value"), dict):
                value = cached["value"]
                if "payload" in value and "retrieved_at" in value:
                    retrieved_at = _parse_datetime(value.get("retrieved_at")) or ensure_utc(now_utc())
                    return value.get("payload"), retrieved_at
            raise
        retrieved_at = ensure_utc(now_utc()) or datetime.now(timezone.utc)
        self.cache.set_json(
            cache_key,
            {
                "retrieved_at": retrieved_at.isoformat(),
                "payload": payload,
            },
        )
        return payload, retrieved_at

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {"x-cg-demo-api-key": self.api_key}

    @staticmethod
    def _filter_query(rows: list[CryptoTokenRecord], query: str) -> list[CryptoTokenRecord]:
        normalized_query = _normalize_text(query)
        tokens = set(normalized_query.split())
        if not tokens:
            return rows
        ranked: list[tuple[tuple[int, int, int, str], CryptoTokenRecord]] = []
        for row in rows:
            text = _normalize_text(" ".join(filter(None, [row.name, row.symbol, row.token_id])))
            if not text:
                continue
            coverage = sum(1 for token in tokens if token in text)
            if coverage == 0:
                continue
            ranked.append(
                (
                    (
                        -coverage,
                        row.market_cap_rank or 9_999_999,
                        0 if text.startswith(normalized_query) else 1,
                        row.name.lower(),
                    ),
                    row,
                )
            )
        ranked.sort(key=lambda item: item[0])
        return [row for _, row in ranked]

    def _normalize_market(
        self,
        raw: dict[str, Any],
        *,
        retrieved_at: datetime,
        origin: str,
    ) -> CryptoTokenRecord:
        market_cap = _to_float(raw.get("market_cap"))
        total_volume = _to_float(raw.get("total_volume"))
        fdv = _to_float(raw.get("fully_diluted_valuation"))
        return CryptoTokenRecord(
            token_id=str(raw.get("id") or "").strip(),
            symbol=str(raw.get("symbol") or "").strip(),
            name=str(raw.get("name") or "").strip(),
            image_url=_first_str(raw.get("image")),
            chain=None,
            asset_platform_id=None,
            geckoterminal_network=None,
            contract_address=None,
            market_cap_rank=_to_int(raw.get("market_cap_rank")),
            current_price=_to_float(raw.get("current_price")),
            market_cap=market_cap,
            fully_diluted_valuation=fdv,
            total_volume=total_volume,
            circulating_supply=_to_float(raw.get("circulating_supply")),
            total_supply=_to_float(raw.get("total_supply")),
            max_supply=_to_float(raw.get("max_supply")),
            price_change_pct_24h=_to_float(raw.get("price_change_percentage_24h_in_currency")),
            price_change_pct_7d=_to_float(raw.get("price_change_percentage_7d_in_currency")),
            price_change_pct_30d=_to_float(raw.get("price_change_percentage_30d_in_currency")),
            market_cap_change_pct_24h=_to_float(raw.get("market_cap_change_percentage_24h")),
            high_24h=_to_float(raw.get("high_24h")),
            low_24h=_to_float(raw.get("low_24h")),
            homepage_url=None,
            description=None,
            categories=[],
            turnover_ratio_24h=_safe_ratio(total_volume, market_cap),
            fdv_premium_ratio=_fdv_premium_ratio(fdv, market_cap),
            source_provider=self.provider,
            retrieved_at=_parse_datetime(raw.get("last_updated")) or retrieved_at,
            origin=origin,
            transformation_note="24H turnover ratio is Gamma-defined as total_volume divided by market_cap.",
        )

    def _normalize_detail(
        self,
        raw: dict[str, Any],
        *,
        retrieved_at: datetime,
        origin: str,
    ) -> CryptoTokenRecord:
        market_data = raw.get("market_data") if isinstance(raw.get("market_data"), dict) else {}
        price = market_data.get("current_price", {}) if isinstance(market_data, dict) else {}
        market_cap_payload = market_data.get("market_cap", {}) if isinstance(market_data, dict) else {}
        fdv_payload = market_data.get("fully_diluted_valuation", {}) if isinstance(market_data, dict) else {}
        total_volume_payload = market_data.get("total_volume", {}) if isinstance(market_data, dict) else {}
        asset_platform_id = _first_str(raw.get("asset_platform_id"))
        primary_platform_id, contract_address = _primary_contract_address(
            asset_platform_id,
            raw.get("platforms"),
        )
        categories = [
            str(item or "").strip()
            for item in raw.get("categories", []) or []
            if str(item or "").strip()
        ]
        market_cap = _to_float(market_cap_payload.get("usd"))
        total_volume = _to_float(total_volume_payload.get("usd"))
        fdv = _to_float(fdv_payload.get("usd"))
        description = None
        raw_description = raw.get("description")
        if isinstance(raw_description, dict):
            description = _compact_description(raw_description.get("en"))
        homepage = None
        links = raw.get("links")
        if isinstance(links, dict):
            homepage_rows = links.get("homepage", []) or []
            if isinstance(homepage_rows, list):
                homepage = _first_str(*homepage_rows)
        chain_label = _display_chain(primary_platform_id)
        if chain_label is None and categories:
            for category in categories:
                lowered = category.lower()
                if "ecosystem" in lowered or "layer" in lowered:
                    chain_label = category
                    break
        return CryptoTokenRecord(
            token_id=str(raw.get("id") or "").strip(),
            symbol=str(raw.get("symbol") or "").strip(),
            name=str(raw.get("name") or "").strip(),
            image_url=_first_str((raw.get("image") or {}).get("large"), (raw.get("image") or {}).get("small")),
            chain=chain_label,
            asset_platform_id=primary_platform_id,
            geckoterminal_network=None,
            contract_address=contract_address,
            market_cap_rank=_to_int(raw.get("market_cap_rank")),
            current_price=_to_float(price.get("usd")),
            market_cap=market_cap,
            fully_diluted_valuation=fdv,
            total_volume=total_volume,
            circulating_supply=_to_float(market_data.get("circulating_supply")),
            total_supply=_to_float(market_data.get("total_supply")),
            max_supply=_to_float(market_data.get("max_supply")),
            price_change_pct_24h=_to_float(market_data.get("price_change_percentage_24h")),
            price_change_pct_7d=_to_float(market_data.get("price_change_percentage_7d")),
            price_change_pct_30d=_to_float(market_data.get("price_change_percentage_30d")),
            market_cap_change_pct_24h=_to_float(market_data.get("market_cap_change_percentage_24h")),
            high_24h=_to_float(market_data.get("high_24h", {}).get("usd")),
            low_24h=_to_float(market_data.get("low_24h", {}).get("usd")),
            homepage_url=homepage,
            description=description,
            categories=categories,
            turnover_ratio_24h=_safe_ratio(total_volume, market_cap),
            fdv_premium_ratio=_fdv_premium_ratio(fdv, market_cap),
            source_provider=self.provider,
            retrieved_at=_parse_datetime(raw.get("last_updated")) or retrieved_at,
            origin=origin,
            transformation_note=(
                "Chain and contract metadata prefer CoinGecko asset_platform_id and platform mappings; 24H turnover ratio is Gamma-defined as total_volume divided by market_cap."
            ),
        )


class GeckoTerminalAdapter:
    provider = "geckoterminal"
    _base_url = "https://api.geckoterminal.com/api/v2"

    def __init__(self, cache: CacheService, fetch_json: JsonFetcher | None = None) -> None:
        self.cache = cache
        self.fetch_json = fetch_json or default_json_fetcher

    def get_liquidity_summary(
        self,
        token: CryptoTokenRecord,
        *,
        force_refresh: bool = False,
    ) -> CryptoDexLiquiditySummary:
        warnings: list[str] = []
        pools: list[CryptoDexPoolRecord] = []
        lookup_strategy = "unavailable"

        network_map = self.get_network_map(force_refresh=force_refresh)
        retrieved_at = ensure_utc(now_utc()) or datetime.now(timezone.utc)

        if token.asset_platform_id and token.contract_address:
            network_id = network_map.get(token.asset_platform_id)
            if network_id:
                lookup_strategy = "contract_lookup"
                cache_key = self.cache.make_key(
                    "crypto",
                    self.provider,
                    "token_pools",
                    network_id,
                    token.contract_address.lower(),
                )
                try:
                    payload, retrieved_at = self._fetch_cached_json(
                        cache_key,
                        f"{self._base_url}/networks/{network_id}/tokens/{token.contract_address.lower()}/pools",
                        force_refresh=force_refresh,
                        max_age=_MARKET_CACHE_AGE,
                    )
                    pools = self._normalize_pools(payload, retrieved_at=retrieved_at, origin="geckoterminal.token_pools")
                except Exception as exc:
                    warnings.append(f"Exact DEX pool lookup failed: {exc}")
            else:
                warnings.append(
                    f"GeckoTerminal does not currently map CoinGecko platform `{token.asset_platform_id}` in Gamma's network index."
                )

        if not pools:
            lookup_strategy = "search_fallback"
            try:
                query = " ".join(filter(None, [token.name, token.symbol.upper()])).strip()
                cache_key = self.cache.make_key("crypto", self.provider, "pool_search", _normalize_text(query))
                payload, retrieved_at = self._fetch_cached_json(
                    cache_key,
                    f"{self._base_url}/search/pools",
                    {"query": query, "page": 1},
                    force_refresh=force_refresh,
                    max_age=_MARKET_CACHE_AGE,
                )
                candidate_pools = self._normalize_pools(payload, retrieved_at=retrieved_at, origin="geckoterminal.search.pools")
                pools = [pool for pool in candidate_pools if _pool_matches_token(pool, token)]
            except Exception as exc:
                warnings.append(f"DEX search fallback failed: {exc}")

        pools.sort(key=lambda pool: (-(pool.reserve_usd or 0.0), -(pool.volume_24h or 0.0), pool.dex.lower()))
        selected_pools = pools[:8]
        dominant_pool = selected_pools[0] if selected_pools else None
        return CryptoDexLiquiditySummary(
            token_id=token.token_id,
            lookup_strategy=lookup_strategy,
            matched_networks=sorted({pool.network for pool in selected_pools}),
            total_reserve_usd=_sum_float(pool.reserve_usd for pool in selected_pools),
            total_volume_24h=_sum_float(pool.volume_24h for pool in selected_pools),
            total_buys_24h=sum(pool.buys_24h for pool in selected_pools),
            total_sells_24h=sum(pool.sells_24h for pool in selected_pools),
            total_buyers_24h=sum(pool.buyers_24h for pool in selected_pools),
            total_sellers_24h=sum(pool.sellers_24h for pool in selected_pools),
            dominant_dex=dominant_pool.dex if dominant_pool is not None else None,
            pools=selected_pools,
            warnings=warnings,
            source_provider=self.provider,
            retrieved_at=max((pool.retrieved_at for pool in selected_pools if pool.retrieved_at is not None), default=retrieved_at),
            origin="geckoterminal.liquidity_summary",
            transformation_note=(
                "Gamma aggregates the top matched pools by reserve_usd and volume_usd. Search-fallback pool matching is heuristic when no exact contract lookup is available."
            ),
        )

    def get_network_map(self, *, force_refresh: bool = False) -> dict[str, str]:
        cache_key = self.cache.make_key("crypto", self.provider, "networks")
        payload, _ = self._fetch_cached_json(
            cache_key,
            f"{self._base_url}/networks",
            {"page": 1},
            force_refresh=force_refresh,
            max_age=_NETWORK_CACHE_AGE,
        )
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        mapping: dict[str, str] = {}
        links = payload.get("links") if isinstance(payload, dict) else None
        next_url = links.get("next") if isinstance(links, dict) else None
        while next_url:
            page_key = self.cache.make_key("crypto", self.provider, "networks", _normalize_text(next_url))
            page_payload, _ = self._fetch_cached_json(
                page_key,
                next_url,
                None,
                force_refresh=force_refresh,
                max_age=_NETWORK_CACHE_AGE,
            )
            page_rows = page_payload.get("data", []) if isinstance(page_payload, dict) else []
            rows.extend(page_rows if isinstance(page_rows, list) else [])
            page_links = page_payload.get("links") if isinstance(page_payload, dict) else None
            next_url = page_links.get("next") if isinstance(page_links, dict) else None

        for item in rows:
            if not isinstance(item, dict):
                continue
            attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            platform_id = str(attributes.get("coingecko_asset_platform_id") or "").strip()
            network_id = str(item.get("id") or "").strip()
            if platform_id and network_id and platform_id not in mapping:
                mapping[platform_id] = network_id
        return mapping

    def _fetch_cached_json(
        self,
        cache_key: str,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        force_refresh: bool,
        max_age: timedelta,
    ) -> tuple[Any, datetime]:
        if not force_refresh:
            cached = self.cache.get_json_entry(cache_key, max_age=max_age)
            if isinstance(cached, dict) and isinstance(cached.get("value"), dict):
                value = cached["value"]
                if "payload" in value and "retrieved_at" in value:
                    retrieved_at = _parse_datetime(value.get("retrieved_at")) or ensure_utc(now_utc())
                    return value.get("payload"), retrieved_at
        try:
            payload = self.fetch_json(url, params, None)
        except Exception:
            cached = self.cache.get_json_entry(cache_key, max_age=_STALE_FALLBACK_AGE)
            if isinstance(cached, dict) and isinstance(cached.get("value"), dict):
                value = cached["value"]
                if "payload" in value and "retrieved_at" in value:
                    retrieved_at = _parse_datetime(value.get("retrieved_at")) or ensure_utc(now_utc())
                    return value.get("payload"), retrieved_at
            raise
        retrieved_at = ensure_utc(now_utc()) or datetime.now(timezone.utc)
        self.cache.set_json(
            cache_key,
            {
                "retrieved_at": retrieved_at.isoformat(),
                "payload": payload,
            },
        )
        return payload, retrieved_at

    @staticmethod
    def _normalize_pools(
        payload: Any,
        *,
        retrieved_at: datetime,
        origin: str,
    ) -> list[CryptoDexPoolRecord]:
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        pools: list[CryptoDexPoolRecord] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            relationships = item.get("relationships") if isinstance(item.get("relationships"), dict) else {}
            dex_payload = relationships.get("dex") if isinstance(relationships.get("dex"), dict) else {}
            dex_data = dex_payload.get("data") if isinstance(dex_payload.get("data"), dict) else {}
            network = str(item.get("id") or "").split("_", 1)[0]
            pair_name = str(attributes.get("name") or "").strip()
            transactions = attributes.get("transactions") if isinstance(attributes.get("transactions"), dict) else {}
            h24_transactions = transactions.get("h24") if isinstance(transactions.get("h24"), dict) else {}
            price_changes = attributes.get("price_change_percentage") if isinstance(attributes.get("price_change_percentage"), dict) else {}
            volumes = attributes.get("volume_usd") if isinstance(attributes.get("volume_usd"), dict) else {}
            pools.append(
                CryptoDexPoolRecord(
                    pool_id=str(item.get("id") or "").strip(),
                    network=network,
                    dex=str(dex_data.get("id") or "").strip() or "unknown_dex",
                    pair_name=pair_name,
                    address=str(attributes.get("address") or "").strip(),
                    quote_token_symbol=_quote_symbol_from_pair(pair_name),
                    base_token_price_usd=_to_float(attributes.get("base_token_price_usd")),
                    fdv_usd=_to_float(attributes.get("fdv_usd")),
                    market_cap_usd=_to_float(attributes.get("market_cap_usd")),
                    reserve_usd=_to_float(attributes.get("reserve_in_usd")),
                    volume_24h=_to_float(volumes.get("h24")),
                    price_change_pct_24h=_to_float(price_changes.get("h24")),
                    buys_24h=_to_int(h24_transactions.get("buys")) or 0,
                    sells_24h=_to_int(h24_transactions.get("sells")) or 0,
                    buyers_24h=_to_int(h24_transactions.get("buyers")) or 0,
                    sellers_24h=_to_int(h24_transactions.get("sellers")) or 0,
                    pool_created_at=_parse_datetime(attributes.get("pool_created_at")),
                    source_provider="geckoterminal",
                    retrieved_at=retrieved_at,
                    origin=origin,
                    transformation_note="Gamma uses GeckoTerminal pool reserve, volume, and 24H transaction counts as a read-only liquidity and flow proxy.",
                )
            )
        return pools


def _match_category(categories: list[dict[str, Any]], keywords: tuple[str, ...]) -> dict[str, Any] | None:
    for category in categories:
        if not isinstance(category, dict):
            continue
        haystack = _normalize_text(" ".join([str(category.get("id") or ""), str(category.get("name") or "")]))
        if any(_normalize_text(keyword) in haystack for keyword in keywords):
            return category
    return None


def _primary_contract_address(
    preferred_platform_id: str | None,
    platforms_payload: Any,
) -> tuple[str | None, str | None]:
    if not isinstance(platforms_payload, dict):
        return preferred_platform_id, None
    preferred = str(preferred_platform_id or "").strip()
    if preferred:
        preferred_contract = _first_str(platforms_payload.get(preferred))
        if preferred_contract:
            return preferred, preferred_contract
    for platform_id, contract_value in platforms_payload.items():
        contract = _first_str(contract_value)
        if contract:
            return str(platform_id or "").strip() or None, contract
    return preferred_platform_id, None


def _display_chain(platform_id: str | None) -> str | None:
    text = str(platform_id or "").strip()
    if not text:
        return None
    normalized = text.replace("-", " ").replace("_", " ")
    return " ".join(part.upper() if len(part) <= 3 else part.capitalize() for part in normalized.split())


def _pool_matches_token(pool: CryptoDexPoolRecord, token: CryptoTokenRecord) -> bool:
    symbol = token.symbol.upper()
    pair_name = pool.pair_name.upper()
    if f"{symbol} /" in pair_name or f"/ {symbol}" in pair_name or pair_name.startswith(f"{symbol} "):
        return True
    return symbol in {part.strip().upper() for part in pair_name.split("/")}


def _quote_symbol_from_pair(pair_name: str) -> str | None:
    parts = [part.strip() for part in pair_name.split("/")]
    if len(parts) < 2:
        return None
    quote = parts[1]
    quote = re.sub(r"\s+\d.*$", "", quote).strip()
    return quote or None


def _compact_description(value: Any, limit: int = 360) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "").replace("\r", " ").replace("\n", " ")).strip()
    if not text:
        return None
    return text[: limit - 3].rstrip() + "..." if len(text) > limit else text


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _prettify_identifier(value: str) -> str:
    words = [part for part in re.split(r"[-_]+", str(value or "").strip()) if part]
    if not words:
        return str(value or "")
    return " ".join(word.upper() if len(word) <= 3 else word.capitalize() for word in words)


def _sum_float(values: Any) -> float | None:
    total = 0.0
    seen = False
    for value in values:
        parsed = _to_float(value)
        if parsed is None:
            continue
        total += parsed
        seen = True
    return total if seen else None


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _fdv_premium_ratio(fdv: float | None, market_cap: float | None) -> float | None:
    if fdv is None or market_cap is None or market_cap <= 0:
        return None
    return (fdv - market_cap) / market_cap


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        return ensure_utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    numeric = _to_float(value)
    if numeric is None:
        return None
    try:
        return int(numeric)
    except (TypeError, ValueError):
        return None


def _first_str(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None
