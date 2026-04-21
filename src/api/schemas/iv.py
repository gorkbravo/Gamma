from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.application.iv_service import IVSurfaceResult


class IVSurfaceResponseModel(BaseModel):
    symbol: str
    timestamp: datetime
    snapshot_available: bool
    spot: float | None = None
    expiries: list[str] = Field(default_factory=list)
    strikes: list[float] = Field(default_factory=list)
    iv_grid: list[list[float]] = Field(default_factory=list)
    delayed: bool | None = None
    points: int = 0
    warnings: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    source_provider: str = "ibkr"
    retrieved_at: datetime
    origin: str = "gamma.iv.surface"
    transformation_note: str | None = None
    freshness_label: str = "unknown"

    @classmethod
    def from_service_result(cls, symbol: str, result: IVSurfaceResult) -> "IVSurfaceResponseModel":
        if result.snapshot is None:
            return cls(
                symbol=symbol,
                timestamp=datetime.utcnow(),
                retrieved_at=datetime.utcnow(),
                snapshot_available=False,
                warnings=list(result.warnings),
                messages=list(result.messages),
                freshness_label="unavailable",
            )
        snapshot = result.snapshot
        return cls(
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
            retrieved_at=datetime.utcnow(),
            snapshot_available=True,
            spot=float(snapshot.spot),
            expiries=list(snapshot.expiries),
            strikes=[float(strike) for strike in snapshot.strikes],
            iv_grid=[[float(value) for value in row] for row in snapshot.iv_grid.tolist()],
            delayed=bool(snapshot.delayed),
            points=int(snapshot.points),
            warnings=list(result.warnings),
            messages=list(result.messages),
            source_provider=snapshot.source_provider,
            origin=snapshot.origin,
            transformation_note=snapshot.transformation_note,
            freshness_label=snapshot.freshness_label,
        )


class IVSessionRequestModel(BaseModel):
    symbol: str = "SPY"
    market_data_mode: str | None = None


class IVSessionStatusResponseModel(BaseModel):
    running: bool
    status_text: str
    active_symbol: str | None = None
    market_data_mode: str
    surface: IVSurfaceResponseModel
    messages: list[str] = Field(default_factory=list)
