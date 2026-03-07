from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

from ib_insync import IB, Forex

from src.services.cache import CacheService
from src.services.ib_thread import IBThreadRunner

if TYPE_CHECKING:
    from src.services.market_data import MarketDataService


class FXService:
    def __init__(
        self,
        ib: IB | None,
        cache: CacheService | None = None,
        market_data: "MarketDataService | None" = None,
        ib_runner: IBThreadRunner | None = None,
        cache_minutes: int = 30,
    ) -> None:
        self.ib = ib
        self.cache = cache
        self.market_data = market_data
        self.ib_runner = ib_runner
        self.ttl = timedelta(minutes=cache_minutes)
        self._memory_cache: dict[str, tuple[float, datetime]] = {}

    def set_ib(self, ib: IB | None) -> None:
        self.ib = ib

    def set_ib_runner(self, ib_runner: IBThreadRunner | None) -> None:
        self.ib_runner = ib_runner

    def set_market_data(self, market_data: "MarketDataService | None") -> None:
        self.market_data = market_data

    def _run_ib(self, fn, *args, **kwargs):
        if self.ib_runner is not None:
            return self.ib_runner.run(fn, *args, **kwargs)
        return fn(*args, **kwargs)

    def _is_connected(self) -> bool:
        if self.ib is None:
            return False
        try:
            return bool(self._run_ib(lambda: self.ib.isConnected()))
        except Exception:
            return False

    def get_rate(self, base: str, quote: str) -> Optional[float]:
        base_ccy = self._normalize_currency(base)
        quote_ccy = self._normalize_currency(quote)
        if base_ccy == quote_ccy:
            return 1.0
        if not self._is_valid_currency_code(base_ccy) or not self._is_valid_currency_code(quote_ccy):
            return None
        key = self._cache_key(base_ccy, quote_ccy)
        cached = self._get_cached_rate(key)
        if cached is not None:
            return cached

        if self.market_data is not None:
            rate = self.market_data.fetch_fx_rate(base_ccy, quote_ccy)
            if rate is not None:
                self._store_rate(key, rate)
                return rate

        if not self._is_connected():
            return None
        def _do_request():
            try:
                inverse = Forex(f"{base_ccy}{quote_ccy}")
                ticker = self.ib.reqMktData(inverse, snapshot=True)
                self.ib.sleep(1)
                inv_rate = ticker.marketPrice()
                try:
                    self.ib.wrapper.endTicker(ticker, "mktData")
                except Exception:
                    pass
                if inv_rate is not None and inv_rate == inv_rate and inv_rate != 0:
                    return float(1.0 / inv_rate)
                return None
            except Exception:
                return None

        rate = self._run_ib(_do_request)
        if rate is None or rate != rate:
            return cached
        rate = float(rate) if rate != 0 else None
        if rate is None:
            return cached
        self._store_rate(key, rate)
        return rate

    @staticmethod
    def _normalize_currency(value: str | None) -> str:
        return str(value or "").strip().upper()

    @classmethod
    def _is_valid_currency_code(cls, value: str | None) -> bool:
        ccy = cls._normalize_currency(value)
        return len(ccy) == 3 and ccy.isalpha()

    def _cache_key(self, base: str, quote: str) -> str:
        if self.cache is not None:
            return self.cache.make_key("fx", base, quote)
        return f"fx_{quote}_{base}".lower()

    def _get_cached_rate(self, key: str) -> Optional[float]:
        now = datetime.utcnow()
        if key in self._memory_cache:
            value, ts = self._memory_cache[key]
            if now - ts <= self.ttl:
                return value
        if self.cache is not None:
            return self.cache.get_value(key)
        return None

    def _store_rate(self, key: str, value: float) -> None:
        self._memory_cache[key] = (value, datetime.utcnow())
        if self.cache is not None:
            self.cache.set_value(key, value)
