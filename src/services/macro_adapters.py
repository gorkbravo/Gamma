from __future__ import annotations

import json
import logging
import re
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from html import unescape
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from src.models.macro import MacroEventRecord, MacroSeriesPoint
from src.services.cache import CacheService
from src.services.fred import FredClient
from src.services.market_data import MarketDataService
from src.utils.time import now_utc


TextFetcher = Callable[[str], str]
JsonFetcher = Callable[[str], Any]
_US_EASTERN = ZoneInfo("America/New_York")
logger = logging.getLogger(__name__)


def default_text_fetcher(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.bls.gov/",
        },
    )
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", "ignore")


# Calendarios oficiales de USMacroEventsAdapter. Un User-Agent de navegador desde urllib es
# justo lo que el filtro de bots de bls.gov (Akamai) rechaza con 403; Gamma se identifica tal
# cual es y solo añade el contacto del usuario donde la fuente lo exige (bls.gov).
MACRO_CALENDAR_USER_AGENT = "Gamma/0.1 read-only macro calendar"
_MACRO_CALENDAR_ACCEPT = "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"
_MACRO_CALENDAR_TTL = timedelta(hours=12)
# Tras un fallo no se vuelve a pedir la fuente durante este intervalo (salvo force_refresh):
# repetir peticiones rechazadas a un host con filtro de bots solo empeora el bloqueo.
_MACRO_CALENDAR_FAILURE_BACKOFF = timedelta(minutes=15)
# Los calendarios se publican con meses de antelación: una copia antigua sigue siendo útil.
_MACRO_CALENDAR_STALE_LIMIT = timedelta(days=30)


@lru_cache(maxsize=1)
def _calendar_ssl_context() -> ssl.SSLContext:
    """Raíces del sistema más las de certifi.

    En Windows el almacén local solo contiene las raíces que CryptoAPI ya descargó, y Python
    no dispara esa descarga: www.ecb.europa.eu encadena a "Sectigo Public Server
    Authentication Root E46" y falla con CERTIFICATE_VERIFY_FAILED aunque el navegador la
    acepte. Añadir el paquete de certifi amplía las raíces de confianza sin desactivar nada.
    """

    context = ssl.create_default_context()
    try:
        import certifi
    except ImportError:
        return context
    context.load_verify_locations(cafile=certifi.where())
    return context


def fetch_calendar_page(url: str, *, user_agent: str, extra_roots: bool = False) -> str:
    request = Request(url, headers={"User-Agent": user_agent, "Accept": _MACRO_CALENDAR_ACCEPT})
    # Pasar context= abre un opener propio, así que solo se hace donde hace falta.
    options: dict[str, Any] = {"context": _calendar_ssl_context()} if extra_roots else {}
    with urlopen(request, timeout=20, **options) as response:
        return response.read().decode("utf-8", "ignore")


def default_json_fetcher(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": "Gamma/0.1 read-only macro adapter",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8", "ignore"))


@dataclass(frozen=True)
class DBnomicsSeriesMetadata:
    provider_code: str
    dataset_code: str
    series_code: str
    dataset_name: str | None
    series_name: str | None
    frequency: str | None
    indexed_at: datetime | None = None


@dataclass(frozen=True)
class DBnomicsSeriesResult:
    points: list[MacroSeriesPoint]
    retrieved_at: datetime
    metadata: DBnomicsSeriesMetadata


@dataclass(frozen=True)
class CensusTradePartnerResult:
    partner_code: str
    partner_name: str
    export_value: float
    import_value: float
    source_provider: str
    retrieved_at: datetime
    origin: str
    transformation_note: str

    @property
    def total_trade_value(self) -> float:
        return self.export_value + self.import_value

    @property
    def trade_balance(self) -> float:
        return self.export_value - self.import_value


@dataclass(frozen=True)
class MacroEventsResult:
    """Eventos del calendario y un aviso por cada fuente oficial que no aportó datos frescos.

    ``status`` es "incomplete" cuando alguna fuente falta o se sirve desde una copia antigua,
    para que el registro de uso de proveedores no lo cuente como una carga completa.
    """

    events: list[MacroEventRecord]
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "incomplete" if self.warnings else "ready"


@dataclass(frozen=True)
class _CalendarSource:
    source_id: str
    label: str
    url: str
    parser: Callable[[str, datetime], list[MacroEventRecord]]
    # bls.gov bloquea los robots sin datos de contacto del propietario.
    needs_contact: bool = False
    # www.ecb.europa.eu necesita raíces que el almacén de Windows puede no tener.
    extra_roots: bool = False


class FredMacroAdapter:
    provider = "fred"

    def __init__(self, cache: CacheService, client: FredClient | None = None) -> None:
        self.cache = cache
        self.client = client or FredClient(cache=cache)

    def get_series(
        self,
        provider_series_id: str,
        *,
        start: datetime,
        end: datetime,
        ttl: timedelta,
        force_refresh: bool = False,
    ) -> tuple[list[MacroSeriesPoint], datetime]:
        observations, retrieved_at = self.client.get_series_observations(
            provider_series_id,
            observation_start=start,
            observation_end=end,
            ttl=ttl,
            force_refresh=force_refresh,
        )
        points = [
            MacroSeriesPoint(
                timestamp=observation.timestamp,
                value=observation.value,
                source_provider=self.provider,
                retrieved_at=retrieved_at,
                origin=f"fred.series.observations:{provider_series_id}",
            )
            for observation in observations
        ]
        return points, retrieved_at


class IBKRMacroFXAdapter:
    provider = "ibkr"

    def __init__(self, market_data: MarketDataService | None) -> None:
        self.market_data = market_data

    def get_series(
        self,
        display_base_currency: str,
        display_quote_currency: str,
        *,
        start: datetime,
        end: datetime,
        force_refresh: bool = False,
    ) -> tuple[list[MacroSeriesPoint], datetime]:
        del force_refresh
        retrieved_at = now_utc()
        if self.market_data is None:
            return [], retrieved_at
        lookback_days = max((end.date() - start.date()).days + 5, 5)
        # MarketDataService.fetch_fx_history(base, quote) returns the quote->base conversion series.
        # For display pairs like EUR/USD we want the direct displayed quote, so we reverse the inputs.
        raw_series = self.market_data.fetch_fx_history(display_quote_currency, display_base_currency, lookback_days)
        if raw_series is None or raw_series.empty:
            return [], retrieved_at
        points: list[MacroSeriesPoint] = []
        pair_code = f"{str(display_base_currency).upper()}{str(display_quote_currency).upper()}"
        for timestamp, value in raw_series.items():
            if value is None or value != value:
                continue
            point_time = timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp
            if point_time.tzinfo is not None:
                point_time = point_time.astimezone(timezone.utc).replace(tzinfo=None)
            points.append(
                MacroSeriesPoint(
                    timestamp=point_time,
                    value=float(value),
                    source_provider=self.provider,
                    retrieved_at=retrieved_at,
                    origin=f"ibkr.fx_history:{pair_code}",
                )
            )
        return [point for point in points if start <= point.timestamp <= end], retrieved_at


class DBnomicsMacroAdapter:
    provider = "dbnomics"
    BASE_URL = "https://api.db.nomics.world/v22"

    def __init__(self, cache: CacheService, fetch_json: JsonFetcher | None = None) -> None:
        self.cache = cache
        self.fetch_json = fetch_json or default_json_fetcher

    def get_series(
        self,
        provider_code: str,
        dataset_code: str,
        series_code: str,
        *,
        start: datetime,
        end: datetime,
        ttl: timedelta,
        force_refresh: bool = False,
    ) -> DBnomicsSeriesResult:
        provider_code = _clean_dbnomics_code(provider_code)
        dataset_code = _clean_dbnomics_code(dataset_code)
        series_code = _clean_dbnomics_code(series_code)
        if not provider_code or not dataset_code or not series_code:
            raise ValueError("DB.nomics provider_code, dataset_code, and series_code are required.")

        cache_key = self.cache.make_key("macro", "dbnomics", provider_code, dataset_code, series_code)
        cached: Any = None
        if not force_refresh:
            cached = self.cache.get_json(cache_key, max_age=ttl)
        if isinstance(cached, dict) and "payload" in cached and "retrieved_at" in cached:
            payload = cached["payload"]
            retrieved_at = _parse_datetime(cached["retrieved_at"]) or now_utc()
        else:
            url = (
                f"{self.BASE_URL}/series/{quote(provider_code, safe='')}/"
                f"{quote(dataset_code, safe='')}/{quote(series_code, safe='')}"
                "?observations=1&format=json"
            )
            payload = self.fetch_json(url)
            retrieved_at = now_utc()
            self.cache.set_json(
                cache_key,
                {
                    "retrieved_at": retrieved_at.isoformat(),
                    "payload": payload,
                },
            )
        return self._parse_series_payload(
            payload,
            provider_code=provider_code,
            dataset_code=dataset_code,
            series_code=series_code,
            start=start,
            end=end,
            retrieved_at=retrieved_at,
        )

    def _parse_series_payload(
        self,
        payload: Any,
        *,
        provider_code: str,
        dataset_code: str,
        series_code: str,
        start: datetime,
        end: datetime,
        retrieved_at: datetime,
    ) -> DBnomicsSeriesResult:
        docs = []
        if isinstance(payload, dict):
            series_root = payload.get("series")
            if isinstance(series_root, dict) and isinstance(series_root.get("docs"), list):
                docs = series_root["docs"]
        doc = docs[0] if docs and isinstance(docs[0], dict) else {}
        metadata = DBnomicsSeriesMetadata(
            provider_code=provider_code,
            dataset_code=dataset_code,
            series_code=series_code,
            dataset_name=_optional_str(doc.get("dataset_name")),
            series_name=_optional_str(doc.get("series_name")),
            frequency=_optional_str(doc.get("@frequency") or doc.get("frequency")),
            indexed_at=_parse_datetime(doc.get("indexed_at")),
        )
        periods = doc.get("period") if isinstance(doc.get("period"), list) else []
        values = doc.get("value") if isinstance(doc.get("value"), list) else []
        full_id = f"{provider_code}/{dataset_code}/{series_code}"
        note = (
            "DB.nomics wraps the original provider series. Gamma preserves raw observations, "
            "skips missing values, and does not fill absent periods."
        )
        points: list[MacroSeriesPoint] = []
        for period, value in zip(periods, values):
            timestamp = _parse_dbnomics_period(period)
            parsed_value = _parse_float(value)
            if timestamp is None or parsed_value is None:
                continue
            if timestamp < start or timestamp > end:
                continue
            points.append(
                MacroSeriesPoint(
                    timestamp=timestamp,
                    value=parsed_value,
                    source_provider=self.provider,
                    retrieved_at=retrieved_at,
                    origin=f"dbnomics.series.observations:{full_id}",
                    transformation_note=note,
                )
            )
        return DBnomicsSeriesResult(points=points, retrieved_at=retrieved_at, metadata=metadata)


class CensusTradePartnerAdapter:
    provider = "census"
    BASE_URL = "https://api.census.gov/data/timeseries/intltrade"

    def __init__(
        self,
        cache: CacheService,
        *,
        api_key: str | None = None,
        fetch_json: JsonFetcher | None = None,
    ) -> None:
        self.cache = cache
        self.api_key = str(api_key or "").strip()
        self.fetch_json = fetch_json or default_json_fetcher

    def get_us_trade_partners(
        self,
        *,
        year_month: str | None = None,
        ttl: timedelta = timedelta(hours=24),
        force_refresh: bool = False,
        limit: int = 8,
    ) -> tuple[list[CensusTradePartnerResult], datetime]:
        candidates = [year_month] if year_month else self._candidate_months()
        last_retrieved_at = now_utc()
        for candidate in candidates:
            if not candidate:
                continue
            try:
                rows, retrieved_at = self._get_month(candidate, ttl=ttl, force_refresh=force_refresh, limit=limit)
            except Exception as exc:
                logger.debug("Census trade partner month %s unavailable: %s", candidate, exc)
                continue
            last_retrieved_at = retrieved_at
            if rows:
                return rows, retrieved_at
        return [], last_retrieved_at

    def _get_month(
        self,
        year_month: str,
        *,
        ttl: timedelta,
        force_refresh: bool,
        limit: int,
    ) -> tuple[list[CensusTradePartnerResult], datetime]:
        cache_key = self.cache.make_key("macro", "census", "trade_partners", year_month)
        cached: Any = None
        if not force_refresh:
            cached = self.cache.get_json(cache_key, max_age=ttl)
        if isinstance(cached, dict) and "exports" in cached and "imports" in cached and "retrieved_at" in cached:
            exports_payload = cached["exports"]
            imports_payload = cached["imports"]
            retrieved_at = _parse_datetime(cached["retrieved_at"]) or now_utc()
        else:
            exports_payload = self.fetch_json(self._build_url("exports", year_month))
            imports_payload = self.fetch_json(self._build_url("imports", year_month))
            retrieved_at = now_utc()
            self.cache.set_json(
                cache_key,
                {
                    "retrieved_at": retrieved_at.isoformat(),
                    "exports": exports_payload,
                    "imports": imports_payload,
                },
            )
        return self._parse_partner_payloads(
            exports_payload,
            imports_payload,
            year_month=year_month,
            retrieved_at=retrieved_at,
            limit=limit,
        ), retrieved_at

    def _build_url(self, flow: str, year_month: str) -> str:
        if flow == "exports":
            path = "exports/naics"
            value_field = "ALL_VAL_YR"
        elif flow == "imports":
            path = "imports/naics"
            value_field = "GEN_VAL_YR"
        else:
            raise ValueError(f"Unsupported Census trade flow: {flow}")
        params = {
            "get": f"CTY_CODE,CTY_NAME,SUMMARY_LVL,{value_field},YEAR,MONTH",
            "time": year_month,
        }
        if self.api_key:
            params["key"] = self.api_key
        return f"{self.BASE_URL}/{path}?{urlencode(params)}"

    def _parse_partner_payloads(
        self,
        exports_payload: Any,
        imports_payload: Any,
        *,
        year_month: str,
        retrieved_at: datetime,
        limit: int,
    ) -> list[CensusTradePartnerResult]:
        exports = self._parse_flow_rows(exports_payload, "ALL_VAL_YR")
        imports = self._parse_flow_rows(imports_payload, "GEN_VAL_YR")
        partner_keys = set(exports) | set(imports)
        rows: list[CensusTradePartnerResult] = []
        origin = f"census.intltrade.naics:{year_month}"
        note = (
            "Official Census International Trade NAICS country rows normalized from year-to-date export and general-import values; "
            "Gamma converts dollars to USD billions and ranks by combined trade."
        )
        for key in partner_keys:
            export_row = exports.get(key)
            import_row = imports.get(key)
            partner_name = (export_row or import_row or {}).get("partner_name") or key
            export_value = float((export_row or {}).get("value") or 0.0) / 1_000_000_000.0
            import_value = float((import_row or {}).get("value") or 0.0) / 1_000_000_000.0
            if export_value <= 0 and import_value <= 0:
                continue
            rows.append(
                CensusTradePartnerResult(
                    partner_code=_census_partner_code(key, partner_name),
                    partner_name=_title_country_name(partner_name),
                    export_value=export_value,
                    import_value=import_value,
                    source_provider=self.provider,
                    retrieved_at=retrieved_at,
                    origin=origin,
                    transformation_note=note,
                )
            )
        rows.sort(key=lambda row: row.export_value + row.import_value, reverse=True)
        return rows[: max(limit, 1)]

    def _parse_flow_rows(self, payload: Any, value_field: str) -> dict[str, dict[str, Any]]:
        if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[0], list):
            return {}
        header = [str(value) for value in payload[0]]
        index = {name: position for position, name in enumerate(header)}
        required = {"CTY_CODE", "CTY_NAME", "SUMMARY_LVL", value_field}
        if not required.issubset(index):
            return {}
        rows: dict[str, dict[str, Any]] = {}
        for raw_row in payload[1:]:
            if not isinstance(raw_row, list):
                continue
            summary_level = str(_list_get(raw_row, index["SUMMARY_LVL"]) or "").strip().upper()
            country_code = str(_list_get(raw_row, index["CTY_CODE"]) or "").strip()
            if summary_level != "DET" or country_code in {"", "-"}:
                continue
            value = _parse_float(_list_get(raw_row, index[value_field]))
            if value is None or value <= 0:
                continue
            rows[country_code] = {
                "partner_name": str(_list_get(raw_row, index["CTY_NAME"]) or "").strip() or country_code,
                "value": value,
            }
        return rows

    def _candidate_months(self) -> list[str]:
        current = now_utc()
        year = current.year
        month = current.month - 1
        candidates: list[str] = []
        for _ in range(18):
            if month <= 0:
                year -= 1
                month += 12
            candidates.append(f"{year:04d}-{month:02d}")
            month -= 1
        return candidates


class TreasuryCurveAdapter:
    provider = "treasury"
    BASE_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
    NOMINAL_FIELDS = {
        "3M": "BC_3MONTH",
        "2Y": "BC_2YEAR",
        "5Y": "BC_5YEAR",
        "10Y": "BC_10YEAR",
        "30Y": "BC_30YEAR",
    }
    REAL_FIELDS = {
        "5Y": "TC_5YEAR",
        "7Y": "TC_7YEAR",
        "10Y": "TC_10YEAR",
        "20Y": "TC_20YEAR",
        "30Y": "TC_30YEAR",
    }

    def __init__(self, cache: CacheService, fetch_text: TextFetcher | None = None) -> None:
        self.cache = cache
        self.fetch_text = fetch_text or default_text_fetcher

    def get_curve_history(
        self,
        curve_kind: str,
        *,
        years: list[int],
        ttl: timedelta,
        force_refresh: bool = False,
    ) -> tuple[dict[datetime, dict[str, float]], datetime]:
        merged: dict[datetime, dict[str, float]] = {}
        retrieved_at = datetime.min
        for year in sorted(set(years)):
            cache_key = self.cache.make_key("macro", "treasury", curve_kind, str(year))
            cached: Any = None
            if not force_refresh:
                cached = self.cache.get_json(cache_key, max_age=ttl)
            if isinstance(cached, dict) and "payload" in cached and "retrieved_at" in cached:
                xml_text = str(cached["payload"])
                cached_at = _parse_datetime(cached["retrieved_at"]) or now_utc()
            else:
                url = f"{self.BASE_URL}?data={curve_kind}&field_tdr_date_value={year}"
                xml_text = self.fetch_text(url)
                cached_at = now_utc()
                self.cache.set_json(
                    cache_key,
                    {
                        "retrieved_at": cached_at.isoformat(),
                        "payload": xml_text,
                    },
                )
            merged.update(self._parse_curve_xml(xml_text, curve_kind))
            retrieved_at = max(retrieved_at, cached_at)
        if retrieved_at == datetime.min:
            retrieved_at = now_utc()
        return merged, retrieved_at

    def _parse_curve_xml(self, xml_text: str, curve_kind: str) -> dict[datetime, dict[str, float]]:
        root = ET.fromstring(xml_text)
        namespace = {"m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"}
        field_map = self.NOMINAL_FIELDS if curve_kind == "daily_treasury_yield_curve" else self.REAL_FIELDS
        result: dict[datetime, dict[str, float]] = {}
        for properties in root.findall(".//m:properties", namespace):
            values: dict[str, str] = {}
            for child in properties:
                values[_strip_namespace(child.tag)] = str(child.text or "").strip()
            row_date = _parse_datetime(values.get("NEW_DATE"))
            if row_date is None:
                continue
            row: dict[str, float] = {}
            for tenor, field_name in field_map.items():
                parsed = _parse_float(values.get(field_name))
                if parsed is not None:
                    row[tenor] = parsed
            if row:
                result[row_date] = row
        return result


class USMacroEventsAdapter:
    provider = "macro_calendar"
    FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    CPI_URL = "https://www.bls.gov/schedule/news_release/cpi.htm"
    PPI_URL = "https://www.bls.gov/schedule/news_release/ppi.htm"
    EMPSIT_URL = "https://www.bls.gov/schedule/news_release/empsit.htm"
    JOLTS_URL = "https://www.bls.gov/schedule/news_release/jolts.htm"
    BEA_SCHEDULE_URL = "https://www.bea.gov/news/schedule"
    ECB_CALENDAR_URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"

    def __init__(
        self,
        cache: CacheService,
        fetch_text: TextFetcher | None = None,
        *,
        contact_user_agent: Callable[[], str | None] | None = None,
    ) -> None:
        self.cache = cache
        # Solo los tests inyectan fetch_text; en producción cada fuente fija sus cabeceras.
        self.fetch_text = fetch_text
        # Devuelve el contacto configurado ("Nombre email") o None; se consulta en cada carga
        # para recoger cambios hechos en el asistente sin reiniciar.
        self.contact_user_agent = contact_user_agent

    def list_events(
        self,
        *,
        region: str,
        as_of: datetime,
        force_refresh: bool = False,
        limit: int = 12,
    ) -> list[MacroEventRecord]:
        return self.load_events(region=region, as_of=as_of, force_refresh=force_refresh, limit=limit).events

    def load_events(
        self,
        *,
        region: str,
        as_of: datetime,
        force_refresh: bool = False,
        limit: int = 12,
    ) -> MacroEventsResult:
        if region not in {"US", "EU", "Global"}:
            return MacroEventsResult(events=[])
        normalized_as_of = _as_utc_naive(as_of)
        events: list[MacroEventRecord] = []
        warnings: list[str] = []
        contact = self._contact()
        skipped_for_contact: list[str] = []
        for source in self._sources(region):
            if source.needs_contact and contact is None:
                # Sin contacto no se hace la petición: bls.gov la rechazaría con 403.
                skipped_for_contact.append(source.label)
                continue
            payload, retrieved_at, warning = self._load_payload(source, contact=contact, force_refresh=force_refresh)
            if warning:
                warnings.append(warning)
            if payload is None or retrieved_at is None:
                continue
            try:
                parsed = source.parser(payload, retrieved_at)
            except Exception as exc:
                logger.info("Macro calendar source could not be parsed: source=%s error=%s", source.source_id, exc)
                warnings.append(f"Macro calendar: {source.label} could not be parsed ({exc.__class__.__name__}).")
                continue
            if not parsed:
                warnings.append(
                    f"Macro calendar: {source.label} returned no recognizable events; the official page layout may have changed."
                )
            events.extend(parsed)
        if skipped_for_contact:
            warnings.insert(
                0,
                "Macro calendar: BLS release dates ("
                + ", ".join(label.removeprefix("BLS ").removesuffix(" release schedule") for label in skipped_for_contact)
                + ") were not requested because no contact name and email is configured; bls.gov blocks automated "
                "requests that carry no contact details. Add your name and email in Setup (Settings > Run Setup) to load them.",
            )

        unique: dict[str, MacroEventRecord] = {}
        for event in events:
            if _as_utc_naive(event.scheduled_at) < normalized_as_of:
                continue
            normalized = event
            if region == "Global":
                normalized = MacroEventRecord(
                    **{
                        **event.__dict__,
                        "region": "Global",
                        "transformation_note": (
                            "Global mode reuses the US macro calendar in V1 because US releases remain the highest-signal cross-asset catalysts."
                        ),
                    }
                )
            unique[normalized.event_id] = normalized
        rows = sorted(unique.values(), key=lambda row: row.scheduled_at)
        return MacroEventsResult(events=rows[:limit], warnings=warnings)

    def _contact(self) -> str | None:
        if self.contact_user_agent is None:
            return None
        try:
            value = self.contact_user_agent()
        except Exception:
            return None
        text = " ".join(str(value or "").split())
        return text or None

    def _sources(self, region: str) -> list[_CalendarSource]:
        if region == "EU":
            return [
                _CalendarSource("ecb", "ECB Governing Council calendar", self.ECB_CALENDAR_URL, self._parse_ecb_calendar, extra_roots=True),
            ]
        return [
            _CalendarSource("fomc", "Federal Reserve FOMC calendar", self.FOMC_URL, self._parse_fomc_page),
            _CalendarSource(
                "cpi",
                "BLS CPI release schedule",
                self.CPI_URL,
                lambda html, ts: self._parse_bls_schedule(html, ts, title="CPI Release", category="inflation"),
                needs_contact=True,
            ),
            _CalendarSource(
                "ppi",
                "BLS PPI release schedule",
                self.PPI_URL,
                lambda html, ts: self._parse_bls_schedule(html, ts, title="PPI Release", category="inflation"),
                needs_contact=True,
            ),
            _CalendarSource(
                "employment",
                "BLS Employment Situation release schedule",
                self.EMPSIT_URL,
                lambda html, ts: self._parse_bls_schedule(html, ts, title="Employment Situation", category="growth", importance="high"),
                needs_contact=True,
            ),
            _CalendarSource(
                "jolts",
                "BLS JOLTS release schedule",
                self.JOLTS_URL,
                lambda html, ts: self._parse_bls_schedule(html, ts, title="JOLTS", category="growth"),
                needs_contact=True,
            ),
            _CalendarSource("bea_schedule", "BEA release schedule", self.BEA_SCHEDULE_URL, self._parse_bea_schedule),
        ]

    def _load_payload(
        self,
        source: _CalendarSource,
        *,
        contact: str | None,
        force_refresh: bool,
    ) -> tuple[str | None, datetime | None, str | None]:
        """Devuelve (html, retrieved_at, aviso). Sin html, el aviso explica qué falló."""

        cache_key = self.cache.make_key("macro", "events", source.source_id)
        failure_key = self.cache.make_key("macro", "events", source.source_id, "failure")
        if not force_refresh:
            fresh = _cached_calendar_payload(self.cache.get_json(cache_key, max_age=_MACRO_CALENDAR_TTL))
            if fresh is not None:
                return fresh[0], fresh[1], None
            recent_failure = self.cache.get_json(failure_key, max_age=_MACRO_CALENDAR_FAILURE_BACKOFF)
            if isinstance(recent_failure, dict) and recent_failure.get("error"):
                return self._stale_payload(source, cache_key, error=str(recent_failure["error"]))
        try:
            payload = self._fetch(source, contact=contact)
        except Exception as exc:
            error = _describe_calendar_error(exc, source)
            logger.info("Macro calendar source unavailable: source=%s url=%s error=%s", source.source_id, source.url, error)
            self.cache.set_json(failure_key, {"error": error})
            return self._stale_payload(source, cache_key, error=error)
        retrieved_at = now_utc()
        self.cache.set_json(cache_key, {"retrieved_at": retrieved_at.isoformat(), "payload": payload})
        return payload, retrieved_at, None

    def _fetch(self, source: _CalendarSource, *, contact: str | None) -> str:
        if self.fetch_text is not None:
            return self.fetch_text(source.url)
        # El contacto del usuario solo viaja a la fuente que lo exige.
        user_agent = f"{MACRO_CALENDAR_USER_AGENT} ({contact})" if source.needs_contact and contact else MACRO_CALENDAR_USER_AGENT
        return fetch_calendar_page(source.url, user_agent=user_agent, extra_roots=source.extra_roots)

    def _stale_payload(
        self,
        source: _CalendarSource,
        cache_key: str,
        *,
        error: str,
    ) -> tuple[str | None, datetime | None, str]:
        stale = _cached_calendar_payload(self.cache.get_json(cache_key, max_age=_MACRO_CALENDAR_STALE_LIMIT))
        if stale is None:
            return None, None, f"Macro calendar: {source.label} unavailable ({error})."
        payload, retrieved_at = stale
        return (
            payload,
            retrieved_at,
            f"Macro calendar: {source.label} refresh failed ({error}); showing the copy retrieved {retrieved_at:%Y-%m-%d %H:%M} UTC.",
        )

    def _parse_fomc_page(self, html: str, retrieved_at: datetime) -> list[MacroEventRecord]:
        section_pattern = re.compile(
            r'<h4><a id="[^"]+">(?P<year>\d{4}) FOMC Meetings</a></h4>(?P<body>.*?)(?=<div class="panel panel-default"><div class="panel-heading"><h4><a id="|$)',
            re.IGNORECASE | re.DOTALL,
        )
        # Las reuniones alternas llevan "fomc-meeting--shaded" delante de la clase de mes:
        # se busca la clase en cualquier posición o se pierde la mitad del calendario.
        row_pattern = re.compile(
            r'<div class="[^"]*\bfomc-meeting__month\b[^"]*"[^>]*>\s*<strong>(?P<month>[^<]+)</strong>\s*</div>\s*'
            r'<div class="[^"]*\bfomc-meeting__date\b[^"]*"[^>]*>(?P<date_text>[^<]+)</div>',
            re.IGNORECASE | re.DOTALL,
        )
        rows: list[MacroEventRecord] = []
        for section in section_pattern.finditer(html):
            year = int(section.group("year"))
            body = section.group("body")
            for match in row_pattern.finditer(body):
                month = _clean_html(match.group("month"))
                date_text = _clean_html(match.group("date_text"))
                # Una votación por escrito no es una reunión del calendario.
                if "notation vote" in date_text.lower():
                    continue
                # "*" marca las reuniones con Summary of Economic Projections.
                has_projections = "*" in date_text
                date_text = date_text.replace("*", "").strip()
                start_date = _parse_month_range(year, month, date_text)
                if start_date is None:
                    continue
                rows.append(
                    MacroEventRecord(
                        event_id=f"fomc:{start_date.date().isoformat()}",
                        title=f"FOMC Meeting ({month} {date_text}{', SEP' if has_projections else ''})",
                        category="policy",
                        region="US",
                        scheduled_at=start_date,
                        relative_label=None,
                        importance="high",
                        source_provider="federalreserve",
                        retrieved_at=retrieved_at,
                        origin="macro.events.fomc_calendar",
                    )
                )
        return rows

    def _parse_bls_schedule(
        self,
        html: str,
        retrieved_at: datetime,
        *,
        title: str,
        category: str,
        importance: str = "medium",
    ) -> list[MacroEventRecord]:
        row_pattern = re.compile(
            r"<tr[^>]*>\s*<td[^>]*>(?P<period>[^<]+)</td>\s*<td[^>]*>(?P<release_date>[^<]+)</td>\s*<td[^>]*>(?P<release_time>[^<]+)</td>",
            re.IGNORECASE | re.DOTALL,
        )
        rows: list[MacroEventRecord] = []
        for match in row_pattern.finditer(html):
            scheduled_at = _parse_bls_release_datetime(
                _clean_html(match.group("release_date")),
                _clean_html(match.group("release_time")),
            )
            if scheduled_at is None:
                continue
            rows.append(
                MacroEventRecord(
                    event_id=f"bls:{title.lower().replace(' ', '_')}:{scheduled_at.date().isoformat()}",
                    title=title,
                    category=category,
                    region="US",
                    scheduled_at=scheduled_at,
                    relative_label=_clean_html(match.group("period")),
                    importance=importance,
                    source_provider="bls",
                    retrieved_at=retrieved_at,
                    origin="macro.events.bls_schedule",
                )
            )
        return rows

    def _parse_bea_schedule(self, html: str, retrieved_at: datetime) -> list[MacroEventRecord]:
        # La agenda es una tabla: cabecera "Year 2026" y una fila por publicación, con el tipo
        # en la clase de la fila (press = News Release; data, visual y article no son
        # catalizadores macro). El año del título es el periodo de referencia, no el de la
        # publicación ("..., 2024" se publica en 2026), así que manda el de la cabecera.
        year_match = re.search(r"<th[^>]*>\s*Year\s+(?P<year>\d{4})\s*</th>", html, re.IGNORECASE)
        year = int(year_match.group("year")) if year_match else retrieved_at.year
        row_pattern = re.compile(
            r'<tr[^>]*class="[^"]*\bscheduled-releases-type-(?P<kind>[a-z]+)\b[^"]*"[^>]*>(?P<body>.*?)</tr>',
            re.IGNORECASE | re.DOTALL,
        )
        date_pattern = re.compile(r'<div class="release-date">(?P<date>[^<]+)</div>', re.IGNORECASE)
        time_pattern = re.compile(r"<small[^>]*class=\"[^\"]*text-muted[^\"]*\"[^>]*>(?P<time>[^<]+)</small>", re.IGNORECASE)
        title_pattern = re.compile(r'<td[^>]*class="[^"]*\brelease-title\b[^"]*"[^>]*>(?P<title>.*?)</td>', re.IGNORECASE | re.DOTALL)
        rows: list[MacroEventRecord] = []
        for match in row_pattern.finditer(html):
            if match.group("kind").lower() != "press":
                continue
            body = match.group("body")
            date_match = date_pattern.search(body)
            title_match = title_pattern.search(body)
            if date_match is None or title_match is None:
                continue
            title = " ".join(_clean_html(title_match.group("title")).split())
            if not title:
                continue
            time_match = time_pattern.search(body)
            time_text = _clean_html(time_match.group("time")) if time_match else ""
            scheduled_at = _parse_schedule_month_day(_clean_html(date_match.group("date")), year=year, time_text=time_text)
            if scheduled_at is None:
                continue
            category = _categorize_bea_title(title)
            rows.append(
                MacroEventRecord(
                    event_id=f"bea:{_slugify(title)}:{scheduled_at.date().isoformat()}",
                    title=title,
                    category=category,
                    region="US",
                    scheduled_at=scheduled_at,
                    relative_label=None,
                    importance=_bea_importance(title),
                    source_provider="bea",
                    retrieved_at=retrieved_at,
                    origin="macro.events.bea_schedule",
                    transformation_note=(
                        "BEA events are parsed from the official release schedule (News Releases only). Macro theme category and importance are inferred heuristically from the release title."
                    ),
                )
            )
        return rows

    def _parse_ecb_calendar(self, html: str, retrieved_at: datetime) -> list[MacroEventRecord]:
        pair_pattern = re.compile(r"<dt[^>]*>(?P<date>.*?)</dt>\s*<dd[^>]*>(?P<title>.*?)</dd>", re.IGNORECASE | re.DOTALL)
        meetings: list[tuple[datetime, str]] = []
        press_conferences: list[tuple[datetime, str]] = []
        for match in pair_pattern.finditer(html):
            title = " ".join(_clean_html(match.group("title")).split())
            if not title:
                continue
            lowered = title.lower()
            # "non-monetary policy meeting" contiene "monetary policy meeting" y no es una decisión.
            is_policy_meeting = "monetary policy meeting" in lowered and "non-monetary" not in lowered
            if not is_policy_meeting and "press conference" not in lowered:
                continue
            scheduled_at = _parse_day_month_year(_clean_html(match.group("date")))
            if scheduled_at is None:
                continue
            (meetings if is_policy_meeting else press_conferences).append((scheduled_at, title))
        # La rueda de prensa aparece también como entrada propia el día 2 de la reunión.
        meeting_days = {scheduled_at.date() for scheduled_at, _ in meetings}
        selected = meetings + [row for row in press_conferences if row[0].date() not in meeting_days]
        rows: list[MacroEventRecord] = []
        for scheduled_at, title in selected:
            rows.append(
                MacroEventRecord(
                    event_id=f"ecb:{_slugify(title)}:{scheduled_at.date().isoformat()}",
                    title=title,
                    category="policy",
                    region="EU",
                    scheduled_at=scheduled_at,
                    relative_label=None,
                    importance="high",
                    source_provider="ecb",
                    retrieved_at=retrieved_at,
                    origin="macro.events.ecb_calendar",
                )
            )
        return rows


def _clean_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", unescape(str(value or ""))).replace("\xa0", " ").strip()


def _list_get(values: list[Any], index: int) -> Any:
    return values[index] if 0 <= index < len(values) else None


_CENSUS_COUNTRY_CODE_MAP = {
    "1220": "CA",
    "2010": "MX",
    "5700": "CN",
    "4280": "DE",
    "5880": "JP",
    "4120": "GB",
    "4279": "FR",
    "4759": "IT",
    "4210": "NL",
    "5800": "KR",
    "5330": "IN",
    "5830": "TW",
    "3510": "BR",
    "6021": "AU",
    "4010": "ES",
}


def _census_partner_code(country_code: str, partner_name: str) -> str:
    mapped = _CENSUS_COUNTRY_CODE_MAP.get(str(country_code or "").strip())
    if mapped:
        return mapped
    words = re.findall(r"[A-Z0-9]+", str(partner_name or "").upper())
    if not words:
        return str(country_code or "").strip() or "NA"
    if len(words) == 1:
        return words[0][:3]
    return "".join(word[0] for word in words[:3])


def _title_country_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    acronyms = {"USA", "US", "UAE", "UK", "EU", "OECD", "USMCA", "NAFTA"}
    titled_words = []
    for word in text.split():
        cleaned = word.strip()
        titled_words.append(cleaned if cleaned.upper() in acronyms else cleaned.capitalize())
    return " ".join(titled_words)


def _strip_namespace(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone().replace(tzinfo=None)
    return parsed


def _parse_float(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text or text.upper() in {"N/A", "NA", "NULL", "NONE", "."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _clean_dbnomics_code(value: str) -> str:
    return str(value or "").strip().strip("/")


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _parse_dbnomics_period(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    quarter_match = re.fullmatch(r"(?P<year>\d{4})[- ]?Q(?P<quarter>[1-4])", text, flags=re.IGNORECASE)
    if quarter_match:
        month = (int(quarter_match.group("quarter")) - 1) * 3 + 1
        return datetime(int(quarter_match.group("year")), month, 1)
    semester_match = re.fullmatch(r"(?P<year>\d{4})[- ]?S(?P<semester>[1-2])", text, flags=re.IGNORECASE)
    if semester_match:
        month = 1 if semester_match.group("semester") == "1" else 7
        return datetime(int(semester_match.group("year")), month, 1)
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return _parse_datetime(text)


def _parse_month_range(year: int, month: str, date_text: str) -> datetime | None:
    digits = re.findall(r"\d{1,2}", date_text)
    if not digits:
        return None
    # Las reuniones a caballo entre dos meses llegan como "Apr/May 30-1": empieza en el primero.
    start_month = month.split("/")[0].strip().rstrip(".")
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(f"{start_month} {digits[0]} {year}", fmt)
        except ValueError:
            continue
    return None


def _parse_bls_release_date(value: str) -> datetime | None:
    cleaned = value.replace("Sept.", "Sep.").strip()
    for fmt in ("%b. %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def _parse_bls_release_datetime(date_value: str, time_value: str) -> datetime | None:
    release_date = _parse_bls_release_date(date_value)
    if release_date is None:
        return None
    cleaned_time = (
        str(time_value or "")
        .replace("a.m.", "AM")
        .replace("p.m.", "PM")
        .replace("a.m", "AM")
        .replace("p.m", "PM")
        .replace("am", "AM")
        .replace("pm", "PM")
        .strip()
    )
    cleaned_time = re.sub(r"\bET\b|\bEST\b|\bEDT\b", "", cleaned_time, flags=re.IGNORECASE).strip()
    for fmt in ("%I:%M %p", "%I %p"):
        try:
            parsed_time = datetime.strptime(cleaned_time, fmt)
            localized = release_date.replace(hour=parsed_time.hour, minute=parsed_time.minute, tzinfo=_US_EASTERN)
            return localized.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            continue
    return release_date


def _parse_schedule_month_day(
    value: str,
    *,
    year: int,
    time_text: str | None = None,
) -> datetime | None:
    cleaned = _clean_html(value).replace(".", "").strip()
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            parsed_date = datetime.strptime(f"{cleaned} {year}", fmt)
            if time_text:
                parsed_with_time = _parse_bls_release_datetime(parsed_date.strftime("%B %d, %Y"), time_text)
                if parsed_with_time is not None:
                    return parsed_with_time
            return parsed_date
        except ValueError:
            continue
    return None


def _parse_day_month_year(value: str) -> datetime | None:
    cleaned = _clean_html(value).replace(".", "").strip()
    # El calendario del BCE publica "28/10/2026"; versiones anteriores, "16 April 2026".
    for fmt in ("%d/%m/%Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def _cached_calendar_payload(cached: Any) -> tuple[str, datetime] | None:
    if not isinstance(cached, dict) or "payload" not in cached or "retrieved_at" not in cached:
        return None
    retrieved_at = _parse_datetime(cached["retrieved_at"])
    if retrieved_at is None:
        return None
    return str(cached["payload"]), retrieved_at


def _describe_calendar_error(exc: Exception, source: _CalendarSource) -> str:
    host = urlsplit(source.url).hostname or source.url
    if isinstance(exc, HTTPError):
        detail = f"HTTP {exc.code} from {host}"
        if exc.code == 403 and source.needs_contact:
            detail += "; bls.gov refused the automated request, check the contact name and email in Setup"
        return detail
    reason = getattr(exc, "reason", None)
    if isinstance(reason, ssl.SSLCertVerificationError) or isinstance(exc, ssl.SSLCertVerificationError):
        return f"TLS certificate for {host} could not be verified"
    text = str(reason if reason is not None else exc).strip() or exc.__class__.__name__
    return f"{exc.__class__.__name__}: {text[:200]} ({host})"


def _categorize_bea_title(title: str) -> str:
    lowered = title.lower()
    if any(keyword in lowered for keyword in ("price index", "prices", "personal income and outlays", "pce")):
        return "inflation"
    return "growth"


def _bea_importance(title: str) -> str:
    lowered = title.lower()
    if any(keyword in lowered for keyword in ("gross domestic product", "gdp", "personal income and outlays", "employment")):
        return "high"
    return "medium"


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", _clean_html(value).lower()).strip("-")
    return text or "event"


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
