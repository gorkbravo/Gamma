from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from src.api.schemas.copilot import (
    CopilotDraftMutationModel,
    CopilotFundamentalsDcfMutationRequestModel,
    CopilotMemoCreateRequestModel,
    CopilotMemoModel,
    CopilotMemoUpdateRequestModel,
    CopilotMutationApplyRequestModel,
    CopilotMutationApplyResultModel,
    CopilotOperatorPlanModel,
    CopilotResearchCardRequestModel,
    CopilotResearchCardResponseModel,
    CopilotResearchActionDefinitionModel,
    CopilotRunCancelResponseModel,
    CopilotRunEventModel,
    CopilotResearchPlanModel,
    CopilotResearchReportModel,
    CopilotResearchReportRequestModel,
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


@router.post("/copilot/operator-plan", response_model=CopilotOperatorPlanModel)
def plan_research_operator(
    payload: CopilotResearchCardRequestModel,
    request: Request,
) -> CopilotOperatorPlanModel:
    runtime = request.app.state.runtime
    plan = runtime.copilot_service.plan_research_operator(payload.to_domain())
    return CopilotOperatorPlanModel.from_domain(plan)


@router.post("/copilot/operator-plan/execute", response_model=CopilotResearchCardResponseModel)
def execute_research_operator_plan(
    payload: CopilotResearchCardRequestModel,
    request: Request,
) -> CopilotResearchCardResponseModel:
    runtime = request.app.state.runtime
    result = runtime.copilot_service.execute_research_operator_plan(payload.to_domain())
    return CopilotResearchCardResponseModel.from_domain(result)


@router.get("/copilot/actions", response_model=list[CopilotResearchActionDefinitionModel])
def list_copilot_actions(request: Request) -> list[CopilotResearchActionDefinitionModel]:
    runtime = request.app.state.runtime
    return [
        CopilotResearchActionDefinitionModel.from_domain(item)
        for item in runtime.copilot_service.list_research_action_definitions()
    ]


@router.post("/copilot/research-plan/execute", response_model=CopilotResearchCardResponseModel)
def execute_research_plan(
    payload: CopilotResearchCardRequestModel,
    request: Request,
) -> CopilotResearchCardResponseModel:
    runtime = request.app.state.runtime
    result = runtime.copilot_service.execute_research_plan(payload.to_domain())
    return CopilotResearchCardResponseModel.from_domain(result)


@router.post("/copilot/research-card/stream")
def stream_research_card(
    payload: CopilotResearchCardRequestModel,
    request: Request,
) -> StreamingResponse:
    """Stream one research-card run as NDJSON Gamma run events.

    Events arrive as they happen (`run.created`, `text.delta`, `tool.call`,
    `tool.result`, `warning`, `refusal`, `incomplete`, `usage`) and exactly one
    terminal event (`completed`, `failed`, or `cancelled`) carries the final
    persisted result.
    """
    runtime = request.app.state.runtime

    def iter_events():
        for event in runtime.copilot_service.stream_research_card_events(
            payload.to_domain(),
            run_id=payload.run_id,
        ):
            yield CopilotRunEventModel.from_domain(event).model_dump_json() + "\n"

    return StreamingResponse(iter_events(), media_type="application/x-ndjson")


@router.post("/copilot/runs/{run_id}/cancel", response_model=CopilotRunCancelResponseModel)
def cancel_copilot_run(run_id: str, request: Request) -> CopilotRunCancelResponseModel:
    runtime = request.app.state.runtime
    outcome = runtime.copilot_service.cancel_run(run_id)
    return CopilotRunCancelResponseModel(**outcome)


@router.post("/copilot/mutations/fundamentals/dcf/propose", response_model=CopilotDraftMutationModel)
def propose_fundamentals_dcf_mutation(
    payload: CopilotFundamentalsDcfMutationRequestModel,
    request: Request,
) -> CopilotDraftMutationModel:
    runtime = request.app.state.runtime
    try:
        mutation = runtime.copilot_service.propose_fundamentals_dcf_update(
            ticker=payload.ticker,
            scenario_id=payload.scenario_id,
            active_scenario_id=payload.active_scenario_id,
            assumptions=payload.assumptions,
            overrides=payload.overrides,
            rationale=payload.rationale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CopilotDraftMutationModel.from_domain(mutation)


@router.post("/copilot/mutations/{mutation_id}/apply", response_model=CopilotMutationApplyResultModel)
def apply_copilot_mutation(
    mutation_id: str,
    payload: CopilotMutationApplyRequestModel,
    request: Request,
) -> CopilotMutationApplyResultModel:
    runtime = request.app.state.runtime
    try:
        result = runtime.copilot_service.apply_fundamentals_dcf_update(
            mutation_id=mutation_id,
            confirmation_token=payload.confirmation_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CopilotMutationApplyResultModel.from_domain(result)


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


@router.post("/copilot/sessions/{session_id}/report", response_model=CopilotResearchReportModel)
def generate_copilot_research_report(
    session_id: str,
    payload: CopilotResearchReportRequestModel,
    request: Request,
) -> CopilotResearchReportModel:
    runtime = request.app.state.runtime
    try:
        report = runtime.copilot_service.generate_research_report(
            session_id=session_id,
            title=payload.title,
            notes=payload.notes,
            source_turn_ids=payload.source_turn_ids,
            source_memo_ids=payload.source_memo_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CopilotResearchReportModel.from_domain(report)


@router.post("/copilot/sessions/{session_id}/report/export")
def export_copilot_research_report(
    session_id: str,
    payload: CopilotResearchReportRequestModel,
    request: Request,
) -> Response:
    runtime = request.app.state.runtime
    try:
        markdown = runtime.copilot_service.export_research_report_markdown(
            session_id=session_id,
            title=payload.title,
            notes=payload.notes,
            source_turn_ids=payload.source_turn_ids,
            source_memo_ids=payload.source_memo_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=markdown, media_type="text/markdown; charset=utf-8")


@router.get("/copilot/memos/{memo_id}/export")
def export_copilot_memo(memo_id: str, request: Request) -> Response:
    runtime = request.app.state.runtime
    try:
        markdown = runtime.copilot_service.export_memo_markdown(memo_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=markdown, media_type="text/markdown; charset=utf-8")
