from __future__ import annotations

from fastapi import APIRouter, Request

from src.api.schemas.copilot import CopilotResearchCardRequestModel, CopilotResearchCardResponseModel


router = APIRouter(tags=["copilot"])


@router.post("/copilot/research-card", response_model=CopilotResearchCardResponseModel)
def generate_research_card(
    payload: CopilotResearchCardRequestModel,
    request: Request,
) -> CopilotResearchCardResponseModel:
    runtime = request.app.state.runtime
    result = runtime.copilot_service.generate_research_card(payload.to_domain())
    return CopilotResearchCardResponseModel.from_domain(result)
