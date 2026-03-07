from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

import pandas as pd


class PortfolioHistoryStore:
    def __init__(self, base_dir: str | Path = "data", mock: bool = False) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        filename = "portfolio_history_mock.csv" if mock else "portfolio_history_live.csv"
        self.path = self.base_dir / filename
        self._lock = threading.Lock()

    def append_snapshot(
        self,
        timestamp: datetime,
        netliq: float | None,
        market_value: float | None,
        cash: float | None,
        base_ccy: str,
    ) -> None:
        if netliq is None and market_value is None and cash is None:
            return
        portfolio_value = (
            float(netliq)
            if netliq is not None
            else float((market_value or 0.0) + (cash or 0.0))
        )
        row = {
            "date": timestamp.date().isoformat(),
            "timestamp": timestamp.isoformat(),
            "netliq": float(netliq) if netliq is not None else None,
            "market_value": float(market_value) if market_value is not None else None,
            "cash": float(cash) if cash is not None else None,
            "portfolio_value": portfolio_value,
            "base_ccy": str(base_ccy or "").upper(),
        }
        with self._lock:
            df = self._read()
            if df.empty:
                out = pd.DataFrame([row])
            else:
                mask = df["date"] == row["date"]
                if mask.any():
                    idx = df.index[mask][0]
                    for col, value in row.items():
                        df.at[idx, col] = value
                    out = df
                else:
                    out = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            out = out.sort_values("date").reset_index(drop=True)
            out.to_csv(self.path, index=False)

    def load_series(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        with self._lock:
            df = self._read()
        if df.empty:
            return df
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
        if start is not None:
            df = df[df["timestamp"] >= pd.Timestamp(start)]
        if end is not None:
            df = df[df["timestamp"] <= pd.Timestamp(end)]
        if df.empty:
            return df
        return df.set_index("timestamp")

    def clear(self) -> None:
        with self._lock:
            try:
                self.path.unlink(missing_ok=True)
            except TypeError:
                if self.path.exists():
                    self.path.unlink()

    def _read(self) -> pd.DataFrame:
        if not self.path.exists():
            return pd.DataFrame(
                columns=[
                    "date",
                    "timestamp",
                    "netliq",
                    "market_value",
                    "cash",
                    "portfolio_value",
                    "base_ccy",
                ]
            )
        try:
            return pd.read_csv(self.path)
        except Exception:
            return pd.DataFrame(
                columns=[
                    "date",
                    "timestamp",
                    "netliq",
                    "market_value",
                    "cash",
                    "portfolio_value",
                    "base_ccy",
                ]
            )
