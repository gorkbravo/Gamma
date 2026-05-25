from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd

from src.models.instruments import build_instrument_id
from src.models.portfolio import PortfolioSnapshot, PositionItem
from src.utils.time import now_utc


class MockDataService:
    def __init__(self, base_path: str | Path = "sample_data") -> None:
        self.base_path = Path(base_path)

    def load_snapshot(self, base_currency: str) -> PortfolioSnapshot:
        account_summary = {
            "NetLiquidation": "125000",
            "PreviousDayEquityWithLoanValue": "123500",
            "TotalCashValue:EUR": "25000",
            "TotalCashValue:USD": "5000",
        }
        positions = [
            PositionItem(
                symbol="AAPL",
                sec_type="STK",
                currency="USD",
                quantity=50,
                avg_cost=150.0,
                market_price=195.0,
                market_value=9750.0,
                unrealized_pnl=2250.0,
                instrument_id=build_instrument_id(
                    provider="mock",
                    symbol="AAPL",
                    sec_type="STK",
                    exchange="SMART",
                    currency="USD",
                ),
                display_symbol="AAPL",
                exchange="SMART",
                provider="mock",
            ),
            PositionItem(
                symbol="MSFT",
                sec_type="STK",
                currency="USD",
                quantity=30,
                avg_cost=280.0,
                market_price=320.0,
                market_value=9600.0,
                unrealized_pnl=1200.0,
                instrument_id=build_instrument_id(
                    provider="mock",
                    symbol="MSFT",
                    sec_type="STK",
                    exchange="SMART",
                    currency="USD",
                ),
                display_symbol="MSFT",
                exchange="SMART",
                provider="mock",
            ),
            PositionItem(
                symbol="SAP",
                sec_type="STK",
                currency="EUR",
                quantity=40,
                avg_cost=120.0,
                market_price=150.0,
                market_value=6000.0,
                unrealized_pnl=1200.0,
                instrument_id=build_instrument_id(
                    provider="mock",
                    symbol="SAP",
                    sec_type="STK",
                    exchange="SMART",
                    currency="EUR",
                ),
                display_symbol="SAP",
                exchange="SMART",
                provider="mock",
            ),
        ]
        return PortfolioSnapshot(
            timestamp=now_utc(),
            base_currency=base_currency,
            account_summary=account_summary,
            positions=positions,
        )

    def load_history(self, symbol: str) -> pd.Series | None:
        path = self.base_path / f"history_{symbol}.csv"
        if not path.exists():
            return None
        df = pd.read_csv(path, parse_dates=["date"], index_col="date")
        return df["close"]

    def load_ohlcv_history(self, symbol: str) -> pd.DataFrame | None:
        path = self.base_path / f"history_{symbol}.csv"
        if not path.exists():
            return None
        df = pd.read_csv(path, parse_dates=["date"], index_col="date")
        columns = [column for column in ("open", "high", "low", "close", "volume") if column in df.columns]
        if "close" not in columns:
            return None
        frame = df[columns].apply(pd.to_numeric, errors="coerce").dropna(subset=["close"])
        return frame.sort_index() if not frame.empty else None

    def load_all_histories(self) -> Dict[str, pd.Series]:
        histories: Dict[str, pd.Series] = {}
        for csv in self.base_path.glob("history_*.csv"):
            symbol = csv.stem.replace("history_", "")
            df = pd.read_csv(csv, parse_dates=["date"], index_col="date")
            histories[symbol] = df["close"]
        return histories
