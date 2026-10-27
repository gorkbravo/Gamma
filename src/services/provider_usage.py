from __future__ import annotations

import re
import socket
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from threading import RLock
from typing import Any
from urllib.parse import urlsplit

from src.models.provider_usage import ProviderUsageCall, ProviderUsageHealth, ProviderUsageSnapshot, ProviderUsageSummary
from src.utils.time import now_utc
from src.utils.tls import extended_trust_ssl_context

# Fila explícita para llamadas sin proveedor identificable: nunca desaparecen ni se
# reparten en ids ambiguos como "unknown" (GUA-20260903-10).
UNATTRIBUTED_PROVIDER_ID = "unattributed"

# Valores de ``source_provider`` que describen un estado o una mezcla, no un proveedor:
# no deben sustituir al proveedor llamado (la fila "unavailable" del audit 2026-10-21).
_PLACEHOLDER_PROVIDER_IDS = frozenset(
    {"", "unknown", UNATTRIBUTED_PROVIDER_ID, "unavailable", "none", "null", "n/a", "mixed"}
)

# Ventana retenida por defecto. Con el registro HTTP una carga de SITREP genera decenas de
# peticiones; 500 llamadas se llenaban en pocos minutos (GUA-20260903-10).
DEFAULT_MAX_CALLS = 2000

# Proveedor y endpoint del adaptador trazado que está en curso en este hilo/contexto. Las
# peticiones HTTP anidadas lo usan para nombrar la función que las originó y como
# atribución de reserva para hosts que no identifican un proveedor (feeds RSS, BLS...).
_TRACE_CONTEXT: ContextVar[tuple[str, str] | None] = ContextVar("gamma_provider_trace", default=None)

# Hosts de API externas -> proveedor. El host identifica el servicio real aunque la
# llamada salga de un adaptador compuesto: las referencias EIA/FRED de las curvas IBKR se
# atribuían a "ibkr" y sus HTTPError no se contaban en ningún sitio (GUA-20260903-10).
_HTTP_HOST_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("stlouisfed.org", "fred"),
    ("treasury.gov", "treasury"),
    ("eia.gov", "eia"),
    ("polymarket.com", "polymarket"),
    ("kalshi.com", "kalshi"),
    ("coingecko.com", "coingecko"),
    ("geckoterminal.com", "geckoterminal"),
    ("sec.gov", "sec"),
    ("db.nomics.world", "dbnomics"),
    ("census.gov", "census"),
    ("openai.com", "openai"),
    ("aisstream.io", "aisstream"),
)


@dataclass(frozen=True)
class ProviderActivationCondition:
    provider_id: str
    display_name: str
    expected_when: str
    configured: bool
    active: bool = False
    idle_status: str = "not_requested"
    idle_reason: str = "Provider has not been requested in this backend session."
    action_label: str | None = None


class ProviderUsageLedger:
    def __init__(self, *, max_calls: int = DEFAULT_MAX_CALLS, clock: Callable[[], Any] = now_utc) -> None:
        self.max_calls = max(1, int(max_calls))
        self._clock = clock
        self._calls: deque[ProviderUsageCall] = deque(maxlen=self.max_calls)
        self._activation_conditions: dict[str, ProviderActivationCondition] = {}
        self._lifetime_calls = 0
        self._lock = RLock()

    def register_activation_condition(self, condition: ProviderActivationCondition) -> None:
        with self._lock:
            self._activation_conditions[_attributed_provider_id(condition.provider_id)] = condition

    def record(
        self,
        *,
        provider_id: str,
        endpoint: str,
        status: str,
        cache_status: str | None = None,
        duration_ms: float = 0.0,
        message: str | None = None,
        kind: str = "provider",
    ) -> None:
        call = ProviderUsageCall(
            provider_id=_attributed_provider_id(provider_id),
            endpoint=_clean(endpoint, "unknown"),
            status=_normalize_status(status),
            cache_status=_normalize_cache_status(cache_status),
            duration_ms=max(0.0, float(duration_ms or 0.0)),
            recorded_at=self._clock(),
            message=str(message)[:500] if message else None,
            kind="http" if kind == "http" else "provider",
        )
        with self._lock:
            self._calls.append(call)
            self._lifetime_calls += 1

    def snapshot(self, *, limit: int = 50) -> ProviderUsageSnapshot:
        with self._lock:
            calls = list(self._calls)
            conditions = list(self._activation_conditions.values())
            lifetime_calls = self._lifetime_calls
        summaries = _summarize(calls)
        recent_limit = max(0, int(limit))
        return ProviderUsageSnapshot(
            generated_at=self._clock(),
            providers=summaries,
            health=_health_rows(summaries, conditions),
            recent_calls=list(reversed(calls[-recent_limit:])) if recent_limit else [],
            total_calls=len(calls),
            lifetime_calls=lifetime_calls,
            retained_limit=self.max_calls,
        )


class TraceableProvider:
    def __init__(
        self,
        provider: Any,
        ledger: ProviderUsageLedger,
        *,
        endpoint_prefix: str | None = None,
        provider_id: str | None = None,
    ) -> None:
        self._provider = provider
        self._ledger = ledger
        self._endpoint_prefix = endpoint_prefix
        self._provider_id = _provider_id(provider, fallback=provider_id)

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._provider, name)
        if not callable(value) or name.startswith("_"):
            return value

        @wraps(value)
        def traced(*args: Any, **kwargs: Any) -> Any:
            endpoint = self._endpoint(name)
            started = time.perf_counter()
            # Las peticiones HTTP anidadas heredan este contexto (GUA-20260903-10).
            token = _TRACE_CONTEXT.set((self._provider_id, endpoint))
            try:
                result = value(*args, **kwargs)
            except Exception as exc:
                self._ledger.record(
                    provider_id=self._provider_id,
                    endpoint=endpoint,
                    status=_exception_status(exc),
                    duration_ms=(time.perf_counter() - started) * 1000,
                    message=_exception_message(exc, redact=self._endpoint_prefix == "copilot"),
                )
                raise
            finally:
                _TRACE_CONTEXT.reset(token)
            reported_provider_id, reported_cache_status = _result_provider_identity(result)
            recorded_provider_id = reported_provider_id or self._provider_id
            self._ledger.record(
                provider_id=recorded_provider_id,
                endpoint=endpoint,
                status=_result_status(result),
                cache_status=_result_cache_status(result) or reported_cache_status,
                duration_ms=(time.perf_counter() - started) * 1000,
                message=_result_message(
                    result,
                    provider_id=recorded_provider_id,
                    redact=self._endpoint_prefix == "copilot",
                ),
            )
            return result

        return traced

    def _endpoint(self, name: str) -> str:
        return f"{self._endpoint_prefix}.{name}" if self._endpoint_prefix else name

    @property
    def __class__(self):
        return self._provider.__class__


def trace_provider(
    provider: Any,
    ledger: ProviderUsageLedger,
    *,
    endpoint_prefix: str | None = None,
    provider_id: str | None = None,
) -> Any:
    """Wrap a provider so its calls are recorded.

    Pass `provider_id` for any adapter that does not name itself: without it the
    call is attributed to whatever the result reports, and adapters that return
    plain values report nothing, which is how most of a session ends up filed
    under `unknown` (GUA-20260903-10).
    """

    return TraceableProvider(provider, ledger, endpoint_prefix=endpoint_prefix, provider_id=provider_id)


# ── Registro HTTP central (GUA-20260903-10) ──────────────────────────────
#
# Todos los adaptadores HTTP de Gamma usan ``urllib.request.urlopen`` sin ``context=``, que
# delega en el opener global. Instalar un opener que registra cada petición cuenta todas las
# llamadas externas (FRED, Tesoro, EIA, Polymarket, Kalshi, SEC, RSS...), incluidos los
# HTTPError que los adaptadores capturan y convierten en avisos, sin tocar cada adaptador.

_HTTP_RECORDER_LOCK = threading.Lock()
_HTTP_RECORDER_STATE: dict[str, ProviderUsageLedger | None] = {"ledger": None}
_HTTP_RECORDER_LOCAL = threading.local()


class _UsageRecordingOpener(urllib.request.OpenerDirector):
    """Opener global que registra cada petición en el ledger activo y la deja pasar igual."""

    def __init__(self, base: urllib.request.OpenerDirector) -> None:
        super().__init__()
        for handler in list(getattr(base, "handlers", [])):
            self.add_handler(handler)

    def open(self, fullurl: Any, *args: Any, **kwargs: Any) -> Any:
        ledger = _HTTP_RECORDER_STATE["ledger"]
        depth = int(getattr(_HTTP_RECORDER_LOCAL, "depth", 0) or 0)
        # Las redirecciones vuelven a entrar en open(): solo cuenta la petición exterior.
        if ledger is None or depth:
            return super().open(fullurl, *args, **kwargs)
        _HTTP_RECORDER_LOCAL.depth = depth + 1
        started = time.perf_counter()
        try:
            response = super().open(fullurl, *args, **kwargs)
        except Exception as exc:
            _record_http_call(
                ledger,
                fullurl,
                status=_http_exception_status(exc),
                duration_ms=(time.perf_counter() - started) * 1000,
                message=_http_exception_message(exc, fullurl),
            )
            raise
        finally:
            _HTTP_RECORDER_LOCAL.depth = depth
        code = _response_code(response)
        _record_http_call(
            ledger,
            fullurl,
            status="error" if code is not None and code >= 400 else "success",
            duration_ms=(time.perf_counter() - started) * 1000,
            message=f"HTTP {code} from {_url_location(fullurl)}" if code is not None and code >= 400 else None,
        )
        return response


def install_http_usage_recorder(ledger: ProviderUsageLedger) -> None:
    """Registra en ``ledger`` cada petición que pase por ``urllib.request.urlopen``.

    Idempotente: una segunda instalación solo cambia el ledger activo (el último runtime
    construido). Conserva los handlers de un opener instalado previamente.
    """

    with _HTTP_RECORDER_LOCK:
        _HTTP_RECORDER_STATE["ledger"] = ledger
        current = getattr(urllib.request, "_opener", None)
        if isinstance(current, _UsageRecordingOpener):
            return
        # Sin opener previo, el HTTPS confía en las raíces del sistema más las de certifi: así una
        # cadena como la del BCE (Sectigo E46, ausente del almacén de Windows) verifica en el primer
        # intento por este opener y queda registrada, en vez de fallar y reintentarse fuera de él.
        base = (
            current
            if isinstance(current, urllib.request.OpenerDirector)
            else urllib.request.build_opener(urllib.request.HTTPSHandler(context=extended_trust_ssl_context()))
        )
        urllib.request.install_opener(_UsageRecordingOpener(base))


def uninstall_http_usage_recorder() -> None:
    """Deja de registrar peticiones HTTP (el opener sigue instalado y solo las deja pasar)."""

    with _HTTP_RECORDER_LOCK:
        _HTTP_RECORDER_STATE["ledger"] = None


def http_provider_for_host(host: str | None) -> str | None:
    text = str(host or "").strip().lower().rstrip(".")
    if not text:
        return None
    for suffix, provider_id in _HTTP_HOST_PROVIDERS:
        if text == suffix or text.endswith("." + suffix):
            return provider_id
    return None


def _record_http_call(
    ledger: ProviderUsageLedger,
    fullurl: Any,
    *,
    status: str,
    duration_ms: float,
    message: str | None,
) -> None:
    host = _url_host(fullurl)
    context = _TRACE_CONTEXT.get()
    context_provider = context[0] if context and context[0].lower() not in _PLACEHOLDER_PROVIDER_IDS else None
    provider_id = http_provider_for_host(host) or context_provider or UNATTRIBUTED_PROVIDER_ID
    endpoint = f"http:{host or 'unknown-host'}"
    if context:
        endpoint = f"{endpoint} via {context[1]}"
    try:
        ledger.record(
            provider_id=provider_id,
            endpoint=endpoint,
            status=status,
            duration_ms=duration_ms,
            message=message,
            kind="http",
        )
    except Exception:  # noqa: BLE001 - el diagnóstico nunca debe romper la petición
        return


def _request_url(fullurl: Any) -> str:
    return str(getattr(fullurl, "full_url", fullurl) or "")


def _url_host(fullurl: Any) -> str:
    try:
        return (urlsplit(_request_url(fullurl)).hostname or "").lower()
    except ValueError:
        return ""


def _url_location(fullurl: Any) -> str:
    """Host y ruta, nunca la query: FRED y EIA llevan la clave de API en ella."""

    try:
        parts = urlsplit(_request_url(fullurl))
    except ValueError:
        return "unknown URL"
    return f"{(parts.hostname or 'unknown-host').lower()}{parts.path or ''}"


def _response_code(response: Any) -> int | None:
    for attribute in ("status", "code"):
        value = getattr(response, attribute, None)
        if isinstance(value, int):
            return value
    getcode = getattr(response, "getcode", None)
    if callable(getcode):
        try:
            value = getcode()
        except Exception:  # noqa: BLE001
            return None
        return value if isinstance(value, int) else None
    return None


def _http_exception_status(exc: Exception) -> str:
    reason = getattr(exc, "reason", None)
    if isinstance(exc, (TimeoutError, socket.timeout)) or isinstance(reason, (TimeoutError, socket.timeout)):
        return "timeout"
    return "error"


def _http_exception_message(exc: Exception, fullurl: Any) -> str:
    location = _url_location(fullurl)
    if isinstance(exc, urllib.error.HTTPError):
        reason = str(getattr(exc, "reason", "") or "").strip()
        return f"HTTP {exc.code}{(' ' + reason) if reason else ''} from {location}"
    reason = getattr(exc, "reason", None)
    detail = str(reason if reason is not None else exc).strip() or exc.__class__.__name__
    # Algunos errores (p. ej. "unknown url type") repiten la URL completa con su query.
    detail = re.sub(r"\?[^\s'\"<>]*", "?<redacted>", detail)
    return f"{exc.__class__.__name__}: {detail} ({location})"


def _summarize(calls: list[ProviderUsageCall]) -> list[ProviderUsageSummary]:
    grouped: dict[str, list[ProviderUsageCall]] = {}
    for call in calls:
        grouped.setdefault(call.provider_id, []).append(call)

    summaries: list[ProviderUsageSummary] = []
    for provider_id, rows in grouped.items():
        call_count = len(rows)
        durations = [row.duration_ms for row in rows]
        endpoints = sorted({row.endpoint for row in rows})
        last = rows[-1]
        last_error = next(
            (
                row.message
                for row in reversed(rows)
                if row.status in {"error", "refused", "incomplete", "cancelled", "timeout"}
                and row.message
            ),
            None,
        )
        summaries.append(
            ProviderUsageSummary(
                provider_id=provider_id,
                call_count=call_count,
                success_count=sum(1 for row in rows if row.status == "success"),
                unavailable_count=sum(1 for row in rows if row.status == "unavailable"),
                # Una respuesta parcial ("incomplete") no es un fallo: tiene su propio contador.
                # Contarla en los dos inflaba "failed" (us_macro_events sin BLS, superficies IBKR
                # con celdas ajustadas) y la salud decía "3 failed and 3 returned partial data".
                error_count=sum(
                    1 for row in rows if row.status in {"error", "refused", "cancelled", "timeout"}
                ),
                incomplete_count=sum(1 for row in rows if row.status == "incomplete"),
                cache_hit_count=sum(1 for row in rows if row.cache_status == "hit"),
                cache_miss_count=sum(1 for row in rows if row.cache_status == "miss"),
                average_duration_ms=sum(durations) / call_count if call_count else 0.0,
                last_status=last.status,
                last_message=last.message,
                last_error=last_error,
                last_called_at=last.recorded_at,
                endpoints=endpoints,
                http_request_count=sum(1 for row in rows if row.kind == "http"),
            )
        )
    return sorted(summaries, key=lambda row: (row.last_called_at is None, row.last_called_at), reverse=True)


def _health_rows(
    summaries: list[ProviderUsageSummary],
    conditions: list[ProviderActivationCondition],
) -> list[ProviderUsageHealth]:
    by_provider = {row.provider_id: row for row in summaries}
    condition_ids = {condition.provider_id for condition in conditions}
    rows = [_health_for_condition(condition, by_provider.get(condition.provider_id)) for condition in conditions]
    for summary in summaries:
        if summary.provider_id not in condition_ids:
            if summary.provider_id == UNATTRIBUTED_PROVIDER_ID:
                rows.append(
                    _health_for_summary(
                        summary,
                        summary.provider_id,
                        "Unattributed calls",
                        "A call reached Gamma's usage ledger without an identifiable provider.",
                    )
                )
                continue
            rows.append(_health_for_summary(summary, summary.provider_id, summary.provider_id, "Provider was requested."))
    return sorted(rows, key=lambda row: (_health_sort_rank(row.health_status), row.provider_id))


def _health_for_condition(
    condition: ProviderActivationCondition,
    summary: ProviderUsageSummary | None,
) -> ProviderUsageHealth:
    if summary is not None:
        return _health_for_summary(summary, condition.provider_id, condition.display_name, condition.expected_when)
    if not condition.configured:
        return ProviderUsageHealth(
            provider_id=condition.provider_id,
            display_name=condition.display_name,
            health_status="needs_config",
            health_label="Needs config",
            expected_when=condition.expected_when,
            reason="Provider is not configured for the current runtime.",
            action_label=condition.action_label,
        )
    status = condition.idle_status if not condition.active else "not_requested"
    return ProviderUsageHealth(
        provider_id=condition.provider_id,
        display_name=condition.display_name,
        health_status=status,
        health_label=_health_label(status),
        expected_when=condition.expected_when,
        reason=condition.idle_reason,
        action_label=condition.action_label,
    )


def _health_for_summary(
    summary: ProviderUsageSummary,
    provider_id: str,
    display_name: str,
    expected_when: str,
) -> ProviderUsageHealth:
    """Health across the whole retained window, not just the last request.

    GUA-20260903-5: a badge derived only from `last_status` reported IBKR as
    Healthy with 86/86 successes while user-visible requests inside that window
    had failed or come back partial. Session reachability and request outcomes
    are now reported as separate facts.
    """
    session_status = "connected" if summary.last_status != "error" else "unstable"
    failed = int(summary.error_count or 0)
    partial = int(summary.incomplete_count or 0)
    unavailable = int(summary.unavailable_count or 0)

    if summary.last_status in {"error", "refused", "cancelled", "timeout"}:
        status = "degraded"
        reason = summary.last_error or summary.last_message or "Recent provider request failed."
    elif summary.last_status == "incomplete":
        status = "degraded"
        reason = summary.last_message or "The most recent provider request returned incomplete data."
    elif summary.last_status == "unavailable":
        status = "unavailable"
        reason = summary.last_message or "Provider was requested but returned unavailable data."
    elif failed or partial or unavailable:
        # The last call succeeded, but requests inside this window did not.
        status = "degraded"
        parts = []
        if failed:
            parts.append(f"{failed} failed")
        if partial:
            parts.append(f"{partial} returned partial data")
        if unavailable:
            parts.append(f"{unavailable} returned no data")
        reason = (
            f"The last request succeeded, but {' and '.join(parts)} out of {summary.call_count} recent "
            f"{display_name} requests."
        )
    else:
        status = "healthy"
        reason = summary.last_message or "Recent provider requests succeeded."
    return ProviderUsageHealth(
        provider_id=provider_id,
        display_name=display_name,
        health_status=status,
        health_label=_health_label(status),
        expected_when=expected_when,
        reason=reason,
        call_count=summary.call_count,
        success_count=summary.success_count,
        unavailable_count=summary.unavailable_count,
        error_count=summary.error_count,
        incomplete_count=partial,
        session_status=session_status,
        last_called_at=summary.last_called_at,
    )


def _health_label(status: str) -> str:
    return {
        "healthy": "Healthy",
        "degraded": "Degraded",
        "unavailable": "Unavailable",
        "needs_config": "Needs config",
        "idle_by_design": "Idle by design",
        "not_requested": "Not requested",
    }.get(status, status.replace("_", " ").title())


def _health_sort_rank(status: str) -> int:
    return {
        "degraded": 0,
        "unavailable": 1,
        "needs_config": 2,
        "healthy": 3,
        "idle_by_design": 4,
        "not_requested": 5,
    }.get(status, 9)


def _provider_id(provider: Any, *, fallback: str | None = None) -> str:
    """A provider that names itself wins: only it knows whether it is the live
    adapter, a mock, or a disabled stand-in."""

    declared = _clean(
        getattr(provider, "provider_id", None)
        or getattr(provider, "source_name", None)
        or getattr(provider, "provider_name", None),
        "",
    )
    return declared or _clean(fallback, "") or _provider_id_from_class(provider)


def _provider_id_from_class(provider: Any) -> str:
    """Last resort before `unknown`: name the adapter that was called.

    An adapter class name identifies the provider well enough to act on
    (`FredMacroAdapter` -> `fred_macro`), which is more than `unknown` ever tells
    the user about which source failed.
    """

    name = provider.__class__.__name__
    for suffix in ("DataProvider", "Provider", "Adapter", "Client", "Service"):
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
            break
    snake = re.sub(r"(?<!^)(?=[A-Z][a-z])", "_", name).lower()
    snake = re.sub(r"_+", "_", snake).strip("_")
    return snake or "unknown"


def _result_provider_id(result: Any) -> str | None:
    return _result_provider_identity(result)[0]


def _result_provider_identity(result: Any) -> tuple[str | None, str | None]:
    """Proveedor que declara el resultado y, si lo indica el sufijo, un acierto de caché.

    Un ``source_provider`` de estado ("unavailable", "mixed"...) no nombra a nadie y no
    sustituye al proveedor llamado; ``ibkr_cached`` es IBKR servido desde caché, no un
    proveedor aparte (GUA-20260903-10).
    """

    value = _clean(getattr(result, "source_provider", None), "")
    if not value or value.lower() in _PLACEHOLDER_PROVIDER_IDS:
        return None, None
    lowered = value.lower()
    if lowered.endswith("_cached") and len(lowered) > len("_cached"):
        return value[: -len("_cached")], "hit"
    return value, None


def _attributed_provider_id(value: Any) -> str:
    text = _clean(value, "")
    if not text or text.lower() in {"unknown", UNATTRIBUTED_PROVIDER_ID}:
        return UNATTRIBUTED_PROVIDER_ID
    return text


def _result_status(result: Any) -> str:
    terminal_status = str(getattr(result, "status", "") or "").strip().lower()
    if terminal_status in {"ready", "completed", "complete", "success", "ok"}:
        return "success"
    if terminal_status in {"unavailable", "disabled", "unconfigured"}:
        return "unavailable"
    if terminal_status in {"refused", "incomplete", "cancelled", "canceled", "timeout", "timed_out"}:
        return _normalize_status(terminal_status)
    if terminal_status in {"error", "failed", "failure"}:
        return "error"
    freshness = str(getattr(result, "freshness_label", "") or "").lower()
    source_provider = str(getattr(result, "source_provider", "") or "").lower()
    if source_provider == "unavailable" or "unavailable" in freshness:
        return "unavailable"
    if getattr(result, "series", True) is None:
        return "unavailable"
    return "success"


def _result_cache_status(result: Any) -> str | None:
    freshness = str(getattr(result, "freshness_label", "") or "").lower()
    if "cached" in freshness:
        return "hit"
    return None


# Tokens that identify a provider inside free-text warnings. A composed result
# legitimately carries other providers' warnings -- an IBKR commodities snapshot
# is built on a reference provider -- so the first warning on a result is not
# necessarily about the provider that was called.
_PROVIDER_WARNING_TOKENS: dict[str, tuple[str, ...]] = {
    "ibkr": ("ibkr", "tws", "interactive brokers"),
    "fred": ("fred",),
    "treasury": ("treasury",),
    "dbnomics": ("dbnomics", "db.nomics"),
    "census": ("census",),
    "eia": ("eia",),
    "sec": ("sec ", "edgar"),
    "yfinance": ("yfinance", "yahoo"),
    "polymarket": ("polymarket",),
    "kalshi": ("kalshi",),
    "coingecko": ("coingecko",),
    "geckoterminal": ("geckoterminal",),
    "aisstream": ("aisstream",),
    "openai": ("openai",),
    "rss": ("rss",),
}


def _warning_names_provider(warning: str, provider_id: str) -> bool:
    text = warning.lower()
    tokens = _PROVIDER_WARNING_TOKENS.get(provider_id)
    if tokens:
        return any(token in text for token in tokens)
    return provider_id.replace("_", " ") in text or provider_id in text


def _warning_names_another_provider(warning: str, provider_id: str) -> bool:
    text = warning.lower()
    for candidate, tokens in _PROVIDER_WARNING_TOKENS.items():
        if candidate == provider_id:
            continue
        if any(token in text for token in tokens):
            return True
    return False


def _attributable_warning(warnings: list[Any], provider_id: str) -> str | None:
    """The first warning that belongs to this provider.

    A warning that names this provider wins; a generic warning that names no
    provider at all is still attributable; a warning that names someone else is
    not, and reporting it as this provider's health is how a FRED failure ended
    up under a healthy IBKR badge (GUA-20260903-10).
    """

    texts = [str(warning) for warning in warnings if str(warning).strip()]
    for text in texts:
        if _warning_names_provider(text, provider_id):
            return text
    for text in texts:
        if not _warning_names_another_provider(text, provider_id):
            return text
    return None


def _result_message(result: Any, *, provider_id: str = "unknown", redact: bool = False) -> str | None:
    if redact:
        status = _result_status(result)
        model = _clean(getattr(result, "model", None), "")
        return f"status={status}" + (f"; model={model}" if model else "")
    warnings = getattr(result, "warnings", None)
    if isinstance(warnings, list) and warnings:
        own = _attributable_warning(warnings, provider_id)
        if own is not None:
            return own
        return f"{len(warnings)} warning(s) on the result, none of them about {provider_id}."
    return None


def _exception_status(exc: Exception) -> str:
    reason = str(getattr(exc, "reason", "") or "").strip().lower()
    if reason in {"timeout", "timed_out"}:
        return "timeout"
    if exc.__class__.__name__ == "CopilotRunCancelled":
        return "cancelled"
    if isinstance(exc, TimeoutError) or "timeout" in exc.__class__.__name__.lower():
        return "timeout"
    return "error"


def _exception_message(exc: Exception, *, redact: bool = False) -> str:
    if redact:
        reason = _clean(getattr(exc, "reason", None), "")
        return exc.__class__.__name__ + (f": {reason}" if reason else "")
    return str(exc)


def _normalize_status(value: str) -> str:
    normalized = _clean(value, "success").lower()
    if normalized in {"ok", "hit", "miss"}:
        return "success"
    if normalized in {"unavailable", "empty", "missing"}:
        return "unavailable"
    if normalized in {"error", "failed", "exception"}:
        return "error"
    if normalized in {"canceled"}:
        return "cancelled"
    if normalized in {"timed_out"}:
        return "timeout"
    return normalized


def _normalize_cache_status(value: str | None) -> str | None:
    normalized = _clean(value, "").lower()
    return normalized if normalized in {"hit", "miss", "stale", "bypass"} else None


def _clean(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback
