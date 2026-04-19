from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Callable, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.models.commodities import (
    CommodityCoverageMetadata,
    CommodityCurveNode,
    CommodityCurveSnapshot,
    CommodityEventRecord,
    CommodityFuturesContract,
    CommodityInstrument,
    CommodityInventoryPoint,
    CommodityInventorySeries,
    CommodityInventorySeriesMetadata,
    CommodityPriceHistory,
    CommodityPricePoint,
    CommodityProviderSnapshot,
)
from src.services.cache import CacheService
from src.services.fred import FredClient
from src.utils.time import now_utc


JsonFetcher = Callable[[str, dict[str, Any] | None], Any]


class CommoditiesDataProvider(Protocol):
    provider_id: str
    provider_label: str

    def get_snapshot(self, *, force_refresh: bool = False) -> CommodityProviderSnapshot:
        ...


@dataclass(frozen=True)
class EiaSeriesConfig:
    series_id: str
    instrument_id: str | None
    label: str
    category: str
    unit: str
    frequency: str = "weekly"


@dataclass(frozen=True)
class FredPriceConfig:
    series_id: str
    instrument_id: str
    label: str
    unit: str


EIA_INVENTORY_SERIES: tuple[EiaSeriesConfig, ...] = (
    EiaSeriesConfig(
        series_id=os.getenv("EIA_CRUDE_STOCKS_SERIES_ID", "PET.WCESTUS1.W"),
        instrument_id="wti",
        label="US Commercial Crude Stocks",
        category="inventories",
        unit="million bbl",
    ),
    EiaSeriesConfig(
        series_id=os.getenv("EIA_GASOLINE_STOCKS_SERIES_ID", "PET.WGTSTUS1.W"),
        instrument_id="gasoline",
        label="US Motor Gasoline Stocks",
        category="inventories",
        unit="million bbl",
    ),
    EiaSeriesConfig(
        series_id=os.getenv("EIA_DISTILLATE_STOCKS_SERIES_ID", "PET.WDISTUS1.W"),
        instrument_id="heating_oil",
        label="US Distillate Fuel Oil Stocks",
        category="inventories",
        unit="million bbl",
    ),
    EiaSeriesConfig(
        series_id=os.getenv("EIA_NATGAS_STORAGE_SERIES_ID", "NG.NW2_EPG0_SWO_R48_BCF.W"),
        instrument_id="henry_hub",
        label="Lower 48 Working Gas Storage",
        category="storage",
        unit="bcf",
    ),
)

FRED_PRICE_SERIES: tuple[FredPriceConfig, ...] = (
    FredPriceConfig("DCOILWTICO", "wti", "WTI Spot Proxy", "USD/bbl"),
    FredPriceConfig("DCOILBRENTEU", "brent", "Brent Spot Proxy", "USD/bbl"),
    FredPriceConfig("DHHNGSP", "henry_hub", "Henry Hub Spot Proxy", "USD/MMBtu"),
    FredPriceConfig("GOLDAMGBD228NLBM", "gold", "Gold London AM Fix", "USD/oz"),
    FredPriceConfig("SLVPRUSD", "silver", "Silver Price Proxy", "USD/oz"),
    FredPriceConfig("PCOPPUSDM", "copper", "Copper Price Proxy", "USD/metric ton"),
)

MONTH_CODES = "FGHJKMNQUVXZ"


def default_eia_fetcher(url: str, params: dict[str, Any] | None = None) -> Any:
    cleaned = {
        key: value
        for key, value in (params or {}).items()
        if value is not None and value != "" and value != []
    }
    target_url = f"{url}?{urlencode(cleaned, doseq=True)}" if cleaned else url
    request = Request(
        target_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Gamma/0.1 commodities-research",
        },
    )
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


class SampleCommoditiesDataProvider:
    provider_id = "sample_commodities"
    provider_label = "Sample Commodities Dataset"

    def get_snapshot(self, *, force_refresh: bool = False) -> CommodityProviderSnapshot:
        del force_refresh
        retrieved_at = now_utc().replace(microsecond=0)
        instruments = _sample_instruments(retrieved_at)
        price_histories = _sample_price_histories(instruments, retrieved_at)
        curves = _sample_curves(instruments, retrieved_at)
        inventories = _sample_inventory_series(retrieved_at)
        events = _sample_events(retrieved_at)
        warnings = [
            "Commodities is using sample data; it is not live futures, spot, or inventory coverage.",
            "Futures curves and spreads are synthetic samples until an entitled futures data provider is configured.",
            "Inventory seasonality is a first-pass research heuristic and should not be treated as an official surprise model.",
        ]
        coverage = CommodityCoverageMetadata(
            coverage_status="sample",
            provider_id=self.provider_id,
            provider_label=self.provider_label,
            freshness_label="mocked",
            instruments=[instrument.instrument_id for instrument in instruments],
            regions=["US", "Global"],
            as_of=retrieved_at,
            source_timestamp=retrieved_at,
            caveats=[
                "Sample prices, curves, inventories, and events are generated for offline Workstream 8 development.",
                "The workspace is read-only and does not expose order entry or strategy execution.",
            ],
            supports_prices=True,
            supports_curves=True,
            supports_inventories=True,
            supports_events=True,
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_commodities.coverage",
            transformation_note="Coverage is labeled sample because no live commodities provider is required.",
        )
        return CommodityProviderSnapshot(
            coverage=coverage,
            instruments=instruments,
            price_histories=price_histories,
            curve_snapshots=curves,
            inventory_series=inventories,
            events=events,
            warnings=warnings,
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_commodities.snapshot",
            transformation_note=(
                "Static Gamma sample records are materialized into normalized commodity entities for Workstream 8 development."
            ),
        )


class EiaCommoditiesDataProvider:
    provider_id = "eia"
    provider_label = "EIA + FRED Commodities"

    SERIES_ID_URL = "https://api.eia.gov/v2/seriesid/{series_id}"

    def __init__(
        self,
        *,
        api_key: str | None,
        cache: CacheService | None = None,
        reference_provider: CommoditiesDataProvider | None = None,
        fred_client: FredClient | None = None,
        fetch_json: JsonFetcher | None = None,
        cache_seconds: int = 21_600,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.cache = cache
        self.reference_provider = reference_provider or SampleCommoditiesDataProvider()
        self.fred_client = fred_client
        self.fetch_json = fetch_json or default_eia_fetcher
        self.cache_seconds = max(0, int(cache_seconds))

    def get_snapshot(self, *, force_refresh: bool = False) -> CommodityProviderSnapshot:
        reference = self.reference_provider.get_snapshot(force_refresh=False)
        if not self.api_key:
            return _with_provider_warning(
                reference,
                "COMMODITIES_PROVIDER=eia but EIA_API_KEY is not configured; using sample commodities fallback.",
            )

        retrieved_at = now_utc().replace(microsecond=0)
        warnings: list[str] = []
        inventories = {series.metadata.series_id: series for series in reference.inventory_series}
        official_count = 0
        for config in EIA_INVENTORY_SERIES:
            try:
                series = self._fetch_eia_inventory_series(config, force_refresh=force_refresh)
            except Exception as exc:
                warnings.append(f"EIA series {config.series_id} failed: {exc.__class__.__name__}.")
                continue
            if series.points:
                inventories[series.metadata.series_id] = series
                official_count += 1

        price_histories = {history.instrument_id: history for history in reference.price_histories}
        fred_count = 0
        if self.fred_client is not None:
            for config in FRED_PRICE_SERIES:
                try:
                    history = self._fetch_fred_price_history(config, force_refresh=force_refresh)
                except Exception as exc:
                    warnings.append(f"FRED series {config.series_id} failed: {exc.__class__.__name__}.")
                    continue
                if history.points:
                    price_histories[history.instrument_id] = history
                    fred_count += 1

        if official_count == 0 and fred_count == 0:
            return _with_provider_warning(
                reference,
                "EIA/FRED enrichment returned no usable commodity series; using sample commodities fallback.",
                extra_warnings=warnings,
            )

        latest_source = _max_datetime(
            retrieved_at,
            *(series.retrieved_at for series in inventories.values()),
            *(history.retrieved_at for history in price_histories.values()),
        )
        coverage = CommodityCoverageMetadata(
            coverage_status="official_partial",
            provider_id=self.provider_id,
            provider_label=self.provider_label,
            freshness_label="official_release_lag",
            instruments=[instrument.instrument_id for instrument in reference.instruments],
            regions=["US", "Global"],
            as_of=latest_source,
            source_timestamp=_max_datetime(
                *(series.points[-1].timestamp for series in inventories.values() if series.points),
                *(history.points[-1].timestamp for history in price_histories.values() if history.points),
            ),
            caveats=[
                "EIA enrichment covers selected official US energy fundamentals only.",
                "FRED price histories are spot or proxy series where configured; futures curves remain sample unless a futures provider is added.",
                "Gamma keeps provider credentials server-side and exposes read-only normalized research data.",
                *warnings,
            ],
            credential_env_vars=["EIA_API_KEY", "FRED_API_KEY"],
            supports_prices=fred_count > 0,
            supports_curves=True,
            supports_inventories=official_count > 0,
            supports_events=True,
            source_provider="eia",
            retrieved_at=latest_source,
            origin="eia_commodities.coverage",
            transformation_note=(
                "Gamma combined EIA official energy fundamentals, optional FRED price proxies, and sample futures curves into one normalized workspace."
            ),
        )
        return CommodityProviderSnapshot(
            coverage=coverage,
            instruments=reference.instruments,
            price_histories=list(price_histories.values()),
            curve_snapshots=reference.curve_snapshots,
            inventory_series=list(inventories.values()),
            events=reference.events,
            warnings=_dedupe(
                [
                    *warnings,
                    "Futures curves are still sample-derived in this provider slice; add IBKR/Databento-style futures-chain coverage for live curves.",
                    "Official EIA data can be delayed by release cadence and revision timing.",
                ]
            ),
            source_provider="eia",
            retrieved_at=latest_source,
            origin="eia_commodities.snapshot",
            transformation_note=(
                "Selected official energy fundamentals replace sample inventory series; unsupported fields remain explicit sample fallbacks."
            ),
        )

    def _fetch_eia_inventory_series(
        self,
        config: EiaSeriesConfig,
        *,
        force_refresh: bool = False,
    ) -> CommodityInventorySeries:
        payload, retrieved_at = self._get_eia_payload(config.series_id, force_refresh=force_refresh)
        rows = _extract_eia_rows(payload)
        points: list[CommodityInventoryPoint] = []
        previous_value: float | None = None
        for row in rows:
            timestamp = _parse_period(row.get("period") or row.get("date"))
            value = _float_value(row.get("value"))
            if timestamp is None or value is None:
                continue
            normalized_value = value / 1000.0 if "bbl" in config.unit.lower() and abs(value) > 10_000 else value
            change = normalized_value - previous_value if previous_value is not None else None
            points.append(
                CommodityInventoryPoint(
                    series_id=_series_slug(config.label),
                    timestamp=timestamp,
                    value=round(normalized_value, 4),
                    change=round(change, 4) if change is not None else None,
                    source_provider="eia",
                    retrieved_at=retrieved_at,
                    origin=f"eia.seriesid:{config.series_id}",
                    transformation_note=(
                        "Gamma normalized an EIA APIv2 seriesid response into a commodity inventory/fundamental point."
                    ),
                )
            )
            previous_value = normalized_value
        points.sort(key=lambda point: point.timestamp)
        metadata = CommodityInventorySeriesMetadata(
            series_id=_series_slug(config.label),
            instrument_id=config.instrument_id,
            label=config.label,
            category=config.category,
            unit=config.unit,
            frequency=config.frequency,
            provider_series_id=config.series_id,
            source_provider="eia",
            retrieved_at=retrieved_at,
            origin=f"eia.seriesid:{config.series_id}",
            transformation_note="Gamma maps selected EIA energy series into normalized commodities fundamentals.",
        )
        return CommodityInventorySeries(
            metadata=metadata,
            points=points,
            source_provider="eia",
            retrieved_at=retrieved_at,
            origin=f"eia.seriesid:{config.series_id}",
            transformation_note="Latest value, change, and seasonal context are computed by the Commodities service.",
        )

    def _get_eia_payload(self, series_id: str, *, force_refresh: bool) -> tuple[Any, datetime]:
        cache_key = ""
        max_age = timedelta(seconds=self.cache_seconds) if self.cache_seconds > 0 else None
        if self.cache is not None:
            cache_key = self.cache.make_key("commodities", "eia", series_id)
            if not force_refresh:
                cached = self.cache.get_json(cache_key, max_age=max_age)
                if isinstance(cached, dict) and "payload" in cached and "retrieved_at" in cached:
                    cached_at = _parse_datetime(cached.get("retrieved_at")) or now_utc()
                    return cached.get("payload"), cached_at

        payload = self.fetch_json(
            self.SERIES_ID_URL.format(series_id=series_id),
            {
                "api_key": self.api_key,
                "sort[0][column]": "period",
                "sort[0][direction]": "asc",
                "length": 260,
            },
        )
        retrieved_at = now_utc().replace(microsecond=0)
        if self.cache is not None and cache_key:
            self.cache.set_json(cache_key, {"retrieved_at": retrieved_at.isoformat(), "payload": payload})
        return payload, retrieved_at

    def _fetch_fred_price_history(
        self,
        config: FredPriceConfig,
        *,
        force_refresh: bool = False,
    ) -> CommodityPriceHistory:
        if self.fred_client is None:
            return CommodityPriceHistory(
                instrument_id=config.instrument_id,
                label=config.label,
                unit=config.unit,
                points=[],
            )
        end = now_utc().date()
        start = end - timedelta(days=365)
        observations, retrieved_at = self.fred_client.get_series_observations(
            config.series_id,
            observation_start=start,
            observation_end=end,
            ttl=timedelta(seconds=self.cache_seconds) if self.cache_seconds > 0 else None,
            force_refresh=force_refresh,
        )
        points = [
            CommodityPricePoint(
                instrument_id=config.instrument_id,
                timestamp=observation.timestamp,
                value=observation.value,
                unit=config.unit,
                source_provider="fred",
                retrieved_at=retrieved_at,
                origin=f"fred.series.observations:{config.series_id}",
                transformation_note=(
                    "FRED series is used as a spot/proxy price history; futures curve analytics remain separate."
                ),
            )
            for observation in observations
        ]
        return CommodityPriceHistory(
            instrument_id=config.instrument_id,
            label=config.label,
            unit=config.unit,
            points=points,
            source_provider="fred",
            retrieved_at=retrieved_at,
            origin=f"fred.series.observations:{config.series_id}",
            transformation_note="FRED price proxy mapped into the normalized commodity price-history model.",
        )


def _sample_instruments(retrieved_at: datetime) -> list[CommodityInstrument]:
    rows = [
        ("wti", "CL", "WTI Crude Oil", "energy", "crude", "USD/bbl", "NYMEX", "CL"),
        ("brent", "BZ", "Brent Crude Oil", "energy", "crude", "USD/bbl", "ICE", "BZ"),
        ("henry_hub", "NG", "Henry Hub Natural Gas", "energy", "gas", "USD/MMBtu", "NYMEX", "NG"),
        ("gasoline", "RB", "RBOB Gasoline", "energy", "products", "USD/gal", "NYMEX", "RB"),
        ("heating_oil", "HO", "Heating Oil / Diesel", "energy", "products", "USD/gal", "NYMEX", "HO"),
        ("gold", "GC", "Gold", "metals", "precious", "USD/oz", "COMEX", "GC"),
        ("silver", "SI", "Silver", "metals", "precious", "USD/oz", "COMEX", "SI"),
        ("copper", "HG", "Copper", "metals", "industrial", "USD/lb", "COMEX", "HG"),
    ]
    return [
        CommodityInstrument(
            instrument_id=instrument_id,
            symbol=symbol,
            name=name,
            family=family,
            subgroup=subgroup,
            quote_unit=unit,
            exchange=exchange,
            front_symbol=front_symbol,
            provider_symbols={"sample": symbol, "ibkr": front_symbol, "fred": _fred_symbol_for(instrument_id)},
            aliases=[name.lower(), symbol.lower()],
            description=f"{name} research instrument for read-only commodity analysis.",
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_commodities.instruments",
            transformation_note="Sample commodity universe normalized into Gamma instrument metadata.",
        )
        for instrument_id, symbol, name, family, subgroup, unit, exchange, front_symbol in rows
    ]


def _sample_price_histories(
    instruments: list[CommodityInstrument],
    retrieved_at: datetime,
) -> list[CommodityPriceHistory]:
    specs = {
        "wti": (78.4, 4.2, -0.018),
        "brent": (82.1, 3.8, -0.015),
        "henry_hub": (3.2, 0.35, 0.002),
        "gasoline": (2.38, 0.11, -0.0008),
        "heating_oil": (2.62, 0.12, -0.0005),
        "gold": (2385.0, 46.0, 0.42),
        "silver": (31.4, 1.1, 0.012),
        "copper": (4.58, 0.17, 0.0015),
    }
    histories: list[CommodityPriceHistory] = []
    for instrument in instruments:
        base, amplitude, drift = specs[instrument.instrument_id]
        points: list[CommodityPricePoint] = []
        start = retrieved_at - timedelta(days=119)
        for index in range(120):
            timestamp = (start + timedelta(days=index)).replace(hour=0, minute=0, second=0, microsecond=0)
            cycle = math.sin(index / 9.0) * amplitude + math.cos(index / 17.0) * amplitude * 0.35
            value = max(0.01, base + cycle + drift * index)
            points.append(
                CommodityPricePoint(
                    instrument_id=instrument.instrument_id,
                    timestamp=timestamp,
                    value=round(value, 4),
                    unit=instrument.quote_unit,
                    source_provider="sample_data",
                    retrieved_at=retrieved_at,
                    origin="sample_commodities.price_history",
                    transformation_note="Synthetic offline price path for commodities workspace development.",
                )
            )
        histories.append(
            CommodityPriceHistory(
                instrument_id=instrument.instrument_id,
                label=f"{instrument.name} sample price",
                unit=instrument.quote_unit,
                points=points,
                source_provider="sample_data",
                retrieved_at=retrieved_at,
                origin="sample_commodities.price_history",
                transformation_note="Synthetic offline price history; not a market quotation.",
            )
        )
    return histories


def _sample_curves(
    instruments: list[CommodityInstrument],
    retrieved_at: datetime,
) -> list[CommodityCurveSnapshot]:
    levels = {
        "wti": [79.2, 78.45, 77.95, 77.35, 76.9, 76.25],
        "brent": [83.0, 82.35, 81.9, 81.45, 81.0, 80.55],
        "henry_hub": [3.05, 3.16, 3.32, 3.54, 3.73, 3.86],
        "gasoline": [2.42, 2.40, 2.37, 2.34, 2.31, 2.29],
        "heating_oil": [2.68, 2.66, 2.64, 2.62, 2.59, 2.57],
        "gold": [2392.0, 2397.0, 2404.0, 2412.0, 2420.0, 2429.0],
        "silver": [31.55, 31.62, 31.71, 31.82, 31.95, 32.08],
        "copper": [4.61, 4.58, 4.55, 4.52, 4.50, 4.47],
    }
    curves: list[CommodityCurveSnapshot] = []
    for instrument in instruments:
        nodes: list[CommodityCurveNode] = []
        for index, price in enumerate(levels[instrument.instrument_id]):
            contract = _contract_for(instrument, retrieved_at, index)
            previous = price - (0.08 if index == 0 else 0.03) + math.sin(index) * 0.02
            nodes.append(
                CommodityCurveNode(
                    contract=contract,
                    price=round(price, 4),
                    previous_price=round(previous, 4),
                    change=round(price - previous, 4),
                    days_to_expiry=30 * (index + 1),
                    source_provider="sample_data",
                    retrieved_at=retrieved_at,
                    origin="sample_commodities.curve_nodes",
                    transformation_note="Synthetic futures curve node for offline commodities research.",
                )
            )
        curves.append(
            CommodityCurveSnapshot(
                instrument_id=instrument.instrument_id,
                as_of=retrieved_at,
                nodes=nodes,
                source_provider="sample_data",
                retrieved_at=retrieved_at,
                origin="sample_commodities.curve_snapshot",
                transformation_note=(
                    "Synthetic curve snapshot; Gamma service computes term-structure analytics from these nodes."
                ),
            )
        )
    return curves


def _sample_inventory_series(retrieved_at: datetime) -> list[CommodityInventorySeries]:
    specs = [
        ("us-commercial-crude-stocks", "wti", "US Commercial Crude Stocks", "inventories", "million bbl", 432.0, 18.0, 1.9),
        ("us-motor-gasoline-stocks", "gasoline", "US Motor Gasoline Stocks", "inventories", "million bbl", 226.0, 9.0, -0.5),
        ("us-distillate-stocks", "heating_oil", "US Distillate Fuel Oil Stocks", "inventories", "million bbl", 118.0, 7.0, 0.4),
        ("lower-48-working-gas-storage", "henry_hub", "Lower 48 Working Gas Storage", "storage", "bcf", 2430.0, 620.0, 22.0),
        ("us-crude-production", "wti", "US Crude Oil Production", "production", "million b/d", 13.1, 0.35, 0.02),
        ("refinery-utilization", "gasoline", "US Refinery Utilization", "refinery", "pct", 88.4, 5.2, 0.15),
    ]
    series_rows: list[CommodityInventorySeries] = []
    for series_id, instrument_id, label, category, unit, base, amplitude, drift in specs:
        points: list[CommodityInventoryPoint] = []
        start = retrieved_at - timedelta(weeks=78)
        previous: float | None = None
        for index in range(79):
            timestamp = (start + timedelta(weeks=index)).replace(hour=0, minute=0, second=0, microsecond=0)
            seasonal = math.sin((index % 52) / 52.0 * math.tau) * amplitude
            value = base + seasonal + drift * (index - 39)
            change = value - previous if previous is not None else None
            points.append(
                CommodityInventoryPoint(
                    series_id=series_id,
                    timestamp=timestamp,
                    value=round(value, 4),
                    change=round(change, 4) if change is not None else None,
                    source_provider="sample_data",
                    retrieved_at=retrieved_at,
                    origin="sample_commodities.inventory_points",
                    transformation_note="Synthetic weekly fundamental series for offline commodities development.",
                )
            )
            previous = value
        metadata = CommodityInventorySeriesMetadata(
            series_id=series_id,
            instrument_id=instrument_id,
            label=label,
            category=category,
            unit=unit,
            frequency="weekly",
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_commodities.inventory_metadata",
            transformation_note="Sample energy fundamental metadata for Workstream 8 development.",
        )
        series_rows.append(
            CommodityInventorySeries(
                metadata=metadata,
                points=points,
                source_provider="sample_data",
                retrieved_at=retrieved_at,
                origin="sample_commodities.inventory_series",
                transformation_note="Gamma service computes latest change and seasonal context from this sample series.",
            )
        )
    return series_rows


def _sample_events(retrieved_at: datetime) -> list[CommodityEventRecord]:
    next_wednesday = retrieved_at + timedelta(days=(2 - retrieved_at.weekday()) % 7 or 7)
    next_thursday = retrieved_at + timedelta(days=(3 - retrieved_at.weekday()) % 7 or 7)
    return [
        CommodityEventRecord(
            event_id=f"eia-wpsr:{next_wednesday.date().isoformat()}",
            title="EIA Weekly Petroleum Status Report",
            category="official_release",
            scheduled_at=next_wednesday.replace(hour=14, minute=30, second=0, microsecond=0),
            relative_label="Weekly",
            importance="high",
            linked_instrument_ids=["wti", "gasoline", "heating_oil"],
            summary="Official weekly US petroleum inventory, supply, and product-demand context.",
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_commodities.events",
            transformation_note="Sample event calendar row based on regular EIA release cadence.",
        ),
        CommodityEventRecord(
            event_id=f"eia-ngs:{next_thursday.date().isoformat()}",
            title="EIA Weekly Natural Gas Storage",
            category="official_release",
            scheduled_at=next_thursday.replace(hour=14, minute=30, second=0, microsecond=0),
            relative_label="Weekly",
            importance="high",
            linked_instrument_ids=["henry_hub"],
            summary="Official working gas storage update for US natural gas context.",
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_commodities.events",
            transformation_note="Sample event calendar row based on regular EIA release cadence.",
        ),
        CommodityEventRecord(
            event_id="sample-red-sea-energy-watch",
            title="Red Sea / Suez Energy Route Watch",
            category="cross_domain",
            scheduled_at=None,
            relative_label="Watchlist",
            importance="medium",
            linked_instrument_ids=["wti", "brent", "heating_oil"],
            summary="Cross-domain watch item linking oil/products to maritime chokepoint research.",
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_commodities.events",
            transformation_note="Manually curated sample event for Commodities to Maritime handoff development.",
        ),
    ]


def _contract_for(
    instrument: CommodityInstrument,
    retrieved_at: datetime,
    index: int,
) -> CommodityFuturesContract:
    month_index = (retrieved_at.month - 1 + index + 1) % 12
    year = retrieved_at.year + ((retrieved_at.month - 1 + index + 1) // 12)
    code = MONTH_CODES[month_index]
    symbol = f"{instrument.front_symbol or instrument.symbol}{code}{str(year)[-2:]}"
    month_label = datetime(year, month_index + 1, 1).strftime("%b %Y")
    return CommodityFuturesContract(
        contract_id=f"{instrument.instrument_id}-{year}-{month_index + 1:02d}",
        instrument_id=instrument.instrument_id,
        symbol=symbol,
        contract_month=month_label,
        expiry_date=datetime(year, month_index + 1, min(20, 28)),
        is_front_month=index == 0,
        source_provider="sample_data",
        retrieved_at=retrieved_at,
        origin="sample_commodities.contracts",
        transformation_note="Sample futures contract metadata uses standard month codes for UI and analytics development.",
    )


def _with_provider_warning(
    reference: CommodityProviderSnapshot,
    warning: str,
    *,
    extra_warnings: list[str] | None = None,
) -> CommodityProviderSnapshot:
    warnings = _dedupe([warning, *(extra_warnings or []), *reference.warnings])
    coverage = replace(
        reference.coverage,
        caveats=_dedupe([warning, *reference.coverage.caveats]),
        credential_env_vars=_dedupe([*reference.coverage.credential_env_vars, "EIA_API_KEY"]),
    )
    return replace(reference, coverage=coverage, warnings=warnings)


def _extract_eia_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    response = payload.get("response")
    if isinstance(response, dict):
        data = response.get("data")
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
    data = payload.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _parse_period(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidates = [text, f"{text}-01" if len(text) == 7 else text]
    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    for fmt in ("%Y%m%d", "%Y%m", "%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone().replace(tzinfo=None)
    return parsed


def _float_value(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _series_slug(value: str) -> str:
    text = str(value or "").strip().lower()
    return "-".join(part for part in "".join(char if char.isalnum() else "-" for char in text).split("-") if part)


def _fred_symbol_for(instrument_id: str) -> str:
    for config in FRED_PRICE_SERIES:
        if config.instrument_id == instrument_id:
            return config.series_id
    return ""


def _max_datetime(*values: datetime | None) -> datetime | None:
    clean = [value for value in values if value is not None]
    return max(clean) if clean else None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
