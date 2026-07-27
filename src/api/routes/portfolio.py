from __future__ import annotations

from datetime import datetime
import logging

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.schemas.portfolio import (
    PortfolioHistoryClearResponseModel,
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
from src.models.portfolio import PortfolioPerformanceState
from src.services.ibkr_client import PORTFOLIO_QUOTE_TIMEOUT_MAX_SECONDS
from src.utils.time import now_utc


router = APIRouter(tags=["portfolio"])
logger = logging.getLogger(__name__)


@router.get("/portfolio/snapshot", response_model=PortfolioSnapshotModel)
def portfolio_snapshot(
    request: Request,
    quote_mode: str = Query(default="Snapshot", pattern=r"^(Snapshot|Stream)$"),
    quote_timeout_seconds: float | None = Query(
        default=None,
        ge=0.1,
        le=PORTFOLIO_QUOTE_TIMEOUT_MAX_SECONDS,
    ),
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
    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=422,
            detail="Portfolio history start must be on or before end.",
        )
    if refresh_snapshot:
        runtime.portfolio_service.fetch_snapshot(
            PortfolioSnapshotRequest(
                base_currency=runtime.base_currency,
                quote_mode="Snapshot",
                quote_timeout_seconds=runtime.quote_timeout_seconds,
            )
        )
    history_result = runtime.portfolio_service.load_history_result(start=start, end=end)
    return PortfolioHistoryResponseModel.from_result(history_result)


@router.post("/portfolio/performance", response_model=PortfolioPerformanceResponseModel)
def portfolio_performance(
    payload: PortfolioPerformanceRequestModel,
    request: Request,
) -> PortfolioPerformanceResponseModel:
    runtime = request.app.state.runtime
    try:
        result = runtime.portfolio_service.compute_performance(
            PortfolioPerformanceRequest(
                snapshot=payload.snapshot.to_domain(),
                benchmark_symbol=payload.benchmark_symbol,
                lookback_days=payload.lookback_days,
            )
        )
    except Exception as exc:
        logger.exception(
            "Portfolio performance failed for benchmark=%s lookback_days=%s",
            payload.benchmark_symbol,
            payload.lookback_days,
        )
        return PortfolioPerformanceResponseModel(
            benchmark_symbol=payload.benchmark_symbol,
            benchmark_source="none",
            benchmark_source_provider="unavailable",
            state=PortfolioPerformanceState.FAILED.value,
            source_provider="gamma",
            retrieved_at=now_utc(),
            origin="gamma.portfolio.performance",
            freshness_label="unavailable",
            complete=False,
            performance_points=[],
            benchmark_points=[],
            requested_position_count=len(payload.snapshot.positions),
            covered_position_count=0,
            history_coverage_ratio=0.0 if payload.snapshot.positions else None,
            missing_history_symbols=[],
            missing_fx_symbols=[],
            history_source="unavailable",
            history_source_provider="unavailable",
            history_freshness_label="unavailable",
            history_transformation_note="Constituent and local snapshot history were unavailable.",
            history_point_count=0,
            benchmark_freshness_label="unavailable",
            benchmark_transformation_note="The requested benchmark could not be represented.",
            message="Portfolio performance could not be calculated.",
            warnings=[
                "Retry performance. If the failure continues, open Diagnostics and "
                f"reference the {type(exc).__name__} failure category."
            ],
        )
    return PortfolioPerformanceResponseModel(
        benchmark_symbol=payload.benchmark_symbol,
        benchmark_source=result.benchmark_source,
        benchmark_source_provider=result.benchmark_source_provider,
        state=result.state.value,
        source_provider=result.source_provider,
        retrieved_at=result.retrieved_at,
        origin=result.origin,
        freshness_label=result.freshness_label,
        transformation_note=result.transformation_note,
        complete=result.complete,
        performance_points=series_to_points(result.portfolio_cumulative),
        benchmark_points=series_to_points(result.benchmark_cumulative),
        portfolio_base_value=result.portfolio_base_value,
        requested_position_count=result.requested_position_count,
        covered_position_count=result.covered_position_count,
        history_coverage_ratio=result.history_coverage_ratio,
        missing_history_symbols=list(result.missing_history_symbols),
        missing_fx_symbols=list(result.missing_fx_symbols),
        history_source=result.history_source,
        history_source_provider=result.history_source_provider,
        history_freshness_label=result.history_freshness_label,
        history_transformation_note=result.history_transformation_note,
        history_point_count=result.history_point_count,
        benchmark_freshness_label=result.benchmark_freshness_label,
        benchmark_transformation_note=result.benchmark_transformation_note,
        missing_symbols=list(result.missing_symbols),
        day_pnl=result.day_pnl,
        day_pnl_pct=result.day_pnl_pct,
        day_pnl_source=result.day_pnl_source,
        message=result.message,
        warnings=list(result.warnings),
    )


@router.post(
    "/portfolio/history/clear",
    response_model=PortfolioHistoryClearResponseModel,
)
def clear_portfolio_history(request: Request) -> PortfolioHistoryClearResponseModel:
    runtime = request.app.state.runtime
    result = runtime.portfolio_service.clear_history()
    lines = (
        [
            "Local portfolio history cleared.",
            "The previous snapshot trail was preserved in a local recovery archive.",
        ]
        if result.archived
        else ["Local portfolio history was already empty."]
    )
    return PortfolioHistoryClearResponseModel(
        lines=lines,
        archived=result.archived,
        archive_name=result.archive_name,
    )
