from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from src.api.schemas.prediction_markets import (
    CalibrationSummaryResponseModel,
    PredictionMarketListResponseModel,
    PredictionMarketModel,
    PredictionMarketScreenerRequestModel,
    PredictionProbabilityHistoryResponseModel,
    PredictionProbabilityPointModel,
    RelatedMarketListResponseModel,
    RelatedMarketModel,
    WalletSummaryResponseModel,
)


router = APIRouter(tags=["prediction_markets"])


@router.post("/prediction-markets/screener", response_model=PredictionMarketListResponseModel)
def prediction_market_screener(
    payload: PredictionMarketScreenerRequestModel,
    request: Request,
) -> PredictionMarketListResponseModel:
    runtime = request.app.state.runtime
    result = runtime.prediction_market_service.screener(payload.to_domain())
    return PredictionMarketListResponseModel.from_domain(result)


@router.get("/prediction-markets/markets/{market_id}", response_model=PredictionMarketModel)
def prediction_market_detail(market_id: str, request: Request) -> PredictionMarketModel:
    runtime = request.app.state.runtime
    market = runtime.prediction_market_service.get_market_detail(market_id)
    if market is None:
        raise HTTPException(status_code=404, detail=f"Prediction market not found: {market_id}")
    return PredictionMarketModel.from_domain(market)


@router.get(
    "/prediction-markets/markets/{market_id}/history",
    response_model=PredictionProbabilityHistoryResponseModel,
)
def prediction_market_history(market_id: str, request: Request) -> PredictionProbabilityHistoryResponseModel:
    runtime = request.app.state.runtime
    points = runtime.prediction_market_service.get_probability_history(market_id)
    return PredictionProbabilityHistoryResponseModel(
        market_id=market_id,
        points=[PredictionProbabilityPointModel.from_domain(point) for point in points],
    )


@router.get(
    "/prediction-markets/markets/{market_id}/wallet-summary",
    response_model=WalletSummaryResponseModel,
)
def prediction_market_wallet_summary(market_id: str, request: Request) -> WalletSummaryResponseModel:
    runtime = request.app.state.runtime
    summary = runtime.prediction_market_service.get_wallet_summary(market_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Prediction market not found: {market_id}")
    return WalletSummaryResponseModel.from_domain(summary)


@router.get(
    "/prediction-markets/markets/{market_id}/related",
    response_model=RelatedMarketListResponseModel,
)
def prediction_market_related(market_id: str, request: Request) -> RelatedMarketListResponseModel:
    runtime = request.app.state.runtime
    rows = runtime.prediction_market_service.get_related_markets(market_id)
    return RelatedMarketListResponseModel(
        market_id=market_id,
        related=[RelatedMarketModel.from_domain(row) for row in rows],
    )


@router.get(
    "/prediction-markets/markets/{market_id}/calibration",
    response_model=CalibrationSummaryResponseModel,
)
def prediction_market_calibration(market_id: str, request: Request) -> CalibrationSummaryResponseModel:
    runtime = request.app.state.runtime
    summary = runtime.prediction_market_service.get_calibration_summary(market_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Prediction market not found: {market_id}")
    return CalibrationSummaryResponseModel.from_domain(summary)
