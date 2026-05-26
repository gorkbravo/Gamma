from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from src.api.schemas.copilot import (
    CopilotMemoCreateRequestModel,
    CopilotMemoModel,
    CopilotMemoUpdateRequestModel,
    CopilotResearchCardRequestModel,
    CopilotResearchCardResponseModel,
    CopilotResearchPlanModel,
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


@router.post("/copilot/research-plan", response_model=CopilotResearchPlanModel)
def plan_research(
    payload: CopilotResearchCardRequestModel,
    request: Request,
) -> CopilotResearchPlanModel:
    runtime = request.app.state.runtime
    plan = runtime.copilot_service.plan_research(payload.to_domain())
    return CopilotResearchPlanModel.from_domain(plan)


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
def list_copilot_sessions(
    request: Request,
    include_archived: bool = False,
    search: str | None = None,
) -> list[CopilotSessionModel]:
    runtime = request.app.state.runtime
    return [
        CopilotSessionModel.from_domain(item)
        for item in runtime.copilot_service.list_sessions(include_archived=include_archived, search=search)
    ]


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


@router.post("/copilot/sessions/{session_id}/archive", response_model=CopilotSessionModel)
def archive_copilot_session(session_id: str, request: Request) -> CopilotSessionModel:
    runtime = request.app.state.runtime
    try:
        session = runtime.copilot_service.archive_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CopilotSessionModel.from_domain(session)


@router.patch("/copilot/memos/{memo_id}", response_model=CopilotMemoModel)
def update_copilot_memo(
    memo_id: str,
    payload: CopilotMemoUpdateRequestModel,
    request: Request,
) -> CopilotMemoModel:
    runtime = request.app.state.runtime
    try:
        memo = runtime.copilot_service.update_memo(memo_id, title=payload.title, body=payload.body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CopilotMemoModel.from_domain(memo)


@router.get("/copilot/memos/{memo_id}/export")
def export_copilot_memo(memo_id: str, request: Request) -> Response:
    runtime = request.app.state.runtime
    try:
        markdown = runtime.copilot_service.export_memo_markdown(memo_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=markdown, media_type="text/markdown; charset=utf-8")
