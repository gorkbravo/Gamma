"""Observable registry v1 for Ideas criteria (Workstream 12, checkpoint I2).

Each observable is built only on an existing read path, through the services
the runtime already composes:

=====================  ==================================================  =========
Observable             Read path                                           Needs TWS
=====================  ==================================================  =========
equity_close           ``ResearchDataProvider.load_instrument_history_result``  No
macro_series           ``MacroService.get_series_history_result`` (FRED)   No (FX: yes)
prediction_probability ``PredictionMarketService`` detail and history      No
crypto_price           ``CryptoService.get_price_history`` (CoinGecko)     No
commodity_price        ``CommoditiesService.get_price_history``            Partly
commodity_spread       ``CommoditiesService.get_spreads`` (level only)     Partly
macro_event            ``MacroService.get_events_result`` (calendar)       No
calendar_date          Gamma's clock                                       No
script_signal          Latest completed run of the accepted revision       No
option_atm_iv          ``IVService`` snapshot                              Yes
option_skew            ``IVService`` snapshot (same wing rule as Options)  Yes
=====================  ==================================================  =========

Every read is read-only and returns an ``ObservableReading``. A missing
dependency (Trader Workstation closed, no key, provider failure) is
``unavailable`` with the reason, never a value. The registry orders
observables for the reference retail user: the ones that need no TWS first.
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from typing import Any

from src.application.idea_criteria import ObservablePoint, ObservableReading, describe_criterion
from src.models.ideas import CRITERION_CONDITIONS, IdeaValidationError, ObservableRef
from src.models.provenance import ProvenanceRecord
from src.utils.time import now_utc

LEVEL_CONDITIONS = ("above", "below")
SERIES_CONDITIONS = ("above", "below", "crosses_above", "crosses_below", "change_over_window")
ALL_CADENCES = ("on_open", "daily_close", "intraday")
TWS_DEPENDENCY = "Needs Trader Workstation"
# I3d: observables whose intraday reading is the latest IBKR mark of a tracked leg.
INTRADAY_MARK_OBSERVABLES = ("equity_close", "crypto_price")

# Spread ids the Commodities service builds (calendar spreads need IBKR curves).
COMMODITY_SPREADS: tuple[tuple[str, str], ...] = (
    ("wti-m1-m2", "WTI M1-M2"),
    ("wti-m1-m6", "WTI M1-M6"),
    ("brent-m1-m2", "Brent M1-M2"),
    ("henry_hub-m1-m2", "Henry Hub M1-M2"),
    ("gold-silver-ratio", "Gold / Silver"),
    ("gold-platinum-ratio", "Gold / Platinum"),
    ("copper-gold-ratio", "Copper / Gold"),
    ("copper-aluminum-spread", "Copper - Aluminum"),
    ("gasoline-crack", "Gasoline 1-1 Crack Proxy"),
    ("heating-oil-crack", "Distillate 1-1 Crack Proxy"),
    ("two-one-one-crack", "2-1-1 Crack Proxy"),
    ("three-two-one-crack", "3-2-1 Crack Proxy"),
)
PREDICTION_VENUES = ("polymarket", "kalshi")


@dataclass(frozen=True)
class ObservableParam:
    name: str
    label: str
    kind: str  # ticker | select | contract | outcome | token | script | result | event | date | region | text
    required: bool = True
    placeholder: str | None = None
    # (value, label) or (value, label, unit); the unit lets the form format a threshold like the server.
    options: tuple[tuple[str, ...], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "kind": self.kind,
            "required": self.required,
            "placeholder": self.placeholder,
            "options": [
                {"value": option[0], "label": option[1], "unit": option[2] if len(option) > 2 else None}
                for option in self.options
            ],
        }


@dataclass(frozen=True)
class ObservableDefinition:
    observable_id: str
    label: str
    group: str
    source: str
    params: tuple[ObservableParam, ...]
    conditions: tuple[str, ...]
    change_unit: str  # percent | points
    value_unit: str  # price | percent | probability | bp | index | fx | days | number
    needs_tws: bool = False
    needs_keys: tuple[str, ...] = ()
    intraday_capable: bool = False
    stale_after_days: float | None = None
    dependency_label: str | None = None
    order: int = 100
    cadences: tuple[str, ...] = ALL_CADENCES


class ObservableRegistry:
    """Validates observable references and reads them through existing services."""

    def __init__(
        self,
        *,
        research_provider: Any = None,
        macro_service: Any = None,
        prediction_service: Any = None,
        commodities_service: Any = None,
        iv_service: Any = None,
        crypto_service: Any = None,
        script_service: Any = None,
        client: Any = None,
        mock_mode: bool = False,
        market_data_mode: Callable[[], str] | str = "delayed",
        clock: Callable[[], datetime] = now_utc,
        env: Callable[[str], str | None] = os.getenv,
    ) -> None:
        self.research_provider = research_provider
        self.macro_service = macro_service
        self.prediction_service = prediction_service
        self.commodities_service = commodities_service
        self.iv_service = iv_service
        self.crypto_service = crypto_service
        self.script_service = script_service
        self.client = client
        self.mock_mode = bool(mock_mode)
        self._market_data_mode = market_data_mode
        self._clock = clock
        self._env = env
        # I3d: última marca IBKR grabada por la capa intradía (observable, params) -> cotización o None.
        # Los criterios intradía la leen; nunca piden una cotización nueva a IBKR.
        self.intraday_quotes: Callable[..., Any] | None = None
        self._definitions = {item.observable_id: item for item in self._build_definitions()}

    # -- registry ------------------------------------------------------------

    def definitions(self) -> list[ObservableDefinition]:
        return sorted(self._definitions.values(), key=lambda item: (item.order, item.label))

    def get(self, observable_id: str) -> ObservableDefinition:
        definition = self._definitions.get(str(observable_id or "").strip().lower())
        if definition is None:
            raise IdeaValidationError(f"Unknown observable {observable_id!r}.")
        return definition

    def tws_connected(self) -> bool:
        """Trader Workstation is connected for real (the mock client always says yes)."""
        if self.mock_mode or self.client is None:
            return False
        try:
            return bool(self.client.is_connected())
        except Exception:  # noqa: BLE001
            return False

    def availability(self, definition: ObservableDefinition, ref: ObservableRef | None = None) -> tuple[bool, str | None]:
        """Whether an observable can be read; with ``ref``, for that instance (an FX series needs no FRED key)."""
        if definition.needs_tws and not self.mock_mode and not self.tws_connected():
            return False, f"{TWS_DEPENDENCY}; connect it in Settings."
        needs_keys = definition.needs_keys
        if ref is not None and definition.observable_id == "macro_series" and _macro_spec(ref.params.get("series_id")).get("kind") == "fx":
            needs_keys = ()
        missing = [key for key in needs_keys if not str(self._env(key) or "").strip()]
        if missing:
            return False, f"Needs {', '.join(missing)} in Settings."
        if self._service_for(definition.observable_id) is None and definition.observable_id != "calendar_date":
            return False, "The service behind this observable is not running."
        return True, None

    def describe_all(self) -> list[dict[str, Any]]:
        rows = []
        for definition in self.definitions():
            available, reason = self.availability(definition)
            rows.append(
                {
                    "observable_id": definition.observable_id,
                    "label": definition.label,
                    "group": definition.group,
                    "source": definition.source,
                    "params": [param.to_dict() for param in self._params_with_options(definition)],
                    "conditions": list(definition.conditions),
                    "cadences": list(definition.cadences),
                    "change_unit": definition.change_unit,
                    "value_unit": definition.value_unit,
                    "needs_tws": definition.needs_tws,
                    "needs_keys": list(definition.needs_keys),
                    "intraday_capable": definition.intraday_capable,
                    "available": available,
                    "unavailable_reason": reason,
                    "dependency_label": definition.dependency_label,
                    "order": definition.order,
                }
            )
        return rows

    def change_unit(self, ref: ObservableRef) -> str:
        definition = self.get(ref.observable_id)
        if ref.observable_id == "macro_series":
            return "points" if _macro_unit(ref.params.get("series_id")) in {"pct", "bps"} else "percent"
        return definition.change_unit

    def intraday_capable(self, observable_id: str) -> bool:
        return self.get(observable_id).intraday_capable

    def format_value(self, ref: ObservableRef, value: float | None) -> str:
        if value is None or not math.isfinite(float(value)):
            return "N/A"
        unit = self._value_unit(ref)
        number = float(value)
        if unit == "percent":
            return f"{number:,.2f}%"
        if unit == "probability":
            return f"{number:,.1f}%"
        if unit == "bp":
            return f"{number:,.0f} bp"
        if unit == "points":
            return f"{number:,.2f} pts"
        if unit == "price":
            return f"{number:,.2f}" if abs(number) >= 1 else f"{number:,.4f}"
        if unit == "fx":
            return f"{number:,.4f}"
        if unit == "usd":
            return f"${number:,.2f}" if abs(number) >= 1 else f"${number:,.6f}"
        return f"{number:,.4g}" if abs(number) < 1 else f"{number:,.2f}"

    def format_threshold(self, ref: ObservableRef, value: float | None) -> str:
        return self.format_value(ref, value)

    # -- validation ----------------------------------------------------------

    def validate(self, ref: ObservableRef, *, condition: str | None, cadence: str | None) -> ObservableRef:
        """Normalize params, check the condition fits, and fill the display label."""
        definition = self.get(ref.observable_id)
        if condition is not None:
            if condition not in CRITERION_CONDITIONS:
                raise IdeaValidationError(f"Unknown condition {condition!r}.")
            if condition not in definition.conditions:
                allowed = ", ".join(definition.conditions)
                raise IdeaValidationError(f"{definition.label} supports {allowed}; not {condition}.")
        if cadence is not None and cadence not in definition.cadences:
            raise IdeaValidationError(f"{definition.label} cannot be evaluated {cadence}.")
        params = {key: value for key, value in ref.params.items()}
        allowed_names = {param.name for param in definition.params}
        unknown = sorted(set(params) - allowed_names)
        if unknown:
            raise IdeaValidationError(f"{definition.label} does not take {', '.join(unknown)}.")
        for param in definition.params:
            if param.required and not params.get(param.name):
                raise IdeaValidationError(f"{definition.label} needs {param.label.lower()}.")
        params = self._normalize_params(definition, params)
        label = ref.label if ref.label and ref.label != ref.observable_id else self._default_label(definition, params)
        return ObservableRef(observable_id=definition.observable_id, params=params, label=label)

    def describe(self, ref: ObservableRef, *, condition: str, threshold: float | None, window: str | None) -> str:
        return describe_criterion(
            observable_label=ref.label,
            condition=condition,
            threshold=threshold,
            window=window,
            change_unit=self.change_unit(ref),
            format_threshold=lambda value: self.format_threshold(ref, value),
        )

    # -- reading -------------------------------------------------------------

    def read(self, ref: ObservableRef, *, now: datetime | None = None, intraday: bool = False) -> ObservableReading:
        moment = now or self._clock()
        definition = self.get(ref.observable_id)
        available, reason = self.availability(definition, ref)
        if not available:
            return ObservableReading.unavailable(str(reason))
        reader = getattr(self, f"_read_{definition.observable_id}")
        reading = reader(ref, moment)
        if intraday and ref.observable_id in INTRADAY_MARK_OBSERVABLES and not reading.is_unavailable:
            reading = self._with_intraday_mark(ref, reading, moment)
        return reading

    def _with_intraday_mark(self, ref: ObservableRef, reading: ObservableReading, now: datetime) -> ObservableReading:
        """Append the latest fresh IBKR mark (live or delayed) recorded for a tracked leg.

        The daily closes stay the canonical history; the mark is one more
        observation at its instant, labelled with its quality. Without one the
        reading is returned unchanged, with the reason the rule falls back to
        the daily close.
        """
        quote = None
        if self.intraday_quotes is not None:
            try:
                quote = self.intraday_quotes(ref.observable_id, dict(ref.params), now=now)
            except Exception:  # noqa: BLE001 - una marca ilegible equivale a no tener marca
                quote = None
        label = ref.params.get("symbol") or ref.params.get("token_id") or ref.label
        if quote is None:
            return replace(
                reading,
                intraday_note=(
                    f"No fresh IBKR mark for {label}: Gamma marks only the legs of tracked ideas, every 5 minutes "
                    "while Trader Workstation is connected. Evaluated at the daily close."
                ),
            )
        last = reading.history[-1].at if reading.history else None
        if last is not None and quote.at <= last:
            return reading
        quality = str(quote.quality).replace("_", "-")
        point = ObservablePoint(at=quote.at, value=float(quote.price))
        return replace(
            reading,
            value=point.value,
            as_of=point.at,
            history=(*reading.history, point),
            value_display=self.format_value(ref, point.value),
            provenance=ProvenanceRecord(
                source_provider=f"IBKR/TWS ({quality})",
                retrieved_at=quote.at,
                origin="ibkr.reqMktData(snapshot)",
                transformation_note="Latest intraday IBKR mark of a tracked leg, appended to the daily history; the daily close stays canonical.",
            ),
            stale_reason=None,
            warnings=(*reading.warnings, f"Intraday IBKR mark ({quality}) at {quote.at.strftime('%H:%M')} UTC."),
            intraday_from=point.at,
        )

    def _read_equity_close(self, ref: ObservableRef, now: datetime) -> ObservableReading:
        from src.models.instruments import InstrumentReference

        symbol = ref.params["symbol"]
        result = self.research_provider.load_instrument_history_result(
            InstrumentReference(symbol=symbol),
            420,
            max_age_seconds=1800,
        )
        warnings = list(result.warnings or [])
        provenance = _provenance(
            result.source_label or result.source_provider,
            result.retrieved_at,
            result.origin or "research_market_data.history",
            result.transformation_note,
        )
        series = result.series
        if series is None or len(series) == 0:
            reason = warnings[0] if warnings else f"No configured history provider returned closes for {symbol}."
            return ObservableReading.unavailable(reason, provenance=provenance, warnings=warnings[1:])
        points = []
        for index, value in series.items():
            number = _finite(value)
            if number is None:
                continue
            points.append(ObservablePoint(at=_session_instant(index), value=number))
        if not points:
            return ObservableReading.unavailable(f"The closes for {symbol} had no usable values.", provenance=provenance)
        label = str(getattr(result.freshness_label, "value", result.freshness_label) or "")
        if label == "mocked":
            warnings.insert(0, "Demo sample history, not market data.")
        return ObservableReading(
            value=points[-1].value,
            as_of=points[-1].at,
            history=tuple(points),
            value_display=self.format_value(ref, points[-1].value),
            provenance=provenance,
            stale_reason=_stale_reason(points[-1].at, now, 5, "close"),
            warnings=tuple(warnings),
        )

    def _read_macro_series(self, ref: ObservableRef, now: datetime) -> ObservableReading:
        series_id = ref.params["series_id"]
        spec = _macro_spec(series_id)
        if spec.get("kind") == "fx":
            # The demo market data has no FX history, so demo mode says so instead of "no observations".
            if self.mock_mode:
                return ObservableReading.unavailable("Demo mode has no FX history; FX series come from IBKR through Trader Workstation.")
            if not self.tws_connected():
                return ObservableReading.unavailable(f"{TWS_DEPENDENCY}: FX series come from IBKR.")
        history, warnings = self.macro_service.get_series_history_result(series_id, timeframe="1Y")
        if history is None or not history.points:
            reason = warnings[0] if warnings else _macro_empty_reason(series_id, spec)
            return ObservableReading.unavailable(reason, warnings=warnings[1:])
        provenance = _provenance(history.source_provider, history.retrieved_at, history.origin, history.transformation_note)
        points = [
            ObservablePoint(at=_naive_utc(point.timestamp), value=float(point.value))
            for point in history.points
            if _finite(point.value) is not None
        ]
        if not points:
            return ObservableReading.unavailable(f"{series_id} had no usable observations.", provenance=provenance)
        tolerance = {"daily": 7, "weekly": 14, "monthly": 75, "quarterly": 140}.get(str(spec.get("frequency") or ""), 45)
        return ObservableReading(
            value=points[-1].value,
            as_of=points[-1].at,
            history=tuple(points),
            value_display=self.format_value(ref, points[-1].value),
            provenance=provenance,
            stale_reason=_stale_reason(points[-1].at, now, tolerance, "observation"),
            warnings=tuple(warnings),
        )

    def _read_prediction_probability(self, ref: ObservableRef, now: datetime) -> ObservableReading:
        market_id = ref.params["market_id"]
        outcome_id = ref.params.get("outcome_id")
        detail = self.prediction_service.get_market_detail(market_id)
        if detail is None:
            return ObservableReading.unavailable(f"{market_id} was not found on its venue.")
        provenance = _provenance(
            detail.source_provider or detail.venue,
            detail.retrieved_at or now,
            detail.origin or "prediction_market_service.get_market_detail",
            getattr(detail, "transformation_note", None),
        )
        probability = detail.current_probability
        outcome = None
        if outcome_id:
            outcome = next((item for item in detail.outcomes if item.outcome_id == outcome_id), None)
            if outcome is None:
                return ObservableReading.unavailable(f"Outcome {outcome_id} is not on {market_id}.", provenance=provenance)
            probability = outcome.probability
        warnings: list[str] = []
        points: list[ObservablePoint] = []
        try:
            history = self.prediction_service.get_history_series(
                market_id, range_key="1y", resolution_minutes=1440, outcome_id=outcome_id or None
            )
        except Exception as exc:  # noqa: BLE001 - history is optional for level rules
            history = None
            warnings.append(f"History unavailable: {exc}")
        if history is not None:
            warnings.extend(str(item) for item in (history.warnings or []))
            for point in history.points:
                number = _finite(point.probability)
                if number is not None:
                    points.append(ObservablePoint(at=_naive_utc(point.timestamp), value=number * 100.0))
        value = None if _finite(probability) is None else float(probability) * 100.0
        as_of = _naive_utc(detail.retrieved_at) if detail.retrieved_at else now
        status = str(detail.status or "").lower()
        released: bool | None
        if outcome is not None and outcome.resolved is not None:
            released = bool(outcome.resolved and outcome.winner)
        elif status == "resolved":
            released = (detail.resolved_probability or 0.0) >= 0.99
        else:
            released = False
        status_display = {
            "resolved": "Resolved Yes" if released else "Resolved No",
            "open": "Open",
            "closed": "Closed, not resolved",
        }.get(status, status.capitalize() or "Unknown")
        freshness = detail.freshness
        stale = freshness.reason if (freshness is not None and freshness.is_stale and status == "open") else None
        if value is None and not points:
            return ObservableReading(
                provenance=provenance,
                unavailable_reason=None if status == "resolved" else f"{market_id} has no current probability.",
                event_released=released,
                event_time=_naive_utc(detail.close_time or detail.end_time) if (detail.close_time or detail.end_time) else None,
                value_display=status_display,
                warnings=tuple(warnings),
                instant_points=True,
            )
        return ObservableReading(
            value=value,
            as_of=as_of,
            history=tuple(points),
            value_display=self.format_value(ref, value) if value is not None else status_display,
            provenance=provenance,
            stale_reason=stale or None,
            warnings=tuple(warnings),
            event_released=released,
            event_time=_naive_utc(detail.close_time or detail.end_time) if (detail.close_time or detail.end_time) else None,
            event_value=value,
            instant_points=True,
        )

    def _read_crypto_price(self, ref: ObservableRef, now: datetime) -> ObservableReading:
        token_id = ref.params["token_id"]
        rows = self.crypto_service.get_price_history(token_id, days=365) or []
        points = [
            ObservablePoint(at=_naive_utc(row.timestamp), value=float(row.price))
            for row in rows
            if _finite(row.price) is not None
        ]
        if not points:
            return ObservableReading.unavailable(f"CoinGecko returned no prices for {token_id}.")
        latest = rows[-1]
        provenance = _provenance(
            latest.source_provider or "coingecko",
            latest.retrieved_at or now,
            latest.origin or "crypto_service.get_price_history",
            latest.transformation_note,
        )
        return ObservableReading(
            value=points[-1].value,
            as_of=points[-1].at,
            history=tuple(points),
            value_display=self.format_value(ref, points[-1].value),
            provenance=provenance,
            stale_reason=_stale_reason(points[-1].at, now, 3, "price"),
            instant_points=True,
        )

    def _read_commodity_price(self, ref: ObservableRef, now: datetime) -> ObservableReading:
        instrument_id = ref.params["instrument_id"]
        history = self.commodities_service.get_price_history(instrument_id)
        if history is None or not history.points:
            warnings = list(getattr(history, "warnings", []) or [])
            reason = warnings[0] if warnings else f"The configured commodities provider has no prices for {instrument_id}."
            return ObservableReading.unavailable(reason, warnings=warnings[1:])
        provenance = _provenance(history.source_provider, history.retrieved_at or now, history.origin, history.transformation_note)
        points = [
            ObservablePoint(at=_naive_utc(point.timestamp), value=float(point.value))
            for point in history.points
            if _finite(point.value) is not None
        ]
        warnings = list(history.warnings or [])
        if str(history.source_provider or "").startswith("sample"):
            warnings.insert(0, "Demo sample prices, not market data.")
        return ObservableReading(
            value=points[-1].value,
            as_of=points[-1].at,
            history=tuple(points),
            value_display=self.format_value(ref, points[-1].value),
            provenance=provenance,
            stale_reason=_stale_reason(points[-1].at, now, 7, "price"),
            warnings=tuple(warnings),
        )

    def _read_commodity_spread(self, ref: ObservableRef, now: datetime) -> ObservableReading:
        spread_id = ref.params["spread_id"]
        spreads = self.commodities_service.get_spreads()
        match = next((item for item in spreads if item.definition.spread_id == spread_id), None)
        if match is None or _finite(match.value) is None:
            return ObservableReading.unavailable(
                f"The Commodities service did not build {spread_id}; calendar spreads need IBKR curves."
            )
        provenance = _provenance(match.source_provider, match.retrieved_at or now, match.origin, match.transformation_note)
        as_of = _naive_utc(match.observed_at or match.retrieved_at or now)
        value = float(match.value)
        # Level rules only: some spread histories are proxies, so no crossing or change is read from them.
        return ObservableReading(
            value=value,
            as_of=as_of,
            value_display=self.format_value(ref, value),
            provenance=provenance,
            stale_reason=_stale_reason(as_of, now, 7, "observation"),
            warnings=tuple(match.warnings or []),
            instant_points=True,
        )

    def _read_macro_event(self, ref: ObservableRef, now: datetime) -> ObservableReading:
        event_id = ref.params["event_id"]
        stored = _parse_instant(ref.params.get("scheduled_at"))
        result = self.macro_service.get_events_result(region=ref.params.get("region") or "US")
        match = next((item for item in result.events if item.event_id == event_id), None)
        warnings = [str(item) for item in (result.warnings or [])]
        if match is not None:
            provenance = _provenance(match.source_provider, match.retrieved_at or now, match.origin or "macro_calendar", match.transformation_note)
            return ObservableReading(
                event_time=_naive_utc(match.scheduled_at),
                provenance=provenance,
                warnings=tuple(warnings),
            )
        provenance = _provenance("macro_calendar", now, "idea_observables.macro_event", "Scheduled time stored with the criterion.")
        if stored is not None and stored <= now:
            warnings.insert(0, "The calendar drops past events; this uses the time stored when the criterion was set.")
            return ObservableReading(event_time=stored, provenance=provenance, warnings=tuple(warnings))
        return ObservableReading.unavailable(
            "The calendar no longer lists this event; it may have been rescheduled or removed.",
            provenance=provenance,
            warnings=warnings,
        )

    def _read_calendar_date(self, ref: ObservableRef, now: datetime) -> ObservableReading:
        target = date.fromisoformat(ref.params["date"])
        provenance = ProvenanceRecord(
            source_provider="gamma_clock",
            retrieved_at=now,
            origin="idea_observables.calendar_date",
            transformation_note="Compared with Gamma's clock in UTC.",
        )
        return ObservableReading(event_time=datetime(target.year, target.month, target.day), provenance=provenance)

    def _read_script_signal(self, ref: ObservableRef, now: datetime) -> ObservableReading:
        from src.application.script_analytics import inspect_analytics

        script_id = ref.params["script_id"]
        result_id = ref.params.get("result_id")
        try:
            detail = self.script_service.get_script(script_id)
        except Exception as exc:  # noqa: BLE001 - not found and friends are states
            return ObservableReading.unavailable(f"Script {script_id} is not available: {exc}")
        script = getattr(detail, "script", detail)
        canonical = getattr(script, "canonical_revision_id", None)
        runs = self.script_service.list_runs(script_id)
        run = next(
            (item for item in runs if item.status == "completed" and (canonical is None or item.revision_id == canonical)),
            None,
        )
        if run is None:
            return ObservableReading.unavailable("The accepted revision of this script has no completed run yet.")
        report = inspect_analytics(self.script_service, run.run_id)
        artifact = next((item for item in report.get("artifacts", []) if item.get("eligible")), None)
        if artifact is None:
            artifacts = report.get("artifacts", [])
            detail_text = ""
            if artifacts:
                notes = [*artifacts[0].get("errors", []), *artifacts[0].get("warnings", [])]
                detail_text = f" {notes[-1]}" if notes else ""
            return ObservableReading.unavailable(
                "The latest completed run has no eligible analytical result (gamma_analytics.json)." + detail_text
            )
        results = [row.get("result") or {} for row in artifact.get("results", [])]
        chosen = next(
            (row for row in results if (result_id and row.get("result_id") == result_id) or (not result_id and row.get("kind") in {"metric", "signals"})),
            None,
        )
        if chosen is None:
            return ObservableReading.unavailable(
                f"Result {result_id} is not in the latest run." if result_id else "The latest run has no metric or signals result."
            )
        provenance_payload = artifact.get("provenance") or {}
        provenance = _provenance(
            str(provenance_payload.get("source_provider") or "research_script"),
            _parse_instant(provenance_payload.get("retrieved_at")) or now,
            "script_analytics.inspect_retained_artifact",
            f"Run {run.run_id}, revision {run.revision_id}.",
        )
        completed = _naive_utc(run.completed_at) if run.completed_at else now
        stale = _stale_reason(completed, now, 7, "run")
        if chosen.get("kind") == "metric":
            value = _finite(chosen.get("value"))
            if value is None:
                return ObservableReading.unavailable("The metric in the latest run has no value.", provenance=provenance)
            as_of = _parse_instant(chosen.get("as_of")) or completed
            return ObservableReading(
                value=value,
                as_of=as_of,
                history=(ObservablePoint(at=as_of, value=value),),
                value_display=f"{_plain(value)} {chosen.get('unit') or ''}".strip(),
                provenance=provenance,
                stale_reason=stale,
            )
        points = []
        for observation in chosen.get("observations") or []:
            number = _finite(observation.get("value"))
            instant = _parse_instant(observation.get("date"))
            if number is not None and instant is not None:
                points.append(ObservablePoint(at=instant, value=number))
        if not points:
            return ObservableReading.unavailable("The signals result has no values.", provenance=provenance)
        return ObservableReading(
            value=points[-1].value,
            as_of=points[-1].at,
            history=tuple(points),
            value_display=f"{_plain(points[-1].value)} {chosen.get('unit') or ''}".strip(),
            provenance=provenance,
            stale_reason=stale,
        )

    def _read_option_atm_iv(self, ref: ObservableRef, now: datetime) -> ObservableReading:
        return self._read_iv(ref, now, metric="atm")

    def _read_option_skew(self, ref: ObservableRef, now: datetime) -> ObservableReading:
        return self._read_iv(ref, now, metric="skew")

    def _read_iv(self, ref: ObservableRef, now: datetime, *, metric: str) -> ObservableReading:
        from src.application.iv_service import IVSurfaceRequest

        symbol = ref.params["symbol"]
        snapshot = None
        warnings: list[str] = []
        if self.iv_service.is_running():
            active = str(self.iv_service.active_symbol() or "").upper()
            if active != symbol:
                return ObservableReading.unavailable(
                    f"Options is streaming {active or 'another symbol'}; Gamma does not interrupt a live surface to read {symbol}."
                )
            snapshot = self.iv_service.latest_snapshot()
            if snapshot is None:
                # El stream de este símbolo aún no ha emitido su primer snapshot.
                # get_surface() lo detendría, así que se espera a la siguiente pasada.
                return ObservableReading.unavailable(
                    f"Options is still loading the live {symbol} surface; Gamma does not interrupt it and will read it on the next pass."
                )
        if snapshot is None:
            mode = self._market_data_mode() if callable(self._market_data_mode) else self._market_data_mode
            result = self.iv_service.get_surface(IVSurfaceRequest(symbol=symbol, market_data_mode=str(mode or "delayed")))
            snapshot = result.snapshot
            warnings.extend(result.warnings or [])
        if snapshot is None:
            return ObservableReading.unavailable(warnings[0] if warnings else f"No options surface for {symbol}.", warnings=warnings[1:])
        provenance = _provenance(snapshot.source_provider, _naive_utc(snapshot.timestamp), snapshot.origin, snapshot.transformation_note)
        warnings.extend(snapshot.quote_warnings or [])
        if snapshot.delayed:
            warnings.append("Delayed quotes.")
        if str(snapshot.freshness_label) == "mocked":
            warnings.insert(0, "Demo sample surface, not market data.")
        index = _front_expiry_index(snapshot)
        if index is None:
            return ObservableReading.unavailable("The surface has no expiry with an at-the-money reading.", provenance=provenance)
        expiry = snapshot.expiries[index] if index < len(snapshot.expiries) else None
        if metric == "atm":
            analytics = next((item for item in snapshot.expiry_analytics if item.expiry == expiry), None)
            raw = analytics.atm_blended_implied_volatility if analytics else None
            value = None if _finite(raw) is None else float(raw) * 100.0
        else:
            value = _wing_spread_points(snapshot, index)
        if value is None:
            return ObservableReading.unavailable(f"The {expiry} expiry has no {'ATM' if metric == 'atm' else 'wing'} IV.", provenance=provenance)
        as_of = _naive_utc(snapshot.timestamp)
        warnings.append(f"Expiry {expiry}.")
        return ObservableReading(
            value=value,
            as_of=as_of,
            value_display=self.format_value(ref, value),
            provenance=provenance,
            stale_reason=_stale_reason(as_of, now, 1, "snapshot"),
            warnings=tuple(warnings),
            instant_points=True,
        )

    # -- internals -----------------------------------------------------------

    def _service_for(self, observable_id: str) -> Any:
        return {
            "equity_close": self.research_provider,
            "macro_series": self.macro_service,
            "macro_event": self.macro_service,
            "prediction_probability": self.prediction_service,
            "crypto_price": self.crypto_service,
            "commodity_price": self.commodities_service,
            "commodity_spread": self.commodities_service,
            "script_signal": self.script_service,
            "option_atm_iv": self.iv_service,
            "option_skew": self.iv_service,
        }.get(observable_id)

    def _value_unit(self, ref: ObservableRef) -> str:
        if ref.observable_id == "macro_series":
            unit = _macro_unit(ref.params.get("series_id"))
            return {"pct": "percent", "bps": "bp", "fx": "fx", "index": "number"}.get(unit, "number")
        if ref.observable_id == "option_skew":
            return "points"
        return self.get(ref.observable_id).value_unit

    def _normalize_params(self, definition: ObservableDefinition, params: dict[str, str]) -> dict[str, str]:
        oid = definition.observable_id
        if oid in {"equity_close", "option_atm_iv", "option_skew"}:
            symbol = params["symbol"].strip().upper()
            if not symbol or len(symbol) > 24 or any(char.isspace() for char in symbol):
                raise IdeaValidationError("Use a ticker such as XOM or SPY.")
            params["symbol"] = symbol
        elif oid == "macro_series":
            if params["series_id"] not in _macro_registry():
                raise IdeaValidationError(f"Unknown macro series {params['series_id']!r}.")
        elif oid == "prediction_probability":
            venue, _, native = params["market_id"].partition(":")
            if venue.lower() not in PREDICTION_VENUES or not native.strip():
                raise IdeaValidationError("A contract id looks like polymarket:<id> or kalshi:<ticker>.")
            params["market_id"] = f"{venue.lower()}:{native.strip()}"
        elif oid == "crypto_price":
            params["token_id"] = params["token_id"].strip().lower()
        elif oid == "commodity_price":
            if params["instrument_id"] not in {value for value, _ in _commodity_options()}:
                raise IdeaValidationError(f"Unknown commodity {params['instrument_id']!r}.")
        elif oid == "commodity_spread":
            if params["spread_id"] not in {value for value, _ in COMMODITY_SPREADS}:
                raise IdeaValidationError(f"Unknown commodity spread {params['spread_id']!r}.")
        elif oid == "calendar_date":
            try:
                params["date"] = date.fromisoformat(params["date"][:10]).isoformat()
            except ValueError as exc:
                raise IdeaValidationError("Use a date as YYYY-MM-DD.") from exc
        elif oid == "macro_event":
            if params.get("scheduled_at"):
                instant = _parse_instant(params["scheduled_at"])
                if instant is None:
                    raise IdeaValidationError("scheduled_at must be an ISO instant.")
                params["scheduled_at"] = instant.isoformat()
            params["region"] = (params.get("region") or "US").upper()
        return params

    def _default_label(self, definition: ObservableDefinition, params: dict[str, str]) -> str:
        oid = definition.observable_id
        if oid == "equity_close":
            return f"{params['symbol']} close"
        if oid == "option_atm_iv":
            return f"{params['symbol']} ATM IV"
        if oid == "option_skew":
            return f"{params['symbol']} skew"
        if oid == "macro_series":
            return str(_macro_spec(params["series_id"]).get("title") or params["series_id"])
        if oid == "prediction_probability":
            return f"{params['market_id']} probability"
        if oid == "crypto_price":
            return f"{params['token_id']} price"
        if oid == "commodity_price":
            names = dict(_commodity_options())
            return f"{names.get(params['instrument_id'], params['instrument_id'])} price"
        if oid == "commodity_spread":
            return dict(COMMODITY_SPREADS).get(params["spread_id"], params["spread_id"])
        if oid == "calendar_date":
            return params["date"]
        if oid == "macro_event":
            return params.get("title") or params["event_id"]
        if oid == "script_signal":
            return f"Script {params['script_id']}" + (f" · {params['result_id']}" if params.get("result_id") else "")
        return definition.label

    def _params_with_options(self, definition: ObservableDefinition) -> tuple[ObservableParam, ...]:
        if definition.observable_id != "script_signal" or self.script_service is None:
            return definition.params
        try:
            scripts = self.script_service.list_scripts()
        except Exception:  # noqa: BLE001
            return definition.params
        options = tuple((item.script_id, item.title) for item in scripts)[:100]
        return tuple(
            ObservableParam(**{**param.__dict__, "options": options}) if param.name == "script_id" else param
            for param in definition.params
        )

    def _build_definitions(self) -> list[ObservableDefinition]:
        ticker = ObservableParam("symbol", "Ticker", "ticker", placeholder="XOM")
        return [
            ObservableDefinition(
                observable_id="equity_close",
                label="Equity or ETF close",
                group="Markets",
                source="Research market data (Yahoo Finance, then IBKR)",
                params=(ticker,),
                conditions=SERIES_CONDITIONS,
                change_unit="percent",
                value_unit="price",
                intraday_capable=True,
                stale_after_days=5,
                dependency_label="Demo mode has sample history for AAPL, MSFT, SAP and SPY only." if self.mock_mode else None,
                order=10,
            ),
            ObservableDefinition(
                observable_id="macro_series",
                label="Macro series",
                group="Macro",
                source="Macro series history (FRED)",
                params=(ObservableParam("series_id", "Series", "select", options=_macro_options()),),
                conditions=SERIES_CONDITIONS,
                change_unit="points",
                value_unit="number",
                needs_keys=("FRED_API_KEY",),
                stale_after_days=7,
                dependency_label="FX series need Trader Workstation.",
                order=20,
            ),
            ObservableDefinition(
                observable_id="prediction_probability",
                label="Prediction contract probability",
                group="Prediction markets",
                source="Prediction Markets (Polymarket, Kalshi)",
                params=(
                    ObservableParam("market_id", "Contract id", "contract", placeholder="kalshi:TICKER or polymarket:123"),
                    ObservableParam("outcome_id", "Outcome", "outcome", required=False),
                ),
                conditions=(*SERIES_CONDITIONS, "event_occurs"),
                change_unit="points",
                value_unit="probability",
                stale_after_days=1,
                order=30,
            ),
            ObservableDefinition(
                observable_id="crypto_price",
                label="Crypto price",
                group="Crypto",
                source="CoinGecko",
                params=(ObservableParam("token_id", "CoinGecko id", "token", placeholder="bitcoin"),),
                conditions=SERIES_CONDITIONS,
                change_unit="percent",
                value_unit="usd",
                intraday_capable=True,
                stale_after_days=3,
                order=40,
            ),
            ObservableDefinition(
                observable_id="commodity_price",
                label="Commodity price",
                group="Commodities",
                source="Commodities service (EIA/FRED, IBKR futures with TWS)",
                params=(ObservableParam("instrument_id", "Commodity", "select", options=_commodity_options()),),
                conditions=SERIES_CONDITIONS,
                change_unit="percent",
                value_unit="price",
                stale_after_days=7,
                dependency_label="Front-month futures need Trader Workstation; EIA/FRED spot otherwise.",
                order=50,
            ),
            ObservableDefinition(
                observable_id="commodity_spread",
                label="Commodity spread",
                group="Commodities",
                source="Commodities service spreads",
                params=(ObservableParam("spread_id", "Spread", "select", options=COMMODITY_SPREADS),),
                conditions=LEVEL_CONDITIONS,
                change_unit="points",
                value_unit="number",
                stale_after_days=7,
                dependency_label="Level rules only. Calendar spreads need IBKR curves.",
                order=55,
            ),
            ObservableDefinition(
                observable_id="macro_event",
                label="Scheduled economic event",
                group="Dates",
                source="Macro calendar (Fed, BLS, BEA, ECB)",
                params=(
                    ObservableParam("event_id", "Event", "event"),
                    ObservableParam("title", "Title", "text", required=False),
                    ObservableParam("scheduled_at", "Scheduled", "text", required=False),
                    ObservableParam("region", "Region", "region", required=False),
                ),
                conditions=("date_reached",),
                change_unit="points",
                value_unit="days",
                cadences=("on_open", "daily_close"),
                order=60,
            ),
            ObservableDefinition(
                observable_id="calendar_date",
                label="Date",
                group="Dates",
                source="Gamma's clock",
                params=(ObservableParam("date", "Date", "date"),),
                conditions=("date_reached",),
                change_unit="points",
                value_unit="days",
                cadences=("on_open", "daily_close"),
                order=65,
            ),
            ObservableDefinition(
                observable_id="script_signal",
                label="Script signal",
                group="Quant",
                source="Latest completed run of the accepted Script revision",
                params=(
                    ObservableParam("script_id", "Script", "script"),
                    ObservableParam("result_id", "Result id", "result", required=False, placeholder="first metric or signal"),
                ),
                conditions=SERIES_CONDITIONS,
                change_unit="points",
                value_unit="number",
                stale_after_days=7,
                cadences=("on_open", "daily_close"),
                order=70,
            ),
            ObservableDefinition(
                observable_id="option_atm_iv",
                label="At-the-money implied volatility",
                group="Options",
                source="Options IV snapshot (IBKR)",
                params=(ticker,),
                conditions=LEVEL_CONDITIONS,
                change_unit="points",
                value_unit="percent",
                needs_tws=True,
                intraday_capable=True,
                stale_after_days=1,
                dependency_label=TWS_DEPENDENCY,
                order=80,
            ),
            ObservableDefinition(
                observable_id="option_skew",
                label="Volatility skew",
                group="Options",
                source="Options IV snapshot (IBKR)",
                params=(ticker,),
                conditions=LEVEL_CONDITIONS,
                change_unit="points",
                value_unit="points",
                needs_tws=True,
                intraday_capable=True,
                stale_after_days=1,
                dependency_label=TWS_DEPENDENCY,
                order=85,
            ),
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _macro_registry() -> dict[str, dict[str, Any]]:
    from src.application.macro_service import SERIES_REGISTRY

    return SERIES_REGISTRY


def _macro_spec(series_id: str | None) -> dict[str, Any]:
    return dict(_macro_registry().get(str(series_id or ""), {}))


def _macro_empty_reason(series_id: str, spec: dict[str, Any]) -> str:
    """Name the provider and its series code when a macro series loads without observations."""
    title = str(spec.get("title") or series_id)
    if spec.get("kind") == "fx":
        return f"IBKR returned no FX history for {title}."
    codes = [
        str(spec.get(key) or "").strip()
        for key in ("provider_series_id", "left_provider_series_id", "right_provider_series_id")
    ]
    reference = " + ".join(code for code in codes if code)
    suffix = f" ({reference})" if reference else ""
    return f"FRED returned no observations for {title}{suffix} in the last year."


def _macro_unit(series_id: str | None) -> str:
    return str(_macro_spec(series_id).get("unit") or "")


def _macro_options() -> tuple[tuple[str, str, str], ...]:
    rows = []
    units = {"pct": "percent", "bps": "bp", "fx": "fx", "index": "number"}
    for series_id, spec in _macro_registry().items():
        title = str(spec.get("title") or series_id)
        if spec.get("kind") == "fx":
            title += " (needs TWS)"
        rows.append((series_id, title, units.get(str(spec.get("unit") or ""), "number")))
    return tuple(rows)


def _commodity_options() -> tuple[tuple[str, str], ...]:
    from src.services.commodities_adapters import COMMODITY_INSTRUMENTS

    return tuple((item.instrument_id, item.name) for item in COMMODITY_INSTRUMENTS)


def _front_expiry_index(snapshot: Any) -> int | None:
    """First expiry at least seven days out with an ATM reading, else the first with one."""
    analytics = {item.expiry: item for item in snapshot.expiry_analytics}
    candidates = []
    for index, expiry in enumerate(snapshot.expiries):
        item = analytics.get(expiry)
        if item is None or _finite(item.atm_blended_implied_volatility) is None:
            continue
        candidates.append((index, item.days_to_expiry))
    for index, days in candidates:
        if days is not None and days >= 7:
            return index
    return candidates[0][0] if candidates else None


def _wing_spread_points(snapshot: Any, row_index: int) -> float | None:
    """Put-wing minus call-wing IV, in volatility points, with the Options tab's wing rule."""
    strikes = list(snapshot.strikes or [])
    if not strikes:
        return None
    spot = float(snapshot.spot)
    atm_index = min(range(len(strikes)), key=lambda index: abs(strikes[index] - spot))
    offset = max(2, round(len(strikes) * 0.18))
    lower = max(0, min(len(strikes) - 1, atm_index - offset))
    upper = max(0, min(len(strikes) - 1, atm_index + offset))
    if lower == atm_index or upper == atm_index:
        return None
    try:
        row = list(snapshot.iv_grid[row_index])
    except (IndexError, TypeError):
        return None
    put_wing = _finite(row[lower]) if lower < len(row) else None
    call_wing = _finite(row[upper]) if upper < len(row) else None
    if put_wing is None or call_wing is None:
        return None
    return (put_wing - call_wing) * 100.0


def _provenance(source: Any, retrieved_at: Any, origin: Any, note: Any = None) -> ProvenanceRecord:
    return ProvenanceRecord(
        source_provider=str(source or "unknown").strip() or "unknown",
        retrieved_at=_naive_utc(retrieved_at) if retrieved_at else now_utc(),
        origin=str(origin or "idea_observables").strip() or "idea_observables",
        transformation_note=str(note).strip() if note else None,
    )


def _naive_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, date):
        moment = datetime(value.year, value.month, value.day)
    else:
        parsed = _parse_instant(value)
        if parsed is None:
            raise ValueError(f"Not an instant: {value!r}")
        return parsed
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def _session_instant(value: Any) -> datetime:
    """A daily bar's index as the naive-UTC midnight of its session date."""
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    moment = _naive_utc(value)
    return datetime(moment.year, moment.month, moment.day)


def _parse_instant(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return _naive_utc(value)
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed_date = date.fromisoformat(text[:10])
        except ValueError:
            return None
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _stale_reason(as_of: datetime, now: datetime, days: float, noun: str) -> str | None:
    age = now - as_of
    if age <= timedelta(days=days):
        return None
    return f"The latest {noun} is from {as_of.strftime('%Y-%m-%d')}, {age.days} days ago."


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _plain(value: float) -> str:
    return f"{value:,.4g}" if abs(value) < 1 else f"{value:,.2f}"


__all__ = ["COMMODITY_SPREADS", "ObservableDefinition", "ObservableParam", "ObservableRegistry"]
