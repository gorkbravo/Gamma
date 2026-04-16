from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.schemas.fundamentals import (
    FundamentalsDcfModelModel,
    FundamentalsDcfSaveRequestModel,
    FundamentalsDcfSnapshotListResponseModel,
    FundamentalsDcfSnapshotModel,
    FundamentalsDcfSnapshotSaveRequestModel,
    FundamentalsFinancialsResponseModel,
    FundamentalsOverviewResponseModel,
    FundamentalsPeerBasketModel,
    FundamentalsPeerBasketUpdateRequestModel,
    FundamentalsPeersResponseModel,
    FundamentalsReferenceResponseModel,
    FundamentalsReverseValuationResponseModel,
    FundamentalsSearchResponseModel,
    FundamentalsSearchResultModel,
)


router = APIRouter(tags=["fundamentals"])


@router.get("/fundamentals/search", response_model=FundamentalsSearchResponseModel)
def fundamentals_search(
    request: Request,
    query: str = Query(default=""),
    limit: int = Query(default=12, ge=1, le=40),
    force_refresh: bool = Query(default=False),
) -> FundamentalsSearchResponseModel:
    runtime = request.app.state.runtime
    results = runtime.fundamentals_service.search_companies(
        query,
        limit=limit,
        force_refresh=force_refresh,
    )
    return FundamentalsSearchResponseModel(
        results=[FundamentalsSearchResultModel.from_domain(item) for item in results]
    )


@router.get("/fundamentals/{ticker}/overview", response_model=FundamentalsOverviewResponseModel)
def fundamentals_overview(
    ticker: str,
    request: Request,
    force_refresh: bool = Query(default=False),
) -> FundamentalsOverviewResponseModel:
    runtime = request.app.state.runtime
    result = runtime.fundamentals_service.get_overview(ticker, force_refresh=force_refresh)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Fundamentals company not found: {ticker}")
    return FundamentalsOverviewResponseModel.from_domain(result)


@router.get("/fundamentals/{ticker}/financials", response_model=FundamentalsFinancialsResponseModel)
def fundamentals_financials(
    ticker: str,
    request: Request,
    force_refresh: bool = Query(default=False),
) -> FundamentalsFinancialsResponseModel:
    runtime = request.app.state.runtime
    result = runtime.fundamentals_service.get_financials(ticker, force_refresh=force_refresh)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Fundamentals financials not found: {ticker}")
    return FundamentalsFinancialsResponseModel.from_domain(result)


@router.get("/fundamentals/{ticker}/peers", response_model=FundamentalsPeersResponseModel)
def fundamentals_peers(
    ticker: str,
    request: Request,
    force_refresh: bool = Query(default=False),
) -> FundamentalsPeersResponseModel:
    runtime = request.app.state.runtime
    result = runtime.fundamentals_service.get_peers(ticker, force_refresh=force_refresh)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Fundamentals peers not found: {ticker}")
    return FundamentalsPeersResponseModel.from_domain(result)


@router.get("/fundamentals/{ticker}/reverse-valuation", response_model=FundamentalsReverseValuationResponseModel)
def fundamentals_reverse_valuation(
    ticker: str,
    request: Request,
    force_refresh: bool = Query(default=False),
) -> FundamentalsReverseValuationResponseModel:
    runtime = request.app.state.runtime
    result = runtime.fundamentals_service.get_reverse_valuation(ticker, force_refresh=force_refresh)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Fundamentals reverse valuation not found: {ticker}")
    return FundamentalsReverseValuationResponseModel.from_domain(result)


@router.get("/fundamentals/{ticker}/reference", response_model=FundamentalsReferenceResponseModel)
def fundamentals_reference(
    ticker: str,
    request: Request,
    force_refresh: bool = Query(default=False),
) -> FundamentalsReferenceResponseModel:
    runtime = request.app.state.runtime
    result = runtime.fundamentals_service.get_reference(ticker, force_refresh=force_refresh)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Fundamentals reference not found: {ticker}")
    return FundamentalsReferenceResponseModel.from_domain(result)


@router.get("/fundamentals/{ticker}/dcf", response_model=FundamentalsDcfModelModel)
def fundamentals_dcf(
    ticker: str,
    request: Request,
    force_refresh: bool = Query(default=False),
) -> FundamentalsDcfModelModel:
    runtime = request.app.state.runtime
    model = runtime.fundamentals_service.get_dcf_model(ticker, force_refresh=force_refresh)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Fundamentals DCF model not found: {ticker}")
    return FundamentalsDcfModelModel.from_domain(model)


@router.get("/fundamentals/{ticker}/dcf/snapshots", response_model=FundamentalsDcfSnapshotListResponseModel)
def fundamentals_dcf_snapshots(
    ticker: str,
    request: Request,
    force_refresh: bool = Query(default=False),
) -> FundamentalsDcfSnapshotListResponseModel:
    runtime = request.app.state.runtime
    snapshots = runtime.fundamentals_service.list_dcf_snapshots(ticker, force_refresh=force_refresh)
    if snapshots is None:
        raise HTTPException(status_code=404, detail=f"Fundamentals DCF snapshots not found: {ticker}")
    return FundamentalsDcfSnapshotListResponseModel(
        snapshots=[FundamentalsDcfSnapshotModel.from_domain(item) for item in snapshots]
    )


@router.post("/fundamentals/{ticker}/dcf/snapshots", response_model=FundamentalsDcfSnapshotModel)
def fundamentals_save_dcf_snapshot(
    ticker: str,
    payload: FundamentalsDcfSnapshotSaveRequestModel,
    request: Request,
) -> FundamentalsDcfSnapshotModel:
    runtime = request.app.state.runtime
    snapshot = runtime.fundamentals_service.save_dcf_snapshot(ticker, name=payload.name)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Fundamentals DCF snapshot could not be saved: {ticker}")
    return FundamentalsDcfSnapshotModel.from_domain(snapshot)


@router.get("/fundamentals/{ticker}/dcf/snapshots/{snapshot_id}", response_model=FundamentalsDcfModelModel)
def fundamentals_load_dcf_snapshot(
    ticker: str,
    snapshot_id: str,
    request: Request,
    force_refresh: bool = Query(default=False),
) -> FundamentalsDcfModelModel:
    runtime = request.app.state.runtime
    model = runtime.fundamentals_service.load_dcf_snapshot_model(
        ticker,
        snapshot_id,
        force_refresh=force_refresh,
    )
    if model is None:
        raise HTTPException(status_code=404, detail=f"Fundamentals DCF snapshot not found: {ticker}/{snapshot_id}")
    return FundamentalsDcfModelModel.from_domain(model)


@router.post("/fundamentals/{ticker}/dcf", response_model=FundamentalsDcfModelModel)
def fundamentals_save_dcf(
    ticker: str,
    payload: FundamentalsDcfSaveRequestModel,
    request: Request,
) -> FundamentalsDcfModelModel:
    runtime = request.app.state.runtime
    model = runtime.fundamentals_service.save_dcf_model(ticker, payload.to_payload())
    if model is None:
        raise HTTPException(status_code=404, detail=f"Fundamentals DCF model could not be saved: {ticker}")
    return FundamentalsDcfModelModel.from_domain(model)


@router.post("/fundamentals/{ticker}/peers", response_model=FundamentalsPeerBasketModel)
def fundamentals_save_peer_basket(
    ticker: str,
    payload: FundamentalsPeerBasketUpdateRequestModel,
    request: Request,
) -> FundamentalsPeerBasketModel:
    runtime = request.app.state.runtime
    basket = runtime.fundamentals_service.save_peer_basket(ticker, payload.peer_tickers)
    if basket is None:
        raise HTTPException(status_code=404, detail=f"Fundamentals peer basket could not be saved: {ticker}")
    return FundamentalsPeerBasketModel.from_domain(basket)
