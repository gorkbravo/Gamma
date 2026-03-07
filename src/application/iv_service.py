from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from src.services.ibkr_client import IBKRClient
from src.services.iv_surface_engine import IVSurfaceEngine, IVSurfaceSnapshot


@dataclass(frozen=True)
class IVSurfaceRequest:
    symbol: str
    market_data_mode: str = "delayed"
    wait_seconds: float = 2.5


@dataclass
class IVSurfaceResult:
    snapshot: IVSurfaceSnapshot | None
    warnings: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


class IVService:
    def __init__(self, client: IBKRClient, market_data_mode: str = "delayed") -> None:
        self.client = client
        self.market_data_mode = self.normalize_market_data_mode(market_data_mode)

    @staticmethod
    def normalize_market_data_mode(value: str | None) -> str:
        mode = str(value or "").strip().lower()
        if mode in {"delayed", "live", "auto"}:
            return mode
        return "delayed"

    def create_engine(self, market_data_mode: str | None = None) -> IVSurfaceEngine:
        mode = self.normalize_market_data_mode(market_data_mode or self.market_data_mode)
        return IVSurfaceEngine(client=self.client, market_data_mode=mode)

    def get_surface(self, request: IVSurfaceRequest) -> IVSurfaceResult:
        symbol = str(request.symbol or "").strip().upper() or "SPY"
        mode = self.normalize_market_data_mode(request.market_data_mode or self.market_data_mode)
        if self.client.mock:
            return IVSurfaceResult(snapshot=self._mock_snapshot(symbol))
        if not self.client.is_connected():
            return IVSurfaceResult(
                snapshot=None,
                warnings=["Connect to IBKR before requesting an IV surface."],
            )

        engine = self.create_engine(mode)
        if not engine.start(symbol):
            return IVSurfaceResult(
                snapshot=None,
                warnings=["Unable to start IV surface engine."],
                messages=engine.drain_messages(),
            )

        deadline = time.time() + max(float(request.wait_seconds or 0.0), 0.5)
        latest = None
        try:
            while time.time() < deadline:
                latest = engine.snapshot()
                if latest is not None:
                    break
                time.sleep(0.1)
        finally:
            messages = engine.drain_messages()
            engine.stop()

        warnings: list[str] = []
        if latest is None:
            warnings.append(f"No IV surface snapshot available yet for {symbol}.")
        return IVSurfaceResult(snapshot=latest, warnings=warnings, messages=messages)

    def _mock_snapshot(self, symbol: str) -> IVSurfaceSnapshot:
        now = datetime.utcnow()
        expiries = [(now + timedelta(days=7 * index)).strftime("%Y%m%d") for index in range(1, 7)]
        spot = 500.0 if symbol == "SPY" else 100.0
        spot = float(spot + np.sin(now.timestamp() / 8.0) * 0.05)
        strikes = np.round(np.linspace(spot * 0.98, spot * 1.02, 15), 2).tolist()
        iv_grid = np.zeros((len(expiries), len(strikes)), dtype=float)
        for row_index, _expiry in enumerate(expiries):
            for col_index, strike in enumerate(strikes):
                moneyness = (strike / max(spot, 1e-6)) - 1.0
                iv = 0.14 + 0.55 * (moneyness**2) + 0.01 * row_index + 0.01 * np.sin(now.timestamp() * 0.8 + strike * 0.02)
                iv_grid[row_index, col_index] = float(max(0.05, min(iv, 1.5)))
        return IVSurfaceSnapshot(
            symbol=symbol,
            spot=spot,
            expiries=list(expiries),
            strikes=list(strikes),
            iv_grid=iv_grid,
            timestamp=now,
            delayed=True,
            points=int(iv_grid.size),
        )
