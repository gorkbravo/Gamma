from __future__ import annotations

from datetime import datetime
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

from src.models.portfolio import (
    PortfolioHistoryHealth,
    PortfolioHistoryLoadResult,
    PortfolioHistoryState,
    PortfolioPerformanceState,
    PortfolioSnapshot,
    PortfolioSnapshotState,
    PositionItem,
)


class TimeSeriesPoint(BaseModel):
    timestamp: datetime
    value: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None


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
    instrument_id: str | None = None
    display_symbol: str | None = None
    exchange: str | None = None
    primary_exchange: str | None = None
    provider: str | None = None
    provider_id: str | None = None

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
            instrument_id=position.resolved_instrument_id(),
            display_symbol=position.resolved_display_symbol(),
            exchange=position.exchange,
            primary_exchange=position.primary_exchange,
            provider=position.provider,
            provider_id=position.provider_id,
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
            instrument_id=self.instrument_id,
            display_symbol=self.display_symbol,
            exchange=self.exchange,
            primary_exchange=self.primary_exchange,
            provider=self.provider,
            provider_id=self.provider_id,
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
    state: Literal["ready", "partial", "empty", "unavailable", "failed"] = (
        PortfolioSnapshotState.READY.value
    )
    source_provider: str = "unknown"
    retrieved_at: datetime | None = None
    origin: str = "gamma.portfolio.snapshot"
    freshness_label: str = "unknown"
    transformation_note: str | None = None
    quote_mode: Literal["Snapshot", "Stream"] = "Snapshot"
    market_data_mode: str = "unknown"
    complete: bool = True
    connection_ready: bool = False
    account_summary_available: bool = False
    account_subscription_usable: bool = False
    requested_position_count: int = 0
    quoted_position_count: int = 0
    missing_quote_count: int = 0
    missing_quote_symbols: list[str] = Field(default_factory=list)
    cached_quote_count: int = 0
    cached_quote_symbols: list[str] = Field(default_factory=list)
    delayed_quote_count: int = 0
    delayed_quote_symbols: list[str] = Field(default_factory=list)
    available_value_count: int = 0
    history_store_health: "PortfolioHistoryHealthModel | None" = None
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
            state=snapshot.state.value,
            source_provider=snapshot.source_provider,
            retrieved_at=snapshot.retrieved_at,
            origin=snapshot.origin,
            freshness_label=snapshot.freshness_label,
            transformation_note=snapshot.transformation_note,
            quote_mode=snapshot.quote_mode,
            market_data_mode=snapshot.market_data_mode,
            complete=snapshot.complete,
            connection_ready=snapshot.connection_ready,
            account_summary_available=snapshot.account_summary_available,
            account_subscription_usable=snapshot.account_subscription_usable,
            requested_position_count=snapshot.requested_position_count,
            quoted_position_count=snapshot.quoted_position_count,
            missing_quote_count=snapshot.missing_quote_count,
            missing_quote_symbols=list(snapshot.missing_quote_symbols),
            cached_quote_count=snapshot.cached_quote_count,
            cached_quote_symbols=list(snapshot.cached_quote_symbols),
            delayed_quote_count=snapshot.delayed_quote_count,
            delayed_quote_symbols=list(snapshot.delayed_quote_symbols),
            available_value_count=snapshot.available_value_count,
            history_store_health=(
                PortfolioHistoryHealthModel.from_domain(snapshot.history_store_health)
                if snapshot.history_store_health is not None
                else None
            ),
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
            state=PortfolioSnapshotState(self.state),
            source_provider=self.source_provider,
            retrieved_at=self.retrieved_at,
            origin=self.origin,
            freshness_label=self.freshness_label,
            transformation_note=self.transformation_note,
            quote_mode=self.quote_mode,
            market_data_mode=self.market_data_mode,
            complete=self.complete,
            connection_ready=self.connection_ready,
            account_summary_available=self.account_summary_available,
            account_subscription_usable=self.account_subscription_usable,
            requested_position_count=self.requested_position_count,
            quoted_position_count=self.quoted_position_count,
            missing_quote_count=self.missing_quote_count,
            missing_quote_symbols=list(self.missing_quote_symbols),
            cached_quote_count=self.cached_quote_count,
            cached_quote_symbols=list(self.cached_quote_symbols),
            delayed_quote_count=self.delayed_quote_count,
            delayed_quote_symbols=list(self.delayed_quote_symbols),
            available_value_count=self.available_value_count,
            history_store_health=(
                self.history_store_health.to_domain()
                if self.history_store_health is not None
                else None
            ),
            warnings=list(self.warnings),
        )


class PortfolioHistoryPointModel(BaseModel):
    timestamp: datetime
    portfolio_value: float
    net_liquidation: float | None = None
    market_value: float | None = None
    cash: float | None = None
    base_currency: str | None = None


class PortfolioHistoryHealthModel(BaseModel):
    status: Literal["ready", "empty", "recovered", "degraded", "failed"] = (
        PortfolioHistoryState.EMPTY.value
    )
    point_count: int = 0
    base_currency: str | None = None
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    malformed_row_count: int = 0
    duplicate_row_count: int = 0
    recovery_archive_name: str | None = None
    last_write_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, health: PortfolioHistoryHealth) -> "PortfolioHistoryHealthModel":
        return cls(
            status=health.status.value,
            point_count=health.point_count,
            base_currency=health.base_currency,
            first_timestamp=health.first_timestamp,
            last_timestamp=health.last_timestamp,
            malformed_row_count=health.malformed_row_count,
            duplicate_row_count=health.duplicate_row_count,
            recovery_archive_name=health.recovery_archive_name,
            last_write_at=health.last_write_at,
            warnings=list(health.warnings),
        )

    def to_domain(self) -> PortfolioHistoryHealth:
        return PortfolioHistoryHealth(
            status=PortfolioHistoryState(self.status),
            point_count=self.point_count,
            base_currency=self.base_currency,
            first_timestamp=self.first_timestamp,
            last_timestamp=self.last_timestamp,
            malformed_row_count=self.malformed_row_count,
            duplicate_row_count=self.duplicate_row_count,
            recovery_archive_name=self.recovery_archive_name,
            last_write_at=self.last_write_at,
            warnings=list(self.warnings),
        )


class PortfolioHistoryResponseModel(BaseModel):
    source: str
    state: Literal["ready", "empty", "recovered", "degraded", "failed"] = (
        PortfolioHistoryState.EMPTY.value
    )
    source_provider: str = "local_history_store"
    retrieved_at: datetime | None = None
    origin: str = "gamma.portfolio.local_history"
    freshness_label: str = "historical"
    transformation_note: str = (
        "Locally accumulated daily portfolio snapshots observed by Gamma; "
        "not a broker backfill."
    )
    points: list[PortfolioHistoryPointModel]
    health: PortfolioHistoryHealthModel = Field(default_factory=PortfolioHistoryHealthModel)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_result(cls, result: PortfolioHistoryLoadResult) -> "PortfolioHistoryResponseModel":
        history_df = result.frame
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
        return cls(
            source="local_history_store",
            state=result.health.status.value,
            source_provider="local_history_store",
            retrieved_at=datetime.now().astimezone(),
            origin="gamma.portfolio.local_history",
            freshness_label=(
                "unavailable"
                if result.health.status == PortfolioHistoryState.FAILED
                else "historical"
            ),
            points=points,
            health=PortfolioHistoryHealthModel.from_domain(result.health),
            warnings=list(result.health.warnings),
        )

    @classmethod
    def from_dataframe(cls, history_df: pd.DataFrame) -> "PortfolioHistoryResponseModel":
        status = (
            PortfolioHistoryState.READY
            if history_df is not None and not history_df.empty
            else PortfolioHistoryState.EMPTY
        )
        health = PortfolioHistoryHealth(status=status, point_count=int(len(history_df)))
        return cls.from_result(PortfolioHistoryLoadResult(frame=history_df, health=health))


class PortfolioPerformanceRequestModel(BaseModel):
    snapshot: PortfolioSnapshotModel
    benchmark_symbol: str = Field(
        default="SPY",
        min_length=1,
        max_length=32,
        pattern=r"^[A-Za-z0-9._:/-]+$",
    )
    lookback_days: int = Field(default=504, ge=2, le=5000)


class PortfolioPerformanceResponseModel(BaseModel):
    benchmark_symbol: str
    benchmark_source: str
    benchmark_source_provider: str = "unavailable"
    state: Literal["ready", "partial", "unavailable", "failed"] = (
        PortfolioPerformanceState.UNAVAILABLE.value
    )
    source_provider: str = "gamma"
    retrieved_at: datetime | None = None
    origin: str = "gamma.portfolio.performance"
    freshness_label: str = "derived"
    transformation_note: str = (
        "Gamma-derived weighted performance from aligned constituent histories, "
        "or from the explicitly labeled local snapshot trail when constituent history is unavailable."
    )
    complete: bool = False
    performance_points: list[TimeSeriesPoint]
    benchmark_points: list[TimeSeriesPoint]
    portfolio_base_value: float | None = None
    requested_position_count: int = 0
    covered_position_count: int = 0
    history_coverage_ratio: float | None = None
    missing_history_symbols: list[str] = Field(default_factory=list)
    missing_fx_symbols: list[str] = Field(default_factory=list)
    history_source: str = "unavailable"
    history_source_provider: str = "unavailable"
    history_freshness_label: str = "unavailable"
    history_transformation_note: str | None = None
    history_point_count: int = 0
    benchmark_freshness_label: str = "unavailable"
    benchmark_transformation_note: str | None = None
    missing_symbols: list[str] = Field(default_factory=list)
    day_pnl: float | None = None
    day_pnl_pct: float | None = None
    day_pnl_source: str | None = None
    message: str | None = None
    warnings: list[str] = Field(default_factory=list)


class PortfolioHistoryClearResponseModel(BaseModel):
    success: bool = True
    lines: list[str] = Field(default_factory=list)
    archived: bool = False
    archive_name: str | None = None


def series_to_points(series: pd.Series, ohlcv: pd.DataFrame | None = None) -> list[TimeSeriesPoint]:
    if series is None or series.empty:
        return []
    clean = series.dropna()
    normalized_ohlcv = _normalize_ohlcv_frame(ohlcv)
    points: list[TimeSeriesPoint] = []
    for index, value in clean.items():
        point_kwargs = {
            "timestamp": pd.Timestamp(index).to_pydatetime(),
            "value": float(value),
        }
        if normalized_ohlcv is not None and index in normalized_ohlcv.index:
            row = normalized_ohlcv.loc[index]
            point_kwargs.update(
                {
                    "open": _to_float(row.get("open")),
                    "high": _to_float(row.get("high")),
                    "low": _to_float(row.get("low")),
                    "close": _to_float(row.get("close")),
                    "volume": _to_float(row.get("volume")),
                }
            )
        points.append(TimeSeriesPoint(**point_kwargs))
    return points


def _normalize_ohlcv_frame(frame: pd.DataFrame | None) -> pd.DataFrame | None:
    if frame is None or frame.empty:
        return None
    columns = {str(column).strip().lower(): column for column in frame.columns}
    selected: dict[str, pd.Series] = {}
    for key in ("open", "high", "low", "close", "volume"):
        column = columns.get(key)
        if column is not None:
            selected[key] = pd.to_numeric(frame[column], errors="coerce")
    if not selected:
        return None
    normalized = pd.DataFrame(selected, index=frame.index).dropna(how="all")
    return normalized.sort_index() if not normalized.empty else None


def _to_float(value) -> float | None:
    if value is None or value != value:
        return None
    return float(value)


def _to_str(value) -> str | None:
    if value is None or value != value:
        return None
    return str(value)
