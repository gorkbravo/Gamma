from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.schemas.commodities import (
    CommodityCurveResponseModel,
    CommodityCurveSnapshotModel,
    CommodityPriceHistoryModel,
    CommodityPriceHistoryResponseModel,
    CommoditySpreadListResponseModel,
    CommoditySpreadSnapshotModel,
    CommodityWorkspaceRequestModel,
    CommodityWorkspaceResponseModel,
)


router = APIRouter(tags=["commodities"])


@router.post("/commodities/workspace", response_model=CommodityWorkspaceResponseModel)
def commodities_workspace(
    payload: CommodityWorkspaceRequestModel,
    request: Request,
) -> CommodityWorkspaceResponseModel:
    runtime = request.app.state.runtime
    result = runtime.commodities_service.get_workspace(payload.to_domain())
    return CommodityWorkspaceResponseModel.from_domain(result)


@router.get("/commodities/overview", response_model=CommodityWorkspaceResponseModel)
def commodities_overview(
    request: Request,
    selected_instrument_id: str = Query(default="wti"),
    force_refresh: bool = Query(default=False),
) -> CommodityWorkspaceResponseModel:
    runtime = request.app.state.runtime
    result = runtime.commodities_service.get_workspace(
        CommodityWorkspaceRequestModel(
            mode="overview",
            selected_instrument_id=selected_instrument_id,
            force_refresh=force_refresh,
        ).to_domain()
    )
    return CommodityWorkspaceResponseModel.from_domain(result)


@router.get("/commodities/price-history", response_model=CommodityPriceHistoryResponseModel)
def commodities_price_history(
    request: Request,
    instrument_id: str = Query(default="wti"),
    force_refresh: bool = Query(default=False),
) -> CommodityPriceHistoryResponseModel:
    runtime = request.app.state.runtime
    history = runtime.commodities_service.get_price_history(instrument_id, force_refresh=force_refresh)
    if history is None:
        raise HTTPException(status_code=404, detail=f"Commodity price history not found: {instrument_id}")
    return CommodityPriceHistoryResponseModel(
        instrument_id=instrument_id,
        history=CommodityPriceHistoryModel.from_domain(history),
    )


@router.get("/commodities/curve", response_model=CommodityCurveResponseModel)
def commodities_curve(
    request: Request,
    instrument_id: str = Query(default="wti"),
    force_refresh: bool = Query(default=False),
) -> CommodityCurveResponseModel:
    runtime = request.app.state.runtime
    curve = runtime.commodities_service.get_curve(instrument_id, force_refresh=force_refresh)
    if curve is None:
        raise HTTPException(status_code=404, detail=f"Commodity curve not found: {instrument_id}")
    return CommodityCurveResponseModel(
        instrument_id=instrument_id,
        curve=CommodityCurveSnapshotModel.from_domain(curve),
    )


@router.get("/commodities/spreads", response_model=CommoditySpreadListResponseModel)
def commodities_spreads(
    request: Request,
    force_refresh: bool = Query(default=False),
) -> CommoditySpreadListResponseModel:
    runtime = request.app.state.runtime
    spreads = runtime.commodities_service.get_spreads(force_refresh=force_refresh)
    return CommoditySpreadListResponseModel(
        spreads=[CommoditySpreadSnapshotModel.from_domain(row) for row in spreads],
    )


@router.get("/commodities/markets", response_model=CommodityWorkspaceResponseModel)
def commodities_markets(
    request: Request,
    selected_instrument_id: str = Query(default="wti"),
    force_refresh: bool = Query(default=False),
) -> CommodityWorkspaceResponseModel:
    return commodities_overview(
        request,
        selected_instrument_id=selected_instrument_id,
        force_refresh=force_refresh,
    )


@router.get("/commodities/inventories", response_model=CommodityWorkspaceResponseModel)
def commodities_inventories(
    request: Request,
    selected_instrument_id: str = Query(default="wti"),
    force_refresh: bool = Query(default=False),
) -> CommodityWorkspaceResponseModel:
    runtime = request.app.state.runtime
    result = runtime.commodities_service.get_workspace(
        CommodityWorkspaceRequestModel(
            mode="inventories_fundamentals",
            selected_instrument_id=selected_instrument_id,
            force_refresh=force_refresh,
        ).to_domain()
    )
    return CommodityWorkspaceResponseModel.from_domain(result)


@router.get("/commodities/events", response_model=CommodityWorkspaceResponseModel)
def commodities_events(
    request: Request,
    selected_instrument_id: str = Query(default="wti"),
    force_refresh: bool = Query(default=False),
) -> CommodityWorkspaceResponseModel:
    runtime = request.app.state.runtime
    result = runtime.commodities_service.get_workspace(
        CommodityWorkspaceRequestModel(
            mode="events_cross_domain",
            selected_instrument_id=selected_instrument_id,
            force_refresh=force_refresh,
        ).to_domain()
    )
    return CommodityWorkspaceResponseModel.from_domain(result)


@router.get("/commodities/cross-domain", response_model=CommodityWorkspaceResponseModel)
def commodities_cross_domain(
    request: Request,
    selected_instrument_id: str = Query(default="wti"),
    force_refresh: bool = Query(default=False),
) -> CommodityWorkspaceResponseModel:
    return commodities_events(
        request,
        selected_instrument_id=selected_instrument_id,
        force_refresh=force_refresh,
    )
