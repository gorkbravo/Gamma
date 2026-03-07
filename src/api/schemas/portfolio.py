from __future__ import annotations

from datetime import datetime

import pandas as pd
from pydantic import BaseModel, Field

from src.models.portfolio import PortfolioSnapshot, PositionItem


class TimeSeriesPoint(BaseModel):
    timestamp: datetime
    value: float


class PositionModel(BaseModel):
    symbol: str
    sec_type: str
    currency: str
    quantity: float
    avg_cost: float | None = None
    market_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    weight: float | None = None
    base_market_value: float | None = None
    fx_rate: float | None = None

    @classmethod
    def from_domain(cls, position: PositionItem) -> "PositionModel":
        return cls(
            symbol=position.symbol,
            sec_type=position.sec_type,
            currency=position.currency,
            quantity=float(position.quantity),
            avg_cost=position.avg_cost,
            market_price=position.market_price,
            market_value=position.market_value,
            unrealized_pnl=position.unrealized_pnl,
            weight=position.weight,
            base_market_value=position.base_market_value,
            fx_rate=position.fx_rate,
        )

    def to_domain(self) -> PositionItem:
        return PositionItem(
            symbol=self.symbol,
            sec_type=self.sec_type,
            currency=self.currency,
            quantity=self.quantity,
            avg_cost=self.avg_cost,
            market_price=self.market_price,
            market_value=self.market_value,
            unrealized_pnl=self.unrealized_pnl,
            weight=self.weight,
            base_market_value=self.base_market_value,
            fx_rate=self.fx_rate,
        )


class PortfolioSnapshotModel(BaseModel):
    timestamp: datetime
    base_currency: str
    account_summary: dict[str, str]
    positions: list[PositionModel]
    total_market_value: float | None = None
    total_cash: float | None = None
    net_liquidation: float | None = None
    day_pnl: float | None = None
    day_pnl_pct: float | None = None
    day_pnl_source: str | None = None
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, snapshot: PortfolioSnapshot) -> "PortfolioSnapshotModel":
        return cls(
            timestamp=snapshot.timestamp,
            base_currency=snapshot.base_currency,
            account_summary=dict(snapshot.account_summary),
            positions=[PositionModel.from_domain(position) for position in snapshot.positions],
            total_market_value=snapshot.total_market_value,
            total_cash=snapshot.total_cash,
            net_liquidation=snapshot.net_liquidation,
            day_pnl=snapshot.day_pnl,
            day_pnl_pct=snapshot.day_pnl_pct,
            day_pnl_source=snapshot.day_pnl_source,
            warnings=list(snapshot.warnings),
        )

    def to_domain(self) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            timestamp=self.timestamp,
            base_currency=self.base_currency,
            account_summary=dict(self.account_summary),
            positions=[position.to_domain() for position in self.positions],
            total_market_value=self.total_market_value,
            total_cash=self.total_cash,
            net_liquidation=self.net_liquidation,
            day_pnl=self.day_pnl,
            day_pnl_pct=self.day_pnl_pct,
            day_pnl_source=self.day_pnl_source,
            warnings=list(self.warnings),
        )


class PortfolioHistoryPointModel(BaseModel):
    timestamp: datetime
    portfolio_value: float
    net_liquidation: float | None = None
    market_value: float | None = None
    cash: float | None = None
    base_currency: str | None = None


class PortfolioHistoryResponseModel(BaseModel):
    source: str
    points: list[PortfolioHistoryPointModel]

    @classmethod
    def from_dataframe(cls, history_df: pd.DataFrame) -> "PortfolioHistoryResponseModel":
        points: list[PortfolioHistoryPointModel] = []
        if not history_df.empty:
            for timestamp, row in history_df.reset_index().iterrows():
                ts = row["timestamp"] if "timestamp" in row else row.iloc[0]
                points.append(
                    PortfolioHistoryPointModel(
                        timestamp=pd.Timestamp(ts).to_pydatetime(),
                        portfolio_value=float(row["portfolio_value"]),
                        net_liquidation=_to_float(row.get("netliq")),
                        market_value=_to_float(row.get("market_value")),
                        cash=_to_float(row.get("cash")),
                        base_currency=_to_str(row.get("base_ccy")),
                    )
                )
        return cls(source="local_history_store", points=points)


def series_to_points(series: pd.Series) -> list[TimeSeriesPoint]:
    if series is None or series.empty:
        return []
    clean = series.dropna()
    return [
        TimeSeriesPoint(timestamp=pd.Timestamp(index).to_pydatetime(), value=float(value))
        for index, value in clean.items()
    ]


def _to_float(value) -> float | None:
    if value is None or value != value:
        return None
    return float(value)


def _to_str(value) -> str | None:
    if value is None or value != value:
        return None
    return str(value)
