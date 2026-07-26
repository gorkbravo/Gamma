from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.schemas.prediction_markets import (
    CalibrationSummaryResponseModel,
    PredictionComparisonRequestModel,
    PredictionMarketComparisonResponseModel,
    PredictionMarketListResponseModel,
    PredictionMarketModel,
    PredictionMarketScreenerRequestModel,
    PredictionOutcomeSeriesModel,
    PredictionOutcomeSeriesResponseModel,
    PredictionProbabilityHistoryResponseModel,
    RelatedMarketListResponseModel,
    RelatedMarketModel,
    WalletSummaryResponseModel,
)
from src.application.prediction_market_service import HISTORY_RANGE_KEYS


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
def prediction_market_history(
    market_id: str,
    request: Request,
    range_key: str = Query(default="max", alias="range"),
    resolution_minutes: int | None = Query(default=None, ge=1, le=1440, alias="resolution"),
    outcome_id: str | None = Query(default=None, max_length=256),
) -> PredictionProbabilityHistoryResponseModel:
    if range_key not in HISTORY_RANGE_KEYS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported range '{range_key}'. Supported: {', '.join(HISTORY_RANGE_KEYS)}.",
        )
    runtime = request.app.state.runtime
    history = runtime.prediction_market_service.get_history_series(
        market_id,
        range_key=range_key,
        resolution_minutes=resolution_minutes,
        outcome_id=outcome_id,
    )
    if history is None:
        raise HTTPException(status_code=404, detail=f"Prediction market not found: {market_id}")
    return PredictionProbabilityHistoryResponseModel.from_domain(history)


@router.get(
    "/prediction-markets/markets/{market_id}/outcome-history",
    response_model=PredictionOutcomeSeriesResponseModel,
)
def prediction_market_outcome_history(
    market_id: str,
    request: Request,
    range_key: str = Query(default="max", alias="range"),
    resolution_minutes: int | None = Query(default=None, ge=1, le=1440, alias="resolution"),
) -> PredictionOutcomeSeriesResponseModel:
    if range_key not in HISTORY_RANGE_KEYS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported range '{range_key}'. Supported: {', '.join(HISTORY_RANGE_KEYS)}.",
        )
    runtime = request.app.state.runtime
    series = runtime.prediction_market_service.get_outcome_series(
        market_id,
        range_key=range_key,
        resolution_minutes=resolution_minutes,
    )
    return PredictionOutcomeSeriesResponseModel(
        market_id=market_id,
        requested_range=range_key,
        series=[PredictionOutcomeSeriesModel.from_domain(item) for item in series],
    )


@router.post("/prediction-markets/compare", response_model=PredictionMarketComparisonResponseModel)
def prediction_market_compare(
    payload: PredictionComparisonRequestModel,
    request: Request,
) -> PredictionMarketComparisonResponseModel:
    if payload.range_key not in HISTORY_RANGE_KEYS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported range '{payload.range_key}'. Supported: {', '.join(HISTORY_RANGE_KEYS)}.",
        )
    runtime = request.app.state.runtime
    result = runtime.prediction_market_service.compare_markets(
        list(payload.market_ids),
        range_key=payload.range_key,
        resolution_minutes=payload.resolution_minutes,
    )
    return PredictionMarketComparisonResponseModel.from_domain(result)


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
