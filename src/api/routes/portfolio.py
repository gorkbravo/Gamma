from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Request

from src.api.schemas.portfolio import PortfolioHistoryResponseModel, PortfolioSnapshotModel
from src.application.portfolio_service import PortfolioSnapshotRequest


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
