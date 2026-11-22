"""Read-only IBKR marks for the legs of tracked ideas (Workstream 12, checkpoint I3d).

The intraday layer of an idea's hypothetical record needs one price per leg
every few minutes while Trader Workstation is connected. This adapter asks
TWS for market-data snapshots and nothing else: no orders, no account data,
no positions. IBKR capacity is scarce (roadmap budget model), so it:

* requests each instrument once per pass, in small batches, and stays inside
  the lines the Options surface engine keeps in reserve while it streams;
* runs each batch as one task on the shared IB thread, so the market-data
  type it sets (live, frozen, delayed, delayed-frozen) cannot leak into a
  request from another service, and restores the session default afterwards;
* never starts, stops or reconfigures the Options stream.

Every mark carries the data type TWS served and the field it came from, so a
delayed or frozen quote is labelled as such and never passed off as live.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Tipos de datos de mercado de TWS (reqMarketDataType).
MD_LIVE, MD_FROZEN, MD_DELAYED, MD_DELAYED_FROZEN = 1, 2, 3, 4
MARK_QUALITIES = ("live", "delayed", "frozen", "delayed_frozen")
# Lotes pequeños: con el stream de Options activo se cabe en sus líneas reservadas.
BATCH_SIZE = 8
BATCH_SIZE_WHILE_OPTIONS_STREAM = 4
QUOTE_TIMEOUT_SECONDS = 2.0
# Una suscripción breve (cripto de IBKR) tarda más en dar su primer tick que una instantánea.
STREAMING_WAIT_FACTOR = 2.5
# Cripto de IBKR (Paxos): ids de CoinGecko y símbolos que IBKR lista.
IBKR_CRYPTO = {"bitcoin": "BTC", "btc": "BTC", "ethereum": "ETH", "eth": "ETH", "litecoin": "LTC", "ltc": "LTC", "bitcoin-cash": "BCH", "bch": "BCH"}
IBKR_CRYPTO_EXCHANGE = "PAXOS"
_PRIOR_CLOSE_FIELDS = {"close", "delayedClose"}
# Errores de TWS que significan "no habrá datos" (sin suscripción, sin definición): se espera una hora.
NO_DATA_ERRORS = {200, 354, 10089, 10168, 10186}
NO_DATA_BACKOFF_SECONDS = 3600
# Avisos informativos que no impiden el dato (p. ej. "se muestran datos diferidos").
_INFO_CODES = {10167, 10090}


@dataclass(frozen=True)
class MarkRequest:
    """One instrument to mark: the leg key, how IBKR knows it and whether its market is open now."""

    key: str
    label: str
    sec_type: str  # STK | CRYPTO
    symbol: str
    market_open: bool | None = None  # None: Gamma does not know this market's hours


@dataclass(frozen=True)
class LegMark:
    """One IBKR price for one instrument, with what TWS said about it."""

    key: str
    price: float | None
    field: str | None = None
    md_type: int | None = None
    quality: str | None = None
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.price is not None


@dataclass
class MarkBatch:
    """The marks of one pass, or the reason there are none."""

    marks: dict[str, LegMark] = field(default_factory=dict)
    unavailable_reason: str | None = None
    warnings: list[str] = field(default_factory=list)


def mark_quality(md_type: int | None, price_field: str | None, market_open: bool | None) -> str:
    """Label a mark: ``live`` only when TWS served live data during the session.

    Frozen means the last price at or before the close (the market is closed,
    TWS served frozen data, or the only price is the prior session's close).
    Delayed means TWS served delayed data. Both together are delayed-frozen.
    """
    field_name = str(price_field or "")
    delayed = md_type in (MD_DELAYED, MD_DELAYED_FROZEN) or field_name.startswith("delayed")
    frozen = md_type in (MD_FROZEN, MD_DELAYED_FROZEN) or field_name in _PRIOR_CLOSE_FIELDS or market_open is False
    if delayed and frozen:
        return "delayed_frozen"
    if frozen:
        return "frozen"
    if delayed:
        return "delayed"
    return "live"


def ibkr_crypto_symbol(token: str) -> str | None:
    return IBKR_CRYPTO.get(str(token or "").strip().lower())


def _valid(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def best_price(ticker: Any) -> tuple[float | None, str | None]:
    """The most current price a snapshot ticker holds and the field it came from.

    The ``close`` tick is never a mark: TWS reports the close of the session
    before the latest one there (checked live on 2026-11-22, a Sunday: the
    delayed ``close`` was Thursday's, not Friday's), so using it would invent a
    move. A ticker with only that tick has no mark.
    """
    value = _valid(getattr(ticker, "last", None))
    if value is not None:
        return value, "last"
    bid = _valid(getattr(ticker, "bid", None))
    ask = _valid(getattr(ticker, "ask", None))
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0, "mid"
    for name in ("delayedLast",):
        value = _valid(getattr(ticker, name, None))
        if value is not None:
            return value, name
    dbid = _valid(getattr(ticker, "delayedBid", None))
    dask = _valid(getattr(ticker, "delayedAsk", None))
    if dbid is not None and dask is not None:
        return (dbid + dask) / 2.0, "delayedMid"
    return None, None


def only_prior_close(ticker: Any) -> bool:
    """TWS answered with nothing but the prior-session close."""
    return best_price(ticker)[0] is None and any(
        _valid(getattr(ticker, name, None)) is not None for name in _PRIOR_CLOSE_FIELDS
    )


class IbkrMarkReader:
    """Snapshot marks through the read-only IBKR client the runtime already holds."""

    def __init__(
        self,
        client: Any,
        *,
        iv_service: Any = None,
        market_data_mode: Callable[[], str] | str = "delayed",
        usage_ledger: Any = None,
        timeout_seconds: float = QUOTE_TIMEOUT_SECONDS,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.client = client
        self.iv_service = iv_service
        self._mode = market_data_mode
        self.usage_ledger = usage_ledger
        self.timeout_seconds = float(timeout_seconds)
        self._sleep = sleep
        self._contracts: dict[str, Any] = {}
        self._unknown: dict[str, str] = {}
        # Contrato -> (hasta cuándo no se pide, motivo de TWS); ahorra líneas de datos inútiles.
        self._backoff: dict[str, tuple[float, str]] = {}

    # -- estado ----------------------------------------------------------------

    def connected(self) -> bool:
        """TWS is connected for real (demo mode never is)."""
        if self.client is None or getattr(self.client, "mock", False):
            return False
        try:
            return bool(self.client.is_connected())
        except Exception:  # noqa: BLE001
            return False

    def options_streaming(self) -> bool:
        try:
            return bool(self.iv_service is not None and self.iv_service.is_running())
        except Exception:  # noqa: BLE001
            return False

    def market_data_mode(self) -> str:
        mode = self._mode() if callable(self._mode) else self._mode
        mode = str(mode or "delayed").strip().lower()
        return mode if mode in {"live", "auto", "delayed"} else "delayed"

    # -- lectura ---------------------------------------------------------------

    def fetch(self, requests: Sequence[MarkRequest]) -> MarkBatch:
        if not self.connected():
            return MarkBatch(unavailable_reason="Trader Workstation is not connected.")
        batch = MarkBatch()
        started = time.monotonic()
        wanted: list[tuple[MarkRequest, Any]] = []
        for request in requests:
            blocked = self._backoff.get(f"{request.sec_type}:{request.symbol}")
            if blocked is not None and blocked[0] > time.monotonic():
                batch.marks[request.key] = LegMark(key=request.key, price=None, reason=blocked[1])
                continue
            contract, reason = self._contract(request)
            if contract is None:
                batch.marks[request.key] = LegMark(key=request.key, price=None, reason=reason)
            else:
                wanted.append((request, contract))
        size = BATCH_SIZE_WHILE_OPTIONS_STREAM if self.options_streaming() else BATCH_SIZE
        for offset in range(0, len(wanted), size):
            chunk = wanted[offset : offset + size]
            try:
                results = self._run(lambda chunk=chunk: self._snapshot_chunk(chunk), timeout=self._chunk_timeout(chunk))
            except Exception as exc:  # noqa: BLE001 - TWS ocupado o caído: la pasada queda sin marca
                reason = f"IBKR did not answer the snapshot request: {exc.__class__.__name__}: {exc}"[:240]
                for request, _contract in chunk:
                    batch.marks[request.key] = LegMark(key=request.key, price=None, reason=reason)
                batch.warnings.append(reason)
                continue
            batch.marks.update(results)
        self._record_usage(batch, duration_ms=(time.monotonic() - started) * 1000.0)
        return batch

    def _types_for(self, market_open: bool | None) -> tuple[int, ...]:
        delayed_only = self.market_data_mode() == "delayed"
        if market_open is False:
            return (MD_DELAYED_FROZEN,) if delayed_only else (MD_FROZEN, MD_DELAYED_FROZEN)
        return (MD_DELAYED,) if delayed_only else (MD_LIVE, MD_DELAYED)

    def _wait_seconds(self, request: MarkRequest) -> float:
        return self.timeout_seconds * (STREAMING_WAIT_FACTOR if request.sec_type == "CRYPTO" else 1.0)

    def _default_type(self) -> int:
        return MD_DELAYED if self.market_data_mode() == "delayed" else MD_LIVE

    def _chunk_timeout(self, chunk: Sequence[tuple[MarkRequest, Any]]) -> float:
        passes = max(len(self._types_for(request.market_open)) for request, _ in chunk) if chunk else 1
        groups = len({self._types_for(request.market_open) for request, _ in chunk}) or 1
        factor = STREAMING_WAIT_FACTOR if any(request.sec_type == "CRYPTO" for request, _ in chunk) else 1.0
        return self.timeout_seconds * factor * passes * groups + 5.0

    def _snapshot_chunk(self, chunk: Sequence[tuple[MarkRequest, Any]]) -> dict[str, LegMark]:
        """Runs on the IB thread: set a type, request, wait, fall back, restore the default type."""
        ib = self.client.ib
        out: dict[str, LegMark] = {}
        groups: dict[tuple[int, ...], list[tuple[MarkRequest, Any]]] = {}
        for request, contract in chunk:
            groups.setdefault(self._types_for(request.market_open), []).append((request, contract))
        try:
            for types, members in groups.items():
                pending = list(members)
                last_error: dict[str, str] = {}
                no_data: dict[str, str] = {}
                for md_type in types:
                    if not pending:
                        break
                    ib.reqMarketDataType(md_type)
                    got = self._request_and_wait(ib, pending, md_type, last_error, no_data)
                    out.update(got)
                    pending = [(request, contract) for request, contract in pending if request.key not in got]
                    no_data = {key: text for key, text in no_data.items() if key not in got}
                for request, _contract in pending:
                    # Sin datos con ningún tipo y con un error "sin suscripción": no se vuelve a pedir en una hora.
                    if request.key in no_data:
                        self._backoff[f"{request.sec_type}:{request.symbol}"] = (
                            time.monotonic() + NO_DATA_BACKOFF_SECONDS,
                            no_data[request.key],
                        )
                    out[request.key] = LegMark(
                        key=request.key,
                        price=None,
                        reason=last_error.get(request.key) or f"IBKR returned no price for {request.label} within {self._wait_seconds(request):.0f} s.",
                    )
        finally:
            try:
                ib.reqMarketDataType(self._default_type())
            except Exception:  # noqa: BLE001
                pass
        return out

    def _request_and_wait(
        self,
        ib: Any,
        members: Sequence[tuple[MarkRequest, Any]],
        md_type: int,
        errors: dict[str, str],
        no_data: dict[str, str] | None = None,
    ) -> dict[str, LegMark]:
        no_data = {} if no_data is None else no_data
        by_conid = {getattr(contract, "conId", 0): request for request, contract in members}
        failed: set[str] = set()

        def on_error(_req_id: int, code: int, message: str, contract: Any = None) -> None:
            request = by_conid.get(getattr(contract, "conId", None))
            if request is None or code in _INFO_CODES:
                return
            text = f"IBKR error {code}: {' '.join(str(message or '').split())}"[:240]
            errors[request.key] = text
            failed.add(request.key)
            if code in NO_DATA_ERRORS:
                no_data[request.key] = text

        event = getattr(ib, "errorEvent", None)
        if event is not None:
            event += on_error
        try:
            return self._request_and_collect(ib, members, md_type, errors, failed)
        finally:
            if event is not None:
                try:
                    event -= on_error
                except Exception:  # noqa: BLE001
                    pass

    def _request_and_collect(
        self, ib: Any, members: Sequence[tuple[MarkRequest, Any]], md_type: int, errors: dict[str, str], failed: set[str]
    ) -> dict[str, LegMark]:
        tickers: list[tuple[MarkRequest, Any, Any, bool]] = []
        for request, contract in members:
            streaming = request.sec_type == "CRYPTO"
            try:
                # Las acciones piden instantánea; la cripto de IBKR no la admite y se suscribe un momento.
                ticker = ib.reqMktData(contract, "", not streaming, False)
            except Exception as exc:  # noqa: BLE001
                errors[request.key] = f"IBKR refused the quote request for {request.label}: {exc}"[:240]
                continue
            tickers.append((request, contract, ticker, streaming))
        found: dict[str, LegMark] = {}
        streaming_any = any(streaming for _request, _contract, _ticker, streaming in tickers)
        deadline = time.monotonic() + self.timeout_seconds * (STREAMING_WAIT_FACTOR if streaming_any else 1.0)
        while tickers and time.monotonic() < deadline:
            for request, _contract, ticker, _streaming in tickers:
                if request.key in found or request.key in failed:
                    continue
                price, price_field = best_price(ticker)
                if price is not None:
                    found[request.key] = self._mark(request, ticker, price, price_field, md_type)
            if len(found) + len(failed - set(found)) >= len(tickers):
                break
            self._wait(ib, 0.1)
        for request, contract, ticker, streaming in tickers:
            if request.key not in found and request.key not in failed and only_prior_close(ticker):
                errors[request.key] = (
                    f"IBKR served only the prior session's close for {request.label} (no last trade or bid/ask); "
                    "it is not used as a mark."
                )
            try:
                if request.key in failed:
                    # TWS ya cerró la petición al rechazarla; cancelarla daría el error 300.
                    ib.wrapper.endTicker(ticker, "mktData")
                elif streaming:
                    ib.cancelMktData(contract)
                else:
                    # Una instantánea termina sola; cancelarla provoca el error 300 de TWS.
                    ib.wrapper.endTicker(ticker, "mktData")
            except Exception:  # noqa: BLE001
                pass
        return found

    def _mark(self, request: MarkRequest, ticker: Any, price: float, price_field: str | None, requested: int) -> LegMark:
        reported = getattr(ticker, "marketDataType", None)
        # ib_insync deja 1 por defecto si TWS no informa: se conserva el tipo pedido, que es el prudente.
        md_type = reported if isinstance(reported, int) and reported in (2, 3, 4) else requested
        return LegMark(
            key=request.key,
            price=float(price),
            field=price_field,
            md_type=md_type,
            quality=mark_quality(md_type, price_field, request.market_open),
        )

    def _wait(self, ib: Any, seconds: float) -> None:
        if self._sleep is not None:
            self._sleep(seconds)
            return
        try:
            ib.sleep(seconds)
        except Exception:  # noqa: BLE001
            time.sleep(seconds)

    # -- contratos -------------------------------------------------------------

    def _contract(self, request: MarkRequest) -> tuple[Any | None, str | None]:
        cache_key = f"{request.sec_type}:{request.symbol}"
        if cache_key in self._contracts:
            return self._contracts[cache_key], None
        if cache_key in self._unknown:
            return None, self._unknown[cache_key]
        from ib_insync import Contract

        if request.sec_type == "CRYPTO":
            contract = Contract(symbol=request.symbol, secType="CRYPTO", exchange=IBKR_CRYPTO_EXCHANGE, currency="USD")
        else:
            from src.models.instruments import InstrumentReference
            from src.services.research_market_data import contract_for_instrument

            contract = contract_for_instrument(InstrumentReference(symbol=request.symbol))
        try:
            qualified = self._run(lambda: self.client.ib.qualifyContracts(contract), timeout=8.0) or []
        except Exception as exc:  # noqa: BLE001 - sin cualificar no se pide nada; se reintenta en la siguiente pasada
            return None, f"IBKR could not identify {request.label}: {exc.__class__.__name__}"
        if not qualified or not getattr(qualified[0], "conId", 0):
            reason = f"IBKR does not list {request.label} as {request.sec_type} {request.symbol}."
            self._unknown[cache_key] = reason
            return None, reason
        self._contracts[cache_key] = qualified[0]
        return qualified[0], None

    def _run(self, fn: Callable[[], Any], *, timeout: float | None = None) -> Any:
        runner = getattr(self.client, "_run_ib", None)
        if callable(runner):
            return runner(fn, timeout=timeout)
        return fn()

    def _record_usage(self, batch: MarkBatch, *, duration_ms: float) -> None:
        if self.usage_ledger is None:
            return
        priced = sum(1 for mark in batch.marks.values() if mark.ok)
        total = len(batch.marks)
        status = "success" if total and priced == total else ("incomplete" if priced else "unavailable")
        try:
            self.usage_ledger.record(
                provider_id="ibkr",
                endpoint="ideas.intraday_marks",
                status=status,
                duration_ms=duration_ms,
                message=f"{priced} of {total} idea legs marked from IBKR snapshots.",
            )
        except Exception:  # pragma: no cover - la telemetría nunca rompe una pasada
            logger.debug("Could not record intraday mark usage", exc_info=True)


def requests_from(items: Mapping[str, MarkRequest]) -> list[MarkRequest]:
    return [items[key] for key in sorted(items)]


__all__ = [
    "BATCH_SIZE",
    "BATCH_SIZE_WHILE_OPTIONS_STREAM",
    "IBKR_CRYPTO",
    "IbkrMarkReader",
    "LegMark",
    "MARK_QUALITIES",
    "MarkBatch",
    "MarkRequest",
    "best_price",
    "ibkr_crypto_symbol",
    "mark_quality",
]
