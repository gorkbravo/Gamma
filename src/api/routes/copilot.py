from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from src.api.schemas.copilot import (
    CopilotArtifactCreateRequestModel,
    CopilotArtifactDuplicateRequestModel,
    CopilotArtifactModel,
    CopilotArtifactUpdateRequestModel,
    CopilotContextSnapshotModel,
    CopilotDeleteResultModel,
    CopilotDraftMutationModel,
    CopilotDiagnosticsModel,
    CopilotFundamentalsDcfMutationRequestModel,
    CopilotMemoCreateRequestModel,
    CopilotMemoModel,
    CopilotMemoUpdateRequestModel,
    CopilotMutationApplyRequestModel,
    CopilotMutationApplyResultModel,
    CopilotMutationRejectRequestModel,
    CopilotOperatorPlanModel,
    CopilotResearchCardRequestModel,
    CopilotResearchCardResponseModel,
    CopilotResearchActionDefinitionModel,
    CopilotRunCancelResponseModel,
    CopilotRunEventModel,
    CopilotResearchPlanModel,
    CopilotResearchReportModel,
    CopilotResearchReportRequestModel,
    CopilotSessionCreateRequestModel,
    CopilotSessionDetailModel,
    CopilotSessionModel,
    CopilotSessionUpdateRequestModel,
    CopilotShelfPromotionModel,
    CopilotShelfPromotionRequestModel,
    CopilotStorageStatusModel,
    CopilotStorageWarningModel,
    CopilotTurnModel,
    CopilotWorkingAnalysisModel,
)
from src.services.copilot_store import CopilotStoreConflictError, CopilotStoreNotFoundError


router = APIRouter(tags=["copilot"])


def _raise_store_error(exc: ValueError) -> None:
    if isinstance(exc, CopilotStoreNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, CopilotStoreConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _markdown_download_headers(title: str, artifact_id: str) -> dict[str, str]:
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", title.strip()).strip("-._")[:80]
    safe_stem = safe_stem or artifact_id
    return {"Content-Disposition": f'attachment; filename="{safe_stem}.md"'}


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
    result = runtime.copilot_service.execute_research_operator_plan(
        payload.to_domain(),
        run_id=payload.run_id,
    )
    return CopilotResearchCardResponseModel.from_domain(result)


@router.post("/copilot/operator-plan/execute/stream")
def stream_research_operator_plan(
    payload: CopilotResearchCardRequestModel,
    request: Request,
) -> StreamingResponse:
    """Stream Agent and Operator work through the same Gamma run envelope."""
    runtime = request.app.state.runtime
    try:
        events = runtime.copilot_service.stream_research_operator_events(
            payload.to_domain(),
            run_id=payload.run_id,
            after_sequence=payload.last_seen_sequence if payload.last_seen_sequence is not None else -1,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    def iter_events():
        for event in events:
            yield CopilotRunEventModel.from_domain(event).model_dump_json() + "\n"

    return StreamingResponse(iter_events(), media_type="application/x-ndjson")


@router.get("/copilot/actions", response_model=list[CopilotResearchActionDefinitionModel])
def list_copilot_actions(request: Request) -> list[CopilotResearchActionDefinitionModel]:
    runtime = request.app.state.runtime
    return [
        CopilotResearchActionDefinitionModel.from_domain(item)
        for item in runtime.copilot_service.list_research_action_definitions()
    ]


@router.get("/copilot/diagnostics", response_model=CopilotDiagnosticsModel)
def get_copilot_diagnostics(request: Request) -> CopilotDiagnosticsModel:
    diagnostics = request.app.state.runtime.copilot_service.diagnostics()
    return CopilotDiagnosticsModel.from_domain(diagnostics)


@router.post("/copilot/shelf/promote", response_model=CopilotShelfPromotionModel)
def promote_copilot_shelf(
    payload: CopilotShelfPromotionRequestModel,
    request: Request,
) -> CopilotShelfPromotionModel:
    promotion = request.app.state.runtime.copilot_service.promote_shelf(
        payload.to_domain()
    )
    return CopilotShelfPromotionModel.from_domain(promotion)


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

    try:
        events = runtime.copilot_service.stream_research_card_events(
            payload.to_domain(),
            run_id=payload.run_id,
            after_sequence=payload.last_seen_sequence if payload.last_seen_sequence is not None else -1,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    def iter_events():
        for event in events:
            yield CopilotRunEventModel.from_domain(event).model_dump_json() + "\n"

    return StreamingResponse(iter_events(), media_type="application/x-ndjson")


@router.get("/copilot/runs/{run_id}/events")
def replay_copilot_run_events(
    run_id: str,
    request: Request,
    after_sequence: int = -1,
) -> StreamingResponse:
    """Resume an active or recently completed run from a monotonic cursor."""
    runtime = request.app.state.runtime
    try:
        events = runtime.copilot_service.stream_existing_run_events(
            run_id,
            after_sequence=max(-1, after_sequence),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    def iter_events():
        for event in events:
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
            session_id=payload.user_session_id,
            workflow_id=payload.workflow_id,
            run_id=payload.run_id,
            checkpoint_id=payload.checkpoint_id,
            context_fingerprint=payload.context_fingerprint,
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
            session_id=payload.user_session_id,
            context_fingerprint=payload.context_fingerprint,
            proposal_hash=payload.proposal_hash,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CopilotMutationApplyResultModel.from_domain(result)


@router.get("/copilot/mutations/{mutation_id}", response_model=CopilotDraftMutationModel)
def get_copilot_mutation(
    mutation_id: str,
    request: Request,
) -> CopilotDraftMutationModel:
    mutation = request.app.state.runtime.copilot_service.get_copilot_mutation(mutation_id)
    if mutation is None:
        raise HTTPException(status_code=404, detail=f"Copilot mutation not found: {mutation_id}")
    return CopilotDraftMutationModel.from_domain(mutation)


@router.post("/copilot/mutations/{mutation_id}/reject", response_model=CopilotDraftMutationModel)
def reject_copilot_mutation(
    mutation_id: str,
    payload: CopilotMutationRejectRequestModel,
    request: Request,
) -> CopilotDraftMutationModel:
    try:
        mutation = request.app.state.runtime.copilot_service.reject_copilot_mutation(
            mutation_id=mutation_id,
            session_id=payload.user_session_id,
        )
    except ValueError as exc:
        _raise_store_error(exc)
    return CopilotDraftMutationModel.from_domain(mutation)


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


@router.post("/copilot/sessions", response_model=CopilotSessionModel)
def create_copilot_session(
    payload: CopilotSessionCreateRequestModel,
    request: Request,
) -> CopilotSessionModel:
    """Create the authoritative empty session that `New chat` selects."""
    try:
        session = request.app.state.runtime.copilot_service.create_session(
            title=payload.title,
            session_id=payload.session_id,
        )
    except ValueError as exc:
        _raise_store_error(exc)
    return CopilotSessionModel.from_domain(session)


@router.get("/copilot/sessions/{session_id}", response_model=CopilotSessionDetailModel)
def get_copilot_session(session_id: str, request: Request) -> CopilotSessionDetailModel:
    runtime = request.app.state.runtime
    session = runtime.copilot_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Copilot session not found: {session_id}")
    storage_status = runtime.copilot_service.storage_status()
    return CopilotSessionDetailModel(
        session=CopilotSessionModel.from_domain(session),
        turns=[CopilotTurnModel.from_domain(item) for item in runtime.copilot_service.list_turns(session_id)],
        memos=[CopilotMemoModel.from_domain(item) for item in runtime.copilot_service.list_memos(session_id)],
        context_snapshots=[
            CopilotContextSnapshotModel.from_domain(item)
            for item in runtime.copilot_service.list_context_snapshots(session_id)
        ],
        artifacts=[
            CopilotArtifactModel.from_domain(item)
            for item in runtime.copilot_service.list_artifacts(session_id)
        ],
        mutations=[
            CopilotDraftMutationModel.from_domain(item)
            for item in runtime.copilot_service.list_copilot_mutations(session_id)
        ],
        working_analyses=[
            CopilotWorkingAnalysisModel.from_domain(item)
            for item in runtime.copilot_service.list_working_analyses(session_id)
        ],
        storage_warnings=[
            CopilotStorageWarningModel.from_domain(item)
            for item in storage_status.warnings
        ],
    )


@router.get("/copilot/storage-status", response_model=CopilotStorageStatusModel)
def get_copilot_storage_status(request: Request) -> CopilotStorageStatusModel:
    return CopilotStorageStatusModel.from_domain(request.app.state.runtime.copilot_service.storage_status())


@router.patch("/copilot/sessions/{session_id}", response_model=CopilotSessionModel)
def rename_copilot_session(
    session_id: str,
    payload: CopilotSessionUpdateRequestModel,
    request: Request,
) -> CopilotSessionModel:
    try:
        session = request.app.state.runtime.copilot_service.rename_session(
            session_id,
            title=payload.title,
            expected_updated_at=payload.expected_updated_at,
        )
    except ValueError as exc:
        _raise_store_error(exc)
    return CopilotSessionModel.from_domain(session)


@router.post("/copilot/sessions/{session_id}/restore", response_model=CopilotSessionModel)
def restore_copilot_session(session_id: str, request: Request) -> CopilotSessionModel:
    try:
        session = request.app.state.runtime.copilot_service.restore_session(session_id)
    except ValueError as exc:
        _raise_store_error(exc)
    return CopilotSessionModel.from_domain(session)


@router.delete("/copilot/sessions/{session_id}", response_model=CopilotDeleteResultModel)
def delete_copilot_session(
    session_id: str,
    request: Request,
    confirm_session_id: str,
) -> CopilotDeleteResultModel:
    try:
        result = request.app.state.runtime.copilot_service.delete_session(
            session_id,
            confirmation=confirm_session_id,
        )
    except ValueError as exc:
        _raise_store_error(exc)
    return CopilotDeleteResultModel.from_domain(result)


@router.get("/copilot/memos", response_model=list[CopilotMemoModel])
def list_copilot_memos(request: Request, session_id: str | None = None) -> list[CopilotMemoModel]:
    runtime = request.app.state.runtime
    return [CopilotMemoModel.from_domain(item) for item in runtime.copilot_service.list_memos(session_id)]


@router.get("/copilot/sessions/{session_id}/artifacts", response_model=list[CopilotArtifactModel])
def list_copilot_artifacts(session_id: str, request: Request) -> list[CopilotArtifactModel]:
    runtime = request.app.state.runtime
    if runtime.copilot_store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail=f"Copilot session not found: {session_id}")
    return [
        CopilotArtifactModel.from_domain(item)
        for item in runtime.copilot_service.list_artifacts(session_id)
    ]


@router.get(
    "/copilot/sessions/{session_id}/working-analyses",
    response_model=list[CopilotWorkingAnalysisModel],
)
def list_copilot_working_analyses(
    session_id: str,
    request: Request,
    include_inactive: bool = True,
) -> list[CopilotWorkingAnalysisModel]:
    runtime = request.app.state.runtime
    if runtime.copilot_store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail=f"Copilot session not found: {session_id}")
    return [
        CopilotWorkingAnalysisModel.from_domain(item)
        for item in runtime.copilot_service.list_working_analyses(
            session_id,
            include_inactive=include_inactive,
        )
    ]


@router.get(
    "/copilot/working-analyses/{analysis_id}",
    response_model=CopilotWorkingAnalysisModel,
)
def get_copilot_working_analysis(
    analysis_id: str,
    request: Request,
) -> CopilotWorkingAnalysisModel:
    analysis = request.app.state.runtime.copilot_service.get_working_analysis(analysis_id)
    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail=f"Copilot working analysis not found: {analysis_id}",
        )
    return CopilotWorkingAnalysisModel.from_domain(analysis)


@router.post(
    "/copilot/working-analyses/{analysis_id}/materialize",
    response_model=CopilotWorkingAnalysisModel,
)
def materialize_copilot_working_analysis(
    analysis_id: str,
    request: Request,
) -> CopilotWorkingAnalysisModel:
    try:
        analysis = request.app.state.runtime.copilot_service.materialize_working_analysis(
            analysis_id
        )
    except ValueError as exc:
        _raise_store_error(exc)
    return CopilotWorkingAnalysisModel.from_domain(analysis)


@router.post(
    "/copilot/working-analyses/{analysis_id}/discard",
    response_model=CopilotWorkingAnalysisModel,
)
def discard_copilot_working_analysis(
    analysis_id: str,
    request: Request,
) -> CopilotWorkingAnalysisModel:
    try:
        analysis = request.app.state.runtime.copilot_service.discard_working_analysis(
            analysis_id
        )
    except ValueError as exc:
        _raise_store_error(exc)
    return CopilotWorkingAnalysisModel.from_domain(analysis)


@router.post("/copilot/sessions/{session_id}/artifacts", response_model=CopilotArtifactModel)
def create_copilot_artifact(
    session_id: str,
    payload: CopilotArtifactCreateRequestModel,
    request: Request,
) -> CopilotArtifactModel:
    try:
        artifact = request.app.state.runtime.copilot_service.create_artifact(
            session_id=session_id,
            artifact_type=payload.artifact_type,
            template=payload.template,
            title=payload.title,
            body=payload.body,
            source_turn_ids=payload.source_turn_ids,
            source_memo_ids=payload.source_memo_ids,
        )
    except ValueError as exc:
        _raise_store_error(exc)
    return CopilotArtifactModel.from_domain(artifact)


@router.patch("/copilot/artifacts/{artifact_id}", response_model=CopilotArtifactModel)
def update_copilot_artifact(
    artifact_id: str,
    payload: CopilotArtifactUpdateRequestModel,
    request: Request,
) -> CopilotArtifactModel:
    try:
        artifact = request.app.state.runtime.copilot_service.update_artifact(
            artifact_id,
            title=payload.title,
            body=payload.body,
            expected_updated_at=payload.expected_updated_at,
        )
    except ValueError as exc:
        _raise_store_error(exc)
    return CopilotArtifactModel.from_domain(artifact)


@router.post("/copilot/artifacts/{artifact_id}/duplicate", response_model=CopilotArtifactModel)
def duplicate_copilot_artifact(
    artifact_id: str,
    payload: CopilotArtifactDuplicateRequestModel,
    request: Request,
) -> CopilotArtifactModel:
    try:
        artifact = request.app.state.runtime.copilot_service.duplicate_artifact(
            artifact_id,
            title=payload.title,
        )
    except ValueError as exc:
        _raise_store_error(exc)
    return CopilotArtifactModel.from_domain(artifact)


@router.delete("/copilot/artifacts/{artifact_id}", response_model=CopilotDeleteResultModel)
def delete_copilot_artifact(
    artifact_id: str,
    request: Request,
    confirm_artifact_id: str,
) -> CopilotDeleteResultModel:
    try:
        result = request.app.state.runtime.copilot_service.delete_artifact(
            artifact_id,
            confirmation=confirm_artifact_id,
        )
    except ValueError as exc:
        _raise_store_error(exc)
    return CopilotDeleteResultModel.from_domain(result)


@router.get("/copilot/artifacts/{artifact_id}/export")
def export_copilot_artifact(artifact_id: str, request: Request) -> Response:
    runtime = request.app.state.runtime
    artifact = runtime.copilot_store.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Copilot artifact not found: {artifact_id}")
    markdown = runtime.copilot_service.export_artifact_markdown(artifact_id)
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers=_markdown_download_headers(artifact.title, artifact.artifact_id),
    )


@router.post("/copilot/memos", response_model=CopilotMemoModel)
def create_copilot_memo(
    payload: CopilotMemoCreateRequestModel,
    request: Request,
) -> CopilotMemoModel:
    runtime = request.app.state.runtime
    try:
        memo = runtime.copilot_service.create_memo(
            session_id=payload.session_id,
            title=payload.title,
            notes=payload.notes,
            source_turn_ids=payload.source_turn_ids,
        )
    except ValueError as exc:
        _raise_store_error(exc)
    return CopilotMemoModel.from_domain(memo)


@router.post("/copilot/sessions/{session_id}/archive", response_model=CopilotSessionModel)
def archive_copilot_session(session_id: str, request: Request) -> CopilotSessionModel:
    runtime = request.app.state.runtime
    try:
        session = runtime.copilot_service.archive_session(session_id)
    except ValueError as exc:
        _raise_store_error(exc)
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
        _raise_store_error(exc)
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
    session = runtime.copilot_store.get_session(session_id)
    export_title = payload.title or (f"{session.title} Research Report" if session else "copilot-report")
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers=_markdown_download_headers(export_title, session_id),
    )


@router.get("/copilot/memos/{memo_id}/export")
def export_copilot_memo(memo_id: str, request: Request) -> Response:
    runtime = request.app.state.runtime
    memo = runtime.copilot_store.get_memo(memo_id)
    if memo is None:
        raise HTTPException(status_code=404, detail=f"Copilot memo not found: {memo_id}")
    try:
        markdown = runtime.copilot_service.export_memo_markdown(memo_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers=_markdown_download_headers(memo.title, memo.memo_id),
    )
