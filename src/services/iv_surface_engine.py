from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Sequence, Tuple

import numpy as np
import pandas as pd
from ib_insync import Contract

from src.services.ibkr_client import IBKRClient


logger = logging.getLogger(__name__)


@dataclass
class IVSurfaceSnapshot:
    symbol: str
    spot: float
    expiries: List[str]
    strikes: List[float]
    iv_grid: np.ndarray
    timestamp: datetime
    delayed: bool
    points: int


class IVSurfaceEngine:
    def __init__(
        self,
        client: IBKRClient,
        market_data_mode: str = "delayed",
        max_expiries: int = 6,
        strike_band_pct: float = 0.02,
        max_contracts: int = 180,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        self.client = client
        self.market_data_mode = self._normalize_market_data_mode(market_data_mode)
        self.max_expiries = max(1, int(max_expiries))
        self.strike_band_pct = max(0.005, float(strike_band_pct))
        self.max_contracts = max(20, int(max_contracts))
        self.poll_interval_seconds = max(0.2, float(poll_interval_seconds))

        self._latest: IVSurfaceSnapshot | None = None
        self._lock = threading.Lock()
        self._status_lock = threading.Lock()
        self._message_lock = threading.Lock()
        self._messages: List[str] = []
        self._status = "Idle"

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False

        self._underlying_ticker = None
        self._option_tickers: List[Tuple[object, str, float]] = []
        self._spot = 0.0

    @staticmethod
    def _normalize_market_data_mode(value: str | None) -> str:
        mode = str(value or "").strip().lower()
        if mode in {"delayed", "live", "auto"}:
            return mode
        return "delayed"

    def is_running(self) -> bool:
        return self._running

    def status_text(self) -> str:
        with self._status_lock:
            return self._status

    def drain_messages(self) -> List[str]:
        with self._message_lock:
            items = list(self._messages)
            self._messages.clear()
        return items

    def start(self, symbol: str = "SPY") -> bool:
        self.stop()
        symbol = (symbol or "SPY").strip().upper()
        if not symbol:
            symbol = "SPY"
        if not self.client.mock and not self.client.is_connected():
            self._set_status("Error: Not connected")
            self._add_message("Connect to IBKR before starting IV surface.")
            return False

        self._stop_event.clear()
        self._latest = None
        self._underlying_ticker = None
        self._option_tickers.clear()
        self._spot = 0.0
        self._thread = threading.Thread(target=self._run_loop, args=(symbol,), daemon=True, name="IVSurfaceEngine")
        self._running = True
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._running = False
        self._cancel_subscriptions()
        if self.status_text().startswith("Running") or self.status_text().startswith("Starting"):
            self._set_status("Stopped")

    def snapshot(self) -> IVSurfaceSnapshot | None:
        with self._lock:
            return self._latest

    def _set_status(self, text: str) -> None:
        with self._status_lock:
            self._status = text

    def _add_message(self, message: str) -> None:
        text = str(message or "").strip()
        if not text:
            return
        with self._message_lock:
            if self._messages and self._messages[-1] == text:
                return
            self._messages.append(text)
            if len(self._messages) > 200:
                self._messages = self._messages[-200:]

    def _run_ib(self, fn, *args, timeout: float = 10.0, **kwargs):
        runner = self.client.ib_runner
        if runner is None:
            return fn(*args, **kwargs)
        return runner.run(fn, *args, timeout=timeout, **kwargs)

    def _sleep_with_stop(self, seconds: float) -> None:
        deadline = time.time() + max(0.0, seconds)
        while not self._stop_event.is_set() and time.time() < deadline:
            time.sleep(min(0.05, max(0.0, deadline - time.time())))

    def _run_loop(self, symbol: str) -> None:
        try:
            if self.client.mock:
                self._run_mock_loop(symbol)
            else:
                self._run_live_loop(symbol)
        except Exception as exc:
            logger.exception("IV surface engine failed")
            detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            self._set_status("Error")
            self._add_message(f"IV surface failed: {detail}")
        finally:
            self._running = False
            self._cancel_subscriptions()

    def _run_mock_loop(self, symbol: str) -> None:
        self._set_status(f"Running ({symbol}, Mock)")
        expiries = [(datetime.utcnow() + timedelta(days=7 * i)).strftime("%Y%m%d") for i in range(1, 7)]
        spot = 500.0 if symbol == "SPY" else 100.0
        strikes = np.round(np.linspace(spot * 0.98, spot * 1.02, 15), 2).tolist()
        while not self._stop_event.is_set():
            t = time.time()
            spot += np.sin(t / 8.0) * 0.05
            iv_grid = np.zeros((len(expiries), len(strikes)), dtype=float)
            for i, exp in enumerate(expiries):
                for j, strike in enumerate(strikes):
                    m = (strike / max(spot, 1e-6)) - 1.0
                    iv = 0.14 + 0.55 * (m**2) + 0.01 * i + 0.01 * np.sin(t * 0.8 + strike * 0.02)
                    iv_grid[i, j] = float(max(0.05, min(iv, 1.5)))
            snap = IVSurfaceSnapshot(
                symbol=symbol,
                spot=float(spot),
                expiries=list(expiries),
                strikes=list(strikes),
                iv_grid=iv_grid,
                timestamp=datetime.utcnow(),
                delayed=True,
                points=iv_grid.size,
            )
            with self._lock:
                self._latest = snap
            self._sleep_with_stop(self.poll_interval_seconds)

    def _run_live_loop(self, symbol: str) -> None:
        self._set_status(f"Starting ({symbol})")
        self._set_market_data_type(live=self.market_data_mode == "live")

        underlying = Contract(symbol=symbol, secType="STK", exchange="SMART", currency="USD")
        qualified_underlying = self._run_ib(lambda: self.client.ib.qualifyContracts(underlying), timeout=8.0) or []
        if not qualified_underlying:
            raise RuntimeError(f"Unable to qualify underlying contract for {symbol}")
        underlying = qualified_underlying[0]
        self._underlying_ticker = self._run_ib(
            lambda: self.client.ib.reqMktData(underlying, genericTickList="", snapshot=False),
            timeout=8.0,
        )

        spot = self._wait_for_spot(timeout_seconds=12.0)
        if spot is None:
            raise RuntimeError(f"No underlying price for {symbol}")
        self._spot = spot

        chains = self._run_ib(
            lambda: self.client.ib.reqSecDefOptParams(symbol, "", "STK", int(underlying.conId)),
            timeout=10.0,
        ) or []
        chain = self._choose_chain(chains)
        if chain is None:
            raise RuntimeError(f"No option chain available for {symbol}")

        expiries = self._choose_expiries(chain.expirations)
        strikes = self._choose_strikes(chain.strikes, spot)
        if not expiries or not strikes:
            raise RuntimeError(f"No usable expiries/strikes for {symbol}")

        max_per_expiry = max(3, self.max_contracts // max(1, len(expiries)))
        if len(strikes) > max_per_expiry:
            strikes = sorted(strikes, key=lambda x: abs(x - spot))[:max_per_expiry]
            strikes = sorted(strikes)

        self._set_status(f"Subscribing ({symbol})")
        option_exchange = "SMART"
        for exp in expiries:
            for strike in strikes:
                if self._stop_event.is_set():
                    break
                right = "C" if strike >= spot else "P"
                option = Contract(
                    symbol=symbol,
                    secType="OPT",
                    exchange=option_exchange,
                    currency=underlying.currency or "USD",
                    lastTradeDateOrContractMonth=exp,
                    strike=float(strike),
                    right=right,
                    tradingClass=chain.tradingClass,
                    multiplier=chain.multiplier,
                )
                try:
                    ticker = self._run_ib(
                        lambda c=option: self.client.ib.reqMktData(
                            c, genericTickList="106", snapshot=False, regulatorySnapshot=False
                        ),
                        timeout=8.0,
                    )
                    self._option_tickers.append((ticker, exp, float(strike)))
                except Exception as exc:
                    self._add_message(f"Option subscription failed {symbol} {exp} {strike}: {exc}")
                self._sleep_with_stop(0.015)

        if not self._option_tickers:
            raise RuntimeError(f"No option IV subscriptions for {symbol}")

        mode_label = "Delayed" if self.market_data_mode == "delayed" else "Live"
        self._set_status(f"Running ({symbol}, {mode_label})")
        while not self._stop_event.is_set():
            spot_now = self._read_spot()
            if spot_now is not None:
                self._spot = spot_now
            snap = self._build_snapshot(symbol, expiries, strikes)
            if snap is not None:
                with self._lock:
                    self._latest = snap
            self._sleep_with_stop(self.poll_interval_seconds)

    def _set_market_data_type(self, live: bool) -> None:
        market_data_type = 1 if live else 3
        try:
            self._run_ib(lambda: self.client.ib.reqMarketDataType(market_data_type), timeout=4.0)
        except Exception:
            pass

    def _wait_for_spot(self, timeout_seconds: float) -> float | None:
        deadline = time.time() + max(1.0, timeout_seconds)
        while not self._stop_event.is_set() and time.time() < deadline:
            spot = self._read_spot()
            if spot is not None:
                return spot
            self._sleep_with_stop(0.1)
        return None

    def _read_spot(self) -> float | None:
        ticker = self._underlying_ticker
        if ticker is None:
            return None
        candidates = [
            getattr(ticker, "last", None),
            getattr(ticker, "close", None),
            getattr(ticker, "delayedLast", None),
            getattr(ticker, "delayedClose", None),
        ]
        midpoint_fn = getattr(ticker, "midpoint", None)
        if callable(midpoint_fn):
            try:
                candidates.append(midpoint_fn())
            except Exception:
                pass
        for value in candidates:
            if self._is_valid_number(value):
                return float(value)
        return None

    def _choose_chain(self, chains: Sequence[object]) -> object | None:
        if not chains:
            return None
        smart = [c for c in chains if str(getattr(c, "exchange", "")).upper() == "SMART"]
        candidates = smart if smart else list(chains)
        candidates = [c for c in candidates if getattr(c, "expirations", None) and getattr(c, "strikes", None)]
        if not candidates:
            return None
        candidates.sort(key=lambda c: len(getattr(c, "strikes", [])), reverse=True)
        return candidates[0]

    def _choose_expiries(self, expirations: Sequence[str]) -> List[str]:
        today = datetime.utcnow().strftime("%Y%m%d")
        valid = sorted(str(e) for e in expirations if str(e) >= today)
        return valid[: self.max_expiries]

    def _choose_strikes(self, strikes: Sequence[float], spot: float) -> List[float]:
        clean = sorted(float(s) for s in strikes if self._is_valid_number(s))
        if not clean:
            return []
        low = spot * (1.0 - self.strike_band_pct)
        high = spot * (1.0 + self.strike_band_pct)
        band = [s for s in clean if low <= s <= high]
        if len(band) >= 5:
            return band
        nearest = sorted(clean, key=lambda x: abs(x - spot))[:15]
        return sorted(nearest)

    def _build_snapshot(self, symbol: str, expiries: List[str], strikes: List[float]) -> IVSurfaceSnapshot | None:
        exp_index = {exp: idx for idx, exp in enumerate(expiries)}
        strike_index = {float(strike): idx for idx, strike in enumerate(strikes)}
        iv_grid = np.full((len(expiries), len(strikes)), np.nan, dtype=float)
        points = 0
        delayed = self.market_data_mode == "delayed"

        for ticker, exp, strike in self._option_tickers:
            row = exp_index.get(exp)
            col = strike_index.get(float(strike))
            if row is None or col is None:
                continue
            iv = self._extract_iv(ticker)
            if iv is None:
                continue
            if np.isnan(iv_grid[row, col]):
                points += 1
            iv_grid[row, col] = iv
            delayed = delayed or self._is_delayed_ticker(ticker)

        if points < max(8, len(strikes) // 2):
            return None

        table = pd.DataFrame(iv_grid, index=expiries, columns=strikes)
        table = table.interpolate(method="linear", axis=0, limit_direction="both")
        table = table.interpolate(method="linear", axis=1, limit_direction="both")
        table = table.bfill().ffill()
        if table.isna().all().all():
            return None

        clean_grid = table.to_numpy(dtype=float)
        clean_grid = np.clip(clean_grid, 0.01, 5.0)
        spot = self._spot if self._is_valid_number(self._spot) else 0.0
        return IVSurfaceSnapshot(
            symbol=symbol,
            spot=float(spot),
            expiries=list(expiries),
            strikes=list(strikes),
            iv_grid=clean_grid,
            timestamp=datetime.utcnow(),
            delayed=bool(delayed),
            points=int(points),
        )

    @staticmethod
    def _extract_iv(ticker) -> float | None:
        for attr in ("modelGreeks", "lastGreeks", "bidGreeks", "askGreeks"):
            greeks = getattr(ticker, attr, None)
            if greeks is None:
                continue
            value = getattr(greeks, "impliedVol", None)
            if IVSurfaceEngine._is_valid_number(value):
                return float(value)
        return None

    @staticmethod
    def _is_valid_number(value) -> bool:
        if value is None:
            return False
        try:
            v = float(value)
        except Exception:
            return False
        return np.isfinite(v) and v > 0

    @staticmethod
    def _is_delayed_ticker(ticker) -> bool:
        market_data_type = getattr(ticker, "marketDataType", None)
        if market_data_type in (3, 4):
            return True
        delayed_fields = ("delayedLast", "delayedClose", "delayedBid", "delayedAsk")
        for field in delayed_fields:
            value = getattr(ticker, field, None)
            if IVSurfaceEngine._is_valid_number(value):
                return True
        return False

    def _cancel_subscriptions(self) -> None:
        contracts: List[Contract] = []
        try:
            if self._underlying_ticker is not None and getattr(self._underlying_ticker, "contract", None) is not None:
                contracts.append(self._underlying_ticker.contract)
            for ticker, _, _ in self._option_tickers:
                contract = getattr(ticker, "contract", None)
                if contract is not None:
                    contracts.append(contract)
        except Exception:
            contracts = []

        self._underlying_ticker = None
        self._option_tickers.clear()
        if not contracts or self.client.mock:
            return

        def _cancel() -> None:
            for contract in contracts:
                try:
                    self.client.ib.cancelMktData(contract)
                except Exception:
                    pass

        try:
            self._run_ib(_cancel, timeout=8.0)
        except Exception:
            pass
