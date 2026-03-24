from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any, Callable
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from src.models.macro import MacroEventRecord, MacroSeriesPoint
from src.services.cache import CacheService
from src.services.fred import FredClient
from src.services.market_data import MarketDataService
from src.utils.time import now_utc


TextFetcher = Callable[[str], str]
_US_EASTERN = ZoneInfo("America/New_York")


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
    EMPSIT_URL = "https://www.bls.gov/schedule/news_release/empsit.htm"

    def __init__(self, cache: CacheService, fetch_text: TextFetcher | None = None) -> None:
        self.cache = cache
        self.fetch_text = fetch_text or default_text_fetcher

    def list_events(
        self,
        *,
        region: str,
        as_of: datetime,
        force_refresh: bool = False,
        limit: int = 8,
        ) -> list[MacroEventRecord]:
        if region not in {"US", "Global"}:
            return []
        normalized_as_of = _as_utc_naive(as_of)
        ttl = timedelta(hours=12)
        events: list[MacroEventRecord] = []
        for source_name, url, parser in (
            ("fomc", self.FOMC_URL, self._parse_fomc_page),
            ("cpi", self.CPI_URL, lambda html, ts: self._parse_bls_schedule(html, ts, title="CPI Release", category="inflation")),
            (
                "employment",
                self.EMPSIT_URL,
                lambda html, ts: self._parse_bls_schedule(html, ts, title="Employment Situation", category="growth"),
            ),
        ):
            cache_key = self.cache.make_key("macro", "events", source_name)
            cached: Any = None
            if not force_refresh:
                cached = self.cache.get_json(cache_key, max_age=ttl)
            if isinstance(cached, dict) and "payload" in cached and "retrieved_at" in cached:
                payload = str(cached["payload"])
                source_retrieved_at = _parse_datetime(cached["retrieved_at"]) or now_utc()
            else:
                payload = self.fetch_text(url)
                source_retrieved_at = now_utc()
                self.cache.set_json(
                    cache_key,
                    {
                        "retrieved_at": source_retrieved_at.isoformat(),
                        "payload": payload,
                    },
                )
            events.extend(parser(payload, source_retrieved_at))

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
        return rows[:limit]

    def _parse_fomc_page(self, html: str, retrieved_at: datetime) -> list[MacroEventRecord]:
        section_pattern = re.compile(
            r'<h4><a id="[^"]+">(?P<year>\d{4}) FOMC Meetings</a></h4>(?P<body>.*?)(?=<div class="panel panel-default"><div class="panel-heading"><h4><a id="|$)',
            re.IGNORECASE | re.DOTALL,
        )
        row_pattern = re.compile(
            r'<div class="fomc-meeting__month[^>]*><strong>(?P<month>[A-Za-z]+)</strong></div>\s*'
            r'<div class="fomc-meeting__date[^>]*>(?P<date_text>[^<]+)</div>',
            re.IGNORECASE | re.DOTALL,
        )
        rows: list[MacroEventRecord] = []
        for section in section_pattern.finditer(html):
            year = int(section.group("year"))
            body = section.group("body")
            for match in row_pattern.finditer(body):
                month = match.group("month")
                date_text = _clean_html(match.group("date_text"))
                start_date = _parse_month_range(year, month, date_text)
                if start_date is None:
                    continue
                rows.append(
                    MacroEventRecord(
                        event_id=f"fomc:{start_date.date().isoformat()}",
                        title=f"FOMC Meeting ({month} {date_text})",
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
                    importance="medium",
                    source_provider="bls",
                    retrieved_at=retrieved_at,
                    origin="macro.events.bls_schedule",
                )
            )
        return rows


def _clean_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", unescape(str(value or ""))).replace("\xa0", " ").strip()


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
    if not text or text.upper() == "N/A":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_month_range(year: int, month: str, date_text: str) -> datetime | None:
    digits = re.findall(r"\d{1,2}", date_text)
    if not digits:
        return None
    try:
        return datetime.strptime(f"{month} {digits[0]} {year}", "%B %d %Y")
    except ValueError:
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


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
