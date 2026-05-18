from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.schemas.research import (
    ResearchAnalyzeRequestModel,
    ResearchAnalyzeResponseModel,
    ResearchCompareRequestModel,
    ResearchCompareResponseModel,
    ResearchOverviewResponseModel,
    SavedResearchCreateRequestModel,
    SavedResearchDeleteResponseModel,
    SavedResearchItemModel,
    SavedResearchListResponseModel,
    StrategyLabAnalyzeRequestModel,
    StrategyLabAnalyzeResponseModel,
    StrategyLabCompositionRequestModel,
    StrategyLabCompositionResponseModel,
)
from src.application.research_service import ResearchAnalysisRequest
from src.application.research_validation import ResearchValidationError
from src.models.research_overview import ResearchOverviewRequest


router = APIRouter(tags=["research"])


@router.get("/research/overview", response_model=ResearchOverviewResponseModel)
def research_overview(
    request: Request,
    universe_id: str = Query(default="broad_us_market"),
    timeframe: str = Query(default="DoD"),
    benchmark_symbol: str = Query(default="SPY"),
    surface: str = Query(default="research_overview"),
    force_refresh: bool = Query(default=False),
) -> ResearchOverviewResponseModel:
    runtime = request.app.state.runtime
    result = runtime.research_service.overview(
        ResearchOverviewRequest(
            universe_id=universe_id,
            timeframe=timeframe,
            benchmark_symbol=benchmark_symbol,
            provider_policy=surface,
            force_refresh=force_refresh,
        )
    )
    return ResearchOverviewResponseModel.from_domain(result)


@router.post("/research/analyze", response_model=ResearchAnalyzeResponseModel)
def analyze_research(
    payload: ResearchAnalyzeRequestModel,
    request: Request,
) -> ResearchAnalyzeResponseModel:
    runtime = request.app.state.runtime
    try:
        result = runtime.research_service.analyze(
            ResearchAnalysisRequest(
                scope_type=payload.scope_type,
                primary_symbol=payload.primary_symbol,
                synthetic_positions=[position.to_domain() for position in payload.synthetic_positions],
                benchmark_symbol=payload.benchmark_symbol,
                lookback_days=payload.lookback_days,
            )
        )
    except ResearchValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    return ResearchAnalyzeResponseModel.from_service_result(result)


@router.post("/research/strategy-lab/analyze", response_model=StrategyLabAnalyzeResponseModel)
def analyze_strategy_lab(
    payload: StrategyLabAnalyzeRequestModel,
    request: Request,
) -> StrategyLabAnalyzeResponseModel:
    runtime = request.app.state.runtime
    try:
        result = runtime.research_service.analyze_strategy_lab(payload.to_domain())
    except ResearchValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    return StrategyLabAnalyzeResponseModel.from_domain(result)


@router.post("/research/strategy-lab/compose", response_model=StrategyLabCompositionResponseModel)
def compose_strategy_lab(
    payload: StrategyLabCompositionRequestModel,
    request: Request,
) -> StrategyLabCompositionResponseModel:
    runtime = request.app.state.runtime
    try:
        result = runtime.research_service.compose_strategy_lab(payload.to_domain())
    except ResearchValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    return StrategyLabCompositionResponseModel.from_domain(result)


@router.post("/research/compare-scenario/analyze", response_model=ResearchCompareResponseModel)
def compare_research(
    payload: ResearchCompareRequestModel,
    request: Request,
) -> ResearchCompareResponseModel:
    runtime = request.app.state.runtime
    try:
        result = runtime.research_service.compare_research(payload.to_domain())
    except ResearchValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    return ResearchCompareResponseModel.from_domain(result)


@router.get("/research/saved", response_model=SavedResearchListResponseModel)
def list_saved_research(request: Request) -> SavedResearchListResponseModel:
    runtime = request.app.state.runtime
    return SavedResearchListResponseModel.from_domain(runtime.research_service.list_saved_research())


@router.post("/research/saved", response_model=SavedResearchItemModel)
def create_saved_research(
    payload: SavedResearchCreateRequestModel,
    request: Request,
) -> SavedResearchItemModel:
    runtime = request.app.state.runtime
    return SavedResearchItemModel.from_domain(runtime.research_service.save_research(payload.to_domain()))


@router.get("/research/saved/{item_id}", response_model=SavedResearchItemModel)
def get_saved_research(item_id: str, request: Request) -> SavedResearchItemModel:
    runtime = request.app.state.runtime
    item = runtime.research_service.load_saved_research(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Saved research item not found")
    return SavedResearchItemModel.from_domain(item)


@router.delete("/research/saved/{item_id}", response_model=SavedResearchDeleteResponseModel)
def delete_saved_research(item_id: str, request: Request) -> SavedResearchDeleteResponseModel:
    runtime = request.app.state.runtime
    return SavedResearchDeleteResponseModel(success=runtime.research_service.delete_saved_research(item_id))
