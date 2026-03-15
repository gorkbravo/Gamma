from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.models.prediction_markets import (
    CalibrationBucket,
    CalibrationObservation,
    CalibrationSummary,
    PredictionMarketOutcome,
    PredictionMarketRecord,
    PredictionProbabilityPoint,
    WalletActivityRecord,
    WalletSummary,
)
from src.services.cache import CacheService
from src.utils.time import now_utc


JsonFetcher = Callable[[str, dict[str, Any] | None], Any]


class PredictionMarketAdapter(Protocol):
    provider: str

    def list_markets(
        self,
        *,
        status: str = "open",
        limit: int = 50,
        force_refresh: bool = False,
        query: str = "",
        category: str | None = None,
    ) -> list[PredictionMarketRecord]:
        ...

    def get_market(self, provider_market_id: str) -> PredictionMarketRecord | None:
        ...

    def get_history(self, market: PredictionMarketRecord) -> list[PredictionProbabilityPoint]:
        ...

    def get_wallet_summary(self, market: PredictionMarketRecord) -> WalletSummary:
        ...

    def list_event_markets(self, market: PredictionMarketRecord, *, limit: int = 12) -> list[PredictionMarketRecord]:
        ...

    def build_calibration_summary(self, *, sample_size: int = 30) -> CalibrationSummary:
        ...


def default_json_fetcher(url: str, params: dict[str, Any] | None = None) -> Any:
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
            "User-Agent": "Gamma/0.1 prediction-market-research",
        },
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


POLYMARKET_CATEGORY_SEARCH_QUERIES: dict[str, tuple[str, ...]] = {
    "Politics": ("politics", "election", "senate"),
    "Finance": ("stocks", "earnings", "treasury", "finance"),
    "Geopolitics": ("iran", "ukraine", "china", "tariff"),
    "Crypto": ("bitcoin", "ethereum", "crypto"),
    "Economy": ("inflation", "fed", "cpi", "economy"),
}


class BasePredictionMarketAdapter:
    provider = "unknown"

    def __init__(self, cache: CacheService, fetch_json: JsonFetcher | None = None) -> None:
        self.cache = cache
        self.fetch_json = fetch_json or default_json_fetcher

    def _fetch_cached_json(
        self,
        cache_key: str,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        force_refresh: bool = False,
    ) -> tuple[Any, datetime]:
        if not force_refresh:
            cached = self.cache.get_json(cache_key)
            if isinstance(cached, dict) and "payload" in cached and "retrieved_at" in cached:
                cached_at = _parse_datetime(cached.get("retrieved_at")) or now_utc()
                return cached["payload"], cached_at
        payload = self.fetch_json(url, params)
        retrieved_at = now_utc()
        self.cache.set_json(
            cache_key,
            {
                "retrieved_at": retrieved_at.isoformat(),
                "payload": payload,
            },
        )
        return payload, retrieved_at

    def _build_calibration_summary(
        self,
        records: list[PredictionMarketRecord],
        *,
        sample_size: int,
        origin: str,
        transformation_note: str,
    ) -> CalibrationSummary:
        resolved = [
            record
            for record in records
            if record.current_probability is not None and record.resolution_outcome is not None
        ][:sample_size]
        retrieved_at = max(
            (record.retrieved_at for record in resolved if record.retrieved_at is not None),
            default=now_utc(),
        )
        if not resolved:
            return CalibrationSummary(
                venue=self.provider,
                sample_size=0,
                warnings=["No resolved markets with calibration inputs were available."],
                source_provider=self.provider,
                retrieved_at=retrieved_at,
                origin=origin,
                transformation_note=transformation_note,
            )

        bucket_ranges = [
            (0.0, 0.1, "0-10%"),
            (0.1, 0.25, "10-25%"),
            (0.25, 0.5, "25-50%"),
            (0.5, 0.75, "50-75%"),
            (0.75, 0.9, "75-90%"),
            (0.9, 1.000001, "90-100%"),
        ]
        buckets: list[CalibrationBucket] = []
        for start, end, label in bucket_ranges:
            rows = [
                record for record in resolved if record.current_probability is not None and start <= record.current_probability < end
            ]
            if not rows:
                continue
            average_probability = sum(record.current_probability or 0.0 for record in rows) / len(rows)
            realized_frequency = sum(1.0 if record.resolution_outcome else 0.0 for record in rows) / len(rows)
            buckets.append(
                CalibrationBucket(
                    label=label,
                    sample_size=len(rows),
                    average_probability=average_probability,
                    realized_frequency=realized_frequency,
                    source_provider=self.provider,
                    retrieved_at=retrieved_at,
                    origin=origin,
                    transformation_note=transformation_note,
                )
            )

        observations = [
            CalibrationObservation(
                market_id=record.market_id,
                title=record.title,
                probability=float(record.current_probability or 0.0),
                outcome=bool(record.resolution_outcome),
                settled_at=record.close_time or record.end_time,
                source_provider=self.provider,
                retrieved_at=record.retrieved_at,
                origin=origin,
                transformation_note=transformation_note,
            )
            for record in resolved[:8]
        ]
        return CalibrationSummary(
            venue=self.provider,
            sample_size=len(resolved),
            buckets=buckets,
            observations=observations,
            source_provider=self.provider,
            retrieved_at=retrieved_at,
            origin=origin,
            transformation_note=transformation_note,
        )


class PolymarketAdapter(BasePredictionMarketAdapter):
    provider = "polymarket"
    _gamma_base = "https://gamma-api.polymarket.com"
    _data_base = "https://data-api.polymarket.com"
    _clob_base = "https://clob.polymarket.com"

    def list_markets(
        self,
        *,
        status: str = "open",
        limit: int = 50,
        force_refresh: bool = False,
        query: str = "",
        category: str | None = None,
    ) -> list[PredictionMarketRecord]:
        if str(query or "").strip():
            return self._list_search_markets(
                query=str(query).strip(),
                status=status,
                limit=limit,
                force_refresh=force_refresh,
            )
        if str(category or "").strip():
            return self._list_category_markets(
                category=str(category).strip(),
                status=status,
                limit=limit,
                force_refresh=force_refresh,
            )
        params: dict[str, Any] = {"limit": max(limit, 1)}
        if status == "open":
            params.update({"active": "true", "closed": "false"})
        elif status == "closed":
            params.update({"closed": "true"})
        cache_key = self.cache.make_key("prediction_markets", self.provider, "screener", status, str(limit))
        payload, retrieved_at = self._fetch_cached_json(
            cache_key,
            f"{self._gamma_base}/markets",
            params,
            force_refresh=force_refresh,
        )
        markets = payload if isinstance(payload, list) else []
        return [self._normalize_market(item, retrieved_at=retrieved_at, origin="polymarket.gamma.markets") for item in markets]

    def _list_search_markets(
        self,
        *,
        query: str,
        status: str,
        limit: int,
        force_refresh: bool,
    ) -> list[PredictionMarketRecord]:
        params: dict[str, Any] = {
            "q": query,
            "limit_per_type": self._search_event_limit(limit),
        }
        event_status = self._search_event_status(status)
        if event_status:
            params["events_status"] = event_status
        cache_key = self.cache.make_key(
            "prediction_markets",
            self.provider,
            "search",
            status,
            query.lower(),
            str(params["limit_per_type"]),
        )
        payload, retrieved_at = self._fetch_cached_json(
            cache_key,
            f"{self._gamma_base}/public-search",
            params,
            force_refresh=force_refresh,
        )
        events = payload.get("events", []) if isinstance(payload, dict) else []
        return self._normalize_search_events(
            events,
            retrieved_at=retrieved_at,
            origin="polymarket.gamma.public_search",
        )

    def _list_category_markets(
        self,
        *,
        category: str,
        status: str,
        limit: int,
        force_refresh: bool,
    ) -> list[PredictionMarketRecord]:
        seed_queries = POLYMARKET_CATEGORY_SEARCH_QUERIES.get(category, (category,))
        target_count = min(max(limit, 20), 80)
        rows: list[PredictionMarketRecord] = []
        seen: set[str] = set()
        for seed_query in seed_queries:
            for row in self._list_search_markets(
                query=seed_query,
                status=status,
                limit=target_count,
                force_refresh=force_refresh,
            ):
                if row.market_id in seen:
                    continue
                seen.add(row.market_id)
                rows.append(row)
            if len(rows) >= target_count:
                break
        return rows

    @staticmethod
    def _search_event_limit(limit: int) -> int:
        requested = max(limit, 1)
        return min(max(requested // 4, 8), 25)

    @staticmethod
    def _search_event_status(status: str) -> str | None:
        if status == "open":
            return "open"
        if status == "closed":
            return "closed"
        return None

    def _normalize_search_events(
        self,
        events: list[dict[str, Any]],
        *,
        retrieved_at: datetime,
        origin: str,
    ) -> list[PredictionMarketRecord]:
        rows: list[PredictionMarketRecord] = []
        seen: set[str] = set()
        for event in events:
            if not isinstance(event, dict):
                continue
            event_stub = self._search_event_stub(event)
            event_tags = event.get("tags", [])
            raw_markets = event.get("markets", [])
            if not isinstance(raw_markets, list):
                continue
            for raw_market in raw_markets:
                if not isinstance(raw_market, dict):
                    continue
                item = dict(raw_market)
                item["events"] = [event_stub]
                if event_tags and not item.get("tags"):
                    item["tags"] = event_tags
                market_id = str(item.get("id") or "").strip()
                if not market_id or market_id in seen:
                    continue
                seen.add(market_id)
                rows.append(self._normalize_market(item, retrieved_at=retrieved_at, origin=origin))
        return rows

    @staticmethod
    def _search_event_stub(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": event.get("id"),
            "title": event.get("title"),
            "description": event.get("description"),
            "category": event.get("category"),
            "openInterest": event.get("openInterest"),
            "series": event.get("series") if isinstance(event.get("series"), list) else [],
        }

    def get_market(self, provider_market_id: str) -> PredictionMarketRecord | None:
        cache_key = self.cache.make_key("prediction_markets", self.provider, "detail", provider_market_id)
        payload, retrieved_at = self._fetch_cached_json(
            cache_key,
            f"{self._gamma_base}/markets/{provider_market_id}",
        )
        if not isinstance(payload, dict) or not payload:
            return None
        enriched = payload
        if not payload.get("events") or not payload.get("tags"):
            condition_id = str(payload.get("conditionId") or "").strip()
            if condition_id:
                extra_key = self.cache.make_key("prediction_markets", self.provider, "detail_extra", condition_id)
                extra_payload, extra_retrieved_at = self._fetch_cached_json(
                    extra_key,
                    f"{self._gamma_base}/markets",
                    {"condition_ids": condition_id},
                )
                if isinstance(extra_payload, list) and extra_payload:
                    enriched = extra_payload[0]
                    retrieved_at = max(retrieved_at, extra_retrieved_at)
        return self._normalize_market(enriched, retrieved_at=retrieved_at, origin="polymarket.gamma.market_detail")

    def get_history(self, market: PredictionMarketRecord) -> list[PredictionProbabilityPoint]:
        token_id = market.outcomes[0].token_id if market.outcomes else None
        if not token_id:
            return []
        cache_key = self.cache.make_key("prediction_markets", self.provider, "history", token_id)
        payload, retrieved_at = self._fetch_cached_json(
            cache_key,
            f"{self._clob_base}/prices-history",
            {"market": token_id, "interval": "max", "fidelity": 60},
        )
        history = payload.get("history", []) if isinstance(payload, dict) else []
        return [
            PredictionProbabilityPoint(
                timestamp=datetime.utcfromtimestamp(int(point["t"])),
                probability=float(point["p"]),
                source_provider=self.provider,
                retrieved_at=retrieved_at,
                origin="polymarket.clob.prices_history",
            )
            for point in history
            if "t" in point and "p" in point
        ]

    def get_wallet_summary(self, market: PredictionMarketRecord) -> WalletSummary:
        condition_id = market.provider_condition_id or market.provider_market_id
        trades_key = self.cache.make_key("prediction_markets", self.provider, "trades", market.provider_market_id)
        holders_key = self.cache.make_key("prediction_markets", self.provider, "holders", market.provider_market_id)
        trades_payload, trades_retrieved_at = self._fetch_cached_json(
            trades_key,
            f"{self._data_base}/trades",
            {"market": condition_id, "limit": 200},
        )
        holders_payload, holders_retrieved_at = self._fetch_cached_json(
            holders_key,
            f"{self._data_base}/holders",
            {"market": condition_id, "limit": 25},
        )
        trades = trades_payload if isinstance(trades_payload, list) else []
        participants: dict[str, dict[str, Any]] = {}
        total_notional = 0.0
        for trade in trades:
            wallet = str(trade.get("proxyWallet") or "").strip()
            if not wallet:
                continue
            item = participants.setdefault(
                wallet,
                {
                    "display_name": _display_name(trade.get("name"), trade.get("pseudonym"), wallet),
                    "trade_count": 0,
                    "total_size": 0.0,
                    "notional": 0.0,
                    "price_x_size": 0.0,
                    "first_seen": None,
                    "last_seen": None,
                    "side": str(trade.get("side") or "").lower() or "mixed",
                    "outcome_label": trade.get("outcome"),
                },
            )
            size = _to_float(trade.get("size")) or 0.0
            price = _to_float(trade.get("price"))
            timestamp = _parse_timestamp(trade.get("timestamp"))
            item["trade_count"] += 1
            item["total_size"] += size
            if price is not None:
                item["notional"] += size * price
                item["price_x_size"] += size * price
            item["first_seen"] = _min_dt(item["first_seen"], timestamp)
            item["last_seen"] = _max_dt(item["last_seen"], timestamp)
            total_notional += size * (price or 0.0)

        holder_balances: dict[str, float] = {}
        holder_groups = holders_payload if isinstance(holders_payload, list) else []
        for group in holder_groups:
            for holder in group.get("holders", []):
                wallet = str(holder.get("proxyWallet") or "").strip()
                if not wallet:
                    continue
                holder_balances[wallet] = holder_balances.get(wallet, 0.0) + (_to_float(holder.get("amount")) or 0.0)

        total_balance = sum(holder_balances.values())
        concentration_hhi = None
        top_share = None
        if total_balance > 0:
            shares = [balance / total_balance for balance in holder_balances.values() if balance > 0]
            if shares:
                concentration_hhi = sum(share * share for share in shares)
                top_share = max(shares)

        current_probability = market.current_probability
        rows = sorted(
            participants.items(),
            key=lambda item: float(item[1].get("notional") or 0.0),
            reverse=True,
        )
        participant_rows = [
            WalletActivityRecord(
                participant_id=wallet,
                display_name=item["display_name"],
                venue=self.provider,
                side=str(item["side"]),
                outcome_label=item.get("outcome_label"),
                trade_count=int(item["trade_count"]),
                total_size=float(item["total_size"]),
                average_price=(
                    float(item["price_x_size"]) / float(item["total_size"])
                    if float(item["total_size"]) > 0
                    else None
                ),
                first_seen=item["first_seen"],
                last_seen=item["last_seen"],
                current_edge=(
                    (current_probability - (float(item["price_x_size"]) / float(item["total_size"])))
                    if current_probability is not None and float(item["total_size"]) > 0
                    else None
                ),
                source_provider=self.provider,
                retrieved_at=max(trades_retrieved_at, holders_retrieved_at),
                origin="polymarket.data.wallet_summary",
            )
            for wallet, item in rows[:10]
        ]
        warnings: list[str] = []
        if not participant_rows:
            warnings.append("Public wallet flow data returned no recent trades for this market.")
        if not holder_balances:
            warnings.append("Holder concentration data was unavailable for this market.")
        return WalletSummary(
            market_id=market.market_id,
            venue=self.provider,
            concentration_hhi=concentration_hhi,
            top_participant_share=top_share,
            total_trades=sum(item.trade_count for item in participant_rows),
            total_notional=total_notional,
            participants=participant_rows,
            warnings=warnings,
            source_provider=self.provider,
            retrieved_at=max(trades_retrieved_at, holders_retrieved_at),
            origin="polymarket.data.wallet_summary",
        )

    def list_event_markets(self, market: PredictionMarketRecord, *, limit: int = 12) -> list[PredictionMarketRecord]:
        event_id = market.provider_event_id
        if not event_id:
            return []
        cache_key = self.cache.make_key("prediction_markets", self.provider, "event", event_id)
        payload, retrieved_at = self._fetch_cached_json(cache_key, f"{self._gamma_base}/events/{event_id}")
        raw_markets = payload.get("markets", []) if isinstance(payload, dict) else []
        records = [
            self._normalize_market(item, retrieved_at=retrieved_at, origin="polymarket.gamma.event_markets")
            for item in raw_markets
        ]
        return [record for record in records if record.market_id != market.market_id][:limit]

    def build_calibration_summary(self, *, sample_size: int = 30) -> CalibrationSummary:
        records = self.list_markets(status="closed", limit=max(sample_size * 2, 40))
        return self._build_calibration_summary(
            records,
            sample_size=sample_size,
            origin="polymarket.gamma.calibration",
            transformation_note="Uses lastTradePrice as the final pre-resolution probability proxy and resolved outcomePrices for the realized outcome.",
        )

    def _normalize_market(self, raw: dict[str, Any], *, retrieved_at: datetime, origin: str) -> PredictionMarketRecord:
        outcomes = _load_json_list(raw.get("outcomes"))
        outcome_prices = _load_json_list(raw.get("outcomePrices"))
        token_ids = _load_json_list(raw.get("clobTokenIds"))
        current_probability = _first_float(raw.get("lastTradePrice"), outcome_prices[0] if outcome_prices else None)
        resolved_probability = _to_float(outcome_prices[0]) if outcome_prices else None
        resolution_outcome = _resolve_polymarket_outcome(outcome_prices)
        nested_event = (raw.get("events") or [None])[0] or {}
        nested_series = ((nested_event.get("series") or [None])[0] or {}) if isinstance(nested_event, dict) else {}
        tags = [
            str(tag.get("label") or "").strip()
            for tag in raw.get("tags", [])
            if str(tag.get("label") or "").strip()
        ]
        category = str(raw.get("category") or nested_event.get("category") or "").strip() or None
        outcome_rows = []
        for index, label in enumerate(outcomes):
            price = _to_float(outcome_prices[index]) if index < len(outcome_prices) else None
            resolved = price in {0.0, 1.0} if price is not None else None
            winner = price == 1.0 if resolved else None
            outcome_rows.append(
                PredictionMarketOutcome(
                    outcome_id=f"{raw.get('id')}:{index}",
                    label=str(label),
                    probability=price,
                    token_id=str(token_ids[index]) if index < len(token_ids) else None,
                    resolved=resolved,
                    winner=winner,
                    source_provider=self.provider,
                    retrieved_at=retrieved_at,
                    origin=origin,
                    transformation_note=None if index == 0 else "Additional venue outcome retained for multi-outcome context.",
                )
            )
        provider_event_id = str(nested_event.get("id") or "").strip() or None
        provider_series_id = str(nested_series.get("id") or "").strip() or None
        return PredictionMarketRecord(
            market_id=f"{self.provider}:{raw.get('id')}",
            venue=self.provider,
            title=str(raw.get("question") or nested_event.get("title") or "").strip(),
            subtitle=str(raw.get("groupItemTitle") or "").strip() or None,
            description=str(raw.get("description") or nested_event.get("description") or "").strip() or None,
            status=_normalize_polymarket_status(raw.get("active"), raw.get("closed"), resolution_outcome),
            category=category,
            event_id=f"{self.provider}:event:{provider_event_id}" if provider_event_id else None,
            event_title=str(nested_event.get("title") or "").strip() or None,
            series_id=f"{self.provider}:series:{provider_series_id}" if provider_series_id else None,
            series_title=str(nested_series.get("title") or "").strip() or None,
            provider_market_id=str(raw.get("id")),
            provider_condition_id=str(raw.get("conditionId") or "").strip() or None,
            provider_event_id=provider_event_id,
            provider_series_id=provider_series_id,
            slug=str(raw.get("slug") or "").strip() or None,
            end_time=_parse_datetime(raw.get("endDate")),
            open_time=_parse_datetime(raw.get("startDate")),
            close_time=_parse_datetime(raw.get("closedTime")),
            current_probability=current_probability,
            probability_label=outcome_rows[0].label if outcome_rows else None,
            volume=_to_float(raw.get("volumeNum") or raw.get("volume")),
            volume_24h=_to_float(raw.get("volume24hr")),
            liquidity=_to_float(raw.get("liquidityNum") or raw.get("liquidity")),
            open_interest=_to_float(nested_event.get("openInterest")),
            best_bid=_to_float(raw.get("bestBid")),
            best_ask=_to_float(raw.get("bestAsk")),
            spread=_to_float(raw.get("spread")),
            recent_price_change=_first_float(raw.get("oneDayPriceChange"), raw.get("oneWeekPriceChange")),
            resolved_probability=resolved_probability,
            resolution_outcome=resolution_outcome,
            image_url=str(raw.get("image") or raw.get("icon") or "").strip() or None,
            resolution_source=str(raw.get("resolutionSource") or nested_event.get("resolutionSource") or "").strip() or None,
            outcomes=outcome_rows,
            tags=tags,
            source_provider=self.provider,
            retrieved_at=retrieved_at,
            origin=origin,
            transformation_note="Current probability tracks the first listed outcome and uses lastTradePrice when available.",
        )


class KalshiAdapter(BasePredictionMarketAdapter):
    provider = "kalshi"
    _trade_base = "https://api.elections.kalshi.com/trade-api/v2"

    def list_markets(
        self,
        *,
        status: str = "open",
        limit: int = 50,
        force_refresh: bool = False,
        query: str = "",
        category: str | None = None,
    ) -> list[PredictionMarketRecord]:
        raw_markets: list[dict[str, Any]] = []
        retrieved_at = now_utc()
        statuses = self._status_queries(status)
        for state in statuses:
            cache_key = self.cache.make_key("prediction_markets", self.provider, "screener", state or "all", str(limit))
            payload, response_time = self._fetch_cached_json(
                cache_key,
                f"{self._trade_base}/markets",
                {"limit": max(limit, 1), "status": state} if state else {"limit": max(limit, 1)},
                force_refresh=force_refresh,
            )
            retrieved_at = max(retrieved_at, response_time)
            raw_markets.extend(payload.get("markets", []) if isinstance(payload, dict) else [])
        seen: set[str] = set()
        records: list[PredictionMarketRecord] = []
        for item in raw_markets:
            ticker = str(item.get("ticker") or "").strip()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            records.append(self._normalize_market(item, retrieved_at=retrieved_at, origin="kalshi.markets"))
        return records

    def get_market(self, provider_market_id: str) -> PredictionMarketRecord | None:
        cache_key = self.cache.make_key("prediction_markets", self.provider, "detail", provider_market_id)
        payload, retrieved_at = self._fetch_cached_json(
            cache_key,
            f"{self._trade_base}/markets/{provider_market_id}",
        )
        market_payload = payload.get("market") if isinstance(payload, dict) else None
        if not isinstance(market_payload, dict):
            return None
        event_payload = self._get_event_payload(str(market_payload.get("event_ticker") or "").strip())
        return self._normalize_market(
            market_payload,
            retrieved_at=max(retrieved_at, event_payload[1] if event_payload else retrieved_at),
            origin="kalshi.market_detail",
            event_payload=event_payload[0] if event_payload else None,
        )

    def get_history(self, market: PredictionMarketRecord) -> list[PredictionProbabilityPoint]:
        if not market.provider_event_id or not market.provider_series_id:
            return []
        end_time = int((market.close_time or market.end_time or now_utc()).timestamp())
        start_time = end_time - 7 * 24 * 60 * 60
        cache_key = self.cache.make_key("prediction_markets", self.provider, "history", market.provider_market_id)
        payload, retrieved_at = self._fetch_cached_json(
            cache_key,
            f"{self._trade_base}/series/{market.provider_series_id}/markets/{market.provider_market_id}/candlesticks",
            {
                "period_interval": 60,
                "start_ts": start_time,
                "end_ts": end_time,
            },
        )
        candles = payload.get("candlesticks", []) if isinstance(payload, dict) else []
        return [
            PredictionProbabilityPoint(
                timestamp=datetime.utcfromtimestamp(int(candle["end_period_ts"])),
                probability=_to_float((candle.get("price") or {}).get("close_dollars")) or 0.0,
                volume=_to_float(candle.get("volume_fp")),
                open_interest=_to_float(candle.get("open_interest_fp")),
                bid=_to_float((candle.get("yes_bid") or {}).get("close_dollars")),
                ask=_to_float((candle.get("yes_ask") or {}).get("close_dollars")),
                spread=_spread(
                    _to_float((candle.get("yes_bid") or {}).get("close_dollars")),
                    _to_float((candle.get("yes_ask") or {}).get("close_dollars")),
                ),
                source_provider=self.provider,
                retrieved_at=retrieved_at,
                origin="kalshi.candlesticks",
            )
            for candle in candles
            if "end_period_ts" in candle
        ]

    def get_wallet_summary(self, market: PredictionMarketRecord) -> WalletSummary:
        cache_key = self.cache.make_key("prediction_markets", self.provider, "trades", market.provider_market_id)
        payload, retrieved_at = self._fetch_cached_json(
            cache_key,
            f"{self._trade_base}/markets/trades",
            {"ticker": market.provider_market_id, "limit": 100},
        )
        trades = payload.get("trades", []) if isinstance(payload, dict) else []
        side_rows: dict[str, dict[str, Any]] = {
            "yes": {"trade_count": 0, "total_size": 0.0, "price_x_size": 0.0},
            "no": {"trade_count": 0, "total_size": 0.0, "price_x_size": 0.0},
        }
        total_size = 0.0
        for trade in trades:
            taker_side = str(trade.get("taker_side") or "").lower()
            if taker_side not in side_rows:
                continue
            count = _to_float(trade.get("count_fp")) or 0.0
            price = _to_float(trade.get("yes_price_dollars") if taker_side == "yes" else trade.get("no_price_dollars"))
            side_rows[taker_side]["trade_count"] += 1
            side_rows[taker_side]["total_size"] += count
            if price is not None:
                side_rows[taker_side]["price_x_size"] += count * price
            total_size += count
        total_notional = sum(item["price_x_size"] for item in side_rows.values())
        participant_rows = []
        for side, item in side_rows.items():
            if item["total_size"] <= 0:
                continue
            avg_price = item["price_x_size"] / item["total_size"]
            current_edge = None
            if market.current_probability is not None:
                current_edge = market.current_probability - avg_price if side == "yes" else (1 - market.current_probability) - avg_price
            participant_rows.append(
                WalletActivityRecord(
                    participant_id=f"{self.provider}:flow:{side}",
                    display_name="Yes Takers" if side == "yes" else "No Takers",
                    venue=self.provider,
                    side=side,
                    outcome_label="Yes" if side == "yes" else "No",
                    trade_count=int(item["trade_count"]),
                    total_size=float(item["total_size"]),
                    average_price=float(avg_price),
                    first_seen=None,
                    last_seen=None,
                    current_edge=current_edge,
                    source_provider=self.provider,
                    retrieved_at=retrieved_at,
                    origin="kalshi.market_trades",
                    transformation_note="Kalshi public market-data trades do not expose wallet identifiers; this row aggregates taker-side flow instead.",
                )
            )
        shares = [item["total_size"] / total_size for item in side_rows.values() if total_size > 0 and item["total_size"] > 0]
        return WalletSummary(
            market_id=market.market_id,
            venue=self.provider,
            concentration_hhi=sum(share * share for share in shares) if shares else None,
            top_participant_share=max(shares) if shares else None,
            total_trades=sum(item.trade_count for item in participant_rows),
            total_notional=total_notional,
            participants=participant_rows,
            warnings=["Kalshi public market-data endpoints do not expose wallet addresses; showing aggregate recent taker flow instead."],
            source_provider=self.provider,
            retrieved_at=retrieved_at,
            origin="kalshi.market_trades",
            transformation_note="Wallet identities are unavailable on Kalshi public market-data endpoints; this summary is flow-based rather than wallet-based.",
        )

    def list_event_markets(self, market: PredictionMarketRecord, *, limit: int = 12) -> list[PredictionMarketRecord]:
        event_ticker = market.provider_event_id
        if not event_ticker:
            return []
        event_payload = self._get_event_payload(event_ticker)
        if event_payload is None:
            return []
        payload, retrieved_at = event_payload
        raw_markets = payload.get("markets", []) if isinstance(payload, dict) else []
        records = [
            self._normalize_market(
                item,
                retrieved_at=retrieved_at,
                origin="kalshi.event_markets",
                event_payload=payload,
            )
            for item in raw_markets
        ]
        return [record for record in records if record.market_id != market.market_id][:limit]

    def build_calibration_summary(self, *, sample_size: int = 30) -> CalibrationSummary:
        records = self.list_markets(status="closed", limit=max(sample_size * 2, 40))
        return self._build_calibration_summary(
            records,
            sample_size=sample_size,
            origin="kalshi.calibration",
            transformation_note="Uses last_price_dollars as the final pre-resolution probability proxy and the resolved Kalshi result field for the realized outcome.",
        )

    def _status_queries(self, status: str) -> list[str | None]:
        if status == "open":
            return ["open"]
        if status == "closed":
            return ["closed", "settled"]
        return [None]

    def _get_event_payload(self, event_ticker: str) -> tuple[dict[str, Any], datetime] | None:
        if not event_ticker:
            return None
        cache_key = self.cache.make_key("prediction_markets", self.provider, "event", event_ticker)
        payload, retrieved_at = self._fetch_cached_json(
            cache_key,
            f"{self._trade_base}/events/{event_ticker}",
        )
        if not isinstance(payload, dict):
            return None
        return payload, retrieved_at

    def _normalize_market(
        self,
        raw: dict[str, Any],
        *,
        retrieved_at: datetime,
        origin: str,
        event_payload: dict[str, Any] | None = None,
    ) -> PredictionMarketRecord:
        event = (event_payload or {}).get("event", {}) if event_payload else {}
        series_ticker = str(event.get("series_ticker") or "").strip() or None
        current_probability = _first_float(
            raw.get("last_price_dollars"),
            _midpoint(raw.get("yes_bid_dollars"), raw.get("yes_ask_dollars")),
            raw.get("yes_bid_dollars"),
            raw.get("yes_ask_dollars"),
        )
        resolution_outcome = _resolve_kalshi_outcome(raw.get("result"))
        resolved_probability = 1.0 if resolution_outcome is True else 0.0 if resolution_outcome is False else None
        return PredictionMarketRecord(
            market_id=f"{self.provider}:{raw.get('ticker')}",
            venue=self.provider,
            title=str(raw.get("title") or event.get("title") or "").strip(),
            subtitle=_first_str(raw.get("yes_sub_title"), raw.get("subtitle"), event.get("sub_title")),
            description=_first_str(raw.get("rules_primary"), raw.get("rules_secondary")),
            status=_normalize_kalshi_status(raw.get("status"), resolution_outcome),
            category=str(event.get("category") or "").strip() or None,
            event_id=f"{self.provider}:event:{raw.get('event_ticker')}" if raw.get("event_ticker") else None,
            event_title=str(event.get("title") or "").strip() or None,
            series_id=f"{self.provider}:series:{series_ticker}" if series_ticker else None,
            series_title=series_ticker,
            provider_market_id=str(raw.get("ticker")),
            provider_condition_id=None,
            provider_event_id=str(raw.get("event_ticker") or "").strip() or None,
            provider_series_id=series_ticker,
            slug=str(raw.get("ticker") or "").strip() or None,
            end_time=_parse_datetime(raw.get("expiration_time")),
            open_time=_parse_datetime(raw.get("open_time")),
            close_time=_parse_datetime(raw.get("close_time") or raw.get("settlement_ts")),
            current_probability=current_probability,
            probability_label="Yes",
            volume=_to_float(raw.get("volume_fp")),
            volume_24h=_to_float(raw.get("volume_24h_fp")),
            liquidity=_to_float(raw.get("liquidity_dollars")),
            open_interest=_to_float(raw.get("open_interest_fp")),
            best_bid=_to_float(raw.get("yes_bid_dollars")),
            best_ask=_to_float(raw.get("yes_ask_dollars")),
            spread=_spread(_to_float(raw.get("yes_bid_dollars")), _to_float(raw.get("yes_ask_dollars"))),
            recent_price_change=(
                current_probability - (_to_float(raw.get("previous_price_dollars")) or current_probability)
                if current_probability is not None
                else None
            ),
            resolved_probability=resolved_probability,
            resolution_outcome=resolution_outcome,
            image_url=None,
            resolution_source=_first_str(raw.get("rules_primary"), raw.get("rules_secondary")),
            outcomes=[
                PredictionMarketOutcome(
                    outcome_id=f"{raw.get('ticker')}:yes",
                    label="Yes",
                    probability=current_probability,
                    resolved=resolution_outcome is not None,
                    winner=resolution_outcome is True,
                    source_provider=self.provider,
                    retrieved_at=retrieved_at,
                    origin=origin,
                ),
                PredictionMarketOutcome(
                    outcome_id=f"{raw.get('ticker')}:no",
                    label="No",
                    probability=(1 - current_probability) if current_probability is not None else None,
                    resolved=resolution_outcome is not None,
                    winner=resolution_outcome is False,
                    source_provider=self.provider,
                    retrieved_at=retrieved_at,
                    origin=origin,
                    transformation_note="Derived as one minus the normalized Yes probability.",
                ),
            ],
            tags=[str(event.get("category") or "").strip()] if str(event.get("category") or "").strip() else [],
            source_provider=self.provider,
            retrieved_at=retrieved_at,
            origin=origin,
            transformation_note="Current probability tracks the normalized Yes side and prefers last_price_dollars before bid/ask fallbacks.",
        )


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text or text.startswith("0001-01-01"):
        return None
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def _parse_timestamp(value: Any) -> datetime | None:
    numeric = _to_float(value)
    if numeric is None:
        return None
    try:
        return datetime.utcfromtimestamp(int(numeric))
    except (OverflowError, OSError, ValueError):
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


def _load_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    text = str(value or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _display_name(name: Any, pseudonym: Any, wallet: str) -> str:
    for candidate in (name, pseudonym):
        text = str(candidate or "").strip()
        if text:
            return text
    return f"{wallet[:6]}...{wallet[-4:]}"


def _first_float(*values: Any) -> float | None:
    for value in values:
        parsed = _to_float(value)
        if parsed is not None:
            return parsed
    return None


def _first_str(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _midpoint(left: Any, right: Any) -> float | None:
    left_value = _to_float(left)
    right_value = _to_float(right)
    if left_value is None or right_value is None:
        return None
    return (left_value + right_value) / 2.0


def _spread(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None:
        return None
    return ask - bid


def _resolve_polymarket_outcome(outcome_prices: list[Any]) -> bool | None:
    if not outcome_prices:
        return None
    first = _to_float(outcome_prices[0])
    second = _to_float(outcome_prices[1]) if len(outcome_prices) > 1 else None
    if first == 1.0:
        return True
    if first == 0.0 and second == 1.0:
        return False
    return None


def _resolve_kalshi_outcome(result: Any) -> bool | None:
    normalized = str(result or "").strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    return None


def _normalize_polymarket_status(active: Any, closed: Any, resolution_outcome: bool | None) -> str:
    if resolution_outcome is not None:
        return "resolved"
    if str(closed).lower() == "true":
        return "closed"
    if str(active).lower() == "true":
        return "open"
    return "inactive"


def _normalize_kalshi_status(raw_status: Any, resolution_outcome: bool | None) -> str:
    status = str(raw_status or "").strip().lower()
    if resolution_outcome is not None:
        return "resolved"
    if status in {"active", "open"}:
        return "open"
    if status:
        return "closed"
    return "inactive"


def _min_dt(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return left if left <= right else right


def _max_dt(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return left if left >= right else right
