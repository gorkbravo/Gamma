from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
from ib_insync import IB, Contract, Forex, util

from src.services.cache import CacheService
from src.services.ib_thread import IBThreadRunner
from src.services.throttle import ThrottleQueue


logger = logging.getLogger(__name__)

_FX_PRIORITY = {
    "EUR": 100,
    "GBP": 90,
    "AUD": 80,
    "NZD": 70,
    "USD": 60,
    "CAD": 50,
    "CHF": 40,
    "JPY": 30,
    "CNH": 25,
    "CNY": 25,
    "NOK": 20,
    "SEK": 10,
}


@dataclass
class QuoteSnapshot:
    price: Optional[float]
    field: Optional[str]
    delayed: bool


class MarketDataService:
    def __init__(
        self,
        ib: IB | None,
        cache: CacheService,
        ib_runner: IBThreadRunner | None = None,
        market_data_mode: str = "delayed",
        min_interval_seconds: float = 1.0,
        history_max_retries: int = 2,
        history_backoff_seconds: float = 2.0,
        history_request_timeout_seconds: float = 15.0,
        quote_timeout_seconds: float = 2.0,
    ) -> None:
        self.ib = ib
        self.ib_runner = ib_runner
        self.cache = cache
        self.market_data_mode = self._normalize_market_data_mode(market_data_mode)
        self.min_interval_seconds = min_interval_seconds
        self.history_max_retries = history_max_retries
        self.history_backoff_seconds = history_backoff_seconds
        self.history_request_timeout_seconds = history_request_timeout_seconds
        self.quote_timeout_seconds = quote_timeout_seconds
        self.queue = ThrottleQueue(min_interval_seconds)
        self._quote_cache: Dict[str, float] = {}
        self._quote_cache_ts: Dict[str, datetime] = {}
        self._errors: List[str] = []
        self._errors_lock = threading.Lock()
        self._history_lock = threading.Lock()
        self._history_cache_hits = 0
        self._history_cache_misses = 0

    def set_ib(self, ib: IB | None) -> None:
        self.ib = ib

    def set_ib_runner(self, ib_runner: IBThreadRunner | None) -> None:
        self.ib_runner = ib_runner

    @staticmethod
    def _normalize_market_data_mode(value: str | None) -> str:
        mode = str(value or "").strip().lower()
        if mode in {"delayed", "live", "auto"}:
            return mode
        return "delayed"

    def set_market_data_mode(self, value: str) -> None:
        self.market_data_mode = self._normalize_market_data_mode(value)

    def _run_ib(self, fn, *args, timeout: float | None = None, **kwargs):
        if self.ib_runner is not None:
            return self.ib_runner.run(fn, *args, timeout=timeout, **kwargs)
        return fn(*args, **kwargs)

    def _is_connected(self) -> bool:
        if self.ib is None:
            return False
        try:
            return bool(self._run_ib(lambda: self.ib.isConnected()))
        except Exception:
            return False

    @staticmethod
    def _normalize_currency(value: str | None) -> str:
        return str(value or "").strip().upper()

    @classmethod
    def _is_valid_currency_code(cls, value: str | None) -> bool:
        ccy = cls._normalize_currency(value)
        return len(ccy) == 3 and ccy.isalpha()

    @classmethod
    def _fx_contract_spec(cls, base: str, quote: str) -> tuple[Forex, bool] | None:
        base_ccy = cls._normalize_currency(base)
        quote_ccy = cls._normalize_currency(quote)
        if base_ccy == quote_ccy:
            return None
        if not cls._is_valid_currency_code(base_ccy) or not cls._is_valid_currency_code(quote_ccy):
            return None

        base_rank = _FX_PRIORITY.get(base_ccy, 0)
        quote_rank = _FX_PRIORITY.get(quote_ccy, 0)
        if quote_rank > base_rank:
            contract = Forex(f"{quote_ccy}{base_ccy}")
            invert = False
        else:
            contract = Forex(f"{base_ccy}{quote_ccy}")
            invert = True
        return contract, invert

    def _sleep(self, seconds: float) -> None:
        if self.ib_runner is not None and self.ib_runner.in_thread():
            try:
                self.ib.sleep(seconds)
                return
            except Exception:
                pass
        time.sleep(seconds)

    def drain_errors(self) -> List[str]:
        with self._errors_lock:
            errors = list(self._errors)
            self._errors.clear()
        return errors

    def quote_key(self, contract: Contract) -> str:
        if getattr(contract, "conId", None):
            return f"conid_{contract.conId}"
        parts = [contract.symbol, contract.secType, contract.currency, contract.exchange, contract.primaryExchange]
        return self.cache.make_key(*parts)

    def _cache_key(self, contract: Contract, lookback_days: int) -> str:
        base = str(contract.conId) if contract.conId else contract.symbol
        if contract.conId:
            return self.cache.make_key(base, contract.secType, contract.currency, f"lookback_{int(lookback_days)}")
        return self.cache.make_key(
            base,
            contract.secType,
            contract.currency,
            contract.exchange,
            contract.primaryExchange,
            f"lookback_{int(lookback_days)}",
        )

    def _ohlcv_cache_key(self, contract: Contract, lookback_days: int) -> str:
        return self.cache.make_key("ohlcv", self._cache_key(contract, lookback_days))

    def _record_error(self, message: str) -> None:
        with self._errors_lock:
            self._errors.append(message)

    def _fetch_history_direct(self, contract: Contract, lookback_days: int) -> Optional[pd.Series]:
        frame = self._fetch_ohlcv_history_direct(contract, lookback_days)
        if frame is None or frame.empty or "close" not in frame.columns:
            return None
        return frame["close"].astype(float).sort_index()

    def _fetch_ohlcv_history_direct(self, contract: Contract, lookback_days: int) -> Optional[pd.DataFrame]:
        if not self._is_connected():
            return None
        duration_days = max(lookback_days + 30, lookback_days)
        duration_str = self._duration_str(duration_days)
        is_fx = str(getattr(contract, "secType", "")).upper() == "CASH"
        what_to_show = "MIDPOINT" if is_fx else "TRADES"
        use_rth = False if is_fx else True

        def _do_request():
            return self.ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=duration_str,
                barSizeSetting="1 day",
                whatToShow=what_to_show,
                useRTH=use_rth,
                formatDate=1,
            )

        bars = self._run_ib(_do_request, timeout=self.history_request_timeout_seconds)
        if not bars:
            return None
        df = util.df(bars)
        index = pd.to_datetime(df["date"])
        columns = [column for column in ("open", "high", "low", "close", "volume") if column in df.columns]
        if "close" not in columns:
            return None
        frame = df.loc[:, columns].apply(pd.to_numeric, errors="coerce")
        frame.index = index
        frame = frame.dropna(subset=["close"]).sort_index()
        return frame if not frame.empty else None

    @staticmethod
    def _duration_str(days: int) -> str:
        if days <= 365:
            return f"{days} D"
        years = math.ceil(days / 365)
        return f"{years} Y"

    def fetch_history(self, contract: Contract, lookback_days: int) -> Optional[pd.Series]:
        key = self._cache_key(contract, lookback_days)
        cached = self.cache.get(key)
        if cached is not None:
            with self._history_lock:
                self._history_cache_hits += 1
            return cached
        with self._history_lock:
            self._history_cache_misses += 1
        if not self._is_connected():
            return None

        done = threading.Event()
        result: Optional[pd.Series] = None

        def task() -> Optional[pd.Series]:
            return self._fetch_history_direct(contract, lookback_days)

        def on_success(series: Optional[pd.Series]) -> None:
            nonlocal result
            result = series
            if series is not None:
                self.cache.set(key, series)
            done.set()

        def on_error(exc: Exception) -> None:
            self._record_error(f"History request failed for {contract.symbol}: {exc}")
            done.set()

        self.queue.submit(
            task,
            on_success,
            on_error,
            max_retries=self.history_max_retries,
            backoff_seconds=self.history_backoff_seconds,
        )
        if not done.wait(timeout=self._history_wait_timeout()):
            self._record_error(
                f"History request timed out for {contract.symbol} after waiting for throttled completion"
            )
            return None
        return result

    def fetch_ohlcv_history(self, contract: Contract, lookback_days: int) -> Optional[pd.DataFrame]:
        key = self._ohlcv_cache_key(contract, lookback_days)
        cached = self.cache.get_frame(key)
        if cached is not None:
            with self._history_lock:
                self._history_cache_hits += 1
            return cached
        with self._history_lock:
            self._history_cache_misses += 1
        if not self._is_connected():
            return None

        done = threading.Event()
        result: Optional[pd.DataFrame] = None

        def task() -> Optional[pd.DataFrame]:
            return self._fetch_ohlcv_history_direct(contract, lookback_days)

        def on_success(frame: Optional[pd.DataFrame]) -> None:
            nonlocal result
            result = frame
            if frame is not None:
                self.cache.set_frame(key, frame)
            done.set()

        def on_error(exc: Exception) -> None:
            self._record_error(f"OHLCV history request failed for {contract.symbol}: {exc}")
            done.set()

        self.queue.submit(
            task,
            on_success,
            on_error,
            max_retries=self.history_max_retries,
            backoff_seconds=self.history_backoff_seconds,
        )
        if not done.wait(timeout=self._history_wait_timeout()):
            self._record_error(
                f"OHLCV history request timed out for {contract.symbol} after waiting for throttled completion"
            )
            return None
        return result

    def _history_wait_timeout(self) -> float:
        attempts = max(int(self.history_max_retries), 0) + 1
        backoff_total = 0.0
        for attempt in range(max(int(self.history_max_retries), 0)):
            backoff_total += self.history_backoff_seconds * (2 ** attempt)
        return (attempts * max(self.history_request_timeout_seconds, 1.0)) + backoff_total + 1.0

    def history_cache_stats(self) -> Dict[str, float]:
        with self._history_lock:
            hits = self._history_cache_hits
            misses = self._history_cache_misses
        total = hits + misses
        hit_rate = (hits / total) if total else 0.0
        return {
            "hits": float(hits),
            "misses": float(misses),
            "requests": float(total),
            "hit_rate": float(hit_rate),
        }

    def fetch_histories(
        self,
        contracts: List[Contract],
        lookback_days: int,
        progress_cb=None,
        keys: List[str] | None = None,
        labels: List[str] | None = None,
    ) -> Tuple[Dict[str, pd.Series], List[str]]:
        prices: Dict[str, pd.Series] = {}
        missing: List[str] = []
        total = len(contracts)
        for idx, contract in enumerate(contracts, start=1):
            series = self.fetch_history(contract, lookback_days)
            key = keys[idx - 1] if keys is not None and idx - 1 < len(keys) else contract.symbol
            label = labels[idx - 1] if labels is not None and idx - 1 < len(labels) else contract.symbol
            if series is None:
                missing.append(label)
            else:
                prices[key] = series.astype(float)
            if progress_cb:
                progress_cb(idx, total, label)
        return prices, missing

    def fetch_fx_rate(self, base: str, quote: str, timeout_seconds: float | None = None) -> Optional[float]:
        base_ccy = self._normalize_currency(base)
        quote_ccy = self._normalize_currency(quote)
        if base_ccy == quote_ccy:
            return 1.0
        if not self._is_valid_currency_code(base_ccy) or not self._is_valid_currency_code(quote_ccy):
            return None
        spec = self._fx_contract_spec(base_ccy, quote_ccy)
        if spec is None:
            return None
        contract, invert = spec
        key = self.cache.make_key("fx", base_ccy, quote_ccy)
        cached = self.cache.get_value(key)
        if cached is not None:
            return cached
        if not self._is_connected():
            return None
        timeout = timeout_seconds or self.quote_timeout_seconds
        prefer_live = self.market_data_mode in {"live", "auto"}
        self._set_market_data_type(live=prefer_live)
        snapshot = self._fetch_snapshot_quote(contract, timeout, prefer_live=prefer_live)
        if snapshot.price is not None and snapshot.price != 0:
            rate = float(snapshot.price)
            if invert:
                rate = 1.0 / rate
            self.cache.set_value(key, rate)
            return rate
        return None

    def fetch_fx_history(self, base: str, quote: str, lookback_days: int) -> Optional[pd.Series]:
        base_ccy = self._normalize_currency(base)
        quote_ccy = self._normalize_currency(quote)
        if base_ccy == quote_ccy:
            return None
        if not self._is_valid_currency_code(base_ccy) or not self._is_valid_currency_code(quote_ccy):
            return None
        spec = self._fx_contract_spec(base_ccy, quote_ccy)
        if spec is None:
            return None
        contract, invert = spec
        series = self.fetch_history(contract, lookback_days)
        if series is None or series.empty:
            return None
        series = series.replace(0, pd.NA).dropna()
        if series.empty:
            return None
        series = series.astype(float)
        return (1.0 / series) if invert else series

    def fetch_snapshot_quotes(
        self, contracts: List[Contract], timeout_seconds: float | None = None
    ) -> Tuple[Dict[str, QuoteSnapshot], List[str]]:
        results: Dict[str, QuoteSnapshot] = {}
        warnings: List[str] = []
        if not self._is_connected():
            return results, ["Market data unavailable: not connected"]

        timeout = timeout_seconds or self.quote_timeout_seconds
        prefer_live = self.market_data_mode in {"live", "auto"}
        self._set_market_data_type(live=prefer_live)

        last_time = 0.0
        for contract in contracts:
            elapsed = time.time() - last_time
            if elapsed < self.min_interval_seconds:
                self._sleep(self.min_interval_seconds - elapsed)
            key = self.quote_key(contract)
            snapshot = self._fetch_snapshot_quote(contract, timeout, prefer_live=prefer_live)
            if snapshot.price is None:
                cached = self._quote_cache.get(key)
                if cached is not None:
                    snapshot.price = cached
                    snapshot.field = "cached"
                    warnings.append(f"Snapshot quote missing for {contract.symbol}; using cached value")
                else:
                    warnings.append(f"Snapshot quote missing for {contract.symbol}")
            else:
                self._quote_cache[key] = snapshot.price
                self._quote_cache_ts[key] = datetime.utcnow()
            if snapshot.delayed:
                warnings.append(f"Delayed market data for {contract.symbol}")
            results[key] = snapshot
            last_time = time.time()

        return results, list(dict.fromkeys(warnings))

    def fetch_snapshot_quotes_batch(
        self,
        contracts: List[Contract],
        timeout_seconds: float | None = None,
        *,
        batch_size: int = 8,
    ) -> Tuple[Dict[str, QuoteSnapshot], List[str]]:
        results: Dict[str, QuoteSnapshot] = {}
        warnings: List[str] = []
        if not self._is_connected():
            return results, ["Market data unavailable: not connected"]

        timeout = timeout_seconds or self.quote_timeout_seconds
        prefer_live = self.market_data_mode in {"live", "auto"}
        self._set_market_data_type(live=prefer_live)

        chunk_size = max(1, int(batch_size or 1))
        for offset in range(0, len(contracts), chunk_size):
            chunk = contracts[offset : offset + chunk_size]
            chunk_results = self._run_ib(
                lambda chunk=chunk: self._request_snapshot_batch(chunk, timeout),
                timeout=timeout + 5.0,
            )
            snapshots_by_key = {
                self.quote_key(contract): snapshot for contract, snapshot in chunk_results
            }
            if prefer_live:
                missing_contracts = [
                    contract
                    for contract in chunk
                    if snapshots_by_key[self.quote_key(contract)].price is None
                ]
                if missing_contracts:
                    self._set_market_data_type(live=False)
                    delayed_results = self._run_ib(
                        lambda missing_contracts=missing_contracts: self._request_snapshot_batch(
                            missing_contracts,
                            timeout,
                        ),
                        timeout=timeout + 5.0,
                    )
                    self._set_market_data_type(live=True)
                    for contract, delayed_snapshot in delayed_results:
                        if delayed_snapshot.price is not None:
                            snapshots_by_key[self.quote_key(contract)] = QuoteSnapshot(
                                delayed_snapshot.price,
                                delayed_snapshot.field,
                                True,
                            )

            missing_symbols: list[str] = []
            for contract in chunk:
                key = self.quote_key(contract)
                snapshot = snapshots_by_key[key]

                if snapshot.price is None:
                    missing_symbols.append(contract.symbol)
                    cached = self._quote_cache.get(key)
                    if cached is not None:
                        snapshot = QuoteSnapshot(cached, "cached", snapshot.delayed)
                        warnings.append(f"Snapshot quote missing for {contract.symbol}; using cached value")
                    else:
                        warnings.append(f"Snapshot quote missing for {contract.symbol}")
                else:
                    self._quote_cache[key] = snapshot.price
                    self._quote_cache_ts[key] = datetime.utcnow()

                if snapshot.delayed:
                    warnings.append(f"Delayed market data for {contract.symbol}")
                results[key] = snapshot
            if missing_symbols:
                warnings.append(
                    "Quote collection reached its "
                    f"{timeout:.1f}s market-data budget for {', '.join(dict.fromkeys(missing_symbols))}; "
                    "the account/position snapshot was retained with available prices."
                )

        return results, list(dict.fromkeys(warnings))

    def _request_snapshot_batch(
        self,
        contracts: List[Contract],
        timeout_seconds: float,
    ) -> list[tuple[Contract, QuoteSnapshot]]:
        tickers = []
        for contract in contracts:
            try:
                ticker = self.ib.reqMktData(contract, snapshot=True)
            except Exception as exc:
                self._record_error(f"Quote request failed for {contract.symbol}: {exc}")
                tickers.append((contract, None))
                continue
            tickers.append((contract, ticker))

        start = time.time()
        prices: dict[int, QuoteSnapshot] = {}
        while time.time() - start < timeout_seconds:
            complete = True
            for index, (_contract, ticker) in enumerate(tickers):
                if index in prices or ticker is None:
                    continue
                price, field, delayed = self._best_price(ticker)
                if price is not None:
                    prices[index] = QuoteSnapshot(price, field, delayed)
                else:
                    complete = False
            if complete:
                break
            self.ib.sleep(0.1)

        results: list[tuple[Contract, QuoteSnapshot]] = []
        for index, (contract, ticker) in enumerate(tickers):
            if ticker is None:
                results.append((contract, QuoteSnapshot(None, None, False)))
                continue
            snapshot = prices.get(index)
            if snapshot is None:
                snapshot = QuoteSnapshot(None, None, self._is_delayed(ticker))
            results.append((contract, snapshot))
            try:
                self.ib.wrapper.endTicker(ticker, "mktData")
            except Exception:
                pass
        return results

    def _set_market_data_type(self, live: bool) -> None:
        market_data_type = 1 if live else 3
        try:
            self._run_ib(lambda: self.ib.reqMarketDataType(market_data_type))
        except Exception:
            pass

    def _fetch_snapshot_quote(self, contract: Contract, timeout_seconds: float, prefer_live: bool) -> QuoteSnapshot:
        if not self._is_connected():
            return QuoteSnapshot(None, None, False)
        price, field, delayed = self._request_snapshot(contract, timeout_seconds)
        if price is not None:
            return QuoteSnapshot(price, field, delayed)

        if not prefer_live:
            return QuoteSnapshot(price, field, delayed or self.market_data_mode == "delayed")

        # Fallback to delayed data if live snapshot produced nothing.
        self._set_market_data_type(live=False)
        price2, field2, delayed2 = self._request_snapshot(contract, timeout_seconds)
        self._set_market_data_type(live=True)
        if price2 is not None:
            return QuoteSnapshot(price2, field2, True)
        return QuoteSnapshot(price, field, delayed or delayed2 or self.market_data_mode == "delayed")

    def _request_snapshot(self, contract: Contract, timeout_seconds: float) -> tuple[Optional[float], Optional[str], bool]:
        def _do_request():
            try:
                ticker = self.ib.reqMktData(contract, snapshot=True)
            except Exception as exc:
                return None, None, False, f"Quote request failed for {contract.symbol}: {exc}"

            start = time.time()
            price = None
            field = None
            delayed = False
            while time.time() - start < timeout_seconds:
                price, field, delayed = self._best_price(ticker)
                if price is not None:
                    break
                self.ib.sleep(0.1)

            # Snapshot requests often complete server-side before cancellation.
            # Cleanup local ticker mapping without sending a cancel that triggers code 300.
            try:
                self.ib.wrapper.endTicker(ticker, "mktData")
            except Exception:
                pass

            if price is None:
                delayed = self._is_delayed(ticker)
            return price, field, delayed, None

        price, field, delayed, error = self._run_ib(_do_request)
        if error:
            self._record_error(error)
        return price, field, delayed

    def _is_valid(self, value: Optional[float]) -> bool:
        if value is None:
            return False
        try:
            return math.isfinite(float(value)) and float(value) > 0
        except Exception:
            return False

    def _is_delayed(self, ticker) -> bool:
        market_data_type = getattr(ticker, "marketDataType", None)
        if market_data_type in (3, 4):
            return True
        if self._is_valid(getattr(ticker, "delayedLast", None)):
            return True
        if self._is_valid(getattr(ticker, "delayedClose", None)):
            return True
        return False

    def _best_price(self, ticker) -> tuple[Optional[float], Optional[str], bool]:
        delayed_flag = self._is_delayed(ticker)
        last = getattr(ticker, "last", None)
        if self._is_valid(last):
            return float(last), "last", delayed_flag
        close = getattr(ticker, "close", None)
        if self._is_valid(close):
            return float(close), "close", delayed_flag
        midpoint = None
        midpoint_fn = getattr(ticker, "midpoint", None)
        if callable(midpoint_fn):
            try:
                midpoint = midpoint_fn()
            except Exception:
                midpoint = None
        if self._is_valid(midpoint):
            return float(midpoint), "mid", delayed_flag
        bid = getattr(ticker, "bid", None)
        ask = getattr(ticker, "ask", None)
        if self._is_valid(bid) and self._is_valid(ask):
            return float((float(bid) + float(ask)) / 2), "mid", delayed_flag
        if self._is_valid(bid):
            return float(bid), "bid", delayed_flag
        if self._is_valid(ask):
            return float(ask), "ask", delayed_flag

        delayed_last = getattr(ticker, "delayedLast", None)
        if self._is_valid(delayed_last):
            return float(delayed_last), "delayedLast", True
        delayed_close = getattr(ticker, "delayedClose", None)
        if self._is_valid(delayed_close):
            return float(delayed_close), "delayedClose", True
        delayed_bid = getattr(ticker, "delayedBid", None)
        delayed_ask = getattr(ticker, "delayedAsk", None)
        if self._is_valid(delayed_bid) and self._is_valid(delayed_ask):
            return float((float(delayed_bid) + float(delayed_ask)) / 2), "delayedMid", True
        if self._is_valid(delayed_bid):
            return float(delayed_bid), "delayedBid", True
        if self._is_valid(delayed_ask):
            return float(delayed_ask), "delayedAsk", True

        return None, None, delayed_flag
