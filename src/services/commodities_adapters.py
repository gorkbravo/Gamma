from __future__ import annotations

import json
import math
import os
from types import SimpleNamespace
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Callable, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
from ib_insync import Contract

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
from src.services.ibkr_client import IBKRClient
from src.services.market_data import MarketDataService, QuoteSnapshot
from src.utils.time import now_utc


JsonFetcher = Callable[[str, dict[str, Any] | None], Any]


class CommoditiesDataProvider(Protocol):
    provider_id: str
    provider_label: str

    def get_snapshot(
        self,
        *,
        force_refresh: bool = False,
        selected_instrument_id: str | None = None,
    ) -> CommodityProviderSnapshot:
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


@dataclass(frozen=True)
class EiaPriceConfig:
    series_id: str
    instrument_id: str
    label: str
    unit: str


@dataclass(frozen=True)
class CommodityInstrumentConfig:
    instrument_id: str
    symbol: str
    name: str
    family: str
    subgroup: str
    quote_unit: str
    exchange: str | None = None
    front_symbol: str | None = None


@dataclass(frozen=True)
class IbkrFutureRootConfig:
    instrument_id: str
    symbol: str
    exchange: str
    currency: str
    quote_unit: str
    label: str
    trading_class: str | None = None
    multiplier: str | None = None


def _env_series_id(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip()


COMMODITY_INSTRUMENTS: tuple[CommodityInstrumentConfig, ...] = (
    CommodityInstrumentConfig("wti", "CL", "WTI Crude Oil", "energy", "crude", "USD/bbl", "NYMEX", "CL"),
    CommodityInstrumentConfig("brent", "BZ", "Brent Crude Oil", "energy", "crude", "USD/bbl", "ICE", "BZ"),
    CommodityInstrumentConfig("henry_hub", "NG", "Henry Hub Natural Gas", "energy", "gas", "USD/MMBtu", "NYMEX", "NG"),
    CommodityInstrumentConfig("gasoline", "RB", "RBOB Gasoline", "energy", "products", "USD/gal", "NYMEX", "RB"),
    CommodityInstrumentConfig("heating_oil", "HO", "Heating Oil / Diesel", "energy", "products", "USD/gal", "NYMEX", "HO"),
    CommodityInstrumentConfig("gold", "GC", "Gold", "metals", "precious", "USD/oz", "COMEX", "GC"),
    CommodityInstrumentConfig("silver", "SI", "Silver", "metals", "precious", "USD/oz", "COMEX", "SI"),
    CommodityInstrumentConfig("platinum", "PL", "Platinum", "metals", "precious", "USD/oz", "NYMEX", "PL"),
    CommodityInstrumentConfig("copper", "HG", "Copper", "metals", "industrial", "USD/lb", "COMEX", "HG"),
    CommodityInstrumentConfig("aluminum", "ALI", "Aluminum", "metals", "industrial", "USD/metric ton", "LME/COMEX", "ALI"),
    CommodityInstrumentConfig("zinc", "ZS", "Zinc", "metals", "industrial", "USD/metric ton", "LME", "ZS"),
    CommodityInstrumentConfig("nickel", "NI", "Nickel", "metals", "industrial", "USD/metric ton", "LME", None),
    CommodityInstrumentConfig("lead", "PB", "Lead", "metals", "industrial", "USD/metric ton", "LME", None),
    CommodityInstrumentConfig("tin", "SN", "Tin", "metals", "industrial", "USD/metric ton", "LME", None),
    CommodityInstrumentConfig("iron_ore", "IO", "Iron Ore", "metals", "bulk", "USD/metric ton", "CFR China", None),
    CommodityInstrumentConfig("uranium", "UX", "Uranium", "metals", "nuclear_fuel", "USD/lb", "Spot", None),
)


EIA_INVENTORY_SERIES: tuple[EiaSeriesConfig, ...] = (
    EiaSeriesConfig(
        series_id=_env_series_id("EIA_CRUDE_STOCKS_SERIES_ID", "PET.WCESTUS1.W"),
        instrument_id="wti",
        label="US Commercial Crude Stocks",
        category="inventories",
        unit="million bbl",
    ),
    EiaSeriesConfig(
        series_id=_env_series_id("EIA_GASOLINE_STOCKS_SERIES_ID", "PET.WGTSTUS1.W"),
        instrument_id="gasoline",
        label="US Motor Gasoline Stocks",
        category="inventories",
        unit="million bbl",
    ),
    EiaSeriesConfig(
        series_id=_env_series_id("EIA_DISTILLATE_STOCKS_SERIES_ID", "PET.WDISTUS1.W"),
        instrument_id="heating_oil",
        label="US Distillate Fuel Oil Stocks",
        category="inventories",
        unit="million bbl",
    ),
    EiaSeriesConfig(
        series_id=_env_series_id("EIA_NATGAS_STORAGE_SERIES_ID", "NG.NW2_EPG0_SWO_R48_BCF.W"),
        instrument_id="henry_hub",
        label="Lower 48 Working Gas Storage",
        category="storage",
        unit="bcf",
    ),
    EiaSeriesConfig(
        series_id=_env_series_id("EIA_CRUDE_PRODUCTION_SERIES_ID", "PET.WCRFPUS2.W"),
        instrument_id="wti",
        label="US Crude Oil Production",
        category="production",
        unit="million b/d",
    ),
    EiaSeriesConfig(
        series_id=_env_series_id("EIA_CRUDE_IMPORTS_SERIES_ID", "PET.WCRIMUS2.W"),
        instrument_id="wti",
        label="US Crude Oil Imports",
        category="imports",
        unit="million b/d",
    ),
    EiaSeriesConfig(
        series_id=_env_series_id("EIA_CRUDE_EXPORTS_SERIES_ID", "PET.WCREXUS2.W"),
        instrument_id="wti",
        label="US Crude Oil Exports",
        category="exports",
        unit="million b/d",
    ),
    EiaSeriesConfig(
        series_id=_env_series_id("EIA_REFINERY_INPUTS_SERIES_ID", "PET.WCRRIUS2.W"),
        instrument_id="wti",
        label="US Refinery Crude Inputs",
        category="refinery",
        unit="million b/d",
    ),
    EiaSeriesConfig(
        series_id=_env_series_id("EIA_REFINERY_UTILIZATION_SERIES_ID", "PET.WPULEUS3.W"),
        instrument_id="gasoline",
        label="US Refinery Utilization",
        category="refinery",
        unit="pct",
    ),
    EiaSeriesConfig(
        series_id=_env_series_id("EIA_GASOLINE_PRODUCT_SUPPLIED_SERIES_ID", "PET.WGFUPUS2.W"),
        instrument_id="gasoline",
        label="US Gasoline Product Supplied",
        category="demand",
        unit="million b/d",
    ),
    EiaSeriesConfig(
        series_id=_env_series_id("EIA_DISTILLATE_PRODUCT_SUPPLIED_SERIES_ID", "PET.WDIUPUS2.W"),
        instrument_id="heating_oil",
        label="US Distillate Product Supplied",
        category="demand",
        unit="million b/d",
    ),
)

FRED_PRICE_SERIES: tuple[FredPriceConfig, ...] = (
    FredPriceConfig("DCOILWTICO", "wti", "WTI Spot Proxy", "USD/bbl"),
    FredPriceConfig("DCOILBRENTEU", "brent", "Brent Spot Proxy", "USD/bbl"),
    FredPriceConfig("DHHNGSP", "henry_hub", "Henry Hub Spot Proxy", "USD/MMBtu"),
    FredPriceConfig("GOLDAMGBD228NLBM", "gold", "Gold London AM Fix", "USD/oz"),
    FredPriceConfig("SLVPRUSD", "silver", "Silver Price Proxy", "USD/oz"),
    FredPriceConfig("PPLTUSDM", "platinum", "Platinum Price Proxy", "USD/oz"),
    FredPriceConfig("PCOPPUSDM", "copper", "Copper Price Proxy", "USD/metric ton"),
    FredPriceConfig("PALUMUSDM", "aluminum", "Aluminum Price Proxy", "USD/metric ton"),
    FredPriceConfig("PZINCUSDM", "zinc", "Zinc Price Proxy", "USD/metric ton"),
    FredPriceConfig("PNICKUSDM", "nickel", "Nickel Price Proxy", "USD/metric ton"),
    FredPriceConfig("PLEADUSDM", "lead", "Lead Price Proxy", "USD/metric ton"),
    FredPriceConfig("PTINUSDM", "tin", "Tin Price Proxy", "USD/metric ton"),
    FredPriceConfig("PIORECRUSDM", "iron_ore", "Iron Ore Price Proxy", "USD/metric ton"),
    FredPriceConfig("PURANUSDM", "uranium", "Uranium Price Proxy", "USD/lb"),
)

EIA_PRICE_SERIES: tuple[EiaPriceConfig, ...] = (
    EiaPriceConfig(
        _env_series_id("EIA_RBOB_GASOLINE_PRICE_SERIES_ID", "PET.EER_EPMRU_PF4_Y35NY_DPG.D"),
        "gasoline",
        "RBOB Gasoline New York Harbor Spot",
        "USD/gal",
    ),
    EiaPriceConfig(
        _env_series_id("EIA_HEATING_OIL_PRICE_SERIES_ID", "PET.EER_EPD2F_PF4_Y35NY_DPG.D"),
        "heating_oil",
        "No. 2 Heating Oil New York Harbor Spot",
        "USD/gal",
    ),
)

IBKR_FUTURES_ROOTS: tuple[IbkrFutureRootConfig, ...] = (
    IbkrFutureRootConfig("wti", "CL", "NYMEX", "USD", "USD/bbl", "WTI Crude Oil", trading_class="CL"),
    IbkrFutureRootConfig("brent", "BZ", "NYMEX", "USD", "USD/bbl", "Brent Crude Oil", trading_class="BZ"),
    IbkrFutureRootConfig("henry_hub", "NG", "NYMEX", "USD", "USD/MMBtu", "Henry Hub Natural Gas", trading_class="NG"),
    IbkrFutureRootConfig("gasoline", "RB", "NYMEX", "USD", "USD/gal", "RBOB Gasoline", trading_class="RB"),
    IbkrFutureRootConfig("heating_oil", "HO", "NYMEX", "USD", "USD/gal", "Heating Oil / Diesel", trading_class="HO"),
    IbkrFutureRootConfig("gold", "GC", "COMEX", "USD", "USD/oz", "Gold", trading_class="GC"),
    IbkrFutureRootConfig("silver", "SI", "COMEX", "USD", "USD/oz", "Silver", trading_class="SI"),
    IbkrFutureRootConfig("copper", "HG", "COMEX", "USD", "USD/lb", "Copper", trading_class="HG"),
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

    def get_snapshot(
        self,
        *,
        force_refresh: bool = False,
        selected_instrument_id: str | None = None,
    ) -> CommodityProviderSnapshot:
        del force_refresh
        del selected_instrument_id
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

    def get_snapshot(
        self,
        *,
        force_refresh: bool = False,
        selected_instrument_id: str | None = None,
    ) -> CommodityProviderSnapshot:
        reference = self.reference_provider.get_snapshot(force_refresh=False, selected_instrument_id=selected_instrument_id)
        reference_is_sample = reference.coverage.coverage_status in {"sample", "mock"} or reference.source_provider == "sample_data"
        if not self.api_key:
            return _with_provider_warning(
                reference,
                "COMMODITIES_PROVIDER=eia but EIA_API_KEY is not configured; "
                + (
                    "using sample commodities fallback."
                    if reference_is_sample
                    else "no commodities fallback data is available in live mode."
                ),
            )

        retrieved_at = now_utc().replace(microsecond=0)
        warnings: list[str] = []
        inventories = {series.metadata.series_id: series for series in reference.inventory_series}
        official_count = 0
        for config in EIA_INVENTORY_SERIES:
            if not config.series_id:
                continue
            try:
                series = self._fetch_eia_inventory_series(config, force_refresh=force_refresh)
            except Exception as exc:
                warnings.append(f"EIA series {config.series_id} failed: {exc.__class__.__name__}.")
                continue
            if series.points:
                inventories[series.metadata.series_id] = series
                official_count += 1

        price_histories = {history.instrument_id: history for history in reference.price_histories}
        eia_price_count = 0
        for config in EIA_PRICE_SERIES:
            if not config.series_id:
                continue
            try:
                history = self._fetch_eia_price_history(config, force_refresh=force_refresh)
            except Exception as exc:
                warnings.append(f"EIA price series {config.series_id} failed: {exc.__class__.__name__}.")
                continue
            if history.points:
                price_histories[history.instrument_id] = history
                eia_price_count += 1

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

        if official_count == 0 and eia_price_count == 0 and fred_count == 0:
            return _with_provider_warning(
                reference,
                "EIA/FRED enrichment returned no usable commodity series; "
                + (
                    "using sample commodities fallback."
                    if reference_is_sample
                    else "no commodities fallback data is available in live mode."
                ),
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
                "EIA enrichment covers configured official US energy inventories, storage, production, trade, refinery, and demand fundamentals where available.",
                "EIA spot price enrichment covers selected US energy products for lightweight SITREP context without opening additional IBKR market-data lines.",
                (
                    "FRED price histories are spot or proxy series where configured; futures curves remain sample unless a futures provider is added."
                    if reference_is_sample
                    else "FRED price histories are spot or proxy series where configured; futures curves remain unavailable unless a futures provider is added."
                ),
                "Gamma keeps provider credentials server-side and exposes read-only normalized research data.",
                *warnings,
            ],
            credential_env_vars=["EIA_API_KEY", "FRED_API_KEY"],
            supports_prices=eia_price_count > 0 or fred_count > 0,
            supports_curves=bool(reference.curve_snapshots),
            supports_inventories=official_count > 0,
            supports_events=bool(reference.events),
            source_provider="eia",
            retrieved_at=latest_source,
            origin="eia_commodities.coverage",
            transformation_note=(
                "Gamma combined EIA official energy fundamentals, optional FRED price proxies, "
                + (
                    "and sample futures curves into one normalized workspace."
                    if reference_is_sample
                    else "and live-mode reference metadata into one normalized workspace."
                )
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
                    (
                        "Selected EIA daily product spot prices are used for gasoline/heating-oil SITREP context."
                        if eia_price_count
                        else ""
                    ),
                    (
                        "Futures curves are still sample-derived in this provider slice; add IBKR/Databento-style futures-chain coverage for live curves."
                        if reference_is_sample
                        else "Futures curves are unavailable in this provider slice; add IBKR/Databento-style futures-chain coverage for live curves."
                    ),
                    "Official EIA data can be delayed by release cadence and revision timing.",
                ]
            ),
            source_provider="eia",
            retrieved_at=latest_source,
            origin="eia_commodities.snapshot",
            transformation_note=(
                "Selected official energy fundamentals replace configured reference inventory series; "
                + (
                    "unsupported fields remain explicit sample fallbacks."
                    if reference_is_sample
                    else "unsupported fields remain unavailable in live mode."
                )
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
            normalized_value = _normalize_eia_value(value, config.unit)
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

    def _fetch_eia_price_history(
        self,
        config: EiaPriceConfig,
        *,
        force_refresh: bool = False,
    ) -> CommodityPriceHistory:
        payload, retrieved_at = self._get_eia_payload(config.series_id, force_refresh=force_refresh)
        rows = _extract_eia_rows(payload)
        points: list[CommodityPricePoint] = []
        for row in rows:
            timestamp = _parse_period(row.get("period") or row.get("date"))
            value = _float_value(row.get("value"))
            if timestamp is None or value is None:
                continue
            points.append(
                CommodityPricePoint(
                    instrument_id=config.instrument_id,
                    timestamp=timestamp,
                    value=round(value, 6),
                    unit=config.unit,
                    source_provider="eia",
                    retrieved_at=retrieved_at,
                    origin=f"eia.seriesid:{config.series_id}",
                    transformation_note=(
                        "EIA daily spot price series mapped into Gamma's normalized commodity price-history model."
                    ),
                )
            )
        points.sort(key=lambda point: point.timestamp)
        return CommodityPriceHistory(
            instrument_id=config.instrument_id,
            label=config.label,
            unit=config.unit,
            points=points,
            source_provider="eia",
            retrieved_at=retrieved_at,
            origin=f"eia.seriesid:{config.series_id}",
            transformation_note=(
                "EIA product spot prices provide lightweight SITREP context; IBKR futures curves remain separate."
            ),
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


class IbkrCommoditiesDataProvider:
    provider_id = "ibkr"
    provider_label = "IBKR Futures Curves"

    def __init__(
        self,
        *,
        client: IBKRClient,
        market_data: MarketDataService,
        cache: CacheService | None = None,
        reference_provider: CommoditiesDataProvider | None = None,
        root_configs: tuple[IbkrFutureRootConfig, ...] | None = None,
        enabled_instrument_ids: list[str] | tuple[str, ...] | None = None,
        startup_instrument_ids: list[str] | tuple[str, ...] | None = None,
        on_demand_enabled: bool = True,
        selected_cache_seconds: int = 300,
        contract_cache_seconds: int = 21_600,
        contract_depth: int = 6,
        history_days: int = 120,
        quote_timeout_seconds: float = 4.0,
        contract_details_timeout_seconds: float = 12.0,
        quote_batch_size: int = 8,
    ) -> None:
        self.client = client
        self.market_data = market_data
        self.cache = cache
        self.reference_provider = reference_provider or SampleCommoditiesDataProvider()
        self.root_configs = {
            config.instrument_id: config for config in (root_configs or _ibkr_root_configs_from_env())
        }
        enabled = enabled_instrument_ids
        if enabled is None:
            enabled = _parse_csv_env(
                "IBKR_COMMODITIES_ENABLED",
                ",".join(config.instrument_id for config in self.root_configs.values()),
            )
        self.enabled_instrument_ids = tuple(_dedupe([_slug(item) for item in enabled]))
        startup = startup_instrument_ids
        if startup is None:
            startup = _parse_csv_env("IBKR_COMMODITIES_STARTUP_ENABLED", "wti")
        allowed = set(self.enabled_instrument_ids)
        self.startup_instrument_ids = tuple(
            item for item in _dedupe([_slug(row) for row in startup]) if item in allowed
        ) or tuple(self.enabled_instrument_ids[:1])
        self.on_demand_enabled = bool(on_demand_enabled)
        self.selected_cache_seconds = max(0, int(selected_cache_seconds or 0))
        self.contract_cache_seconds = max(0, int(contract_cache_seconds or 0))
        self.contract_depth = max(1, int(contract_depth or 1))
        self.history_days = max(0, int(history_days or 0))
        self.quote_timeout_seconds = max(0.5, float(quote_timeout_seconds or 4.0))
        self.contract_details_timeout_seconds = max(1.0, float(contract_details_timeout_seconds or 12.0))
        self.quote_batch_size = max(1, int(quote_batch_size or 1))

    def get_snapshot(
        self,
        *,
        force_refresh: bool = False,
        selected_instrument_id: str | None = None,
    ) -> CommodityProviderSnapshot:
        reference = self.reference_provider.get_snapshot(
            force_refresh=force_refresh,
            selected_instrument_id=selected_instrument_id,
        )
        if getattr(self.client, "mock", False):
            return _with_provider_warning(
                reference,
                "COMMODITIES_PROVIDER=ibkr but Gamma is running in mock IBKR mode; using commodities fallback data.",
                credential_env_vars=_ibkr_credential_env_vars(),
            )
        if not self._is_connected():
            return _with_provider_warning(
                reference,
                "COMMODITIES_PROVIDER=ibkr but TWS/IBKR is not connected; using commodities fallback data.",
                credential_env_vars=_ibkr_credential_env_vars(),
            )

        retrieved_at = now_utc().replace(microsecond=0)
        warnings: list[str] = []
        curve_by_id = {curve.instrument_id: curve for curve in reference.curve_snapshots}
        history_by_id = {history.instrument_id: history for history in reference.price_histories}
        ibkr_curve_ids: list[str] = []
        cached_curve_ids: list[str] = []
        delayed_nodes = 0
        priced_nodes = 0
        selected = _slug(selected_instrument_id or "")
        target_ids = self._target_instrument_ids(selected)

        for instrument in reference.instruments:
            if instrument.instrument_id not in self.enabled_instrument_ids:
                continue
            config = self.root_configs.get(instrument.instrument_id)
            if config is None:
                warnings.append(f"No IBKR futures root configured for {instrument.name}; keeping fallback curve.")
                continue
            is_target = instrument.instrument_id in target_ids
            cached_curve = None if force_refresh else self._cached_curve_snapshot(
                instrument.instrument_id,
                retrieved_at,
                max_age_seconds=self.selected_cache_seconds if self.selected_cache_seconds > 0 else None,
            )
            if cached_curve is not None:
                curve_by_id[instrument.instrument_id] = cached_curve
                cached_curve_ids.append(instrument.instrument_id)
                warnings.append(
                    f"Using cached IBKR curve for {config.label} from {cached_curve.as_of.isoformat()}; no fresh TWS request was made."
                )
                continue
            if not is_target:
                fallback_curve = curve_by_id.get(instrument.instrument_id)
                fallback_source = fallback_curve.source_provider if fallback_curve is not None else "fallback"
                warnings.append(
                    f"{config.label} is outside the current IBKR warm/on-demand request set and remains on {fallback_source} fallback data until selected."
                )
                continue

            contracts, detail_warnings = self._discover_contracts(
                config,
                retrieved_at,
                force_refresh=force_refresh,
            )
            warnings.extend(detail_warnings)
            if not contracts:
                warnings.append(
                    f"IBKR returned no active futures contracts for {config.label} ({config.symbol} {config.exchange}); keeping fallback curve."
                )
                continue

            quote_contracts = [contract for contract, _detail in contracts]
            try:
                quotes, quote_warnings = self._fetch_quotes(quote_contracts)
            except Exception as exc:
                warnings.append(f"IBKR quote fetch failed for {config.label}: {exc.__class__.__name__}.")
                continue
            warnings.extend(quote_warnings)
            delayed_nodes += sum(1 for snapshot in quotes.values() if snapshot.delayed)

            curve = self._build_curve(config, contracts, quotes, retrieved_at)
            curve_priced_nodes = sum(1 for node in curve.nodes if node.price is not None)
            priced_nodes += curve_priced_nodes
            if curve_priced_nodes >= 2:
                curve_by_id[config.instrument_id] = curve
                ibkr_curve_ids.append(config.instrument_id)
                self._append_curve_snapshot(curve)
                warnings.append(
                    f"Fresh IBKR curve loaded for {config.label} with {curve_priced_nodes} priced node(s); live/delayed status is shown on curve-node warnings."
                )
            else:
                warnings.append(
                    f"IBKR curve for {config.label} had fewer than two priced nodes; keeping fallback curve."
                )

            if self.history_days > 0 and curve.nodes and contracts:
                history = self._fetch_front_history(config, contracts[0][0], retrieved_at)
                if history.points:
                    history_by_id[config.instrument_id] = history

        if not ibkr_curve_ids and not cached_curve_ids:
            return _with_provider_warning(
                reference,
                "IBKR futures-chain discovery ran but returned no usable priced curves; using commodities fallback data.",
                extra_warnings=warnings,
                credential_env_vars=_ibkr_credential_env_vars(),
            )

        coverage = CommodityCoverageMetadata(
            coverage_status="partial",
            provider_id=self.provider_id,
            provider_label=self.provider_label,
            freshness_label="ibkr_live_or_delayed_snapshot",
            instruments=[instrument.instrument_id for instrument in reference.instruments],
            regions=["Global"],
            as_of=retrieved_at,
            source_timestamp=retrieved_at,
            caveats=_dedupe(
                [
                    "IBKR curves are built by Gamma from individual read-only FUT contract market-data snapshots.",
                    "Quotes may be live, delayed, cached, or unavailable depending on TWS connectivity and market-data entitlements.",
                    "Startup/warm IBKR curves are limited separately from the allowed commodities universe; non-selected roots use cached or fallback data.",
                    "Historical futures-curve context accumulates from Gamma's local daily snapshots; IBKR is not treated as a bulk curve-history warehouse.",
                    "EIA/FRED/sample fallback data may still supply fundamentals, events, or proxy price histories.",
                    *reference.coverage.caveats,
                    *warnings,
                ]
            ),
            credential_env_vars=_dedupe([*reference.coverage.credential_env_vars, *_ibkr_credential_env_vars()]),
            supports_prices=True,
            supports_curves=True,
            supports_inventories=reference.coverage.supports_inventories,
            supports_events=reference.coverage.supports_events,
            source_provider="ibkr",
            retrieved_at=retrieved_at,
            origin="ibkr.commodities.coverage",
            transformation_note=(
                "Gamma discovered IBKR FUT contracts, requested read-only market-data snapshots, and normalized them into commodity curve nodes."
            ),
        )
        return CommodityProviderSnapshot(
            coverage=coverage,
            instruments=_mark_ibkr_instruments(
                reference.instruments,
                set([*ibkr_curve_ids, *cached_curve_ids]),
                retrieved_at,
            ),
            price_histories=list(history_by_id.values()),
            curve_snapshots=list(curve_by_id.values()),
            inventory_series=reference.inventory_series,
            events=reference.events,
            warnings=_dedupe(
                [
                    *reference.warnings,
                    *warnings,
                    f"Fresh IBKR curves loaded for {len(ibkr_curve_ids)} commodity instruments with {priced_nodes} priced nodes.",
                    f"Cached IBKR curves reused for {len(cached_curve_ids)} commodity instruments." if cached_curve_ids else "",
                    f"Delayed quote nodes detected: {delayed_nodes}." if delayed_nodes else "",
                    "Gamma remains read-only; IBKR is used here for futures market data only.",
                    "Front-contract histories use IBKR historical bars when available; calendar-spread history still depends on saved curve snapshots and provider limits.",
                ]
            ),
            source_provider="ibkr",
            retrieved_at=retrieved_at,
            origin="ibkr.commodities.snapshot",
            transformation_note=(
                "IBKR futures curves replace fallback curves where at least two priced contracts are available; other commodities fields retain explicit fallback provenance."
            ),
        )

    def _is_connected(self) -> bool:
        try:
            return bool(self.client.is_connected())
        except Exception:
            return False

    def _target_instrument_ids(self, selected_instrument_id: str | None) -> set[str]:
        if not self.on_demand_enabled:
            return set(self.enabled_instrument_ids)
        targets = {item for item in self.startup_instrument_ids if item in self.enabled_instrument_ids}
        selected = _slug(selected_instrument_id or "")
        if selected and selected in self.enabled_instrument_ids:
            targets.add(selected)
        return targets

    def _run_ib(self, fn, *, timeout: float | None = None):
        run_ib = getattr(self.client, "_run_ib", None)
        if callable(run_ib):
            return run_ib(fn, timeout=timeout)
        runner = getattr(self.client, "ib_runner", None)
        if runner is not None:
            return runner.run(fn, timeout=timeout)
        return fn()

    def _discover_contracts(
        self,
        config: IbkrFutureRootConfig,
        retrieved_at: datetime,
        *,
        force_refresh: bool = False,
    ) -> tuple[list[tuple[Contract, Any]], list[str]]:
        warnings: list[str] = []
        cached = None if force_refresh else self._cached_contracts(config)
        if cached:
            return cached[: self.contract_depth], [
                f"Using cached IBKR contract discovery for {config.label}; no reqContractDetails request was made."
            ]
        seed = Contract(
            symbol=config.symbol,
            secType="FUT",
            exchange=config.exchange,
            currency=config.currency,
        )
        if config.trading_class:
            seed.tradingClass = config.trading_class
        try:
            details = self._run_ib(
                lambda: self.client.ib.reqContractDetails(seed),
                timeout=self.contract_details_timeout_seconds,
            ) or []
        except Exception as exc:
            return [], [f"IBKR contract discovery failed for {config.label}: {exc.__class__.__name__}."]

        rows: list[tuple[Contract, Any, str, datetime | None]] = []
        seen: set[str] = set()
        for detail in details:
            contract = getattr(detail, "contract", detail)
            if str(getattr(contract, "secType", "")).upper() != "FUT":
                continue
            if config.symbol and str(getattr(contract, "symbol", "")).upper() != config.symbol.upper():
                continue
            expiry = _ibkr_contract_expiry(contract, detail)
            month_key = _ibkr_contract_month_key(contract, detail)
            if expiry is not None and expiry.date() < retrieved_at.date():
                continue
            if not month_key:
                continue
            dedupe_key = str(getattr(contract, "conId", "") or month_key)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append((contract, detail, month_key, expiry))

        rows.sort(key=lambda row: (row[2], row[3] or datetime.max))
        selected = [(contract, detail) for contract, detail, _month_key, _expiry in rows[: self.contract_depth]]
        if len(rows) > self.contract_depth:
            warnings.append(
                f"IBKR returned {len(rows)} active {config.label} contracts; Gamma kept the front {self.contract_depth} nodes."
            )
        if selected:
            self._store_contracts(config, selected)
        return selected, warnings

    def _contract_cache_key(self, instrument_id: str) -> str:
        if self.cache is None:
            return ""
        return self.cache.make_key("commodities", "ibkr", "contracts", instrument_id)

    def _cached_contracts(self, config: IbkrFutureRootConfig) -> list[tuple[Contract, Any]]:
        if self.cache is None or self.contract_cache_seconds <= 0:
            return []
        payload = self.cache.get_json(
            self._contract_cache_key(config.instrument_id),
            max_age=timedelta(seconds=self.contract_cache_seconds),
        )
        if not isinstance(payload, dict):
            return []
        rows = payload.get("contracts")
        if not isinstance(rows, list):
            return []
        contracts: list[tuple[Contract, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            contract = Contract(
                conId=int(row.get("conId") or 0),
                symbol=str(row.get("symbol") or config.symbol),
                secType="FUT",
                exchange=str(row.get("exchange") or config.exchange),
                currency=str(row.get("currency") or config.currency),
                lastTradeDateOrContractMonth=str(row.get("lastTradeDateOrContractMonth") or ""),
                localSymbol=str(row.get("localSymbol") or ""),
                tradingClass=str(row.get("tradingClass") or config.trading_class or ""),
            )
            detail = SimpleNamespace(realExpirationDate=row.get("realExpirationDate"), contract=contract)
            contracts.append((contract, detail))
        return contracts

    def _store_contracts(self, config: IbkrFutureRootConfig, contracts: list[tuple[Contract, Any]]) -> None:
        if self.cache is None:
            return
        rows = []
        for contract, detail in contracts:
            rows.append(
                {
                    "conId": int(getattr(contract, "conId", 0) or 0),
                    "symbol": str(getattr(contract, "symbol", "") or config.symbol),
                    "exchange": str(getattr(contract, "exchange", "") or config.exchange),
                    "currency": str(getattr(contract, "currency", "") or config.currency),
                    "lastTradeDateOrContractMonth": str(
                        getattr(contract, "lastTradeDateOrContractMonth", "") or ""
                    ),
                    "localSymbol": str(getattr(contract, "localSymbol", "") or ""),
                    "tradingClass": str(getattr(contract, "tradingClass", "") or config.trading_class or ""),
                    "realExpirationDate": str(getattr(detail, "realExpirationDate", "") or ""),
                }
            )
        self.cache.set_json(
            self._contract_cache_key(config.instrument_id),
            {
                "retrieved_at": now_utc().replace(microsecond=0).isoformat(),
                "contracts": rows,
            },
        )

    def _fetch_quotes(self, contracts: list[Contract]) -> tuple[dict[str, QuoteSnapshot], list[str]]:
        batch_fetch = getattr(self.market_data, "fetch_snapshot_quotes_batch", None)
        if callable(batch_fetch):
            return batch_fetch(
                contracts,
                timeout_seconds=self.quote_timeout_seconds,
                batch_size=self.quote_batch_size,
            )
        return self.market_data.fetch_snapshot_quotes(contracts, timeout_seconds=self.quote_timeout_seconds)

    def _build_curve(
        self,
        config: IbkrFutureRootConfig,
        contracts: list[tuple[Contract, Any]],
        quotes: dict[str, QuoteSnapshot],
        retrieved_at: datetime,
    ) -> CommodityCurveSnapshot:
        previous_prices = self._previous_curve_prices(config.instrument_id, retrieved_at)
        nodes: list[CommodityCurveNode] = []
        warnings: list[str] = []
        for index, (contract, detail) in enumerate(contracts):
            quote = quotes.get(self.market_data.quote_key(contract), QuoteSnapshot(None, None, False))
            price = quote.price if _valid_positive(quote.price) else None
            expiry = _ibkr_contract_expiry(contract, detail)
            contract_id = _ibkr_contract_id(contract, config)
            month_label = _ibkr_contract_month_label(contract, detail)
            previous_price = previous_prices.get(contract_id) or previous_prices.get(month_label)
            change = price - previous_price if price is not None and previous_price is not None else None
            if price is None:
                warnings.append(f"No IBKR quote for {config.label} {month_label}.")
            if quote.delayed:
                warnings.append(f"Delayed IBKR quote for {config.label} {month_label}.")
            contract_meta = CommodityFuturesContract(
                contract_id=contract_id,
                instrument_id=config.instrument_id,
                symbol=_ibkr_contract_symbol(contract, config),
                contract_month=month_label,
                expiry_date=expiry,
                is_front_month=index == 0,
                source_provider="ibkr",
                retrieved_at=retrieved_at,
                origin=_ibkr_contract_origin(contract),
                transformation_note="IBKR FUT contract metadata normalized from reqContractDetails.",
            )
            nodes.append(
                CommodityCurveNode(
                    contract=contract_meta,
                    price=round(float(price), 6) if price is not None else None,
                    previous_price=round(previous_price, 6) if previous_price is not None else None,
                    change=round(change, 6) if change is not None else None,
                    days_to_expiry=(expiry.date() - retrieved_at.date()).days if expiry is not None else None,
                    source_provider="ibkr",
                    retrieved_at=retrieved_at,
                    origin=f"ibkr.reqMktData:{getattr(contract, 'conId', '') or _ibkr_contract_symbol(contract, config)}",
                    transformation_note=(
                        f"Gamma requested a read-only IBKR futures snapshot and selected {quote.field or 'no usable'} price field."
                    ),
                )
            )
        return CommodityCurveSnapshot(
            instrument_id=config.instrument_id,
            as_of=retrieved_at,
            nodes=nodes,
            warnings=_dedupe(
                [
                    *warnings,
                    "Curve nodes are individual IBKR FUT contracts; this is not a synthetic tradable instrument or order ticket.",
                ]
            ),
            source_provider="ibkr",
            retrieved_at=retrieved_at,
            origin=f"ibkr.commodities.curve:{config.symbol}:{config.exchange}",
            transformation_note=(
                "Gamma constructs the futures curve from IBKR contract details and market-data snapshots, then the application service computes term-structure analytics."
            ),
        )

    def _fetch_front_history(
        self,
        config: IbkrFutureRootConfig,
        contract: Contract,
        retrieved_at: datetime,
    ) -> CommodityPriceHistory:
        try:
            series = self.market_data.fetch_history(contract, self.history_days)
        except Exception:
            series = None
        points: list[CommodityPricePoint] = []
        if series is not None and not series.empty:
            clean = series.dropna().tail(self.history_days)
            for timestamp, value in clean.items():
                if not _valid_positive(value):
                    continue
                ts = timestamp.to_pydatetime() if isinstance(timestamp, pd.Timestamp) else _parse_datetime(timestamp)
                if ts is None:
                    continue
                points.append(
                    CommodityPricePoint(
                        instrument_id=config.instrument_id,
                        timestamp=ts,
                        value=round(float(value), 6),
                        unit=config.quote_unit,
                        source_provider="ibkr",
                        retrieved_at=retrieved_at,
                        origin=f"ibkr.reqHistoricalData:{getattr(contract, 'conId', '') or _ibkr_contract_symbol(contract, config)}",
                        transformation_note=(
                            "IBKR historical daily bars for the current front futures contract; this is not a back-adjusted continuous series."
                        ),
                    )
                )
        return CommodityPriceHistory(
            instrument_id=config.instrument_id,
            label=f"{config.label} IBKR front futures history",
            unit=config.quote_unit,
            points=points,
            source_provider="ibkr",
            retrieved_at=retrieved_at,
            origin=f"ibkr.reqHistoricalData:{getattr(contract, 'conId', '') or _ibkr_contract_symbol(contract, config)}",
            transformation_note="Gamma maps IBKR front-contract futures bars into the normalized commodity price-history model.",
        )

    def _curve_history_key(self, instrument_id: str) -> str:
        if self.cache is None:
            return ""
        return self.cache.make_key("commodities", "ibkr", "curve_history", instrument_id)

    def _load_curve_history(self, instrument_id: str) -> list[dict[str, Any]]:
        if self.cache is None:
            return []
        cached = self.cache.get_json(
            self._curve_history_key(instrument_id),
            max_age=timedelta(days=3650),
        )
        return cached if isinstance(cached, list) else []

    def _append_curve_snapshot(self, curve: CommodityCurveSnapshot) -> None:
        if self.cache is None:
            return
        history = self._load_curve_history(curve.instrument_id)
        curve_date = curve.as_of.date().isoformat()
        entry = {
            "date": curve_date,
            "as_of": curve.as_of.isoformat(),
            "instrument_id": curve.instrument_id,
            "nodes": [
                {
                    "contract_id": node.contract.contract_id,
                    "symbol": node.contract.symbol,
                    "contract_month": node.contract.contract_month,
                    "expiry_date": node.contract.expiry_date.isoformat() if node.contract.expiry_date else None,
                    "price": node.price,
                    "source_provider": node.source_provider,
                    "origin": node.origin,
                }
                for node in curve.nodes
            ],
        }
        deduped = [row for row in history if row.get("date") != curve_date]
        deduped.append(entry)
        deduped = sorted(deduped, key=lambda row: str(row.get("date") or ""))[-400:]
        self.cache.set_json(self._curve_history_key(curve.instrument_id), deduped)

    def _cached_curve_snapshot(
        self,
        instrument_id: str,
        retrieved_at: datetime,
        *,
        max_age_seconds: int | float | None,
    ) -> CommodityCurveSnapshot | None:
        history = self._load_curve_history(instrument_id)
        if not history:
            return None
        latest = sorted(history, key=lambda row: str(row.get("as_of") or row.get("date") or ""))[-1]
        as_of = _parse_datetime(latest.get("as_of")) or _parse_datetime(latest.get("date"))
        if as_of is None:
            return None
        if max_age_seconds is not None and float(max_age_seconds) >= 0:
            age_seconds = (retrieved_at - as_of).total_seconds()
            if age_seconds > float(max_age_seconds):
                return None
        nodes: list[CommodityCurveNode] = []
        for index, row in enumerate(latest.get("nodes") or []):
            if not isinstance(row, dict):
                continue
            price = _float_value(row.get("price"))
            contract_month = str(row.get("contract_month") or "").strip()
            expiry = _parse_datetime(row.get("expiry_date"))
            symbol = str(row.get("symbol") or "").strip()
            contract_id = str(row.get("contract_id") or "").strip()
            if not contract_id or not contract_month:
                continue
            contract = CommodityFuturesContract(
                contract_id=contract_id,
                instrument_id=instrument_id,
                symbol=symbol or contract_id,
                contract_month=contract_month,
                expiry_date=expiry,
                is_front_month=index == 0,
                source_provider="ibkr_cached",
                retrieved_at=retrieved_at,
                origin=str(row.get("origin") or "ibkr.commodities.curve_history"),
                transformation_note="Cached IBKR FUT contract metadata restored from Gamma's local curve snapshot cache.",
            )
            nodes.append(
                CommodityCurveNode(
                    contract=contract,
                    price=round(float(price), 6) if price is not None else None,
                    previous_price=None,
                    change=None,
                    days_to_expiry=(expiry.date() - retrieved_at.date()).days if expiry is not None else None,
                    source_provider="ibkr_cached",
                    retrieved_at=retrieved_at,
                    origin=str(row.get("origin") or "ibkr.commodities.curve_history"),
                    transformation_note=(
                        "Cached IBKR futures node restored from Gamma's local curve snapshot cache; no fresh market-data line was used."
                    ),
                )
            )
        if not nodes:
            return None
        return CommodityCurveSnapshot(
            instrument_id=instrument_id,
            as_of=as_of,
            nodes=nodes,
            warnings=[
                "Cached IBKR curve snapshot; refresh or select the commodity to request fresh live/delayed IBKR nodes."
            ],
            source_provider="ibkr_cached",
            retrieved_at=retrieved_at,
            origin="ibkr.commodities.curve_history_cache",
            transformation_note=(
                "Gamma reused a locally cached IBKR futures curve snapshot to avoid repeated contract discovery and quote requests."
            ),
        )

    def _previous_curve_prices(self, instrument_id: str, retrieved_at: datetime) -> dict[str, float]:
        history = self._load_curve_history(instrument_id)
        today = retrieved_at.date().isoformat()
        previous_rows = [row for row in history if str(row.get("date") or "") < today]
        if not previous_rows:
            return {}
        previous = sorted(previous_rows, key=lambda row: str(row.get("date") or ""))[-1]
        prices: dict[str, float] = {}
        for node in previous.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            price = _float_value(node.get("price"))
            if price is None:
                continue
            contract_id = str(node.get("contract_id") or "").strip()
            month = str(node.get("contract_month") or "").strip()
            if contract_id:
                prices[contract_id] = price
            if month:
                prices[month] = price
        return prices


def _sample_instruments(retrieved_at: datetime) -> list[CommodityInstrument]:
    return [
        CommodityInstrument(
            instrument_id=config.instrument_id,
            symbol=config.symbol,
            name=config.name,
            family=config.family,
            subgroup=config.subgroup,
            quote_unit=config.quote_unit,
            exchange=config.exchange,
            front_symbol=config.front_symbol,
            provider_symbols={
                "sample": config.symbol,
                "ibkr": config.front_symbol or "",
                "fred": _fred_symbol_for(config.instrument_id),
            },
            aliases=[config.name.lower(), config.symbol.lower()],
            description=f"{config.name} research instrument for read-only commodity analysis.",
            source_provider="sample_data",
            retrieved_at=retrieved_at,
            origin="sample_commodities.instruments",
            transformation_note="Sample commodity universe normalized into Gamma instrument metadata.",
        )
        for config in COMMODITY_INSTRUMENTS
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
        "platinum": (985.0, 22.0, 0.08),
        "copper": (4.58, 0.17, 0.0015),
        "aluminum": (2560.0, 84.0, 0.85),
        "zinc": (2860.0, 96.0, 0.7),
        "nickel": (15900.0, 640.0, 3.0),
        "lead": (1980.0, 58.0, 0.35),
        "tin": (31800.0, 950.0, 5.0),
        "iron_ore": (105.0, 6.0, -0.02),
        "uranium": (72.0, 4.4, 0.015),
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
        "platinum": [991.0, 994.0, 998.0, 1002.0, 1006.0, 1010.0],
        "copper": [4.61, 4.58, 4.55, 4.52, 4.50, 4.47],
        "aluminum": [2575.0, 2584.0, 2595.0, 2608.0, 2620.0, 2634.0],
        "zinc": [2878.0, 2890.0, 2901.0, 2915.0, 2928.0, 2940.0],
    }
    curves: list[CommodityCurveSnapshot] = []
    for instrument in instruments:
        if instrument.instrument_id not in levels:
            continue
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
        ("comex-copper-registered-stocks", "copper", "COMEX Copper Registered Stocks", "warehouse", "short tons", 24400.0, 3600.0, -9.0),
        ("lme-copper-on-warrant", "copper", "LME Copper On-Warrant Stocks", "warehouse", "metric tons", 118000.0, 21000.0, -42.0),
        ("lme-aluminum-on-warrant", "aluminum", "LME Aluminum On-Warrant Stocks", "warehouse", "metric tons", 421000.0, 62000.0, 155.0),
        ("lme-zinc-on-warrant", "zinc", "LME Zinc On-Warrant Stocks", "warehouse", "metric tons", 84000.0, 18000.0, -36.0),
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


def _ibkr_root_configs_from_env() -> tuple[IbkrFutureRootConfig, ...]:
    overrides = _parse_ibkr_root_overrides(os.getenv("IBKR_COMMODITIES_ROOT_OVERRIDES"))
    rows: list[IbkrFutureRootConfig] = []
    for config in IBKR_FUTURES_ROOTS:
        override = overrides.get(config.instrument_id, {})
        rows.append(
            IbkrFutureRootConfig(
                instrument_id=config.instrument_id,
                symbol=str(override.get("symbol") or config.symbol).strip().upper(),
                exchange=str(override.get("exchange") or config.exchange).strip().upper(),
                currency=str(override.get("currency") or config.currency).strip().upper(),
                quote_unit=str(override.get("quote_unit") or config.quote_unit).strip(),
                label=str(override.get("label") or config.label).strip(),
                trading_class=str(override.get("trading_class") or config.trading_class or "").strip().upper() or None,
                multiplier=str(override.get("multiplier") or config.multiplier or "").strip() or None,
            )
        )
    return tuple(rows)


def _parse_ibkr_root_overrides(raw: str | None) -> dict[str, dict[str, Any]]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for key, value in payload.items():
        if isinstance(value, dict):
            normalized[_slug(str(key))] = value
    return normalized


def _parse_csv_env(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def _ibkr_credential_env_vars() -> list[str]:
    return [
        "COMMODITIES_PROVIDER",
        "IB_HOST",
        "IB_PORT",
        "IB_CLIENT_ID",
        "IB_MARKET_DATA_MODE",
        "IBKR_COMMODITIES_ENABLED",
        "IBKR_COMMODITIES_STARTUP_ENABLED",
        "IBKR_COMMODITIES_ON_DEMAND",
        "IBKR_COMMODITIES_SELECTED_CACHE_SECONDS",
        "IBKR_COMMODITIES_CONTRACT_CACHE_SECONDS",
        "IBKR_COMMODITIES_CONTRACT_DEPTH",
        "IBKR_COMMODITIES_HISTORY_DAYS",
        "IBKR_COMMODITIES_QUOTE_TIMEOUT_SECONDS",
        "IBKR_COMMODITIES_CONTRACT_TIMEOUT_SECONDS",
        "IBKR_COMMODITIES_QUOTE_BATCH_SIZE",
        "IBKR_COMMODITIES_ROOT_OVERRIDES",
    ]


def _mark_ibkr_instruments(
    instruments: list[CommodityInstrument],
    live_curve_ids: set[str],
    retrieved_at: datetime,
) -> list[CommodityInstrument]:
    rows: list[CommodityInstrument] = []
    for instrument in instruments:
        if instrument.instrument_id not in live_curve_ids:
            rows.append(instrument)
            continue
        rows.append(
            replace(
                instrument,
                source_provider="ibkr",
                retrieved_at=retrieved_at,
                origin="ibkr.commodities.instrument",
                transformation_note=(
                    "Instrument metadata is the Gamma commodity universe with IBKR futures-curve coverage active for this row."
                ),
            )
        )
    return rows


def _ibkr_contract_id(contract: Contract, config: IbkrFutureRootConfig) -> str:
    con_id = str(getattr(contract, "conId", "") or "").strip()
    if con_id and con_id != "0":
        return f"ibkr:{con_id}"
    month = str(getattr(contract, "lastTradeDateOrContractMonth", "") or "").strip()
    return f"ibkr:{config.instrument_id}:{config.symbol}:{month or _ibkr_contract_symbol(contract, config)}"


def _ibkr_contract_symbol(contract: Contract, config: IbkrFutureRootConfig) -> str:
    for attr in ("localSymbol", "symbol"):
        value = str(getattr(contract, attr, "") or "").strip()
        if value:
            return value
    return config.symbol


def _ibkr_contract_origin(contract: Contract) -> str:
    con_id = str(getattr(contract, "conId", "") or "").strip()
    if con_id and con_id != "0":
        return f"ibkr.reqContractDetails:{con_id}"
    return "ibkr.reqContractDetails"


def _ibkr_contract_month_key(contract: Contract, detail: Any = None) -> str:
    raw_values = [
        getattr(contract, "lastTradeDateOrContractMonth", None),
        getattr(detail, "realExpirationDate", None),
    ]
    for value in raw_values:
        text = str(value or "").strip()
        if len(text) >= 6 and text[:6].isdigit():
            return text[:6]
    return ""


def _ibkr_contract_month_label(contract: Contract, detail: Any = None) -> str:
    month_key = _ibkr_contract_month_key(contract, detail)
    if len(month_key) == 6:
        try:
            return datetime(int(month_key[:4]), int(month_key[4:6]), 1).strftime("%b %Y")
        except ValueError:
            pass
    symbol = str(getattr(contract, "localSymbol", "") or getattr(contract, "symbol", "") or "").strip()
    return symbol or "Unknown"


def _ibkr_contract_expiry(contract: Contract, detail: Any = None) -> datetime | None:
    for value in (
        getattr(detail, "realExpirationDate", None),
        getattr(contract, "lastTradeDateOrContractMonth", None),
    ):
        parsed = _parse_ibkr_contract_date(value)
        if parsed is not None:
            return parsed
    month_key = _ibkr_contract_month_key(contract, detail)
    if len(month_key) == 6:
        try:
            year = int(month_key[:4])
            month = int(month_key[4:6])
            next_month = datetime(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
            return next_month - timedelta(days=1)
        except ValueError:
            return None
    return None


def _parse_ibkr_contract_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        try:
            return datetime.strptime(text, "%Y%m%d")
        except ValueError:
            return None
    if len(text) == 6 and text.isdigit():
        try:
            year = int(text[:4])
            month = int(text[4:6])
            next_month = datetime(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
            return next_month - timedelta(days=1)
        except ValueError:
            return None
    return _parse_datetime(text)


def _valid_positive(value: Any) -> bool:
    numeric = _float_value(value)
    return numeric is not None and math.isfinite(numeric) and numeric > 0


def _slug(value: str | None) -> str:
    text = str(value or "").strip().lower()
    return "_".join(part for part in "".join(char if char.isalnum() else "_" for char in text).split("_") if part)


def _with_provider_warning(
    reference: CommodityProviderSnapshot,
    warning: str,
    *,
    extra_warnings: list[str] | None = None,
    credential_env_vars: list[str] | None = None,
) -> CommodityProviderSnapshot:
    warnings = _dedupe([warning, *(extra_warnings or []), *reference.warnings])
    coverage = replace(
        reference.coverage,
        caveats=_dedupe([warning, *reference.coverage.caveats]),
        credential_env_vars=_dedupe([*reference.coverage.credential_env_vars, *(credential_env_vars or ["EIA_API_KEY"])]),
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


def _normalize_eia_value(value: float, unit: str) -> float:
    normalized_unit = unit.lower()
    if "bbl" in normalized_unit and abs(value) > 10_000:
        return value / 1000.0
    if "b/d" in normalized_unit and abs(value) > 1_000:
        return value / 1000.0
    return value


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
