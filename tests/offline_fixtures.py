"""Proveedores externos deterministas para los tests que necesitan datos.

La suite corre sin red (ver ``tests/conftest.py``): los adaptadores externos de un
runtime de test fallan como en una caída del proveedor. Los tests que validan flujos
con datos (screener y comparación de mercados de predicción, workspace de SITREP)
instalan aquí venues y curva del Tesoro sintéticos en lugar de depender de
Polymarket, Kalshi o home.treasury.gov.

Las series se generan relativas al momento de instalación para que las ventanas
"1w" y los umbrales de frescura del servicio se comporten igual en cualquier fecha.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError

from src.models.prediction_markets import (
    CalibrationSummary,
    PredictionMarketOutcome,
    PredictionMarketRecord,
    PredictionProbabilityPoint,
    WalletSummary,
)

OFFLINE_ORIGIN = "tests.offline_fixtures"

# (venue, id del proveedor, título, probabilidad base). Varios venues y contratos para
# que el screener, la comparación por pares y el SITREP tengan al menos tres filas.
_PREDICTION_CONTRACTS = (
    ("polymarket", "offline-fed-cut-december", "Will the Fed cut rates in December?", 0.58),
    ("polymarket", "offline-us-recession-2027", "Will the US enter a recession in 2027?", 0.31),
    ("kalshi", "OFFLINE-CPI-ABOVE-3", "Will CPI print above 3% next month?", 0.44),
    ("kalshi", "OFFLINE-10Y-ABOVE-4-5", "Will the 10Y Treasury yield close above 4.5%?", 0.37),
)
_HISTORY_HOURS = 6 * 24


def _hour_floor(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


class OfflinePredictionVenueAdapter:
    """Venue sin capacidad de ventana propia: el servicio recorta la serie completa."""

    def __init__(self, provider: str, *, now: datetime | None = None) -> None:
        self.provider = provider
        self.now = _hour_floor(now or datetime.now(timezone.utc))
        self.records = [
            self._record(provider_market_id, title, probability)
            for venue, provider_market_id, title, probability in _PREDICTION_CONTRACTS
            if venue == provider
        ]

    def _record(self, provider_market_id: str, title: str, probability: float) -> PredictionMarketRecord:
        market_id = f"{self.provider}:{provider_market_id}"
        outcomes = [
            PredictionMarketOutcome(
                outcome_id=f"{market_id}:yes",
                label="Yes",
                probability=probability,
                token_id=f"{provider_market_id}-yes" if self.provider == "polymarket" else None,
                source_provider=self.provider,
                retrieved_at=self.now,
                origin=OFFLINE_ORIGIN,
            ),
            PredictionMarketOutcome(
                outcome_id=f"{market_id}:no",
                label="No",
                probability=1 - probability,
                token_id=f"{provider_market_id}-no" if self.provider == "polymarket" else None,
                source_provider=self.provider,
                retrieved_at=self.now,
                origin=OFFLINE_ORIGIN,
                transformation_note="Derived as one minus the normalized Yes probability.",
            ),
        ]
        return PredictionMarketRecord(
            market_id=market_id,
            venue=self.provider,
            title=title,
            subtitle=None,
            description=title,
            status="open",
            category="Economy",
            event_id=f"{self.provider}:event:{provider_market_id}",
            event_title=title,
            series_id=f"{self.provider}:series:macro",
            series_title="Macro",
            provider_market_id=provider_market_id,
            provider_condition_id=f"condition-{provider_market_id}" if self.provider == "polymarket" else None,
            provider_event_id=f"event-{provider_market_id}",
            provider_series_id="series-macro",
            slug=provider_market_id.lower(),
            end_time=self.now + timedelta(days=45),
            open_time=self.now - timedelta(days=60),
            close_time=None,
            current_probability=probability,
            probability_label="Yes",
            volume=250_000.0,
            volume_24h=12_000.0,
            liquidity=40_000.0,
            open_interest=90_000.0,
            best_bid=probability - 0.01,
            best_ask=probability + 0.01,
            spread=0.02,
            recent_price_change=0.02,
            resolved_probability=None,
            resolution_outcome=None,
            image_url=None,
            resolution_source="Offline test rulebook",
            outcomes=outcomes,
            tags=["Economy"],
            source_provider=self.provider,
            retrieved_at=self.now,
            origin=OFFLINE_ORIGIN,
            transformation_note="Deterministic offline contract for hermetic tests.",
        )

    def list_markets(self, *, status="open", limit=50, force_refresh=False, query="", category=None):
        del status, force_refresh, query, category
        return list(self.records[:limit])

    def get_market(self, provider_market_id: str) -> PredictionMarketRecord | None:
        return next((row for row in self.records if row.provider_market_id == provider_market_id), None)

    def get_history(self, market: PredictionMarketRecord) -> list[PredictionProbabilityPoint]:
        # Puntos horarios alineados en todos los contratos para que la comparación
        # tenga solape; la forma sinusoidal da correlaciones y spreads no triviales.
        seed = sum(ord(char) for char in market.market_id) % 7
        base = market.current_probability or 0.5
        start = self.now - timedelta(hours=_HISTORY_HOURS - 1)
        points = []
        for index in range(_HISTORY_HOURS):
            value = base + 0.04 * math.sin((index + seed) / 9.0) + 0.0005 * (index - _HISTORY_HOURS)
            points.append(
                PredictionProbabilityPoint(
                    timestamp=start + timedelta(hours=index),
                    probability=round(min(0.98, max(0.02, value)), 4),
                    volume=500.0 + index,
                    source_provider=self.provider,
                    retrieved_at=self.now,
                    origin=OFFLINE_ORIGIN,
                )
            )
        return points

    def get_wallet_summary(self, market: PredictionMarketRecord) -> WalletSummary:
        return WalletSummary(
            market_id=market.market_id,
            venue=self.provider,
            concentration_hhi=None,
            top_participant_share=None,
            total_trades=0,
            total_notional=0.0,
        )

    def list_event_markets(self, market: PredictionMarketRecord, *, limit: int = 12) -> list[PredictionMarketRecord]:
        del market, limit
        return []

    def build_calibration_summary(self, *, sample_size: int = 30) -> CalibrationSummary:
        del sample_size
        return CalibrationSummary(venue=self.provider, sample_size=0)


class OfflineTreasuryCurveAdapter:
    """Curva nominal diaria del Tesoro (claves naive en UTC, como el adaptador real)."""

    def __init__(self, *, now: datetime | None = None) -> None:
        reference = now or datetime.now(timezone.utc)
        self.now = reference.astimezone(timezone.utc).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)

    def get_curve_history(self, curve_kind: str, *, years: list[int], ttl: timedelta, force_refresh: bool = False):
        del curve_kind, years, ttl, force_refresh
        history: dict[datetime, dict[str, float]] = {}
        for days_ago in range(1, 181):
            stamp = self.now - timedelta(days=days_ago)
            if stamp.weekday() >= 5:
                continue
            drift = days_ago / 180.0
            history[stamp] = {
                "3M": round(4.30 + 0.40 * drift, 4),
                "2Y": round(3.90 + 0.35 * drift, 4),
                "5Y": round(3.85 + 0.25 * drift, 4),
                "10Y": round(4.10 + 0.15 * drift, 4),
                "30Y": round(4.55 + 0.10 * drift, 4),
            }
        return history, self.now


# Extractos de los calendarios oficiales tal como se sirvieron el 2026-10-22 (ver la
# cabecera de cada fichero). Cubren los formatos que rompieron los parsers: filas
# sombreadas de la Fed, la tabla de BEA con cabecera "Year 2026" y las fechas DD/MM/AAAA
# del BCE.
MACRO_CALENDAR_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "macro_calendars"
MACRO_CALENDAR_CAPTURED_AT = datetime(2026, 10, 22, 13, 0, 0)
_MACRO_CALENDAR_FIXTURES = {
    "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm": "fomccalendars.htm",
    "https://www.bls.gov/schedule/news_release/cpi.htm": "cpi.htm",
    "https://www.bls.gov/schedule/news_release/ppi.htm": "ppi.htm",
    "https://www.bls.gov/schedule/news_release/empsit.htm": "empsit.htm",
    "https://www.bls.gov/schedule/news_release/jolts.htm": "jolts.htm",
    "https://www.bea.gov/news/schedule": "bea_schedule.html",
    "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html": "ecb_calendar.html",
}


def macro_calendar_fixture(url: str) -> str:
    """HTML guardado de un calendario oficial; una URL desconocida responde 404 como el sitio."""

    name = _MACRO_CALENDAR_FIXTURES.get(url)
    if name is None:
        raise HTTPError(url, 404, "Not Found", hdrs=None, fp=None)
    return (MACRO_CALENDAR_FIXTURES_DIR / name).read_text(encoding="utf-8")


def offline_prediction_adapters(*, now: datetime | None = None) -> dict[str, OfflinePredictionVenueAdapter]:
    return {venue: OfflinePredictionVenueAdapter(venue, now=now) for venue in ("kalshi", "polymarket")}


def install_offline_market_fixtures(runtime) -> None:
    """Sustituye en el runtime los venues de predicción y la curva del Tesoro.

    Se modifican los servicios existentes (no se reemplazan) porque SITREP, Macro y
    Copilot comparten las mismas instancias.
    """
    runtime.prediction_market_service.adapters = offline_prediction_adapters()
    runtime.macro_service.treasury_adapter = OfflineTreasuryCurveAdapter()
