from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response

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
    StrategyLabBookValidationResponseModel,
    StrategyLabCompositionRequestModel,
    StrategyLabCompositionResponseModel,
    StrategyLabHandoffResolveRequestModel,
    StrategyLabResolvedHandoffModel,
    StrategyLabPortfolioCompositionRequestModel,
)
from src.api.schemas.research_script import (
    ResearchScriptCreateRequestModel,
    ResearchScriptDataExportRequestModel,
    ResearchScriptDetailModel,
    ResearchScriptDuplicateRequestModel,
    ResearchScriptInputSnapshotModel,
    ResearchScriptListResponseModel,
    ResearchScriptRevisionCreateRequestModel,
    ResearchScriptRevisionDecisionRequestModel,
    ResearchScriptRunCreateRequestModel,
    ResearchScriptRunComparisonModel,
    ResearchScriptRunListResponseModel,
    ResearchScriptRunModel,
    ResearchScriptRuntimeCapabilitiesModel,
    ResearchScriptStorageDiagnosticsModel,
)
from src.application.research_script_service import (
    ResearchScriptConflictError,
    ResearchScriptNotFoundError,
    ResearchScriptValidationError,
)
from src.application.research_service import ResearchAnalysisRequest
from src.application.research_validation import ResearchValidationError
from src.models.research_overview import ResearchOverviewRequest


router = APIRouter(tags=["research"])


def _raise_script_http_error(exc: Exception) -> None:
    if isinstance(exc, ResearchScriptNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ResearchScriptConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ResearchScriptValidationError):
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    raise exc


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


@router.post("/research/strategy-lab/portfolio-compose", response_model=StrategyLabCompositionResponseModel)
def compose_strategy_lab_portfolio(
    payload: StrategyLabPortfolioCompositionRequestModel,
    request: Request,
) -> StrategyLabCompositionResponseModel:
    runtime = request.app.state.runtime
    try:
        result = runtime.research_service.compose_strategy_lab_portfolio(payload.to_domain())
    except ResearchValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    return StrategyLabCompositionResponseModel.from_domain(result)


@router.post("/research/strategy-lab/portfolio-validate", response_model=StrategyLabBookValidationResponseModel)
def validate_strategy_lab_portfolio(
    payload: StrategyLabPortfolioCompositionRequestModel,
    request: Request,
) -> StrategyLabBookValidationResponseModel:
    runtime = request.app.state.runtime
    result = runtime.research_service.validate_strategy_lab_portfolio(payload.to_domain())
    return StrategyLabBookValidationResponseModel.from_domain(result)


@router.post("/research/strategy-lab/resolve-handoff", response_model=StrategyLabResolvedHandoffModel)
def resolve_strategy_lab_handoff(
    payload: StrategyLabHandoffResolveRequestModel,
    request: Request,
) -> StrategyLabResolvedHandoffModel:
    runtime = request.app.state.runtime
    try:
        result = runtime.research_service.resolve_strategy_lab_handoff(
            payload.to_domain(),
            prediction_market_service=runtime.prediction_market_service,
            commodities_service=runtime.commodities_service,
        )
    except ResearchValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    return StrategyLabResolvedHandoffModel.from_domain(result)


@router.post("/research/strategy-lab/scripts", response_model=ResearchScriptDetailModel, status_code=201)
def create_research_script(
    payload: ResearchScriptCreateRequestModel,
    request: Request,
) -> ResearchScriptDetailModel:
    try:
        detail = request.app.state.runtime.research_script_service.create_script(payload.to_domain())
    except (ResearchScriptNotFoundError, ResearchScriptConflictError, ResearchScriptValidationError) as exc:
        _raise_script_http_error(exc)
    return ResearchScriptDetailModel.from_domain(detail)


@router.get("/research/strategy-lab/scripts", response_model=ResearchScriptListResponseModel)
def list_research_scripts(
    request: Request,
    include_archived: bool = Query(default=False),
) -> ResearchScriptListResponseModel:
    rows = request.app.state.runtime.research_script_service.list_scripts(
        include_archived=include_archived
    )
    return ResearchScriptListResponseModel.from_domain(rows)


@router.get(
    "/research/strategy-lab/scripts/runtime-capabilities",
    response_model=ResearchScriptRuntimeCapabilitiesModel,
)
def get_research_script_runtime_capabilities(
    request: Request,
) -> ResearchScriptRuntimeCapabilitiesModel:
    return ResearchScriptRuntimeCapabilitiesModel.from_domain(
        request.app.state.runtime.research_script_service.capabilities()
    )


@router.get(
    "/research/strategy-lab/scripts/storage-diagnostics",
    response_model=ResearchScriptStorageDiagnosticsModel,
)
def get_research_script_storage_diagnostics(
    request: Request,
) -> ResearchScriptStorageDiagnosticsModel:
    return ResearchScriptStorageDiagnosticsModel.from_domain(
        request.app.state.runtime.research_script_service.storage_diagnostics()
    )


@router.post(
    "/research/strategy-lab/scripts/storage-diagnostics/cleanup",
    response_model=ResearchScriptStorageDiagnosticsModel,
)
def cleanup_research_script_storage(
    request: Request,
) -> ResearchScriptStorageDiagnosticsModel:
    return ResearchScriptStorageDiagnosticsModel.from_domain(
        request.app.state.runtime.research_script_service.cleanup_retained_outputs()
    )


@router.get("/research/strategy-lab/scripts/{script_id}", response_model=ResearchScriptDetailModel)
def get_research_script(script_id: str, request: Request) -> ResearchScriptDetailModel:
    try:
        detail = request.app.state.runtime.research_script_service.get_script(script_id)
    except (ResearchScriptNotFoundError, ResearchScriptConflictError, ResearchScriptValidationError) as exc:
        _raise_script_http_error(exc)
    return ResearchScriptDetailModel.from_domain(detail)


@router.post(
    "/research/strategy-lab/scripts/{script_id}/duplicate",
    response_model=ResearchScriptDetailModel,
    status_code=201,
)
def duplicate_research_script(
    script_id: str,
    payload: ResearchScriptDuplicateRequestModel,
    request: Request,
) -> ResearchScriptDetailModel:
    try:
        detail = request.app.state.runtime.research_script_service.duplicate_script(
            script_id,
            title=payload.title,
        )
    except (ResearchScriptNotFoundError, ResearchScriptConflictError, ResearchScriptValidationError) as exc:
        _raise_script_http_error(exc)
    return ResearchScriptDetailModel.from_domain(detail)


@router.post(
    "/research/strategy-lab/scripts/{script_id}/archive",
    response_model=ResearchScriptDetailModel,
)
def archive_research_script(script_id: str, request: Request) -> ResearchScriptDetailModel:
    try:
        detail = request.app.state.runtime.research_script_service.archive_script(script_id)
    except (ResearchScriptNotFoundError, ResearchScriptConflictError, ResearchScriptValidationError) as exc:
        _raise_script_http_error(exc)
    return ResearchScriptDetailModel.from_domain(detail)


@router.post(
    "/research/strategy-lab/scripts/{script_id}/restore",
    response_model=ResearchScriptDetailModel,
)
def restore_research_script(script_id: str, request: Request) -> ResearchScriptDetailModel:
    try:
        detail = request.app.state.runtime.research_script_service.restore_script(script_id)
    except (ResearchScriptNotFoundError, ResearchScriptConflictError, ResearchScriptValidationError) as exc:
        _raise_script_http_error(exc)
    return ResearchScriptDetailModel.from_domain(detail)


@router.post(
    "/research/strategy-lab/scripts/{script_id}/inputs/export",
    response_model=ResearchScriptInputSnapshotModel,
    status_code=201,
)
def export_research_script_domain_input(
    script_id: str,
    payload: ResearchScriptDataExportRequestModel,
    request: Request,
) -> ResearchScriptInputSnapshotModel:
    try:
        snapshot = request.app.state.runtime.research_script_service.export_domain_input(
            script_id,
            payload.to_domain(),
        )
    except (ResearchScriptNotFoundError, ResearchScriptConflictError, ResearchScriptValidationError) as exc:
        _raise_script_http_error(exc)
    return ResearchScriptInputSnapshotModel.from_domain(snapshot)


@router.post(
    "/research/strategy-lab/scripts/{script_id}/revisions",
    response_model=ResearchScriptDetailModel,
    status_code=201,
)
def create_research_script_revision(
    script_id: str,
    payload: ResearchScriptRevisionCreateRequestModel,
    request: Request,
) -> ResearchScriptDetailModel:
    try:
        detail = request.app.state.runtime.research_script_service.create_revision(
            script_id,
            payload.to_domain(),
        )
    except (ResearchScriptNotFoundError, ResearchScriptConflictError, ResearchScriptValidationError) as exc:
        _raise_script_http_error(exc)
    return ResearchScriptDetailModel.from_domain(detail)


@router.post(
    "/research/strategy-lab/scripts/{script_id}/revisions/{revision_id}/accept",
    response_model=ResearchScriptDetailModel,
)
def accept_research_script_revision(
    script_id: str,
    revision_id: str,
    payload: ResearchScriptRevisionDecisionRequestModel,
    request: Request,
) -> ResearchScriptDetailModel:
    try:
        detail = request.app.state.runtime.research_script_service.accept_staged_revision(
            script_id,
            revision_id,
            expected_parent_sha256=payload.expected_parent_sha256,
        )
    except (ResearchScriptNotFoundError, ResearchScriptConflictError, ResearchScriptValidationError) as exc:
        _raise_script_http_error(exc)
        raise AssertionError("unreachable")
    return ResearchScriptDetailModel.from_domain(detail)


@router.post(
    "/research/strategy-lab/scripts/{script_id}/revisions/{revision_id}/reject",
    response_model=ResearchScriptDetailModel,
)
def reject_research_script_revision(
    script_id: str,
    revision_id: str,
    payload: ResearchScriptRevisionDecisionRequestModel,
    request: Request,
) -> ResearchScriptDetailModel:
    try:
        detail = request.app.state.runtime.research_script_service.reject_staged_revision(
            script_id,
            revision_id,
            expected_parent_sha256=payload.expected_parent_sha256,
        )
    except (ResearchScriptNotFoundError, ResearchScriptConflictError, ResearchScriptValidationError) as exc:
        _raise_script_http_error(exc)
        raise AssertionError("unreachable")
    return ResearchScriptDetailModel.from_domain(detail)


@router.post(
    "/research/strategy-lab/scripts/{script_id}/runs",
    response_model=ResearchScriptRunModel,
    status_code=201,
)
def create_research_script_run(
    script_id: str,
    payload: ResearchScriptRunCreateRequestModel,
    request: Request,
) -> ResearchScriptRunModel:
    try:
        run = request.app.state.runtime.research_script_service.create_run(script_id, payload.to_domain())
    except (ResearchScriptNotFoundError, ResearchScriptConflictError, ResearchScriptValidationError) as exc:
        _raise_script_http_error(exc)
    return ResearchScriptRunModel.from_domain(run)


@router.get(
    "/research/strategy-lab/scripts/{script_id}/runs",
    response_model=ResearchScriptRunListResponseModel,
)
def list_research_script_runs(script_id: str, request: Request) -> ResearchScriptRunListResponseModel:
    try:
        runs = request.app.state.runtime.research_script_service.list_runs(script_id)
    except (ResearchScriptNotFoundError, ResearchScriptConflictError, ResearchScriptValidationError) as exc:
        _raise_script_http_error(exc)
    return ResearchScriptRunListResponseModel.from_domain(runs)


@router.get(
    "/research/strategy-lab/script-inputs/{snapshot_id}",
    response_model=ResearchScriptInputSnapshotModel,
)
def get_research_script_input_snapshot(
    snapshot_id: str,
    request: Request,
) -> ResearchScriptInputSnapshotModel:
    try:
        snapshot = request.app.state.runtime.research_script_service.get_input_snapshot(snapshot_id)
    except (ResearchScriptNotFoundError, ResearchScriptConflictError, ResearchScriptValidationError) as exc:
        _raise_script_http_error(exc)
    return ResearchScriptInputSnapshotModel.from_domain(snapshot)


@router.get(
    "/research/strategy-lab/script-runs/compare",
    response_model=ResearchScriptRunComparisonModel,
)
def compare_research_script_runs(
    request: Request,
    base_run_id: str = Query(..., min_length=1, max_length=128),
    comparison_run_id: str = Query(..., min_length=1, max_length=128),
) -> ResearchScriptRunComparisonModel:
    try:
        comparison = request.app.state.runtime.research_script_service.compare_runs(
            base_run_id,
            comparison_run_id,
        )
    except (ResearchScriptNotFoundError, ResearchScriptConflictError, ResearchScriptValidationError) as exc:
        _raise_script_http_error(exc)
    return ResearchScriptRunComparisonModel.from_domain(comparison)


@router.get("/research/strategy-lab/script-runs/{run_id}", response_model=ResearchScriptRunModel)
def get_research_script_run(run_id: str, request: Request) -> ResearchScriptRunModel:
    try:
        run = request.app.state.runtime.research_script_service.get_run(run_id)
    except (ResearchScriptNotFoundError, ResearchScriptConflictError, ResearchScriptValidationError) as exc:
        _raise_script_http_error(exc)
    return ResearchScriptRunModel.from_domain(run)


@router.get("/research/strategy-lab/script-runs/{run_id}/export")
def export_research_script_run(run_id: str, request: Request) -> Response:
    try:
        filename, content = request.app.state.runtime.research_script_service.export_run_bundle(run_id)
    except (ResearchScriptNotFoundError, ResearchScriptConflictError, ResearchScriptValidationError) as exc:
        _raise_script_http_error(exc)
        raise AssertionError("unreachable")
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/research/strategy-lab/script-runs/{run_id}/outputs/{output_id}")
def download_research_script_output(run_id: str, output_id: str, request: Request) -> Response:
    try:
        filename, media_type, content = (
            request.app.state.runtime.research_script_service.get_output_artifact(run_id, output_id)
        )
    except (ResearchScriptNotFoundError, ResearchScriptConflictError, ResearchScriptValidationError) as exc:
        _raise_script_http_error(exc)
        raise AssertionError("unreachable")
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
