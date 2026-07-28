from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.schemas.prediction_markets import (
    CalibrationSummaryResponseModel,
    PredictionComparisonRequestModel,
    PredictionComparisonSetRequestModel,
    PredictionCrossDomainHandoffListResponseModel,
    PredictionEventBookResponseModel,
    PredictionMarketComparisonResponseModel,
    PredictionMarketListResponseModel,
    PredictionMarketModel,
    PredictionMarketScreenerRequestModel,
    PredictionOrderBookDepthResponseModel,
    PredictionOutcomeSeriesModel,
    PredictionOutcomeSeriesResponseModel,
    PredictionProbabilityHistoryResponseModel,
    PredictionResearchImportRequestModel,
    PredictionSavedResearchResponseModel,
    PredictionWatchlistRequestModel,
    RelatedMarketListResponseModel,
    RelatedMarketModel,
    WalletSummaryResponseModel,
)
from src.application.prediction_market_service import (
    CALIBRATION_DEFAULT_SAMPLE_MARKETS,
    CALIBRATION_MAX_SAMPLE_MARKETS,
    CALIBRATION_SUPPORTED_LEAD_TIMES_HOURS,
    HISTORY_RANGE_KEYS,
    MAX_EVENT_BOOK_LEGS,
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


@router.get("/prediction-markets/saved", response_model=PredictionSavedResearchResponseModel)
def prediction_market_saved_research(request: Request) -> PredictionSavedResearchResponseModel:
    runtime = request.app.state.runtime
    return PredictionSavedResearchResponseModel.from_domain(
        runtime.prediction_market_service.get_saved_research()
    )


@router.post("/prediction-markets/saved/watchlist", response_model=PredictionSavedResearchResponseModel)
def prediction_market_add_watchlist_entry(
    payload: PredictionWatchlistRequestModel,
    request: Request,
) -> PredictionSavedResearchResponseModel:
    runtime = request.app.state.runtime
    try:
        saved = runtime.prediction_market_service.add_watchlist_entry(
            market_id=payload.market_id,
            venue=payload.venue,
            title=payload.title,
            probability=payload.probability,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PredictionSavedResearchResponseModel.from_domain(saved)


@router.delete(
    "/prediction-markets/saved/watchlist/{market_id}",
    response_model=PredictionSavedResearchResponseModel,
)
def prediction_market_remove_watchlist_entry(
    market_id: str,
    request: Request,
) -> PredictionSavedResearchResponseModel:
    runtime = request.app.state.runtime
    saved = runtime.prediction_market_service.remove_watchlist_entry(market_id)
    if saved is None:
        raise HTTPException(status_code=404, detail=f"Watchlist entry not found: {market_id}")
    return PredictionSavedResearchResponseModel.from_domain(saved)


@router.post("/prediction-markets/saved/comparison-sets", response_model=PredictionSavedResearchResponseModel)
def prediction_market_save_comparison_set(
    payload: PredictionComparisonSetRequestModel,
    request: Request,
) -> PredictionSavedResearchResponseModel:
    runtime = request.app.state.runtime
    try:
        saved = runtime.prediction_market_service.save_comparison_set(
            name=payload.name,
            market_ids=list(payload.market_ids),
            set_id=payload.set_id,
            range_key=payload.range_key,
            resolution_minutes=payload.resolution_minutes,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PredictionSavedResearchResponseModel.from_domain(saved)


@router.delete(
    "/prediction-markets/saved/comparison-sets/{set_id}",
    response_model=PredictionSavedResearchResponseModel,
)
def prediction_market_delete_comparison_set(
    set_id: str,
    request: Request,
) -> PredictionSavedResearchResponseModel:
    runtime = request.app.state.runtime
    saved = runtime.prediction_market_service.delete_comparison_set(set_id)
    if saved is None:
        raise HTTPException(status_code=404, detail=f"Comparison set not found: {set_id}")
    return PredictionSavedResearchResponseModel.from_domain(saved)


@router.post("/prediction-markets/saved/import", response_model=PredictionSavedResearchResponseModel)
def prediction_market_import_saved_research(
    payload: PredictionResearchImportRequestModel,
    request: Request,
) -> PredictionSavedResearchResponseModel:
    runtime = request.app.state.runtime
    saved = runtime.prediction_market_service.import_legacy_research(
        watchlist=[row.model_dump() for row in payload.watchlist],
        comparison_basket=list(payload.comparison_basket),
        basket_name=payload.basket_name,
    )
    return PredictionSavedResearchResponseModel.from_domain(saved)


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
    "/prediction-markets/markets/{market_id}/handoffs",
    response_model=PredictionCrossDomainHandoffListResponseModel,
)
def prediction_market_cross_domain_handoffs(
    market_id: str,
    request: Request,
) -> PredictionCrossDomainHandoffListResponseModel:
    runtime = request.app.state.runtime
    handoffs = runtime.prediction_market_service.get_cross_domain_handoffs(market_id)
    if handoffs is None:
        raise HTTPException(status_code=404, detail=f"Prediction market not found: {market_id}")
    return PredictionCrossDomainHandoffListResponseModel(
        market_id=market_id,
        handoffs=[envelope.to_dict() for envelope in handoffs],
    )


@router.get(
    "/prediction-markets/markets/{market_id}/depth",
    response_model=PredictionOrderBookDepthResponseModel,
)
def prediction_market_depth(
    market_id: str,
    request: Request,
    outcome_id: str | None = Query(default=None, max_length=256),
) -> PredictionOrderBookDepthResponseModel:
    """Read-only resting depth behind a contract's quote. No order entry."""
    runtime = request.app.state.runtime
    depth = runtime.prediction_market_service.get_order_book_depth(market_id, outcome_id=outcome_id)
    if depth is None:
        raise HTTPException(status_code=404, detail=f"Prediction market not found: {market_id}")
    return PredictionOrderBookDepthResponseModel.from_domain(depth)


@router.get(
    "/prediction-markets/markets/{market_id}/event-book",
    response_model=PredictionEventBookResponseModel,
)
def prediction_market_event_book(
    market_id: str,
    request: Request,
    limit: int = Query(default=MAX_EVENT_BOOK_LEGS, ge=2, le=MAX_EVENT_BOOK_LEGS),
) -> PredictionEventBookResponseModel:
    runtime = request.app.state.runtime
    book = runtime.prediction_market_service.get_event_book(market_id, limit=limit)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Prediction market not found: {market_id}")
    return PredictionEventBookResponseModel.from_domain(book)


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
def prediction_market_calibration(
    market_id: str,
    request: Request,
    sample_size: int = Query(
        default=CALIBRATION_DEFAULT_SAMPLE_MARKETS,
        ge=1,
        le=CALIBRATION_MAX_SAMPLE_MARKETS,
        alias="sample",
    ),
    lead_times: list[int] | None = Query(default=None, alias="lead"),
) -> CalibrationSummaryResponseModel:
    for lead in lead_times or []:
        if lead not in CALIBRATION_SUPPORTED_LEAD_TIMES_HOURS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Unsupported calibration lead time '{lead}'. Supported hours: "
                    f"{', '.join(str(value) for value in CALIBRATION_SUPPORTED_LEAD_TIMES_HOURS)}."
                ),
            )
    runtime = request.app.state.runtime
    summary = runtime.prediction_market_service.get_calibration_summary(
        market_id,
        sample_size=sample_size,
        lead_times_hours=lead_times,
    )
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Prediction market not found: {market_id}")
    return CalibrationSummaryResponseModel.from_domain(summary)
