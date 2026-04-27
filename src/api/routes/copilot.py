from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.api.schemas.copilot import (
    CopilotMemoCreateRequestModel,
    CopilotMemoModel,
    CopilotResearchCardRequestModel,
    CopilotResearchCardResponseModel,
    CopilotSessionDetailModel,
    CopilotSessionModel,
    CopilotTurnModel,
)


router = APIRouter(tags=["copilot"])


@router.post("/copilot/research-card", response_model=CopilotResearchCardResponseModel)
def generate_research_card(
    payload: CopilotResearchCardRequestModel,
    request: Request,
) -> CopilotResearchCardResponseModel:
    runtime = request.app.state.runtime
    result = runtime.copilot_service.generate_research_card(payload.to_domain())
    return CopilotResearchCardResponseModel.from_domain(result)


@router.post("/copilot/research-card/stream")
def stream_research_card(
    payload: CopilotResearchCardRequestModel,
    request: Request,
) -> StreamingResponse:
    runtime = request.app.state.runtime
    result = runtime.copilot_service.generate_research_card(payload.to_domain())

    def iter_events():
        for event in runtime.copilot_service.stream_events_for_result(result):
            data = event["data"]
            if hasattr(data, "__dataclass_fields__"):
                data = CopilotResearchCardResponseModel.from_domain(data).model_dump(mode="json")
            yield json.dumps({"event": event["event"], "data": data}, default=str) + "\n"

    return StreamingResponse(iter_events(), media_type="application/x-ndjson")


@router.get("/copilot/sessions", response_model=list[CopilotSessionModel])
def list_copilot_sessions(request: Request) -> list[CopilotSessionModel]:
    runtime = request.app.state.runtime
    return [CopilotSessionModel.from_domain(item) for item in runtime.copilot_service.list_sessions()]


@router.get("/copilot/sessions/{session_id}", response_model=CopilotSessionDetailModel)
def get_copilot_session(session_id: str, request: Request) -> CopilotSessionDetailModel:
    runtime = request.app.state.runtime
    session = runtime.copilot_store.get_session(session_id)
    if session is None:
        return CopilotSessionDetailModel(
            session=CopilotSessionModel(
                session_id=session_id,
                title="Missing Copilot Session",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                warnings=[f"Copilot session not found: {session_id}"],
            ),
            turns=[],
            memos=[],
        )
    return CopilotSessionDetailModel(
        session=CopilotSessionModel.from_domain(session),
        turns=[CopilotTurnModel.from_domain(item) for item in runtime.copilot_service.list_turns(session_id)],
        memos=[CopilotMemoModel.from_domain(item) for item in runtime.copilot_service.list_memos(session_id)],
    )


@router.get("/copilot/memos", response_model=list[CopilotMemoModel])
def list_copilot_memos(request: Request, session_id: str | None = None) -> list[CopilotMemoModel]:
    runtime = request.app.state.runtime
    return [CopilotMemoModel.from_domain(item) for item in runtime.copilot_service.list_memos(session_id)]


@router.post("/copilot/memos", response_model=CopilotMemoModel)
def create_copilot_memo(
    payload: CopilotMemoCreateRequestModel,
    request: Request,
) -> CopilotMemoModel:
    runtime = request.app.state.runtime
    memo = runtime.copilot_service.create_memo(
        session_id=payload.session_id,
        title=payload.title,
        notes=payload.notes,
        source_turn_ids=payload.source_turn_ids,
    )
    return CopilotMemoModel.from_domain(memo)
