from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from src.api.schemas.research import ResearchAnalyzeRequestModel, ResearchAnalyzeResponseModel
from src.application.research_service import ResearchAnalysisRequest
from src.application.research_validation import ResearchValidationError


router = APIRouter(tags=["research"])


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
