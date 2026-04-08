from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.schemas.crypto import (
    CryptoComparisonModel,
    CryptoDexLiquiditySummaryModel,
    CryptoFlowSummaryModel,
    CryptoPriceHistoryResponseModel,
    CryptoPricePointModel,
    CryptoSyntheticPortfolioRequestModel,
    CryptoSyntheticPortfolioResponseModel,
    CryptoTokenModel,
    CryptoWorkspaceRequestModel,
    CryptoWorkspaceResponseModel,
)


router = APIRouter(tags=["crypto"])


@router.post("/crypto/workspace", response_model=CryptoWorkspaceResponseModel)
def crypto_workspace(
    payload: CryptoWorkspaceRequestModel,
    request: Request,
) -> CryptoWorkspaceResponseModel:
    runtime = request.app.state.runtime
    result = runtime.crypto_service.get_workspace(payload.to_domain())
    return CryptoWorkspaceResponseModel.from_domain(result)


@router.get("/crypto/tokens/{token_id}", response_model=CryptoTokenModel)
def crypto_token_detail(
    token_id: str,
    request: Request,
    force_refresh: bool = Query(default=False),
) -> CryptoTokenModel:
    runtime = request.app.state.runtime
    token = runtime.crypto_service.get_token_detail(token_id, force_refresh=force_refresh)
    if token is None:
        raise HTTPException(status_code=404, detail=f"Crypto token not found: {token_id}")
    return CryptoTokenModel.from_domain(token)


@router.get("/crypto/tokens/{token_id}/history", response_model=CryptoPriceHistoryResponseModel)
def crypto_token_history(
    token_id: str,
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    force_refresh: bool = Query(default=False),
) -> CryptoPriceHistoryResponseModel:
    runtime = request.app.state.runtime
    points = runtime.crypto_service.get_price_history(token_id, days=days, force_refresh=force_refresh)
    return CryptoPriceHistoryResponseModel(
        token_id=token_id,
        points=[CryptoPricePointModel.from_domain(point) for point in points],
    )


@router.get("/crypto/tokens/{token_id}/liquidity", response_model=CryptoDexLiquiditySummaryModel)
def crypto_token_liquidity(
    token_id: str,
    request: Request,
    force_refresh: bool = Query(default=False),
) -> CryptoDexLiquiditySummaryModel:
    runtime = request.app.state.runtime
    summary = runtime.crypto_service.get_dex_liquidity(token_id, force_refresh=force_refresh)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Crypto token not found: {token_id}")
    return CryptoDexLiquiditySummaryModel.from_domain(summary)


@router.get("/crypto/tokens/{token_id}/flow", response_model=CryptoFlowSummaryModel)
def crypto_token_flow(
    token_id: str,
    request: Request,
    force_refresh: bool = Query(default=False),
) -> CryptoFlowSummaryModel:
    runtime = request.app.state.runtime
    flow = runtime.crypto_service.get_flow_summary(token_id, force_refresh=force_refresh)
    if flow is None:
        raise HTTPException(status_code=404, detail=f"Crypto flow summary not available for: {token_id}")
    return CryptoFlowSummaryModel.from_domain(flow)


@router.get("/crypto/tokens/{token_id}/comparison", response_model=CryptoComparisonModel)
def crypto_token_comparison(
    token_id: str,
    request: Request,
    target_token_id: str | None = Query(default=None),
    basket_id: str | None = Query(default=None),
    force_refresh: bool = Query(default=False),
) -> CryptoComparisonModel:
    runtime = request.app.state.runtime
    comparison = runtime.crypto_service.get_comparison(
        token_id,
        target_token_id=target_token_id,
        basket_id=basket_id,
        force_refresh=force_refresh,
    )
    if comparison is None:
        raise HTTPException(status_code=404, detail=f"Crypto comparison not available for: {token_id}")
    return CryptoComparisonModel.from_domain(comparison)


@router.post("/crypto/portfolio", response_model=CryptoSyntheticPortfolioResponseModel)
def crypto_synthetic_portfolio(
    payload: CryptoSyntheticPortfolioRequestModel,
    request: Request,
) -> CryptoSyntheticPortfolioResponseModel:
    runtime = request.app.state.runtime
    result = runtime.crypto_service.analyze_synthetic_portfolio(payload.to_domain())
    if result is None:
        raise HTTPException(status_code=404, detail="Crypto synthetic portfolio could not be built from the submitted identifiers.")
    return CryptoSyntheticPortfolioResponseModel.from_domain(result)
