"""Bounded, provider-neutral exports. Acquisition stays in the owning services.

Previews hold copied bytes for ten minutes, so Add never re-fetches what the
user inspected. Retained Script bundles remain the durable authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from statistics import median
from threading import RLock
from uuid import uuid4

from src.models.research_overview import RESEARCH_OVERVIEW_UNIVERSES
from src.services.fundamentals_adapters import SecIdentityMissingError
from src.models.research_script import ResearchScriptInputFileCreateRequest
from src.utils.time import now_utc


class DatasetSelectionError(ValueError):
    """Safe, catalog-authored validation message (never provider exception text)."""


class DatasetNotFoundError(DatasetSelectionError):
    """El objeto exacto pedido no existe (p. ej. una captura retenida borrada); la API responde 404."""


class DatasetServiceUnavailableError(DatasetSelectionError):
    """El servicio propietario no está configurado en este runtime; no es un error del cliente (503)."""


def first_non_finite(value, path="data"):
    """Ruta del primer número NaN/Infinity del payload, o None si todos son finitos."""
    if isinstance(value, float) and not math.isfinite(value):
        return path
    if isinstance(value, dict):
        for key, item in value.items():
            if (found := first_non_finite(item, f"{path}.{key}")) is not None:
                return found
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            if (found := first_non_finite(item, f"{path}[{index}]")) is not None:
                return found
    return None


DATASETS = {
    "equity_history": ("Equity · price history", "Curated Equity Research instruments; bounded daily close history, optionally resampled. No complete global security master."),
    "macro_series": ("Macro · series history", "Curated Macro registry only. Provider coverage and frequency vary; no invented observations."),
    "saved_research": ("Saved research", "One saved research payload, including its original provenance and warnings."),
    "fundamentals": ("Fundamentals · financials & ratios", "Normalized annual/quarterly statements, company, filings and valuation ratios. No new provider coverage or generated company summary."),
    "options_capture": ("Options · retained capture", "A retained capture only; observed contracts/pairs are separate from fitted grid/cell sources. No historical chain reconstruction or new subscriptions."),
    "commodity_history": ("Commodities · prices", "Available price history only; basis, units and sample/provider limitations are retained."),
    "commodity_curve": ("Commodities · curve", "Current available curve with exact futures identities. No invented historical curves."),
    "commodity_spread": ("Commodities · spreads", "Available spread definitions, histories and derived statistics; inspect leg identities and formula."),
    "commodity_inventory": ("Commodities · inventories", "Available inventory series with native units and frequency."),
    "crypto_history": ("Crypto · token history", "CoinGecko token price, market cap and volume history, bounded to 30/90/365 days. No wallet or transaction exports."),
    "crypto_liquidity": ("Crypto · market & liquidity", "Current token market data and supported DEX pool liquidity. No historical pool depth or executable prices."),
    "prediction_history": ("Prediction Markets · outcome history", "Exact venue contract and outcome history with event metadata; provider range/resolution limits remain explicit."),
}

EQUITY_DEFAULT_LOOKBACK_DAYS = 756
CRYPTO_TIMEFRAME_DAYS = {"30D": 30, "90D": 90, "1Y": 365}
# Parámetros de ventana/frecuencia que cada dominio aplica de verdad; el resto se etiqueta como no aplicado.
WINDOW_PARAMETERS = {
    "equity_history": {"lookback_days", "frequency"},
    "commodity_history": {"lookback_days"},
    "macro_series": {"timeframe"},
    "crypto_history": {"timeframe"},
    "prediction_history": {"timeframe"},
}
DAY_SECONDS = 86400


def _timestamp(value):
    """Instante comparable (UTC sin zona) de una marca ISO copiada del servicio propietario."""
    parsed = datetime.fromisoformat(str(value))
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


def _shortfall(first, start, instants, window_days):
    """True si la cobertura empieza después del inicio pedido más allá del hueco normal de la serie.

    La tolerancia absorbe fines de semana/festivos (mínimo 4 días, acotado a 1/4 de ventanas cortas)
    y el espaciado nativo de series mensuales o trimestrales; nunca se rellena el hueco.
    """
    unique = sorted(set(instants))
    gaps = [(b - a).total_seconds() for a, b in zip(unique, unique[1:])]
    tolerance = max(median(gaps) if gaps else 0, min(4, window_days / 4) * DAY_SECONDS)
    return (first - start).total_seconds() > tolerance


def coverage(points):
    """Cobertura real de los puntos exportados (marcas tal como se copian), sin suponer orden."""
    instants = [_timestamp(p["timestamp"]) for p in points]
    first, last = instants.index(min(instants)), instants.index(max(instants))
    return {"coverage_start": points[first]["timestamp"], "coverage_end": points[last]["timestamp"],
            "coverage_calendar_days": (instants[last].date() - instants[first].date()).days, "observations": len(points)}


def bound_to_calendar_window(points, days):
    """Recorta observaciones a [última fecha observada − days, última fecha observada].

    Los proveedores pueden imponer un periodo mínimo de descarga o servir una caché más larga; el recorte
    ocurre tras la adquisición, conserva el orden copiado y nunca interpola ni amplía la cobertura.
    Con days=None no se recorta y se declara la historia completa disponible.
    """
    instants = [_timestamp(p["timestamp"]) for p in points]
    anchor = max(instants).date()
    start = anchor - timedelta(days=days) if days is not None else None
    kept = [p for p, t in zip(points, instants) if start is None or t.date() >= start]

    def midnight(day):
        return datetime.combine(day, datetime.min.time())

    if start is None:
        status = "full_available_history"
    elif len(kept) < len(points):
        status = "trimmed_to_request"
    elif _shortfall(midnight(min(instants).date()), midnight(start), [midnight(t.date()) for t in instants], days):
        status = "shorter_than_request"
    else:
        status = "within_request"
    provided = coverage(points)
    window = {
        "basis": "calendar_days" if days is not None else "full_available_history",
        "lookback_days": days, "anchor": "latest_observation",
        "start": start.isoformat() if start else None, "end": anchor.isoformat(), **coverage(kept),
        "provider_coverage_start": provided["coverage_start"], "provider_coverage_end": provided["coverage_end"],
        "provider_observations": len(points), "status": status,
    }
    return kept, window


def resample_last(points, frequency):
    """Última observación de cada semana (cierre viernes) o mes, conservando su fecha observada real.

    A diferencia de una etiqueta de periodo, la fecha nunca queda después de la última observación.
    """
    buckets = {}
    for point in points:
        day = _timestamp(point["timestamp"]).date()
        key = day + timedelta(days=(4 - day.weekday()) % 7) if frequency == "weekly" else (day.year, day.month)
        buckets[key] = point
    return list(buckets.values())


def plain(value):
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def describe(payload):
    """Inspect all records, preserving mixed sources/units rather than guessing."""
    fields, sources, retrieved, dates, warnings, units, frequencies, states = {}, set(), set(), set(), [], set(), set(), set()

    def walk(value, path="", inherited_unit=None):
        if isinstance(value, dict):
            unit = value.get("unit", value.get("quote_unit", inherited_unit))
            for key, item in value.items():
                if key == "warnings" and isinstance(item, list):
                    warnings.extend(str(w) for w in item)
                if key in {"source_provider", "retrieved_at", "unit", "quote_unit", "frequency", "freshness_label", "coverage_status"} and item:
                    target = {"source_provider": sources, "retrieved_at": retrieved, "unit": units, "quote_unit": units, "frequency": frequencies, "freshness_label": states, "coverage_status": states}[key]
                    target.add(str(item))
                if key in {"timestamp", "end_date", "start_date", "coverage_start", "coverage_end"} and isinstance(item, str):
                    dates.add(item)
                walk(item, f"{path}.{key}".strip("."), unit)
        elif isinstance(value, list):
            for item in value:
                walk(item, path + "[]", inherited_unit)
        else:
            kind = "null" if value is None else type(value).__name__
            unit = inherited_unit if path.endswith(("value", "price", "close")) else None
            field = fields.setdefault(path, {"name": path, "types": set(), "units": set()})
            field["types"].add(kind)
            if unit:
                field["units"].add(str(unit))

    walk(payload)
    return {"fields": [{"name": f["name"], "type": " | ".join(sorted(f["types"])), "unit": ", ".join(sorted(f["units"])) or None} for f in fields.values()], "sources": sorted(sources), "retrieval_times": sorted(retrieved),
            "coverage_start": min(dates) if dates else None, "coverage_end": max(dates) if dates else None,
            "units": sorted(units), "frequencies": sorted(frequencies), "states": sorted(states),
            "warnings": list(dict.fromkeys(warnings))}


class ScriptDatasetCatalog:
    MAX_PREVIEWS = 16
    MAX_PREVIEW_BYTES = 32 * 1024 * 1024
    TTL = 600

    def __init__(self, owner, **services):
        self.owner = owner
        self.services = services
        self._previews = {}
        self._lock = RLock()

    def service(self, name):
        service = self.services.get(name)
        if service is None:
            raise DatasetServiceUnavailableError("The owning service is unavailable.")
        return service

    def definitions(self):
        return [{"domain": key, "label": label, "limitations": limitations} for key, (label, limitations) in DATASETS.items()]

    @staticmethod
    def equities():
        return {i.normalized_id(): i for u in RESEARCH_OVERVIEW_UNIVERSES for i in u.instruments}

    def search(self, domain, query=""):
        if domain not in DATASETS:
            raise DatasetSelectionError("Unsupported dataset.")
        if len(query) > 128:
            raise DatasetSelectionError("Search exceeds 128 characters.")
        warnings = []
        rows = []
        def add(identity, label, **selection):
            rows.append({"object_id": identity, "label": label, **selection})
        if domain == "equity_history":
            for identity, i in self.equities().items():
                add(identity, f"{i.symbol} · {i.label} · {i.exchange} · {i.currency}")
        elif domain == "macro_series":
            from src.application.macro_service import SERIES_REGISTRY
            for identity, meta in SERIES_REGISTRY.items():
                add(identity, f"{meta['title']} · {meta['region']} · {meta['unit']}", region=meta["region"])
        elif domain == "saved_research":
            for item in self.service("research").list_saved_research():
                add(item.id, f"{item.title} · {item.object_type}")
        elif domain == "fundamentals":
            try:
                companies = self.service("fundamentals").search_companies(query, limit=20)
            except SecIdentityMissingError as exc:
                # Mensaje redactado por Gamma (sin datos del proveedor): se puede mostrar tal cual.
                return {"items": [], "warnings": [str(exc)], "limitations": DATASETS[domain][1], "status": "unavailable"}
            for item in companies:
                add(item.ticker, f"{item.ticker} · {item.name} · CIK {item.cik}")
        elif domain == "options_capture":
            records, warnings = self.service("options").records()
            for item in sorted(records, key=lambda r: r["captured_at"], reverse=True):
                add(item["snapshot_id"], f"{item['surface']['symbol']} · {item['captured_at']} · {item['snapshot_id']}")
        elif domain.startswith("commodity_"):
            workspace = self.service("commodities").get_workspace()
            warnings = workspace.warnings
            if domain in {"commodity_history", "commodity_curve"}:
                for item in workspace.instruments:
                    add(item.instrument_id, f"{item.name} · {item.symbol} · {item.quote_unit}")
            elif domain == "commodity_spread":
                for item in workspace.spreads:
                    add(item.definition.spread_id, item.definition.label)
            else:
                for item in workspace.inventories:
                    add(item.metadata.series_id, f"{item.metadata.label} · {item.metadata.unit}")
        elif domain.startswith("crypto_"):
            from src.models.crypto import CryptoScreenerRequest
            workspace = self.service("crypto").get_workspace(CryptoScreenerRequest(query=query, limit=20))
            warnings = workspace.warnings
            for item in workspace.tokens:
                add(item.token_id, f"{item.name} · {item.symbol} · {item.token_id}")
        else:
            from src.application.prediction_market_service import PredictionMarketScreenerRequest
            workspace = self.service("prediction").screener(PredictionMarketScreenerRequest(query=query, limit=20))
            warnings = workspace.warnings
            for item in workspace.markets:
                for outcome in item.outcomes:
                    add(item.market_id, f"{item.venue} · {item.title} · {outcome.label}", outcome_id=outcome.outcome_id)
        # Provider search may match text outside the display label; don't filter those again.
        if domain not in {"fundamentals", "crypto_history", "crypto_liquidity", "prediction_history"}:
            rows = [r for r in rows if query.casefold() in (r["label"] + r["object_id"]).casefold()]
        if len(rows) > 40:
            warnings = [*warnings, f"Showing 40 of {len(rows)} matches; refine your search."]
        return {"items": rows[:40], "warnings": warnings, "limitations": DATASETS[domain][1], "status": "available" if rows else "empty"}

    def acquire(self, request):
        domain, identity = request.domain, request.object_id
        if domain not in DATASETS:
            raise DatasetSelectionError("Unsupported dataset.")
        if domain == "equity_history":
            instrument = self.equities().get(identity)
            if instrument is None:
                raise DatasetSelectionError("Select an exact instrument from the curated catalog.")
            days = request.lookback_days or EQUITY_DEFAULT_LOOKBACK_DAYS
            if not 20 <= days <= 3650:
                raise DatasetSelectionError("Equity lookback must be between 20 and 3650 days.")
            frequency = request.frequency or "daily"
            if frequency not in {"daily", "weekly", "monthly"}:
                raise DatasetSelectionError("Unsupported equity frequency.")
            result = self.service("equity").load_instrument_history_result(instrument.to_reference(), days)
            series = result.series
            if series is None or series.empty:
                raise DatasetSelectionError("Selected instrument history is unavailable.")
            series = series.dropna().sort_index()
            # Se copian cierres diarios; apply_window recorta a la ventana pedida y después remuestrea.
            return {"instrument": plain(instrument), "frequency": "daily", "unit": instrument.currency,
                    "source_provider": result.source_provider, "retrieved_at": plain(result.retrieved_at),
                    "origin": result.origin, "freshness_label": plain(result.freshness_label),
                    "transformation_note": result.transformation_note, "warnings": result.warnings,
                    "points": [{"timestamp": plain(t.to_pydatetime()), "close": float(v)} for t, v in series.items()]}
        if domain == "macro_series":
            from src.application.macro_service import SERIES_REGISTRY, TIMEFRAME_DAYS
            meta = SERIES_REGISTRY.get(identity)
            if meta is None or request.region != meta["region"] or (request.timeframe or "1Y") not in TIMEFRAME_DAYS:
                raise DatasetSelectionError("Select an exact Macro series, region and supported timeframe.")
            result = self.service("macro").get_series_history(identity, region=request.region, timeframe=request.timeframe or "1Y", force_refresh=False)
            if result is not None and (result.series_id != identity or result.region != request.region):
                raise DatasetSelectionError("Macro identity mismatch.")
            return result
        if domain == "saved_research":
            return self.service("research").load_saved_research(identity)
        if domain == "fundamentals":
            try:
                result = self.service("fundamentals").get_financials(identity)
            except SecIdentityMissingError as exc:
                raise DatasetServiceUnavailableError(str(exc)) from exc
            if result is not None and result.company.ticker.upper() != identity.upper():
                raise DatasetSelectionError("Company identity mismatch.")
            return result
        if domain == "options_capture":
            # Una captura inexistente o corrupta es un error del objeto pedido, no una caída del proveedor.
            options = self.service("options")  # Fuera del try: un servicio ausente sigue siendo 503.
            try:
                result = options.load(identity)
            except FileNotFoundError as exc:
                raise DatasetNotFoundError("The exact retained capture was not found; nothing was substituted.") from exc
            except ValueError as exc:
                raise DatasetSelectionError("The retained capture failed integrity validation; the original file is retained.") from exc
            if result.get("snapshot_id") != identity or not result.get("surface", {}).get("snapshot_available"):
                raise DatasetSelectionError("The exact retained capture is unavailable.")
            return result
        if domain == "commodity_history":
            result = self.service("commodities").get_price_history(identity)
            if result is not None and result.instrument_id != identity:
                raise DatasetSelectionError("Commodity identity mismatch.")
            return result
        if domain == "commodity_curve":
            result = self.service("commodities").get_curve(identity)
            if result is not None and result.instrument_id != identity:
                raise DatasetSelectionError("Commodity identity mismatch.")
            if result is not None and not result.nodes:
                raise DatasetSelectionError("No curve nodes are available for the selected commodity.")
            return result
        if domain in {"commodity_spread", "commodity_inventory"}:
            workspace = self.service("commodities").get_workspace()
            rows = workspace.spreads if domain == "commodity_spread" else workspace.inventories
            return next((r for r in rows if (r.definition.spread_id if domain == "commodity_spread" else r.metadata.series_id) == identity), None)
        if domain == "crypto_history":
            days = CRYPTO_TIMEFRAME_DAYS.get(request.timeframe or "30D")
            if days is None:
                raise DatasetSelectionError("Crypto timeframe must be 30D, 90D or 1Y.")
            token = self.service("crypto").get_token_detail(identity)
            if token is None or token.token_id != identity:
                raise DatasetSelectionError("Exact token is unavailable.")
            return {"token_id": identity, "unit": "USD", "frequency": "provider observations; not resampled",
                    "points": self.service("crypto").get_price_history(identity, days=days)}
        if domain == "crypto_liquidity":
            token = self.service("crypto").get_token_detail(identity)
            liquidity = self.service("crypto").get_dex_liquidity(identity)
            if token is None or token.token_id != identity or (liquidity and liquidity.token_id != identity):
                raise DatasetSelectionError("Exact token is unavailable.")
            return {"token": token, "liquidity": liquidity, "unit": "USD for market/price/reserve values; supply and pool volumes retain native field units"}
        market = self.service("prediction").get_market_detail(identity)
        if market is None or market.market_id != identity or not request.outcome_id or not any(o.outcome_id == request.outcome_id for o in market.outcomes):
            raise DatasetSelectionError("Select an exact contract and outcome.")
        timeframe = request.timeframe or "1m"
        if timeframe not in {"1d", "1w", "1m", "3m", "1y", "max"}:
            raise DatasetSelectionError("Unsupported probability history range.")
        history = self.service("prediction").get_history_series(identity, range_key=timeframe, outcome_id=request.outcome_id)
        if history is None or history.market_id != identity or history.outcome_id != request.outcome_id:
            raise DatasetSelectionError("Exact outcome history unavailable.")
        return {"market": market, "history": history, "unit": "probability fraction [0,1]", "frequency": "provider resolution; see history.effective_resolution_minutes"}

    @staticmethod
    def apply_window(request, payload):
        """Aplica y describe la ventana pedida sobre el payload copiado (lo modifica en sitio).

        Devuelve (ventana | None, avisos, notas). Una historia más larga que la pedida se recorta; una
        cobertura más corta impuesta por el proveedor se etiqueta. Ninguna ventana cambia en silencio.
        """
        domain, warnings, notes = request.domain, [], []
        supported = WINDOW_PARAMETERS.get(domain, set())
        for name in ("lookback_days", "timeframe", "frequency"):
            value = getattr(request, name)
            if value is not None and name not in supported:
                reason = ("observations keep the owning service's native frequency" if name == "frequency"
                          else "metadata.window describes the window actually exported" if supported
                          else "this dataset has no requested window and is copied as provided")
                warnings.append(f"{name}={value!r} is not applied to {domain}; {reason}.")
        points = (payload.get("history") or {}).get("points") if domain == "prediction_history" else payload.get("points")
        if domain not in WINDOW_PARAMETERS or not isinstance(points, list) or not points:
            return None, warnings, notes
        if domain == "prediction_history":
            # El servicio propietario ya recorta a su ventana; aquí solo se declara y se verifica la cobertura.
            from src.application.prediction_market_service import HISTORY_RANGE_DAYS
            history, timeframe = payload["history"], request.timeframe or "1m"
            days = HISTORY_RANGE_DAYS.get(timeframe)
            window = {"basis": "owning_service_range", "lookback_days": days, "anchor": "owning_service_window",
                      "start": history.get("window_start"), "end": history.get("window_end"),
                      "effective_range": history.get("effective_range"), **coverage(points)}
            if days is None or not window["start"]:
                window["status"] = "full_available_history"
            elif _shortfall(_timestamp(window["coverage_start"]), _timestamp(window["start"]), [_timestamp(p["timestamp"]) for p in points], days):
                window["status"] = "shorter_than_request"
            else:
                window["status"] = "within_request"
        else:
            if domain == "macro_series":
                from src.application.macro_service import TIMEFRAME_DAYS
                days = TIMEFRAME_DAYS[request.timeframe or "1Y"]
            elif domain == "crypto_history":
                days = CRYPTO_TIMEFRAME_DAYS[request.timeframe or "30D"]
            elif domain == "equity_history":
                days = request.lookback_days or EQUITY_DEFAULT_LOOKBACK_DAYS
            else:
                days = request.lookback_days
            payload["points"], window = bound_to_calendar_window(points, days)
            if window["status"] == "trimmed_to_request":
                notes.append(f"The owning service returned {window['provider_observations']} observations "
                             f"({window['provider_coverage_start']} to {window['provider_coverage_end']}); Gamma kept the "
                             f"{window['observations']} observations inside the requested {days}-calendar-day window ending at the latest observation.")
            frequency = request.frequency or "daily"
            if domain == "equity_history" and frequency != "daily":
                payload["points"], payload["frequency"] = resample_last(payload["points"], frequency), frequency
                window.update(coverage(payload["points"]))
                notes.append(f"Resampled to {frequency} after windowing, keeping the last observation per "
                             f"{'week ending Friday' if frequency == 'weekly' else 'calendar month'} at its observed date.")
        window["requested"] = {name: getattr(request, name) for name in sorted(supported)}
        window["lookback_source"] = "requested" if any(getattr(request, n) is not None for n in supported - {"frequency"}) else (
            "not_requested" if domain == "commodity_history" else "default")
        if window["status"] == "shorter_than_request":
            warnings.append(f"Requested {window['lookback_days']} calendar days ending {window['end'] or window['coverage_end']}; the owning "
                            f"service supplied observations only from {window['coverage_start']} ({window['coverage_calendar_days']} "
                            "calendar days). Gamma did not backfill the difference.")
        return window, warnings, notes

    def preview(self, script_id, request):
        self.owner.get_script(script_id)
        payload = plain(self.acquire(request))
        if payload is None:
            raise DatasetSelectionError("Selected dataset is unavailable; existing inputs are unchanged.")
        window, window_warnings, window_notes = self.apply_window(request, payload) if isinstance(payload, dict) else (None, [], [])
        public_token_fields = (
            {"token_id", "outcome_token_id", "subject_token_id", "base_token_price_usd", "quote_token_symbol", "top_tokens"}
            if request.domain.startswith(("crypto_", "prediction_")) else set()
        )
        def contains_sensitive(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    normalized = key.lower()
                    public_wrapper = normalized == "token" and request.domain == "crypto_liquidity" and isinstance(item, dict)
                    if normalized in {"path", "host_path", "local_path", "environment", "environ", "service_handle"} or (not public_wrapper and normalized not in public_token_fields and self.owner._payload_contains_sensitive_key({key: None})):
                        return True
                    if contains_sensitive(item):
                        return True
            elif isinstance(value, list):
                return any(contains_sensitive(item) for item in value)
            return False
        if contains_sensitive(payload):
            raise DatasetSelectionError("Dataset contains fields outside the Script export boundary.")
        metadata = describe(payload)
        sources = " ".join(metadata["sources"]).lower()
        if any(word in sources for word in ("mock", "sample")):
            metadata["states"].append("mock/sample")
            metadata["warnings"].append("Contains mock/sample data; this is not live-provider evidence.")
        if not metadata["states"]:
            metadata["states"].append("unknown freshness")
        origins = json.dumps(payload, ensure_ascii=False)
        metadata["cache_status"] = "cached" if 'research_cache.' in origins else "not_reported_by_owning_service"
        metadata["field_notes"] = {
            "equity_history": "points.close is in instrument.currency; timestamp is the observed date. lookback_days is a calendar-day window ending at the latest observation (metadata.window). Weekly/monthly keeps the last available observation per period at its observed date, without filling gaps.",
            "macro_series": "points.value uses the series unit and native frequency; derived transformations are retained in transformation_note. timeframe is applied as the Macro service's calendar-day window ending at the latest observation (metadata.window).",
            "saved_research": "Saved payload is heterogeneous: units, methodology and coverage are supplied by the saved object's own fields.",
            "fundamentals": "Statement lines carry unit; cells retain period_key, value, filing/accession, date and provenance. Ratios retain their native unit; display_value is presentation only. Missing cells remain null.",
            "options_capture": "surface.contracts contains observed quotes with exact contract_id/con_id/expiry/right/strike/currency/multiplier. Bid/ask/last/model/derived Greeks remain separate. IV is an annualized fraction; grid values may be fitted: inspect cell_sources and surface_model. Captured_at is storage time, not retrieval time.",
            "commodity_history": "points.value uses history.unit; source basis/proxy limitations remain in warnings and origin. lookback_days, when given, is a calendar-day window ending at the latest observation; otherwise all available history is copied (metadata.window).",
            "commodity_curve": "nodes.price uses the selected instrument quote unit; nodes.contract preserves contract_id/month/expiry. Shape/spread/roll metrics are derived, not observations.",
            "commodity_spread": "history.value and value use definition.unit; definition.formula and left/right_leg_id identify transformations and legs. z_score is dimensionless; percentile is percent.",
            "commodity_inventory": "points.value uses metadata.unit and metadata.frequency. Latest change and seasonal percentile are derived; seasonal_percentile is percent.",
            "crypto_history": "points.price, market_cap and total_volume are USD; total_volume is provider-reported rolling market volume, not trade-level volume. Observations retain their native timestamps; timeframe is a calendar-day window ending at the latest observation (metadata.window).",
            "crypto_liquidity": "Prices, market caps, reserves and *_usd fields are USD; supplies are native token quantities. *_pct fields are percent; *_ratio/share fields are dimensionless. Pool records preserve network/address/pool_id. This is a current snapshot, not liquidity history.",
            "prediction_history": "history.points.probability is a fraction [0,1]. Exact market_id, outcome_id and outcome token_id are retained. Effective range/resolution/coverage may differ from the requested range, as reported by the owning service; metadata.window records its window and status.",
        }[request.domain]
        # Empty histories cannot masquerade as successful exports.
        def empty_history(v):
            return isinstance(v, dict) and (("points" in v and not v["points"]) or any(empty_history(i) for i in v.values()))
        if empty_history(payload):
            raise DatasetSelectionError("Selected history has no available observations.")
        metadata.update({"contract_version": "gamma-script-dataset.v1", "domain": request.domain,
                         "source_provider": ",".join(metadata["sources"]) or "unknown",
                         "retrieved_at": metadata["retrieval_times"][0] if metadata["retrieval_times"] else None,
                         "origin": "script_dataset_catalog.preview",
                         "object_id": request.object_id, "outcome_id": request.outcome_id,
                         "timeframe": request.timeframe, "region": request.region,
                         "lookback_days": request.lookback_days, "frequency": request.frequency,
                         "materialized_at": now_utc().isoformat(), "limitations": DATASETS[request.domain][1],
                         "transformation_note": "Copied normalized owning-service payload to JSON; nested units, provenance, identities and missing values retained. No interpolation or historical backfill added."})
        if window is not None:
            # La cobertura publicada es la de las observaciones exportadas, no la de otras fechas del payload.
            metadata["window"] = window
            metadata["coverage_start"], metadata["coverage_end"] = window["coverage_start"], window["coverage_end"]
        if window_notes:
            metadata["transformation_note"] = " ".join([metadata["transformation_note"], *window_notes])
        metadata["warnings"].extend(window_warnings)
        if request.domain == "commodity_curve":
            workspace = self.service("commodities").get_workspace()
            instrument = next((i for i in workspace.instruments if i.instrument_id == request.object_id), None)
            if instrument:
                metadata["units"].append(instrument.quote_unit)
        if request.domain == "options_capture":
            metadata["units"].append("IV: annualized fraction; quotes: contract currency; strikes: underlying currency")
        if request.domain == "crypto_liquidity" and (not payload.get("liquidity") or not payload["liquidity"].get("pools")):
            metadata["states"].append("partial")
            metadata["warnings"].append("DEX pool liquidity unavailable; only available token market fields are included.")
        if not metadata["units"]:
            metadata["warnings"].append("Units are field-specific or unspecified; inspect native unit fields before calculation.")
        if not metadata["retrieval_times"]:
            metadata["warnings"].append("Upstream retrieval time is unavailable; materialized_at is the copy time only.")
        metadata["warnings"].append("Provider cache use may be implicit; original upstream retrieval timestamps are retained when supplied. Preview is a copied snapshot, not a live subscription.")
        # NaN/Infinity no es JSON válido ni un valor que Gamma deba inventar: el dataset elegido no es exportable (422).
        if (location := first_non_finite(payload)) is not None:
            raise DatasetSelectionError(f"Dataset contains a non-finite number (NaN or Infinity) at {location}; Gamma does not "
                                        "convert it to a value. Choose another object or range; existing inputs are unchanged.")
        encoded = json.dumps({"metadata": metadata, "data": payload}, sort_keys=False, ensure_ascii=False, allow_nan=False).encode("utf-8")
        from src.application.request_limits import MAX_RESEARCH_SCRIPT_INDIVIDUAL_INPUT_BYTES
        if len(encoded) > MAX_RESEARCH_SCRIPT_INDIVIDUAL_INPUT_BYTES:
            raise DatasetSelectionError("Dataset exceeds the individual input limit; choose a smaller range.")
        preview_id = uuid4().hex
        result = {**metadata, "preview_id": preview_id, "byte_size": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest()}
        with self._lock:
            self._previews = {k: v for k, v in self._previews.items() if time.monotonic() - v[0] < self.TTL}
            while self._previews and (len(self._previews) >= self.MAX_PREVIEWS or sum(len(v[3]) for v in self._previews.values()) + len(encoded) > self.MAX_PREVIEW_BYTES):
                self._previews.pop(next(iter(self._previews)))
            self._previews[preview_id] = (time.monotonic(), script_id, result, encoded)
        return result

    def retained_preview(self, script_id, request):
        with self._lock:
            item = self._previews.get(request.preview_id)
        if item is None or item[1] != script_id or time.monotonic() - item[0] >= self.TTL:
            raise DatasetSelectionError("Dataset preview expired or belongs to another script. Inspect it again before adding.")
        _, _, metadata, encoded = item
        if any(getattr(request, key) != metadata[key] for key in ("domain", "object_id", "outcome_id", "timeframe", "region", "lookback_days", "frequency")):
            raise DatasetSelectionError("Dataset selection changed. Inspect it again before adding.")
        if not request.logical_filename.endswith(".json"):
            raise DatasetSelectionError("Catalog exports use a .json filename.")
        retrieved = metadata["retrieval_times"]
        return ResearchScriptInputFileCreateRequest(
            logical_filename=request.logical_filename, media_type="application/json", content=encoded,
            gamma_object_id=request.object_id, provider_id=",".join(metadata["sources"]) or "unknown",
            retrieved_at=datetime.fromisoformat(retrieved[0]) if retrieved else None,
            transformation_note=metadata["transformation_note"], source_kind="gamma_state"), metadata
