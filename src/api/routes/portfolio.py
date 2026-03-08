from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Request

from src.api.schemas.portfolio import (
    PortfolioHistoryResponseModel,
    PortfolioPerformanceRequestModel,
    PortfolioPerformanceResponseModel,
    PortfolioSnapshotModel,
    series_to_points,
)
from src.application.portfolio_service import (
    PortfolioPerformanceRequest,
    PortfolioSnapshotRequest,
)
from src.api.schemas.system import ActionResponseModel


router = APIRouter(tags=["portfolio"])


@router.get("/portfolio/snapshot", response_model=PortfolioSnapshotModel)
def portfolio_snapshot(
    request: Request,
    quote_mode: str = Query(default="Snapshot"),
    quote_timeout_seconds: float | None = Query(default=None, ge=0.1, le=30.0),
) -> PortfolioSnapshotModel:
    runtime = request.app.state.runtime
    snapshot = runtime.portfolio_service.fetch_snapshot(
        PortfolioSnapshotRequest(
            base_currency=runtime.base_currency,
            quote_mode=quote_mode,
            quote_timeout_seconds=quote_timeout_seconds or runtime.quote_timeout_seconds,
        )
    )
    return PortfolioSnapshotModel.from_domain(snapshot)


@router.get("/portfolio/history", response_model=PortfolioHistoryResponseModel)
def portfolio_history(
    request: Request,
    refresh_snapshot: bool = Query(default=False),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
) -> PortfolioHistoryResponseModel:
    runtime = request.app.state.runtime
    if refresh_snapshot:
        runtime.portfolio_service.fetch_snapshot(
            PortfolioSnapshotRequest(
                base_currency=runtime.base_currency,
                quote_mode="Snapshot",
                quote_timeout_seconds=runtime.quote_timeout_seconds,
            )
        )
    history_df = runtime.portfolio_service.load_history(start=start, end=end)
    return PortfolioHistoryResponseModel.from_dataframe(history_df)


@router.post("/portfolio/performance", response_model=PortfolioPerformanceResponseModel)
def portfolio_performance(
    payload: PortfolioPerformanceRequestModel,
    request: Request,
) -> PortfolioPerformanceResponseModel:
    runtime = request.app.state.runtime
    result = runtime.portfolio_service.compute_performance(
        PortfolioPerformanceRequest(
            snapshot=payload.snapshot.to_domain(),
            benchmark_symbol=payload.benchmark_symbol,
            lookback_days=payload.lookback_days,
        )
    )
    return PortfolioPerformanceResponseModel(
        benchmark_symbol=payload.benchmark_symbol,
        benchmark_source=result.benchmark_source,
        performance_points=series_to_points(result.portfolio_cumulative),
        benchmark_points=series_to_points(result.benchmark_cumulative),
        portfolio_base_value=result.portfolio_base_value,
        missing_symbols=list(result.missing_symbols),
        day_pnl=result.day_pnl,
        day_pnl_pct=result.day_pnl_pct,
        day_pnl_source=result.day_pnl_source,
        message=result.message,
        warnings=list(result.warnings),
    )


@router.post("/portfolio/history/clear", response_model=ActionResponseModel)
def clear_portfolio_history(request: Request) -> ActionResponseModel:
    runtime = request.app.state.runtime
    runtime.portfolio_service.clear_history()
    return ActionResponseModel(lines=["Local portfolio history cleared."])
