from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.macro_service import MacroService, MacroSnapshotRequest
from src.application.runtime import build_runtime
from src.models.macro import MacroEventRecord, MacroSeriesPoint
from src.services.cache import CacheService
from src.services.fred import FredObservation
from src.services.macro_adapters import FredMacroAdapter, TreasuryCurveAdapter, USMacroEventsAdapter


NOW = datetime(2026, 3, 20, 12, 0, 0)
FRED_RETRIEVED_AT = datetime(2026, 3, 20, 9, 0, 0)
EVENTS_RETRIEVED_AT = datetime(2026, 3, 20, 10, 0, 0)
TREASURY_RETRIEVED_AT = datetime(2026, 3, 20, 11, 0, 0)


def test_fred_macro_adapter_normalizes_series_points_and_provenance(tmp_path):
    class FakeFredClient:
        def get_series_observations(self, series_id: str, **kwargs):
            assert series_id == "DGS10"
            return [
                FredObservation(timestamp=datetime(2026, 3, 18, 0, 0, 0), value=4.21),
                FredObservation(timestamp=datetime(2026, 3, 19, 0, 0, 0), value=4.18),
            ], FRED_RETRIEVED_AT

    adapter = FredMacroAdapter(cache=CacheService(base_dir=tmp_path / "cache"), client=FakeFredClient())

    points, retrieved_at = adapter.get_series(
        "DGS10",
        start=datetime(2026, 3, 1, 0, 0, 0),
        end=datetime(2026, 3, 20, 0, 0, 0),
        ttl=timedelta(hours=24),
    )

    assert retrieved_at == FRED_RETRIEVED_AT
    assert [point.value for point in points] == [4.21, 4.18]
    assert all(point.source_provider == "fred" for point in points)
    assert all(point.retrieved_at == FRED_RETRIEVED_AT for point in points)
    assert all(point.origin == "fred.series.observations:DGS10" for point in points)


def test_treasury_curve_adapter_parses_curve_xml_and_preserves_cached_retrieval_time(tmp_path, monkeypatch):
    calls: list[str] = []
    xml_payload = """
    <feed xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata" xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices">
      <entry>
        <content>
          <m:properties>
            <d:NEW_DATE>2026-03-12T00:00:00</d:NEW_DATE>
            <d:BC_3MONTH>4.80</d:BC_3MONTH>
            <d:BC_2YEAR>4.20</d:BC_2YEAR>
            <d:BC_5YEAR>4.10</d:BC_5YEAR>
            <d:BC_10YEAR>4.00</d:BC_10YEAR>
            <d:BC_30YEAR>4.25</d:BC_30YEAR>
          </m:properties>
        </content>
      </entry>
    </feed>
    """.strip()

    monkeypatch.setattr("src.services.macro_adapters.now_utc", lambda: TREASURY_RETRIEVED_AT)

    def fake_fetch_text(url: str) -> str:
        calls.append(url)
        return xml_payload

    adapter = TreasuryCurveAdapter(CacheService(base_dir=tmp_path / "cache"), fetch_text=fake_fetch_text)

    first_rows, first_retrieved_at = adapter.get_curve_history(
        "daily_treasury_yield_curve",
        years=[2026],
        ttl=timedelta(hours=6),
    )
    second_rows, second_retrieved_at = adapter.get_curve_history(
        "daily_treasury_yield_curve",
        years=[2026],
        ttl=timedelta(hours=6),
    )

    assert len(calls) == 1
    assert first_retrieved_at == TREASURY_RETRIEVED_AT
    assert second_retrieved_at == TREASURY_RETRIEVED_AT
    assert first_rows == second_rows
    assert first_rows[datetime(2026, 3, 12, 0, 0, 0)]["10Y"] == 4.00


def test_us_macro_events_adapter_parses_official_sources_and_marks_global_transform(tmp_path, monkeypatch):
    monkeypatch.setattr("src.services.macro_adapters.now_utc", lambda: EVENTS_RETRIEVED_AT)

    fomc_html = """
    <h4><a id="fomc2026">2026 FOMC Meetings</a></h4>
    <div class="fomc-meeting__month"><strong>May</strong></div>
    <div class="fomc-meeting__date">6-7</div>
    """.strip()
    cpi_html = """
    <table>
      <tr><td>April 2026</td><td>May 12, 2026</td><td>8:30 AM</td></tr>
    </table>
    """.strip()
    employment_html = """
    <table>
      <tr><td>April 2026</td><td>May 1, 2026</td><td>8:30 AM</td></tr>
    </table>
    """.strip()

    def fake_fetch_text(url: str) -> str:
        if url.endswith("fomccalendars.htm"):
            return fomc_html
        if url.endswith("cpi.htm"):
            return cpi_html
        if url.endswith("empsit.htm"):
            return employment_html
        raise AssertionError(f"Unexpected URL: {url}")

    adapter = USMacroEventsAdapter(CacheService(base_dir=tmp_path / "cache"), fetch_text=fake_fetch_text)

    us_rows = adapter.list_events(region="US", as_of=datetime(2026, 4, 15, 0, 0, 0))
    global_rows = adapter.list_events(region="Global", as_of=datetime(2026, 4, 15, 0, 0, 0))

    assert [row.event_id for row in us_rows] == [
        "bls:employment_situation:2026-05-01",
        "fomc:2026-05-06",
        "bls:cpi_release:2026-05-12",
    ]
    assert us_rows[0].scheduled_at == datetime(2026, 5, 1, 8, 30, 0)
    assert us_rows[2].scheduled_at == datetime(2026, 5, 12, 8, 30, 0)
    assert all(row.retrieved_at == EVENTS_RETRIEVED_AT for row in us_rows)
    assert all(row.region == "Global" for row in global_rows)
    assert all(row.transformation_note for row in global_rows)


def test_us_macro_events_adapter_keeps_same_day_future_bls_release(tmp_path, monkeypatch):
    monkeypatch.setattr("src.services.macro_adapters.now_utc", lambda: EVENTS_RETRIEVED_AT)

    fomc_html = """
    <h4><a id="fomc2026">2026 FOMC Meetings</a></h4>
    <div class="fomc-meeting__month"><strong>May</strong></div>
    <div class="fomc-meeting__date">6-7</div>
    """.strip()
    cpi_html = """
    <table>
      <tr><td>April 2026</td><td>May 12, 2026</td><td>8:30 AM</td></tr>
    </table>
    """.strip()
    employment_html = """
    <table>
      <tr><td>April 2026</td><td>May 1, 2026</td><td>8:30 AM</td></tr>
    </table>
    """.strip()

    def fake_fetch_text(url: str) -> str:
        if url.endswith("fomccalendars.htm"):
            return fomc_html
        if url.endswith("cpi.htm"):
            return cpi_html
        if url.endswith("empsit.htm"):
            return employment_html
        raise AssertionError(f"Unexpected URL: {url}")

    adapter = USMacroEventsAdapter(CacheService(base_dir=tmp_path / "cache"), fetch_text=fake_fetch_text)

    rows = adapter.list_events(region="US", as_of=datetime(2026, 5, 1, 7, 0, 0))

    assert [row.event_id for row in rows] == [
        "bls:employment_situation:2026-05-01",
        "fomc:2026-05-06",
        "bls:cpi_release:2026-05-12",
    ]
    assert rows[0].scheduled_at == datetime(2026, 5, 1, 8, 30, 0)


def test_macro_service_snapshot_and_divergences_preserve_provenance(monkeypatch):
    monkeypatch.setattr("src.application.macro_service.now_utc", lambda: NOW)

    service = _build_macro_service()

    snapshot = service.get_snapshot(MacroSnapshotRequest(region="US", timeframe="3M", theme="all"))
    cpi_history = service.get_series_history("us-cpi-yoy", timeframe="1Y")
    slope_history = service.get_series_history("us-2s10s-slope", timeframe="1Y")
    divergences = service.get_divergences(MacroSnapshotRequest(region="US", timeframe="3M", theme="all"))

    assert snapshot.source_provider == "fred"
    assert snapshot.transformation_note is not None
    assert snapshot.retrieved_at == TREASURY_RETRIEVED_AT
    assert {card.title for card in snapshot.snapshot_cards} >= {
        "Growth Context",
        "Inflation Context",
        "Policy Context",
        "Curve Shape",
        "Real Yields / Breakevens",
    }
    assert snapshot.rates_policy is not None
    assert len(snapshot.rates_policy.curve_nodes) == 5
    assert snapshot.rates_policy.transformation_note is not None
    assert cpi_history is not None
    assert cpi_history.transformation_note is not None
    assert cpi_history.points
    assert all(point.transformation_note == cpi_history.transformation_note for point in cpi_history.points)
    assert slope_history is not None
    assert slope_history.transformation_note is not None
    assert slope_history.points
    assert all(point.transformation_note == slope_history.transformation_note for point in slope_history.points)
    assert divergences
    assert divergences[0].theme == "inflation"
    assert divergences[0].score >= divergences[-1].score
    assert all(row.transformation_note is not None for row in divergences)


def test_macro_service_applies_active_timeframe_to_snapshot_cross_asset_and_divergence_metrics(monkeypatch):
    monkeypatch.setattr("src.application.macro_service.now_utc", lambda: NOW)

    service = _build_macro_service()

    snapshot_1m = service.get_snapshot(MacroSnapshotRequest(region="US", timeframe="1M", theme="all"))
    snapshot_1y = service.get_snapshot(MacroSnapshotRequest(region="US", timeframe="1Y", theme="all"))

    dollar_card_1m = next(card for card in snapshot_1m.snapshot_cards if card.card_id == "dollar")
    dollar_card_1y = next(card for card in snapshot_1y.snapshot_cards if card.card_id == "dollar")
    assert dollar_card_1m.metrics[0].delta_value != dollar_card_1y.metrics[0].delta_value

    rates_metric_1m = next(metric for metric in snapshot_1m.rates_policy.policy_metrics if metric.series_id == "us-2y-yield")
    rates_metric_1y = next(metric for metric in snapshot_1y.rates_policy.policy_metrics if metric.series_id == "us-2y-yield")
    assert rates_metric_1m.delta_value != rates_metric_1y.delta_value

    inflation_1m = next(row for row in snapshot_1m.cross_asset if row.theme == "inflation")
    inflation_1y = next(row for row in snapshot_1y.cross_asset if row.theme == "inflation")
    dollar_1m = next(metric for metric in inflation_1m.metrics if metric.series_id == "us-dollar-broad")
    dollar_1y = next(metric for metric in inflation_1y.metrics if metric.series_id == "us-dollar-broad")
    assert dollar_1m.delta_value != dollar_1y.delta_value

    divergence_1m = service.get_divergences(MacroSnapshotRequest(region="US", timeframe="1M", theme="inflation"))
    divergence_1y = service.get_divergences(MacroSnapshotRequest(region="US", timeframe="1Y", theme="inflation"))
    assert divergence_1m[0].metrics[0].delta_value != divergence_1y[0].metrics[0].delta_value


def test_macro_service_uses_frequency_aware_yoy_lag_for_quarterly_series(monkeypatch):
    monkeypatch.setattr("src.application.macro_service.now_utc", lambda: NOW)

    service = _build_macro_service()
    history = service.get_series_history("us-real-gdp-yoy", timeframe="1Y")
    raw_gdp_points = _build_series_map()["GDPC1"]

    assert history is not None
    expected_latest_yoy = ((raw_gdp_points[-1].value / raw_gdp_points[-5].value) - 1.0) * 100.0
    assert history.points
    assert history.points[-1].value == expected_latest_yoy


def test_macro_api_routes_expose_snapshot_history_divergences_and_events(tmp_path, monkeypatch):
    monkeypatch.setattr("src.application.macro_service.now_utc", lambda: NOW)

    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    runtime.macro_service = _build_macro_service()
    client = TestClient(create_app(runtime))
    try:
        snapshot_response = client.post(
            "/macro/snapshot",
            json={"region": "Global", "timeframe": "6M", "theme": "inflation", "comparison_region": "US"},
        )
        history_response = client.get("/macro/series/us-cpi-yoy/history", params={"region": "US", "timeframe": "1Y"})
        divergence_response = client.post("/macro/divergences", json={"region": "US", "timeframe": "3M", "theme": "all"})
        events_response = client.get("/macro/events", params={"region": "Global"})
        missing_response = client.get("/macro/series/unknown-series/history")

        assert snapshot_response.status_code == 200
        snapshot_payload = snapshot_response.json()
        assert snapshot_payload["region"] == "Global"
        assert snapshot_payload["comparison_region"] is None
        assert any("light comparative lens" in warning for warning in snapshot_payload["warnings"])
        assert any("ignored" in warning for warning in snapshot_payload["warnings"])
        assert snapshot_payload["rates_policy"]["curve_nodes"][0]["transformation_note"] is not None
        assert snapshot_payload["snapshot_cards"][0]["source_provider"]

        assert history_response.status_code == 200
        history_payload = history_response.json()
        assert history_payload["series_id"] == "us-cpi-yoy"
        assert history_payload["transformation_note"] is not None
        assert history_payload["points"][0]["transformation_note"] is not None

        assert divergence_response.status_code == 200
        divergence_payload = divergence_response.json()
        assert divergence_payload["divergences"][0]["theme"] == "inflation"
        assert divergence_payload["divergences"][0]["transformation_note"] is not None

        assert events_response.status_code == 200
        events_payload = events_response.json()
        assert events_payload["region"] == "Global"
        assert events_payload["events"][0]["region"] == "Global"
        assert events_payload["events"][0]["transformation_note"] is not None

        assert missing_response.status_code == 404
    finally:
        runtime.shutdown()


@dataclass
class _FakeFredMacroAdapter:
    series_map: dict[str, list[MacroSeriesPoint]]

    def get_series(
        self,
        provider_series_id: str,
        *,
        start: datetime,
        end: datetime,
        ttl: timedelta,
        force_refresh: bool = False,
    ) -> tuple[list[MacroSeriesPoint], datetime]:
        rows = [
            point
            for point in self.series_map[provider_series_id]
            if start <= point.timestamp <= end
        ]
        return rows, FRED_RETRIEVED_AT


@dataclass
class _FakeTreasuryCurveAdapter:
    def get_curve_history(
        self,
        curve_kind: str,
        *,
        years: list[int],
        ttl: timedelta,
        force_refresh: bool = False,
    ) -> tuple[dict[datetime, dict[str, float]], datetime]:
        return {
            NOW - timedelta(days=8): {"3M": 4.95, "2Y": 4.48, "5Y": 4.22, "10Y": 4.15, "30Y": 4.35},
            NOW - timedelta(days=1): {"3M": 4.72, "2Y": 4.12, "5Y": 3.98, "10Y": 3.92, "30Y": 4.11},
        }, TREASURY_RETRIEVED_AT


@dataclass
class _FakeEventsAdapter:
    def list_events(
        self,
        *,
        region: str,
        as_of: datetime,
        force_refresh: bool = False,
        limit: int = 8,
    ) -> list[MacroEventRecord]:
        rows = [
            MacroEventRecord(
                event_id="bls:employment_situation:2026-04-03",
                title="Employment Situation",
                category="growth",
                region="US",
                scheduled_at=datetime(2026, 4, 3, 0, 0, 0),
                relative_label="March 2026",
                importance="medium",
                source_provider="bls",
                retrieved_at=EVENTS_RETRIEVED_AT,
                origin="macro.events.bls_schedule",
            ),
            MacroEventRecord(
                event_id="fomc:2026-04-29",
                title="FOMC Meeting (April 29-30)",
                category="policy",
                region="US",
                scheduled_at=datetime(2026, 4, 29, 0, 0, 0),
                relative_label=None,
                importance="high",
                source_provider="federalreserve",
                retrieved_at=EVENTS_RETRIEVED_AT,
                origin="macro.events.fomc_calendar",
            ),
            MacroEventRecord(
                event_id="bls:cpi_release:2026-05-12",
                title="CPI Release",
                category="inflation",
                region="US",
                scheduled_at=datetime(2026, 5, 12, 0, 0, 0),
                relative_label="April 2026",
                importance="medium",
                source_provider="bls",
                retrieved_at=EVENTS_RETRIEVED_AT,
                origin="macro.events.bls_schedule",
            ),
        ]
        filtered = [row for row in rows if row.scheduled_at >= as_of]
        if region == "Global":
            return [
                MacroEventRecord(
                    **{
                        **row.__dict__,
                        "region": "Global",
                        "transformation_note": "Global mode reuses the US macro calendar in V1 because US releases remain the highest-signal cross-asset catalysts.",
                    }
                )
                for row in filtered[:limit]
            ]
        return filtered[:limit]


def _build_macro_service() -> MacroService:
    return MacroService(
        fred_adapter=_FakeFredMacroAdapter(_build_series_map()),
        treasury_adapter=_FakeTreasuryCurveAdapter(),
        events_adapter=_FakeEventsAdapter(),
    )


def _build_series_map() -> dict[str, list[MacroSeriesPoint]]:
    return {
        "DFF": _daily_points([400, 140, 60, 30, 0], [5.10, 4.75, 4.82, 4.70, 4.50], provider_series_id="DFF"),
        "DGS2": _daily_points([400, 140, 60, 30, 0], [5.20, 4.90, 4.95, 4.70, 4.35], provider_series_id="DGS2"),
        "DGS10": _daily_points([400, 140, 60, 30, 0], [4.95, 4.60, 4.58, 4.45, 4.20], provider_series_id="DGS10"),
        "DGS30": _daily_points([400, 140, 60, 30, 0], [4.98, 4.70, 4.68, 4.55, 4.35], provider_series_id="DGS30"),
        "DFII10": _daily_points([400, 140, 60, 30, 0], [2.35, 2.20, 2.18, 2.05, 1.85], provider_series_id="DFII10"),
        "T5YIE": _daily_points([400, 140, 60, 30, 0], [2.55, 2.10, 2.18, 2.24, 2.45], provider_series_id="T5YIE"),
        "T10YIE": _daily_points([400, 140, 60, 30, 0], [2.60, 2.20, 2.28, 2.32, 2.50], provider_series_id="T10YIE"),
        "UNRATE": _daily_points([150, 60, 0], [4.20, 4.15, 4.10], provider_series_id="UNRATE"),
        "DTWEXBGS": _daily_points([400, 140, 60, 30, 0], [114.0, 118.0, 119.5, 121.0, 124.0], provider_series_id="DTWEXBGS"),
        "BAMLH0A0HYM2": _daily_points([400, 140, 60, 30, 0], [3.20, 3.70, 3.75, 3.90, 4.40], provider_series_id="BAMLH0A0HYM2"),
        "CPIAUCSL": _periodic_points(18, step_days=30, start_value=100.0, increment=1.0, provider_series_id="CPIAUCSL"),
        "CPILFESL": _periodic_points(18, step_days=30, start_value=101.0, increment=0.8, provider_series_id="CPILFESL"),
        "GDPC1": _periodic_points(18, step_days=90, start_value=19_000.0, increment=120.0, provider_series_id="GDPC1"),
        "PAYEMS": _periodic_points(18, step_days=30, start_value=150.0, increment=0.7, provider_series_id="PAYEMS"),
    }


def _daily_points(ages: list[int], values: list[float], *, provider_series_id: str) -> list[MacroSeriesPoint]:
    return [
        MacroSeriesPoint(
            timestamp=NOW - timedelta(days=age),
            value=value,
            source_provider="fred",
            retrieved_at=FRED_RETRIEVED_AT,
            origin=f"fred.series.observations:{provider_series_id}",
        )
        for age, value in sorted(zip(ages, values), reverse=True)
    ]


def _periodic_points(
    periods: int,
    *,
    step_days: int,
    start_value: float,
    increment: float,
    provider_series_id: str,
) -> list[MacroSeriesPoint]:
    rows: list[MacroSeriesPoint] = []
    for index in range(periods):
        remaining = periods - index - 1
        rows.append(
            MacroSeriesPoint(
                timestamp=NOW - timedelta(days=remaining * step_days),
                value=start_value + (index * increment),
                source_provider="fred",
                retrieved_at=FRED_RETRIEVED_AT,
                origin=f"fred.series.observations:{provider_series_id}",
            )
        )
    return rows
