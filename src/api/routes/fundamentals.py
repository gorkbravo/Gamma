from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.schemas.fundamentals import (
    FundamentalsDcfModelModel,
    FundamentalsDcfSaveRequestModel,
    FundamentalsFinancialsResponseModel,
    FundamentalsOverviewResponseModel,
    FundamentalsPeerBasketModel,
    FundamentalsPeerBasketUpdateRequestModel,
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
