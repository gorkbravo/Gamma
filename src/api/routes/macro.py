from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.schemas.macro import (
    MacroDivergenceListResponseModel,
    MacroEventsResponseModel,
    MacroSeriesHistoryResponseModel,
    MacroSnapshotRequestModel,
    MacroSnapshotResponseModel,
)


router = APIRouter(tags=["macro"])


@router.post("/macro/snapshot", response_model=MacroSnapshotResponseModel)
def macro_snapshot(payload: MacroSnapshotRequestModel, request: Request) -> MacroSnapshotResponseModel:
    runtime = request.app.state.runtime
    result = runtime.macro_service.get_snapshot(payload.to_domain())
    return MacroSnapshotResponseModel.from_domain(result)


@router.get("/macro/series/{series_id}/history", response_model=MacroSeriesHistoryResponseModel)
def macro_series_history(
    series_id: str,
    request: Request,
    region: str = Query(default="US"),
    timeframe: str = Query(default="1Y"),
    force_refresh: bool = Query(default=False),
) -> MacroSeriesHistoryResponseModel:
    runtime = request.app.state.runtime
    history = runtime.macro_service.get_series_history(
        series_id,
        region=region,
        timeframe=timeframe,
        force_refresh=force_refresh,
    )
    if history is None:
        raise HTTPException(status_code=404, detail=f"Macro series not found: {series_id}")
    return MacroSeriesHistoryResponseModel.from_domain(history)


@router.post("/macro/divergences", response_model=MacroDivergenceListResponseModel)
def macro_divergences(payload: MacroSnapshotRequestModel, request: Request) -> MacroDivergenceListResponseModel:
    runtime = request.app.state.runtime
    rows = runtime.macro_service.get_divergences(payload.to_domain())
    return MacroDivergenceListResponseModel.from_domain(
        region=payload.region,
        timeframe=payload.timeframe,
        theme=payload.theme,
        comparison_region=payload.comparison_region,
        rows=rows,
    )


@router.get("/macro/events", response_model=MacroEventsResponseModel)
def macro_events(
    request: Request,
    region: str = Query(default="US"),
    force_refresh: bool = Query(default=False),
) -> MacroEventsResponseModel:
    runtime = request.app.state.runtime
    rows = runtime.macro_service.get_events(region=region, force_refresh=force_refresh)
    return MacroEventsResponseModel.from_domain(region=region, rows=rows)
