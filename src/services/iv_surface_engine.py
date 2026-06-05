from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Sequence

import numpy as np
import pandas as pd
from ib_insync import Contract

from src.analytics.options_pricing import calculate_black_scholes_greeks, solve_implied_volatility
from src.models.iv import (
    IVExpiryAnalyticsRecord,
    IVOptionContractRecord,
    IVOptionGreeksRecord,
    IVOptionPairRecord,
    IVPricingAssumptionsRecord,
    IVSurfaceCollectionMetadata,
    IVSurfaceModelMetadata,
    IVSurfaceQualityMetrics,
)
from src.services.ibkr_client import IBKRClient


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OptionTickerSubscription:
    ticker: object
    contract: Contract
    expiry: str
    strike: float
    right: str


@dataclass(frozen=True)
class OptionSubscriptionCandidate:
    contract: Contract
    expiry: str
    strike: float
    right: str


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
    source_provider: str = "ibkr"
    origin: str = "gamma.iv.surface"
    transformation_note: str = (
        "Gamma keeps a call/put option-chain snapshot from the active IBKR/TWS subscriptions, derives contract-"
        "level analytics from the same lines, and interpolates a blended implied-volatility surface for display."
    )
    freshness_label: str = "live"
    contracts: list[IVOptionContractRecord] = field(default_factory=list)
    pairs: list[IVOptionPairRecord] = field(default_factory=list)
    collection: IVSurfaceCollectionMetadata | None = None
    quality: IVSurfaceQualityMetrics | None = None
    surface_model: IVSurfaceModelMetadata = field(
        default_factory=lambda: IVSurfaceModelMetadata(model="linear", label="Line interpolation")
    )
    expiry_analytics: list[IVExpiryAnalyticsRecord] = field(default_factory=list)
    pricing_assumptions: IVPricingAssumptionsRecord | None = None


class IVSurfaceEngine:
    def __init__(
        self,
        client: IBKRClient,
        market_data_mode: str = "delayed",
        max_expiries: int = 6,
        strike_band_pct: float = 0.02,
        max_contracts: int = 180,
        poll_interval_seconds: float = 0.5,
        market_data_line_budget: int = 60,
        reserved_market_data_lines: int = 10,
        include_calls: bool = True,
        include_puts: bool = True,
        depth_preset: str = "standard",
        surface_model: str = "linear",
    ) -> None:
        self.client = client
        self.market_data_mode = self._normalize_market_data_mode(market_data_mode)
        self.depth_preset = self._normalize_depth_preset(depth_preset)
        self.max_expiries = max(1, int(max_expiries))
        self.strike_band_pct = max(0.005, float(strike_band_pct))
        self.max_contracts = max(20, int(max_contracts))
        self.poll_interval_seconds = max(0.2, float(poll_interval_seconds))
        self.market_data_line_budget = max(10, int(market_data_line_budget))
        self.reserved_market_data_lines = max(0, int(reserved_market_data_lines))
        self.include_calls = bool(include_calls)
        self.include_puts = bool(include_puts)
        self.surface_model = self.normalize_surface_model(surface_model)

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
        self._option_tickers: list[OptionTickerSubscription] = []
        self._spot = 0.0

    @staticmethod
    def _normalize_market_data_mode(value: str | None) -> str:
        mode = str(value or "").strip().lower()
        if mode in {"delayed", "live", "auto"}:
            return mode
        return "delayed"

    @staticmethod
    def _normalize_depth_preset(value: str | None) -> str:
        preset = str(value or "").strip().lower().replace("-", "_")
        if preset in {"compact", "standard", "deep", "front_deep", "max"}:
            return preset
        return "standard"

    @staticmethod
    def normalize_surface_model(value: str | None) -> str:
        model = str(value or "").strip().lower().replace("-", "_")
        aliases = {
            "line": "linear",
            "line_interpolation": "linear",
            "linear_interpolation": "linear",
            "spline_interpolation": "spline",
            "ssvi_interpolation": "ssvi",
        }
        model = aliases.get(model, model)
        if model in {"linear", "spline", "ssvi"}:
            return model
        return "linear"

    @staticmethod
    def surface_model_label(value: str | None) -> str:
        model = IVSurfaceEngine.normalize_surface_model(value)
        return {
            "linear": "Line interpolation",
            "spline": "Spline interpolation",
            "ssvi": "SSVI",
        }[model]

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
            self._add_message("Connect to IBKR before starting options surface.")
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

    def build_mock_snapshot(self, symbol: str, *, timestamp: datetime | None = None) -> IVSurfaceSnapshot:
        now = timestamp or datetime.utcnow()
        expiries = [(now + timedelta(days=7 * index)).strftime("%Y%m%d") for index in range(1, self.max_expiries + 1)]
        spot = 500.0 if symbol == "SPY" else 100.0
        spot = float(spot + np.sin(now.timestamp() / 8.0) * 0.05)
        strike_count = min(11, max(5, self._option_contract_budget() // max(1, len(expiries) * len(self._selected_rights()))))
        strikes = np.round(np.linspace(spot * 0.98, spot * 1.02, strike_count), 2).tolist()
        contracts: list[IVOptionContractRecord] = []
        pairs: list[IVOptionPairRecord] = []
        raw_grid = np.full((len(expiries), len(strikes)), np.nan, dtype=float)
        rights = self._selected_rights()

        for row_index, expiry in enumerate(expiries):
            dte = self._days_to_expiry(expiry, now)
            t_years = max(dte / 365.0, 1.0 / 365.0)
            for col_index, strike in enumerate(strikes):
                base_iv = float(
                    max(
                        0.05,
                        min(
                            1.5,
                            0.14
                            + 0.55 * (((strike / max(spot, 1e-6)) - 1.0) ** 2)
                            + 0.01 * row_index
                            + 0.01 * np.sin(now.timestamp() * 0.8 + strike * 0.02),
                        ),
                    )
                )
                pair_id = self._pair_id(symbol, expiry, strike)
                pair_call: IVOptionContractRecord | None = None
                pair_put: IVOptionContractRecord | None = None
                for right in rights:
                    skew_adjustment = -0.015 if right == "P" else 0.01
                    iv = max(0.05, min(1.5, base_iv + skew_adjustment))
                    greeks = self._calculate_greeks_from_iv(
                        right=right,
                        spot=spot,
                        strike=strike,
                        time_to_expiry_years=t_years,
                        volatility=iv,
                        price_hint=None,
                        price_source="model",
                    )
                    midpoint = greeks.option_price if greeks is not None else None
                    bid = midpoint * 0.99 if midpoint is not None else None
                    ask = midpoint * 1.01 if midpoint is not None else None
                    contract = IVOptionContractRecord(
                        contract_id=self._contract_id(symbol, expiry, strike, right),
                        symbol=symbol,
                        expiry=expiry,
                        strike=float(strike),
                        right=right,
                        exchange="SMART",
                        currency="USD",
                        multiplier="100",
                        trading_class=symbol,
                        market_data_type=3,
                        delayed=True,
                        quote_timestamp=now,
                        bid=bid,
                        ask=ask,
                        last=midpoint,
                        close=midpoint,
                        mark_price=midpoint,
                        midpoint=midpoint,
                        bid_size=10.0,
                        ask_size=12.0,
                        last_size=5.0,
                        volume=150.0 + row_index * 10.0,
                        open_interest=1_000.0 + col_index * 25.0,
                        put_call_volume=150.0 + row_index * 10.0,
                        put_call_open_interest=1_000.0 + col_index * 25.0,
                        historical_volatility=max(0.05, iv - 0.01),
                        implied_volatility_30d=iv,
                        price_source="midpoint",
                        spread=(ask - bid) if bid is not None and ask is not None else None,
                        spread_pct_mid=((ask - bid) / midpoint) if bid is not None and ask is not None and midpoint else None,
                        intrinsic_value=self._intrinsic_value(right, spot, strike),
                        extrinsic_value=(midpoint - self._intrinsic_value(right, spot, strike)) if midpoint is not None else None,
                        moneyness=(strike / spot) - 1.0 if spot > 0 else None,
                        distance_from_spot_pct=((strike - spot) / spot) if spot > 0 else None,
                        days_to_expiry=dte,
                        model_greeks=greeks,
                        derived_greeks=greeks,
                    )
                    contracts.append(contract)
                    if right == "C":
                        pair_call = contract
                    else:
                        pair_put = contract
                blended_iv = np.mean(
                    [value for value in [
                        pair_call.model_greeks.implied_volatility if pair_call and pair_call.model_greeks else None,
                        pair_put.model_greeks.implied_volatility if pair_put and pair_put.model_greeks else None,
                    ] if value is not None]
                )
                raw_grid[row_index, col_index] = float(blended_iv)
                pairs.append(
                    self._build_pair_record(
                        pair_id=pair_id,
                        expiry=expiry,
                        strike=float(strike),
                        call_contract=pair_call,
                        put_contract=pair_put,
                        spot=spot,
                    )
                )

        collection = self._build_collection_metadata(
            expiry_count=len(expiries),
            strike_count=len(strikes),
            requested_contract_count=len(contracts),
            subscribed_contract_count=len(contracts),
            selection_note="Mock mode uses the configured IV budget but does not consume TWS market data lines.",
        )
        quality = self._build_quality_metrics(
            contracts=contracts,
            observed_surface_cells=int(np.isfinite(raw_grid).sum()),
            expected_surface_cells=raw_grid.size,
            pairs=pairs,
        )
        display_grid, model_metadata = self._fit_surface_grid(raw_grid, expiries, strikes, spot)
        if display_grid is None:
            display_grid = np.clip(raw_grid, 0.01, 5.0)
        expiry_analytics = self._build_expiry_analytics(expiries=expiries, pairs=pairs, spot=spot)
        return IVSurfaceSnapshot(
            symbol=symbol,
            spot=float(spot),
            expiries=list(expiries),
            strikes=list(strikes),
            iv_grid=display_grid,
            timestamp=now,
            delayed=True,
            points=int(np.isfinite(raw_grid).sum()),
            source_provider="mock",
            origin="gamma.iv.surface.mock",
            transformation_note=(
                "Gamma generated a mock option-chain snapshot with paired call/put rows, fallback greeks, and a "
                "blended IV grid for development and offline checks."
            ),
            freshness_label="mocked",
            contracts=contracts,
            pairs=pairs,
            collection=collection,
            quality=quality,
            surface_model=model_metadata,
            expiry_analytics=expiry_analytics,
            pricing_assumptions=IVPricingAssumptionsRecord(
                spot_reference=spot,
                risk_free_rate=0.0,
                dividend_yield=0.0,
                fallback_greeks_methodology="Black-Scholes fallback using zero-rate/zero-dividend assumptions.",
                notes=["Mock mode uses Gamma-derived option prices and greeks rather than provider quotes."],
            ),
        )

    def _run_loop(self, symbol: str) -> None:
        try:
            if self.client.mock:
                self._run_mock_loop(symbol)
            else:
                self._run_live_loop(symbol)
        except Exception as exc:
            logger.exception("Options surface engine failed")
            detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            self._set_status("Error")
            self._add_message(f"Options surface failed: {detail}")
        finally:
            self._running = False
            self._cancel_subscriptions()

    def _run_mock_loop(self, symbol: str) -> None:
        self._set_status(f"Running ({symbol}, Mock)")
        while not self._stop_event.is_set():
            snap = self.build_mock_snapshot(symbol)
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

        rights = self._selected_rights()
        option_contract_budget = self._option_contract_budget()
        max_strikes_per_expiry = max(1, option_contract_budget // max(1, len(expiries) * len(rights)))
        selection_note = None
        if len(strikes) > max_strikes_per_expiry:
            original_count = len(strikes)
            strikes = self._sample_strikes_for_surface(strikes, spot, max_strikes_per_expiry)
            selection_note = (
                f"Sampled the strike set from {original_count} to {len(strikes)} strikes across the configured "
                f"{self.strike_band_pct:.1%} band to stay within the working budget of "
                f"{option_contract_budget} option quote lines."
            )
        if len(expiries) * len(strikes) * len(rights) > option_contract_budget:
            raise RuntimeError(
                f"Configured IV budget is insufficient for the selected expiries/strikes: "
                f"{len(expiries) * len(strikes) * len(rights)} contracts requested vs {option_contract_budget} budget"
            )

        candidates, validation_note = self._resolve_option_subscription_candidates(
            symbol=symbol,
            underlying_currency=underlying.currency or "USD",
            trading_class=chain.tradingClass,
            multiplier=chain.multiplier,
            expiries=expiries,
            strikes=strikes,
            rights=rights,
        )
        selection_note = self._combine_notes(selection_note, validation_note)
        if not candidates:
            raise RuntimeError(f"No valid option contracts after IBKR contract-details validation for {symbol}")

        self._set_status(f"Subscribing ({symbol})")
        generic_ticks = "100,101,104,106,232"
        for candidate in candidates:
            if self._stop_event.is_set():
                break
            try:
                ticker = self._run_ib(
                    lambda c=candidate.contract: self.client.ib.reqMktData(
                        c,
                        genericTickList=generic_ticks,
                        snapshot=False,
                        regulatorySnapshot=False,
                    ),
                    timeout=8.0,
                )
                self._option_tickers.append(
                    OptionTickerSubscription(
                        ticker=ticker,
                        contract=getattr(ticker, "contract", None) or candidate.contract,
                        expiry=candidate.expiry,
                        strike=float(candidate.strike),
                        right=candidate.right,
                    )
                )
            except Exception as exc:
                self._add_message(
                    f"Option subscription failed {symbol} {candidate.expiry} {candidate.strike} {candidate.right}: {exc}"
                )
            self._sleep_with_stop(0.015)

        if not self._option_tickers:
            self._set_status("Error")
            self._add_message(
                f"No option market-data subscriptions could be opened for {symbol}. "
                "TWS rejected the requested option quote lines or the market-data-line budget was already exhausted."
            )
            return

        mode_label = "Delayed" if self.market_data_mode == "delayed" else "Live"
        self._set_status(f"Running ({symbol}, {mode_label})")
        while not self._stop_event.is_set():
            spot_now = self._read_spot()
            if spot_now is not None:
                self._spot = spot_now
            snap = self._build_snapshot(symbol, expiries, strikes, selection_note=selection_note)
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
            numeric = self._coerce_positive(value)
            if numeric is not None:
                return numeric
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
        today = datetime.utcnow().date()
        valid: list[tuple[str, int]] = []
        for raw_expiry in expirations:
            expiry = str(raw_expiry)
            parsed = self._parse_expiry_date(expiry)
            if parsed is None or parsed < today:
                continue
            valid.append((expiry, (parsed - today).days))
        valid.sort(key=lambda item: (item[1], item[0]))
        if len(valid) <= self.max_expiries:
            return [expiry for expiry, _dte in valid]

        selected: list[tuple[str, int]] = []
        remaining = list(valid)
        for target_dte in self._target_expiry_dtes():
            if len(selected) >= self.max_expiries or not remaining:
                break
            best = min(remaining, key=lambda item: (abs(item[1] - target_dte), item[1], item[0]))
            selected.append(best)
            remaining.remove(best)

        if len(selected) < self.max_expiries:
            selected_keys = {expiry for expiry, _dte in selected}
            for candidate in valid:
                if candidate[0] in selected_keys:
                    continue
                selected.append(candidate)
                if len(selected) >= self.max_expiries:
                    break

        selected.sort(key=lambda item: (item[1], item[0]))
        return [expiry for expiry, _dte in selected[: self.max_expiries]]

    def _choose_strikes(self, strikes: Sequence[float], spot: float) -> List[float]:
        clean = sorted(float(s) for s in strikes if self._coerce_positive(s) is not None)
        if not clean:
            return []
        low = spot * (1.0 - self.strike_band_pct)
        high = spot * (1.0 + self.strike_band_pct)
        band = [s for s in clean if low <= s <= high]
        if len(band) >= 5:
            return band
        nearest = sorted(clean, key=lambda x: abs(x - spot))[:15]
        return sorted(nearest)

    @staticmethod
    def _parse_expiry_date(expiry: str):
        clean = str(expiry or "").replace("-", "")
        if len(clean) < 8:
            return None
        try:
            return datetime.strptime(clean[:8], "%Y%m%d").date()
        except ValueError:
            return None

    @staticmethod
    def _target_expiry_dtes() -> list[int]:
        return [0, 7, 14, 30, 45, 60, 90, 120, 180, 270, 365]

    def _sample_strikes_for_surface(self, strikes: Sequence[float], spot: float, limit: int) -> list[float]:
        clean = sorted(float(strike) for strike in strikes if self._coerce_positive(strike) is not None)
        if len(clean) <= limit:
            return clean
        limit = max(1, int(limit))
        span = max(self.strike_band_pct, 0.01)
        positions = np.linspace(-1.0, 1.0, limit)
        target_offsets = [float(np.sign(pos) * (abs(pos) ** 1.45) * span) for pos in positions]
        selected: list[float] = []
        remaining = list(clean)
        for offset in target_offsets:
            target = spot * (1.0 + offset)
            best = min(remaining, key=lambda strike: (abs(strike - target), abs(strike - spot), strike))
            selected.append(best)
            remaining.remove(best)
            if not remaining:
                break
        if len(selected) < limit:
            selected_keys = set(selected)
            for strike in sorted(clean, key=lambda item: (abs(item - spot), item)):
                if strike in selected_keys:
                    continue
                selected.append(strike)
                if len(selected) >= limit:
                    break
        return sorted(selected[:limit])

    def _resolve_option_subscription_candidates(
        self,
        *,
        symbol: str,
        underlying_currency: str,
        trading_class: str,
        multiplier: str,
        expiries: list[str],
        strikes: list[float],
        rights: list[str],
    ) -> tuple[list[OptionSubscriptionCandidate], str | None]:
        if self.depth_preset == "max":
            return self._build_direct_option_subscription_candidates(
                symbol=symbol,
                underlying_currency=underlying_currency,
                trading_class=trading_class,
                multiplier=multiplier,
                expiries=expiries,
                strikes=strikes,
                rights=rights,
            )

        strike_keys = {self._strike_key(strike) for strike in strikes}
        requested_keys = {
            (expiry, self._strike_key(strike), right)
            for expiry in expiries
            for strike in strikes
            for right in rights
        }
        candidates: list[OptionSubscriptionCandidate] = []
        seen: set[tuple[str, float, str]] = set()

        self._set_status(f"Validating contracts ({symbol})")
        for expiry in expiries:
            if self._stop_event.is_set():
                break
            template = Contract(
                symbol=symbol,
                secType="OPT",
                exchange="SMART",
                currency=underlying_currency,
                lastTradeDateOrContractMonth=expiry,
                tradingClass=trading_class,
                multiplier=multiplier,
            )
            try:
                details = self._run_ib(lambda c=template: self.client.ib.reqContractDetails(c), timeout=12.0) or []
            except Exception as exc:
                self._add_message(f"Option contract validation failed {symbol} {expiry}: {exc}")
                details = []

            for detail in details:
                contract = getattr(detail, "contract", None)
                if contract is None:
                    continue
                right = str(getattr(contract, "right", "") or "").upper()
                strike = self._coerce_positive(getattr(contract, "strike", None))
                contract_expiry = str(getattr(contract, "lastTradeDateOrContractMonth", "") or expiry)
                if not right or right not in rights or strike is None:
                    continue
                if contract_expiry != expiry or self._strike_key(strike) not in strike_keys:
                    continue
                candidate_key = (expiry, self._strike_key(strike), right)
                if candidate_key in seen or candidate_key not in requested_keys:
                    continue
                seen.add(candidate_key)
                candidates.append(
                    OptionSubscriptionCandidate(
                        contract=contract,
                        expiry=expiry,
                        strike=float(strike),
                        right=right,
                    )
                )

        expiry_order = {expiry: index for index, expiry in enumerate(expiries)}
        strike_order = {self._strike_key(strike): index for index, strike in enumerate(strikes)}
        right_order = {right: index for index, right in enumerate(rights)}
        candidates.sort(
            key=lambda item: (
                expiry_order.get(item.expiry, len(expiries)),
                strike_order.get(self._strike_key(item.strike), len(strikes)),
                right_order.get(item.right, len(rights)),
            )
        )
        skipped = max(0, len(requested_keys) - len(candidates))
        note = None
        if skipped:
            note = (
                f"Filtered {skipped} invalid option expiry/strike/right combinations using IBKR contract details "
                "before requesting market data."
            )
        return candidates, note

    def _build_direct_option_subscription_candidates(
        self,
        *,
        symbol: str,
        underlying_currency: str,
        trading_class: str,
        multiplier: str,
        expiries: list[str],
        strikes: list[float],
        rights: list[str],
    ) -> tuple[list[OptionSubscriptionCandidate], str | None]:
        candidates: list[OptionSubscriptionCandidate] = []
        for expiry in expiries:
            for strike in strikes:
                for right in rights:
                    contract = Contract(
                        symbol=symbol,
                        secType="OPT",
                        exchange="SMART",
                        currency=underlying_currency,
                        lastTradeDateOrContractMonth=expiry,
                        strike=float(strike),
                        right=right,
                        tradingClass=trading_class,
                        multiplier=multiplier,
                    )
                    candidates.append(
                        OptionSubscriptionCandidate(
                            contract=contract,
                            expiry=expiry,
                            strike=float(strike),
                            right=right,
                        )
                    )
        return candidates, "Used option-chain parameters directly for max-depth subscriptions to avoid slow per-expiry contract-detail validation."

    @staticmethod
    def _combine_notes(*notes: str | None) -> str | None:
        clean = [note.strip() for note in notes if note and note.strip()]
        return " ".join(clean) if clean else None

    @staticmethod
    def _strike_key(value: float) -> float:
        return round(float(value), 6)

    def _build_snapshot(
        self,
        symbol: str,
        expiries: list[str],
        strikes: list[float],
        *,
        selection_note: str | None,
    ) -> IVSurfaceSnapshot | None:
        exp_index = {exp: idx for idx, exp in enumerate(expiries)}
        strike_index = {float(strike): idx for idx, strike in enumerate(strikes)}
        raw_grid = np.full((len(expiries), len(strikes)), np.nan, dtype=float)
        delayed = self.market_data_mode == "delayed"
        contracts: list[IVOptionContractRecord] = []
        pair_index: dict[tuple[str, float], dict[str, IVOptionContractRecord]] = {}

        for subscription in self._option_tickers:
            row = exp_index.get(subscription.expiry)
            col = strike_index.get(float(subscription.strike))
            if row is None or col is None:
                continue
            contract = self._extract_contract_record(symbol, subscription)
            contracts.append(contract)
            pair_bucket = pair_index.setdefault((subscription.expiry, float(subscription.strike)), {})
            pair_bucket[subscription.right] = contract
            delayed = delayed or bool(contract.delayed)

        if not contracts:
            return None

        pairs: list[IVOptionPairRecord] = []
        for expiry in expiries:
            for strike in strikes:
                key = (expiry, float(strike))
                call_contract = pair_index.get(key, {}).get("C")
                put_contract = pair_index.get(key, {}).get("P")
                pair = self._build_pair_record(
                    pair_id=self._pair_id(symbol, expiry, strike),
                    expiry=expiry,
                    strike=float(strike),
                    call_contract=call_contract,
                    put_contract=put_contract,
                    spot=self._spot,
                )
                pairs.append(pair)
                blended_iv = self._pair_blended_iv(pair)
                if blended_iv is not None:
                    raw_grid[exp_index[expiry], strike_index[float(strike)]] = blended_iv

        observed_cells = int(np.isfinite(raw_grid).sum())
        if observed_cells < max(8, len(strikes) // 2):
            return None

        display_grid, model_metadata = self._fit_surface_grid(raw_grid, expiries, strikes, self._spot)
        if display_grid is None:
            return None

        quality = self._build_quality_metrics(
            contracts=contracts,
            observed_surface_cells=observed_cells,
            expected_surface_cells=raw_grid.size,
            pairs=pairs,
        )
        expiry_analytics = self._build_expiry_analytics(expiries=expiries, pairs=pairs, spot=self._spot)
        collection = self._build_collection_metadata(
            expiry_count=len(expiries),
            strike_count=len(strikes),
            requested_contract_count=len(expiries) * len(strikes) * len(self._selected_rights()),
            subscribed_contract_count=len(self._option_tickers),
            selection_note=selection_note,
        )
        return IVSurfaceSnapshot(
            symbol=symbol,
            spot=float(self._spot if self._coerce_positive(self._spot) is not None else 0.0),
            expiries=list(expiries),
            strikes=list(strikes),
            iv_grid=display_grid,
            timestamp=datetime.utcnow(),
            delayed=bool(delayed),
            points=observed_cells,
            source_provider="ibkr",
            origin="gamma.iv.surface.ibkr",
            transformation_note=(
                "Gamma resolves the underlying through IBKR/TWS, requests option-chain parameters with "
                "reqSecDefOptParams, subscribes to paired near-spot call and put contracts, preserves contract-level "
                "quotes/greeks from those same lines, and interpolates a blended IV grid for the display surface."
            ),
            freshness_label="delayed" if delayed else "live",
            contracts=contracts,
            pairs=pairs,
            collection=collection,
            quality=quality,
            surface_model=model_metadata,
            expiry_analytics=expiry_analytics,
            pricing_assumptions=IVPricingAssumptionsRecord(
                spot_reference=self._spot if self._coerce_positive(self._spot) is not None else None,
                risk_free_rate=0.0,
                dividend_yield=0.0,
                fallback_greeks_methodology="Black-Scholes fallback using zero-rate/zero-dividend assumptions.",
                notes=[
                    "Provider greeks are preferred when IBKR supplies them.",
                    "Gamma only solves or recomputes greeks from already-subscribed quotes; no extra option-pricing API requests are made.",
                ],
            ),
        )

    def _fit_surface_grid(
        self,
        raw_grid: np.ndarray,
        expiries: list[str],
        strikes: list[float],
        spot: float | None,
    ) -> tuple[np.ndarray | None, IVSurfaceModelMetadata]:
        model = self.normalize_surface_model(self.surface_model)
        label = self.surface_model_label(model)
        if model == "spline":
            grid, notes = self._spline_interpolate_grid(raw_grid, expiries, strikes)
        elif model == "ssvi":
            grid, notes = self._ssvi_fit_grid(raw_grid, expiries, strikes, spot)
        else:
            grid = self._linear_interpolate_grid(raw_grid, expiries, strikes)
            notes = ["Linear interpolation filled missing cells across expiry and strike axes."] if grid is not None else []

        if grid is None:
            fallback = self._linear_interpolate_grid(raw_grid, expiries, strikes)
            status = "fallback" if fallback is not None else "unavailable"
            fallback_notes = notes + ["Requested surface model could not be applied; linear interpolation was used instead."]
            return fallback, IVSurfaceModelMetadata(model="linear", label=self.surface_model_label("linear"), status=status, notes=fallback_notes)

        status = "applied"
        if notes and any("fallback" in note.lower() for note in notes):
            status = "partial"
        return grid, IVSurfaceModelMetadata(model=model, label=label, status=status, notes=notes)

    def _linear_interpolate_grid(self, raw_grid: np.ndarray, expiries: list[str], strikes: list[float]) -> np.ndarray | None:
        table = pd.DataFrame(raw_grid, index=expiries, columns=strikes)
        table = table.interpolate(method="linear", axis=0, limit_direction="both")
        table = table.interpolate(method="linear", axis=1, limit_direction="both")
        table = table.bfill().ffill()
        if table.isna().all().all():
            return None
        clean_grid = table.to_numpy(dtype=float)
        return np.clip(clean_grid, 0.01, 5.0)

    def _spline_interpolate_grid(self, raw_grid: np.ndarray, expiries: list[str], strikes: list[float]) -> tuple[np.ndarray | None, list[str]]:
        base = self._linear_interpolate_grid(raw_grid, expiries, strikes)
        if base is None:
            return None, []

        grid = np.array(raw_grid, dtype=float, copy=True)
        strike_axis = np.array([float(strike) for strike in strikes], dtype=float)
        dte_axis = np.array([float(self._days_to_expiry(expiry, datetime.utcnow())) for expiry in expiries], dtype=float)
        row_spline_count = 0
        term_spline_count = 0

        for row_index in range(grid.shape[0]):
            row = grid[row_index, :]
            mask = np.isfinite(row)
            if int(mask.sum()) >= 3:
                grid[row_index, :] = self._natural_cubic_interpolate(strike_axis[mask], row[mask], strike_axis)
                row_spline_count += 1

        for col_index in range(grid.shape[1]):
            col = grid[:, col_index]
            mask = np.isfinite(col)
            if int(mask.sum()) >= 3:
                grid[:, col_index] = self._natural_cubic_interpolate(dte_axis[mask], col[mask], dte_axis)
                term_spline_count += 1

        grid = np.where(np.isfinite(grid), grid, base)
        notes = [f"Spline interpolation used {row_spline_count} strike slices and {term_spline_count} term slices."]
        if int((~np.isfinite(raw_grid)).sum()) and (row_spline_count < grid.shape[0] or term_spline_count < grid.shape[1]):
            notes.append("Spline fallback used linear interpolation for sparse strike or term slices.")
        return np.clip(grid, 0.01, 5.0), notes

    def _ssvi_fit_grid(
        self,
        raw_grid: np.ndarray,
        expiries: list[str],
        strikes: list[float],
        spot: float | None,
    ) -> tuple[np.ndarray | None, list[str]]:
        base = self._linear_interpolate_grid(raw_grid, expiries, strikes)
        clean_spot = self._coerce_positive(spot)
        if base is None or clean_spot is None:
            return base, ["SSVI fit fallback: missing baseline grid or positive spot reference."]

        strike_axis = np.array([float(strike) for strike in strikes], dtype=float)
        valid_strikes = strike_axis > 0
        if int(valid_strikes.sum()) < 4:
            return base, ["SSVI fit fallback: fewer than four positive strikes."]

        log_moneyness = np.log(strike_axis / clean_spot)
        output = np.array(base, dtype=float, copy=True)
        fitted_rows = 0
        fallback_rows = 0
        today = datetime.utcnow()

        for row_index, expiry in enumerate(expiries):
            row = np.array(raw_grid[row_index, :], dtype=float)
            mask = np.isfinite(row) & (row > 0) & valid_strikes
            if int(mask.sum()) < 4:
                fallback_rows += 1
                continue

            dte = self._days_to_expiry(expiry, today)
            t_years = max(dte / 365.0, 1.0 / 365.0)
            variance = np.square(np.clip(row[mask], 0.01, 5.0)) * t_years
            params = self._fit_ssvi_slice(log_moneyness[mask], variance)
            if params is None:
                fallback_rows += 1
                continue

            theta, rho, phi = params
            modeled_variance = self._ssvi_total_variance(log_moneyness, theta, rho, phi)
            modeled_iv = np.sqrt(np.maximum(modeled_variance / t_years, 0.0001))
            output[row_index, :] = modeled_iv
            fitted_rows += 1

        notes = [f"SSVI fitted {fitted_rows}/{len(expiries)} expiry slices from observed blended IV cells."]
        if fallback_rows:
            notes.append(f"SSVI fallback used linear interpolation for {fallback_rows} sparse or unstable expiry slices.")
        return np.clip(output, 0.01, 5.0), notes

    @staticmethod
    def _natural_cubic_interpolate(x_values: np.ndarray, y_values: np.ndarray, targets: np.ndarray) -> np.ndarray:
        order = np.argsort(x_values)
        x = np.asarray(x_values[order], dtype=float)
        y = np.asarray(y_values[order], dtype=float)
        unique_x, unique_indices = np.unique(x, return_index=True)
        x = unique_x
        y = y[unique_indices]
        n = len(x)
        if n < 3:
            return np.interp(targets, x, y)

        h = np.diff(x)
        if np.any(h <= 0):
            return np.interp(targets, x, y)

        alpha = np.zeros(n, dtype=float)
        for i in range(1, n - 1):
            alpha[i] = (3.0 / h[i]) * (y[i + 1] - y[i]) - (3.0 / h[i - 1]) * (y[i] - y[i - 1])

        l = np.ones(n, dtype=float)
        mu = np.zeros(n, dtype=float)
        z = np.zeros(n, dtype=float)
        for i in range(1, n - 1):
            l[i] = 2.0 * (x[i + 1] - x[i - 1]) - h[i - 1] * mu[i - 1]
            if abs(l[i]) < 1e-12:
                return np.interp(targets, x, y)
            mu[i] = h[i] / l[i]
            z[i] = (alpha[i] - h[i - 1] * z[i - 1]) / l[i]

        b = np.zeros(n - 1, dtype=float)
        c = np.zeros(n, dtype=float)
        d = np.zeros(n - 1, dtype=float)
        for j in range(n - 2, -1, -1):
            c[j] = z[j] - mu[j] * c[j + 1]
            b[j] = (y[j + 1] - y[j]) / h[j] - h[j] * (c[j + 1] + 2.0 * c[j]) / 3.0
            d[j] = (c[j + 1] - c[j]) / (3.0 * h[j])

        target_array = np.asarray(targets, dtype=float)
        indices = np.searchsorted(x, target_array, side="right") - 1
        indices = np.clip(indices, 0, n - 2)
        dx = target_array - x[indices]
        result = y[indices] + b[indices] * dx + c[indices] * np.square(dx) + d[indices] * np.power(dx, 3)
        edge = np.interp(target_array, x, y)
        return np.where((target_array < x[0]) | (target_array > x[-1]), edge, result)

    @staticmethod
    def _ssvi_total_variance(k: np.ndarray, theta: float, rho: float, phi: float) -> np.ndarray:
        inner = phi * k + rho
        return 0.5 * theta * (1.0 + rho * phi * k + np.sqrt(np.square(inner) + 1.0 - rho * rho))

    def _fit_ssvi_slice(self, k: np.ndarray, variance: np.ndarray) -> tuple[float, float, float] | None:
        clean_k = np.asarray(k, dtype=float)
        clean_variance = np.asarray(variance, dtype=float)
        if len(clean_k) < 4 or not np.all(np.isfinite(clean_variance)):
            return None

        best: tuple[float, float, float, float] | None = None
        rho_candidates = np.linspace(-0.85, 0.85, 18)
        phi_candidates = np.geomspace(0.5, 80.0, 24)
        for rho in rho_candidates:
            for phi in phi_candidates:
                shape = 0.5 * (1.0 + rho * phi * clean_k + np.sqrt(np.square(phi * clean_k + rho) + 1.0 - rho * rho))
                if not np.all(np.isfinite(shape)) or np.any(shape <= 0):
                    continue
                denom = float(np.dot(shape, shape))
                if denom <= 1e-12:
                    continue
                theta = float(np.dot(clean_variance, shape) / denom)
                if theta <= 0 or not np.isfinite(theta):
                    continue
                fitted = theta * shape
                loss = float(np.mean(np.square(fitted - clean_variance)))
                if best is None or loss < best[0]:
                    best = (loss, theta, float(rho), float(phi))

        if best is None:
            return None
        _, theta, rho, phi = best
        return theta, rho, phi

    def _build_collection_metadata(
        self,
        *,
        expiry_count: int,
        strike_count: int,
        requested_contract_count: int,
        subscribed_contract_count: int,
        selection_note: str | None,
    ) -> IVSurfaceCollectionMetadata:
        option_budget = self._option_contract_budget()
        estimated_total_lines = 1 + subscribed_contract_count
        utilization = estimated_total_lines / max(self.market_data_line_budget, 1)
        return IVSurfaceCollectionMetadata(
            depth_preset=self.depth_preset,
            market_data_mode=self.market_data_mode,
            include_calls=self.include_calls,
            include_puts=self.include_puts,
            max_expiries=self.max_expiries,
            strike_band_pct=self.strike_band_pct,
            configured_max_contracts=self.max_contracts,
            configured_market_data_line_budget=self.market_data_line_budget,
            reserved_market_data_lines=self.reserved_market_data_lines,
            underlying_market_data_lines=1,
            option_market_data_line_budget=option_budget,
            selected_expiry_count=expiry_count,
            selected_strike_count=strike_count,
            requested_contract_count=requested_contract_count,
            subscribed_contract_count=subscribed_contract_count,
            estimated_total_market_data_lines=estimated_total_lines,
            market_data_line_utilization=utilization,
            contract_selection_note=selection_note,
        )

    def _build_quality_metrics(
        self,
        *,
        contracts: list[IVOptionContractRecord],
        observed_surface_cells: int,
        expected_surface_cells: int,
        pairs: list[IVOptionPairRecord],
    ) -> IVSurfaceQualityMetrics:
        return IVSurfaceQualityMetrics(
            expected_surface_cells=expected_surface_cells,
            observed_surface_cells=observed_surface_cells,
            interpolated_surface_cells=max(0, expected_surface_cells - observed_surface_cells),
            interpolation_ratio=(
                max(0, expected_surface_cells - observed_surface_cells) / expected_surface_cells
                if expected_surface_cells > 0
                else None
            ),
            contracts_with_bid_ask=sum(1 for item in contracts if item.bid is not None and item.ask is not None),
            contracts_with_volume=sum(1 for item in contracts if item.volume is not None),
            contracts_with_open_interest=sum(1 for item in contracts if item.open_interest is not None),
            contracts_with_provider_greeks=sum(
                1
                for item in contracts
                if any(value is not None for value in (item.model_greeks, item.bid_greeks, item.ask_greeks, item.last_greeks))
            ),
            contracts_with_derived_greeks=sum(1 for item in contracts if item.derived_greeks is not None),
            call_contract_count=sum(1 for item in contracts if item.right == "C"),
            put_contract_count=sum(1 for item in contracts if item.right == "P"),
            pairs_with_both_sides=sum(1 for item in pairs if item.call_contract_id and item.put_contract_id),
        )

    def _build_expiry_analytics(
        self,
        *,
        expiries: list[str],
        pairs: list[IVOptionPairRecord],
        spot: float,
    ) -> list[IVExpiryAnalyticsRecord]:
        analytics: list[IVExpiryAnalyticsRecord] = []
        for expiry in expiries:
            expiry_pairs = [item for item in pairs if item.expiry == expiry]
            if not expiry_pairs:
                continue
            atm_pair = min(expiry_pairs, key=lambda item: abs((item.strike or 0.0) - spot))
            analytics.append(
                IVExpiryAnalyticsRecord(
                    expiry=expiry,
                    days_to_expiry=atm_pair.days_to_expiry,
                    atm_strike=atm_pair.strike,
                    atm_call_implied_volatility=atm_pair.call_implied_volatility,
                    atm_put_implied_volatility=atm_pair.put_implied_volatility,
                    atm_blended_implied_volatility=atm_pair.blended_implied_volatility,
                    atm_straddle_midpoint=atm_pair.straddle_midpoint,
                    synthetic_forward_price=atm_pair.synthetic_forward_price,
                    implied_move_pct=atm_pair.implied_move_pct,
                    put_call_parity_gap=atm_pair.call_put_parity_gap,
                    pair_count=len(expiry_pairs),
                    pair_count_with_both_sides=sum(1 for item in expiry_pairs if item.call_contract_id and item.put_contract_id),
                )
            )
        return analytics

    def _extract_contract_record(self, symbol: str, subscription: OptionTickerSubscription) -> IVOptionContractRecord:
        ticker = subscription.ticker
        contract = subscription.contract
        expiry = subscription.expiry
        strike = float(subscription.strike)
        right = subscription.right
        quote_timestamp = getattr(ticker, "time", None)

        bid = self._first_positive(getattr(ticker, "bid", None), getattr(ticker, "delayedBid", None))
        ask = self._first_positive(getattr(ticker, "ask", None), getattr(ticker, "delayedAsk", None))
        last = self._first_positive(getattr(ticker, "last", None), getattr(ticker, "delayedLast", None))
        close = self._first_positive(getattr(ticker, "close", None), getattr(ticker, "delayedClose", None))
        mark_price = self._coerce_positive(getattr(ticker, "markPrice", None))
        midpoint = self._ticker_midpoint(ticker, bid=bid, ask=ask)
        price_source = self._price_source(bid=bid, ask=ask, midpoint=midpoint, mark_price=mark_price, last=last, close=close)
        price_for_greeks = midpoint or mark_price or last or close

        bid_size = self._coerce_non_negative(getattr(ticker, "bidSize", None))
        ask_size = self._coerce_non_negative(getattr(ticker, "askSize", None))
        last_size = self._coerce_non_negative(getattr(ticker, "lastSize", None))
        generic_volume = self._coerce_non_negative(getattr(ticker, "volume", None))
        side_volume = self._coerce_non_negative(getattr(ticker, "callVolume" if right == "C" else "putVolume", None))
        side_open_interest = self._coerce_non_negative(
            getattr(ticker, "callOpenInterest" if right == "C" else "putOpenInterest", None)
        )
        volume = side_volume if side_volume is not None else generic_volume
        open_interest = side_open_interest

        bid_greeks = self._extract_greeks(getattr(ticker, "bidGreeks", None), source="bid")
        ask_greeks = self._extract_greeks(getattr(ticker, "askGreeks", None), source="ask")
        last_greeks = self._extract_greeks(getattr(ticker, "lastGreeks", None), source="last")
        model_greeks = self._extract_greeks(getattr(ticker, "modelGreeks", None), source="model")
        implied_volatility_30d = self._coerce_positive(getattr(ticker, "impliedVolatility", None))
        historical_volatility = self._coerce_positive(getattr(ticker, "histVolatility", None))
        delayed = self._is_delayed_ticker(ticker)

        spot_reference = self._best_spot_reference(model_greeks, bid_greeks, ask_greeks, last_greeks)
        dte = self._days_to_expiry(expiry)
        t_years = max(dte / 365.0, 1.0 / 365.0) if dte is not None else None
        provider_iv = self._first_greek_iv(model_greeks, bid_greeks, ask_greeks, last_greeks) or implied_volatility_30d
        derived_greeks = self._calculate_derived_greeks(
            right=right,
            spot=spot_reference,
            strike=strike,
            time_to_expiry_years=t_years,
            price_hint=price_for_greeks,
            provider_iv=provider_iv,
            price_source=price_source,
        )

        intrinsic = self._intrinsic_value(right, spot_reference, strike)
        selected_price = price_for_greeks
        return IVOptionContractRecord(
            contract_id=self._contract_id(symbol, expiry, strike, right),
            symbol=symbol,
            expiry=expiry,
            strike=strike,
            right=right,
            con_id=int(contract.conId) if getattr(contract, "conId", None) else None,
            local_symbol=getattr(contract, "localSymbol", None) or None,
            exchange=getattr(contract, "exchange", None) or None,
            currency=getattr(contract, "currency", None) or None,
            multiplier=str(getattr(contract, "multiplier", "") or "") or None,
            trading_class=getattr(contract, "tradingClass", None) or None,
            market_data_type=int(getattr(ticker, "marketDataType", 0) or 0) or None,
            delayed=delayed,
            quote_timestamp=quote_timestamp,
            bid=bid,
            ask=ask,
            last=last,
            close=close,
            mark_price=mark_price,
            midpoint=midpoint,
            bid_size=bid_size,
            ask_size=ask_size,
            last_size=last_size,
            volume=volume,
            open_interest=open_interest,
            put_call_volume=side_volume,
            put_call_open_interest=side_open_interest,
            historical_volatility=historical_volatility,
            implied_volatility_30d=implied_volatility_30d,
            price_source=price_source,
            spread=(ask - bid) if bid is not None and ask is not None else None,
            spread_pct_mid=((ask - bid) / midpoint) if bid is not None and ask is not None and midpoint else None,
            intrinsic_value=intrinsic,
            extrinsic_value=(selected_price - intrinsic) if selected_price is not None and intrinsic is not None else None,
            moneyness=((strike / spot_reference) - 1.0) if spot_reference is not None and spot_reference > 0 else None,
            distance_from_spot_pct=((strike - spot_reference) / spot_reference) if spot_reference is not None and spot_reference > 0 else None,
            days_to_expiry=dte,
            bid_greeks=bid_greeks,
            ask_greeks=ask_greeks,
            last_greeks=last_greeks,
            model_greeks=model_greeks,
            derived_greeks=derived_greeks,
        )

    def _build_pair_record(
        self,
        *,
        pair_id: str,
        expiry: str,
        strike: float,
        call_contract: IVOptionContractRecord | None,
        put_contract: IVOptionContractRecord | None,
        spot: float,
    ) -> IVOptionPairRecord:
        call_mid = call_contract.midpoint if call_contract is not None else None
        put_mid = put_contract.midpoint if put_contract is not None else None
        call_price, call_price_source = self._contract_display_price(call_contract)
        put_price, put_price_source = self._contract_display_price(put_contract)
        call_iv = self._contract_surface_iv(call_contract)
        put_iv = self._contract_surface_iv(put_contract)
        blended = np.mean([value for value in (call_iv, put_iv) if value is not None]) if any(
            value is not None for value in (call_iv, put_iv)
        ) else None
        straddle_price = (call_price + put_price) if call_price is not None and put_price is not None else None
        synthetic_forward = (strike + call_price - put_price) if call_price is not None and put_price is not None else None
        implied_move_pct = (straddle_price / spot) if straddle_price is not None and spot > 0 else None
        parity_gap = (
            call_price - put_price - (spot - strike)
            if call_price is not None and put_price is not None and spot > 0
            else None
        )
        return IVOptionPairRecord(
            pair_id=pair_id,
            expiry=expiry,
            strike=strike,
            days_to_expiry=call_contract.days_to_expiry if call_contract is not None else put_contract.days_to_expiry if put_contract is not None else None,
            call_contract_id=call_contract.contract_id if call_contract is not None else None,
            put_contract_id=put_contract.contract_id if put_contract is not None else None,
            call_midpoint=call_mid,
            put_midpoint=put_mid,
            call_mark_price=call_contract.mark_price if call_contract is not None else None,
            put_mark_price=put_contract.mark_price if put_contract is not None else None,
            call_price=call_price,
            put_price=put_price,
            call_price_source=call_price_source,
            put_price_source=put_price_source,
            call_implied_volatility=call_iv,
            put_implied_volatility=put_iv,
            blended_implied_volatility=float(blended) if blended is not None else None,
            call_delta=self._best_delta(call_contract),
            put_delta=self._best_delta(put_contract),
            call_open_interest=call_contract.open_interest if call_contract is not None else None,
            put_open_interest=put_contract.open_interest if put_contract is not None else None,
            call_volume=call_contract.volume if call_contract is not None else None,
            put_volume=put_contract.volume if put_contract is not None else None,
            straddle_midpoint=straddle_price,
            synthetic_forward_price=synthetic_forward,
            implied_move_pct=implied_move_pct,
            call_put_parity_gap=parity_gap,
        )

    def _calculate_derived_greeks(
        self,
        *,
        right: str,
        spot: float | None,
        strike: float,
        time_to_expiry_years: float | None,
        price_hint: float | None,
        provider_iv: float | None,
        price_source: str | None,
    ) -> IVOptionGreeksRecord | None:
        if spot is None or time_to_expiry_years is None or time_to_expiry_years <= 0:
            return None
        volatility = provider_iv
        methodology = "black_scholes_fallback_from_provider_iv"
        if volatility is None and price_hint is not None:
            volatility = solve_implied_volatility(
                right=right,
                spot=spot,
                strike=strike,
                time_to_expiry_years=time_to_expiry_years,
                option_price=price_hint,
                risk_free_rate=0.0,
                dividend_yield=0.0,
            )
            methodology = f"black_scholes_fallback_solved_from_{price_source or 'price'}"
        if volatility is None:
            return None
        derived = self._calculate_greeks_from_iv(
            right=right,
            spot=spot,
            strike=strike,
            time_to_expiry_years=time_to_expiry_years,
            volatility=volatility,
            price_hint=price_hint,
            price_source=price_source or "price",
            methodology=methodology,
        )
        return derived

    def _calculate_greeks_from_iv(
        self,
        *,
        right: str,
        spot: float,
        strike: float,
        time_to_expiry_years: float,
        volatility: float,
        price_hint: float | None,
        price_source: str,
        methodology: str = "black_scholes_fallback_from_provider_iv",
    ) -> IVOptionGreeksRecord | None:
        greeks = calculate_black_scholes_greeks(
            right=right,
            spot=spot,
            strike=strike,
            time_to_expiry_years=time_to_expiry_years,
            volatility=volatility,
            risk_free_rate=0.0,
            dividend_yield=0.0,
            methodology=methodology,
        )
        if greeks is None:
            return None
        return IVOptionGreeksRecord(
            source=price_source,
            implied_volatility=greeks.implied_volatility,
            delta=greeks.delta,
            gamma=greeks.gamma,
            vega=greeks.vega,
            theta=greeks.theta,
            option_price=price_hint if price_hint is not None else greeks.option_price,
            pv_dividend=0.0,
            underlying_price=spot,
            risk_free_rate=greeks.risk_free_rate,
            dividend_yield=greeks.dividend_yield,
            methodology=greeks.methodology,
        )

    @staticmethod
    def _extract_greeks(greeks, *, source: str) -> IVOptionGreeksRecord | None:
        if greeks is None:
            return None
        implied_volatility = IVSurfaceEngine._coerce_positive(getattr(greeks, "impliedVol", None))
        delta = IVSurfaceEngine._coerce_float(getattr(greeks, "delta", None))
        gamma = IVSurfaceEngine._coerce_float(getattr(greeks, "gamma", None))
        vega = IVSurfaceEngine._coerce_float(getattr(greeks, "vega", None))
        theta = IVSurfaceEngine._coerce_float(getattr(greeks, "theta", None))
        option_price = IVSurfaceEngine._coerce_positive(getattr(greeks, "optPrice", None))
        pv_dividend = IVSurfaceEngine._coerce_float(getattr(greeks, "pvDividend", None))
        underlying_price = IVSurfaceEngine._coerce_positive(getattr(greeks, "undPrice", None))
        if not any(
            value is not None
            for value in (implied_volatility, delta, gamma, vega, theta, option_price, pv_dividend, underlying_price)
        ):
            return None
        return IVOptionGreeksRecord(
            source=source,
            implied_volatility=implied_volatility,
            delta=delta,
            gamma=gamma,
            vega=vega,
            theta=theta,
            option_price=option_price,
            pv_dividend=pv_dividend,
            underlying_price=underlying_price,
            methodology="ibkr.tickOptionComputation",
        )

    def _selected_rights(self) -> list[str]:
        rights: list[str] = []
        if self.include_calls:
            rights.append("C")
        if self.include_puts:
            rights.append("P")
        return rights or ["C"]

    def _option_contract_budget(self) -> int:
        budget = self.market_data_line_budget - self.reserved_market_data_lines - 1
        return max(1, min(self.max_contracts, budget))

    def _best_spot_reference(self, *greek_sets: IVOptionGreeksRecord | None) -> float | None:
        for greek_set in greek_sets:
            if greek_set is None:
                continue
            numeric = self._coerce_positive(greek_set.underlying_price)
            if numeric is not None:
                return numeric
        return self._coerce_positive(self._spot)

    @staticmethod
    def _first_greek_iv(*greek_sets: IVOptionGreeksRecord | None) -> float | None:
        for greek_set in greek_sets:
            if greek_set is None:
                continue
            numeric = IVSurfaceEngine._coerce_positive(greek_set.implied_volatility)
            if numeric is not None:
                return numeric
        return None

    @staticmethod
    def _best_delta(contract: IVOptionContractRecord | None) -> float | None:
        if contract is None:
            return None
        for greek_set in (contract.model_greeks, contract.bid_greeks, contract.ask_greeks, contract.last_greeks, contract.derived_greeks):
            if greek_set is None:
                continue
            numeric = IVSurfaceEngine._coerce_float(greek_set.delta)
            if numeric is not None:
                return numeric
        return None

    @staticmethod
    def _contract_surface_iv(contract: IVOptionContractRecord | None) -> float | None:
        if contract is None:
            return None
        for greek_set in (contract.model_greeks, contract.bid_greeks, contract.ask_greeks, contract.last_greeks, contract.derived_greeks):
            if greek_set is None:
                continue
            numeric = IVSurfaceEngine._coerce_positive(greek_set.implied_volatility)
            if numeric is not None:
                return numeric
        return contract.implied_volatility_30d

    @staticmethod
    def _contract_display_price(contract: IVOptionContractRecord | None) -> tuple[float | None, str | None]:
        if contract is None:
            return None, None
        for source, value in (
            ("midpoint", contract.midpoint),
            ("mark", contract.mark_price),
            ("last", contract.last),
            ("close", contract.close),
        ):
            numeric = IVSurfaceEngine._coerce_positive(value)
            if numeric is not None:
                return numeric, source
        for source, greeks in (
            ("model", contract.model_greeks),
            ("derived", contract.derived_greeks),
            ("bid_greeks", contract.bid_greeks),
            ("ask_greeks", contract.ask_greeks),
            ("last_greeks", contract.last_greeks),
        ):
            if greeks is None:
                continue
            numeric = IVSurfaceEngine._coerce_positive(greeks.option_price)
            if numeric is not None:
                return numeric, source
        return None, None

    @staticmethod
    def _pair_blended_iv(pair: IVOptionPairRecord) -> float | None:
        values = [value for value in (pair.call_implied_volatility, pair.put_implied_volatility, pair.blended_implied_volatility) if value is not None]
        if not values:
            return None
        return float(np.mean(values[:2] if len(values) >= 2 else values))

    @staticmethod
    def _pair_id(symbol: str, expiry: str, strike: float) -> str:
        return f"{symbol}:{expiry}:{strike:.2f}"

    @staticmethod
    def _contract_id(symbol: str, expiry: str, strike: float, right: str) -> str:
        return f"{symbol}:{expiry}:{strike:.2f}:{right}"

    @staticmethod
    def _days_to_expiry(expiry: str, now: datetime | None = None) -> int | None:
        match = str(expiry or "").strip()
        if len(match) != 8 or not match.isdigit():
            return None
        current = now or datetime.utcnow()
        expiry_date = datetime(int(match[0:4]), int(match[4:6]), int(match[6:8]))
        return max(0, (expiry_date.date() - current.date()).days)

    @staticmethod
    def _intrinsic_value(right: str, spot: float | None, strike: float) -> float | None:
        if spot is None:
            return None
        if right == "P":
            return max(strike - spot, 0.0)
        return max(spot - strike, 0.0)

    @staticmethod
    def _price_source(
        *,
        bid: float | None,
        ask: float | None,
        midpoint: float | None,
        mark_price: float | None,
        last: float | None,
        close: float | None,
    ) -> str | None:
        if midpoint is not None and bid is not None and ask is not None:
            return "midpoint"
        if mark_price is not None:
            return "mark_price"
        if last is not None:
            return "last"
        if close is not None:
            return "close"
        return None

    @staticmethod
    def _ticker_midpoint(ticker, *, bid: float | None, ask: float | None) -> float | None:
        midpoint_fn = getattr(ticker, "midpoint", None)
        if callable(midpoint_fn):
            try:
                midpoint = midpoint_fn()
            except Exception:
                midpoint = None
            numeric = IVSurfaceEngine._coerce_positive(midpoint)
            if numeric is not None:
                return numeric
        if bid is not None and ask is not None:
            return (bid + ask) * 0.5
        return None

    @staticmethod
    def _coerce_positive(value) -> float | None:
        try:
            numeric = float(value)
        except Exception:
            return None
        return numeric if np.isfinite(numeric) and numeric > 0 else None

    @staticmethod
    def _coerce_non_negative(value) -> float | None:
        try:
            numeric = float(value)
        except Exception:
            return None
        return numeric if np.isfinite(numeric) and numeric >= 0 else None

    @staticmethod
    def _coerce_float(value) -> float | None:
        try:
            numeric = float(value)
        except Exception:
            return None
        return numeric if np.isfinite(numeric) else None

    @staticmethod
    def _first_positive(*values) -> float | None:
        for value in values:
            numeric = IVSurfaceEngine._coerce_positive(value)
            if numeric is not None:
                return numeric
        return None

    @staticmethod
    def _is_delayed_ticker(ticker) -> bool:
        market_data_type = getattr(ticker, "marketDataType", None)
        if market_data_type in (3, 4):
            return True
        delayed_fields = ("delayedLast", "delayedClose", "delayedBid", "delayedAsk")
        for field in delayed_fields:
            value = getattr(ticker, field, None)
            if IVSurfaceEngine._coerce_positive(value) is not None:
                return True
        return False

    def _cancel_subscriptions(self) -> None:
        contracts: list[Contract] = []
        try:
            if self._underlying_ticker is not None and getattr(self._underlying_ticker, "contract", None) is not None:
                contracts.append(self._underlying_ticker.contract)
            contracts.extend(subscription.contract for subscription in self._option_tickers if subscription.contract is not None)
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
