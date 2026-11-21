"""``/ideas`` routes (Workstream 12, checkpoints I1, I2, I3a, I3b and I3c).

Local research records plus read-only criterion evaluation and hypothetical
forward tracking. Evaluation and tracking read prices and observables through
existing read-only services; the tracked book is labelled "Hypothetical, not
executed". No route here can place, stage or route an order, or touch an
account.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import NoReturn

from fastapi import APIRouter, HTTPException, Query, Request, Response

from src.api.schemas.ideas import (
    EvaluationPassModel,
    IdeaCloseRequestModel,
    IdeaReviewStatsResponseModel,
    IdeaCreateRequestModel,
    IdeaCriterionModel,
    IdeaCriterionRequestModel,
    IdeaCriterionResponseModel,
    IdeaDeleteResponseModel,
    IdeaEvidenceCreateRequestModel,
    IdeaEvidenceModel,
    IdeaJournalCreateRequestModel,
    IdeaListResponseModel,
    IdeaModel,
    IdeaPatchRequestModel,
    IdeaExplanationModel,
    IdeaExplanationsResponseModel,
    IdeaNotificationModel,
    IdeaNotificationsResponseModel,
    IdeaPinResponseModel,
    IdeaTrackingResponseModel,
    IdeaTrackingSettingsRequestModel,
    ObservableDefinitionModel,
    ObservablePreviewRequestModel,
    ObservablePreviewResponseModel,
    ObservableRefModel,
    ObservableRegistryResponseModel,
)
from src.models.ideas import Idea, IdeaSourceUnavailableError, IdeaValidationError
from src.services.idea_explanations import list_explanations
from src.services.idea_store import IdeaConflictError, IdeaNotFoundError
from src.utils.time import now_utc

router = APIRouter(tags=["ideas"])


def _service(request: Request):
    return request.app.state.runtime.idea_service


def _evaluation(request: Request):
    return request.app.state.runtime.idea_evaluation


def _observables(request: Request):
    return request.app.state.runtime.idea_observables


def _scheduler(request: Request):
    return getattr(request.app.state.runtime, "idea_scheduler", None)


def _tracking(request: Request):
    return request.app.state.runtime.idea_tracking


def _analysis(request: Request):
    return request.app.state.runtime.idea_analysis


def _idea_response(idea: Idea) -> IdeaModel:
    return IdeaModel.from_domain(idea, retrieved_at=now_utc())


def _raise(exc: Exception) -> NoReturn:
    if isinstance(exc, IdeaNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, IdeaConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, IdeaSourceUnavailableError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if isinstance(exc, (IdeaValidationError, ValueError)):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


def _split(value: str | None) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


@router.get("/ideas", response_model=IdeaListResponseModel)
def list_ideas(
    request: Request,
    status: str | None = Query(default=None, description="Comma-separated statuses; empty lists every idea."),
    tag: str | None = Query(default=None, description="Comma-separated tags; an idea must carry all of them."),
) -> IdeaListResponseModel:
    try:
        result = _service(request).list_ideas(statuses=_split(status), tags=_split(tag))
    except Exception as exc:  # noqa: BLE001 - mapped to HTTP errors
        _raise(exc)
    return IdeaListResponseModel.from_domain(result)


@router.post("/ideas", response_model=IdeaModel)
def create_idea(payload: IdeaCreateRequestModel, request: Request) -> IdeaModel:
    try:
        idea = _service(request).create_idea(payload.to_domain())
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return _idea_response(idea)


@router.get("/ideas/observables", response_model=ObservableRegistryResponseModel)
def list_observables(request: Request) -> ObservableRegistryResponseModel:
    registry = _observables(request)
    return ObservableRegistryResponseModel(
        items=[ObservableDefinitionModel(**item) for item in registry.describe_all()],
        tws_connected=registry.tws_connected(),
        retrieved_at=now_utc(),
    )


@router.post("/ideas/observables/preview", response_model=ObservablePreviewResponseModel)
def preview_observable(payload: ObservablePreviewRequestModel, request: Request) -> ObservablePreviewResponseModel:
    """Read an observable once, so the criterion form can show where it stands now."""
    registry = _observables(request)
    try:
        ref = registry.validate(payload.observable.to_domain(), condition=None, cadence=None)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    now = now_utc()
    try:
        reading = registry.read(ref, now=now)
    except Exception as exc:  # noqa: BLE001 - a provider failure is a state
        reading = None
        reason = f"The source failed: {exc}"
    else:
        reason = reading.unavailable_reason
    latest = reading.history[-1] if reading and reading.history else None
    value = reading.value if reading and reading.value is not None else (latest.value if latest else None)
    return ObservablePreviewResponseModel(
        observable=ObservableRefModel.from_domain(ref),
        available=bool(reading) and not reading.is_unavailable,
        value=value,
        value_display=(reading.value_display if reading else None)
        or (registry.format_value(ref.observable_id, value) if value is not None else None),
        as_of=(reading.as_of if reading else None) or (latest.at if latest else None),
        reason=reason,
        stale_reason=reading.stale_reason if reading else None,
        history_points=len(reading.history) if reading else 0,
        event_time=reading.event_time if reading else None,
        event_released=reading.event_released if reading else None,
        provenance=reading.provenance.to_dict() if reading and reading.provenance else None,
        warnings=list(reading.warnings) if reading else [],
        retrieved_at=now,
    )


@router.get("/ideas/notifications", response_model=IdeaNotificationsResponseModel)
def list_notifications(request: Request) -> IdeaNotificationsResponseModel:
    evaluation = _evaluation(request)
    items = evaluation.notifications()
    scheduler = _scheduler(request)
    last_pass = evaluation.last_pass
    return IdeaNotificationsResponseModel(
        items=[IdeaNotificationModel(**item.to_dict()) for item in items],
        triggered=sum(1 for item in items if item.kind == "criterion_triggered"),
        reviews_due=sum(1 for item in items if item.kind == "review_due"),
        evaluation_running=bool(scheduler and scheduler.running),
        last_pass=last_pass.to_dict() if last_pass else None,
        retrieved_at=now_utc(),
    )


@router.get("/ideas/explanations", response_model=IdeaExplanationsResponseModel)
def list_idea_explanations() -> IdeaExplanationsResponseModel:
    return IdeaExplanationsResponseModel(
        items=[IdeaExplanationModel(**item.to_dict()) for item in list_explanations()],
        retrieved_at=now_utc(),
    )


@router.get("/ideas/review", response_model=IdeaReviewStatsResponseModel)
def review_statistics(request: Request) -> IdeaReviewStatsResponseModel:
    """Review mode: the user's closed ideas and descriptive statistics of that record."""
    return IdeaReviewStatsResponseModel.from_domain(_service(request).review_statistics())


@router.post("/ideas/evaluate", response_model=EvaluationPassModel)
def evaluate_all_ideas(request: Request) -> EvaluationPassModel:
    result = _evaluation(request).evaluate_all(trigger="manual")
    return EvaluationPassModel(**result.to_dict())


@router.get("/ideas/{idea_id}", response_model=IdeaModel)
def get_idea(idea_id: str, request: Request) -> IdeaModel:
    try:
        idea = _service(request).get_idea(idea_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return _idea_response(idea)


@router.patch("/ideas/{idea_id}", response_model=IdeaModel)
def update_idea(idea_id: str, payload: IdeaPatchRequestModel, request: Request) -> IdeaModel:
    try:
        idea = _service(request).update_idea(idea_id, payload.to_domain())
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return _idea_response(idea)


@router.delete("/ideas/{idea_id}", response_model=IdeaDeleteResponseModel)
def delete_idea(idea_id: str, request: Request) -> IdeaDeleteResponseModel:
    if not _service(request).delete_idea(idea_id):
        raise HTTPException(status_code=404, detail=f"Idea {idea_id} was not found.")
    return IdeaDeleteResponseModel(success=True, recoverable=True)


@router.post("/ideas/{idea_id}/evidence", response_model=IdeaPinResponseModel)
def pin_evidence(idea_id: str, payload: IdeaEvidenceCreateRequestModel, request: Request) -> IdeaPinResponseModel:
    try:
        idea, evidence = _service(request).pin_evidence(idea_id, payload.to_domain())
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return IdeaPinResponseModel(idea=_idea_response(idea), evidence=IdeaEvidenceModel.from_domain(evidence))


@router.delete("/ideas/{idea_id}/evidence/{evidence_id}", response_model=IdeaModel)
def unpin_evidence(idea_id: str, evidence_id: str, request: Request) -> IdeaModel:
    try:
        idea = _service(request).unpin_evidence(idea_id, evidence_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return _idea_response(idea)


@router.post("/ideas/{idea_id}/journal", response_model=IdeaModel)
def add_journal_entry(idea_id: str, payload: IdeaJournalCreateRequestModel, request: Request) -> IdeaModel:
    try:
        idea = _service(request).add_journal_entry(idea_id, kind=payload.kind, body=payload.body)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return _idea_response(idea)


@router.post("/ideas/{idea_id}/activate", response_model=IdeaModel)
def activate_idea(idea_id: str, request: Request) -> IdeaModel:
    try:
        idea = _service(request).activate(idea_id)
        # Activation arms every criterion; evaluate them once now.
        if idea.criteria:
            idea = _evaluation(request).evaluate_idea(idea_id, trigger="activated")
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return _idea_response(idea)


@router.post("/ideas/{idea_id}/close", response_model=IdeaModel)
def close_idea(idea_id: str, payload: IdeaCloseRequestModel, request: Request) -> IdeaModel:
    """Close an active idea; the review is required and freezes the tracking record as it stands."""
    service = _service(request)
    try:
        idea = service.get_idea(idea_id)
        realized = None
        if idea.tracking is not None and idea.tracking.segments:
            try:
                realized = _tracking(request).compute_for(idea, persist=False).snapshot()
            except Exception:  # noqa: BLE001 - sin precios, la revisión dice que no había registro
                realized = None
        closed = service.close(idea_id, replace(payload.to_domain(), realized=realized))
        if closed.tracking is not None and closed.tracking.segments:
            try:
                _tracking(request).compute(idea_id)
            except Exception:  # noqa: BLE001 - el titular se rehace en la siguiente lectura
                pass
        closed = service.get_idea(idea_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return _idea_response(closed)


@router.post("/ideas/{idea_id}/test", response_model=IdeaModel)
def run_idea_test(idea_id: str, request: Request) -> IdeaModel:
    """Backtest the idea's legs in Strategy Lab and keep the snapshot (in-sample, no costs)."""
    try:
        idea = _analysis(request).run_test(idea_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return _idea_response(idea)


@router.post("/ideas/{idea_id}/risk", response_model=IdeaModel)
def run_idea_risk(idea_id: str, request: Request) -> IdeaModel:
    """Run Risk on the idea's research book (VaR, expected shortfall, stress replay) and keep the snapshot."""
    try:
        idea = _analysis(request).run_risk(idea_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return _idea_response(idea)


@router.post("/ideas/{idea_id}/reopen", response_model=IdeaModel)
def reopen_idea(idea_id: str, request: Request) -> IdeaModel:
    try:
        idea = _service(request).reopen(idea_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return _idea_response(idea)


@router.post("/ideas/{idea_id}/archive", response_model=IdeaModel)
def archive_idea(idea_id: str, request: Request) -> IdeaModel:
    try:
        idea = _service(request).archive(idea_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return _idea_response(idea)


@router.post("/ideas/{idea_id}/restore", response_model=IdeaModel)
def restore_idea(idea_id: str, request: Request) -> IdeaModel:
    try:
        idea = _service(request).restore(idea_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return _idea_response(idea)


@router.post("/ideas/{idea_id}/evaluate", response_model=IdeaModel)
def evaluate_idea(
    idea_id: str,
    request: Request,
    trigger: str = Query(default="manual", pattern="^(manual|open)$"),
) -> IdeaModel:
    """``open`` evaluates on-open criteria (and never-evaluated ones); ``manual`` evaluates all."""
    try:
        idea = _evaluation(request).evaluate_idea(idea_id, trigger=trigger)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return _idea_response(idea)


@router.post("/ideas/{idea_id}/criteria", response_model=IdeaCriterionResponseModel)
def add_criterion(idea_id: str, payload: IdeaCriterionRequestModel, request: Request) -> IdeaCriterionResponseModel:
    try:
        idea, criterion = _service(request).add_criterion(idea_id, payload.to_domain())
        if idea.status == "active":
            idea = _evaluation(request).evaluate_idea(
                idea_id, trigger="criterion_saved", criterion_ids=[criterion.criterion_id]
            )
            criterion = idea.criterion(criterion.criterion_id) or criterion
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return IdeaCriterionResponseModel(idea=_idea_response(idea), criterion=IdeaCriterionModel.from_domain(criterion))


@router.patch("/ideas/{idea_id}/criteria/{criterion_id}", response_model=IdeaModel)
def update_criterion(
    idea_id: str, criterion_id: str, payload: IdeaCriterionRequestModel, request: Request
) -> IdeaModel:
    try:
        idea = _service(request).update_criterion(idea_id, criterion_id, payload.to_domain())
        criterion = idea.criterion(criterion_id)
        if idea.status == "active" and criterion is not None and criterion.last_evaluation is None:
            idea = _evaluation(request).evaluate_idea(idea_id, trigger="criterion_saved", criterion_ids=[criterion_id])
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return _idea_response(idea)


@router.delete("/ideas/{idea_id}/criteria/{criterion_id}", response_model=IdeaModel)
def remove_criterion(idea_id: str, criterion_id: str, request: Request) -> IdeaModel:
    try:
        idea = _service(request).remove_criterion(idea_id, criterion_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return _idea_response(idea)


@router.post("/ideas/{idea_id}/criteria/{criterion_id}/acknowledge", response_model=IdeaModel)
def acknowledge_criterion(idea_id: str, criterion_id: str, request: Request) -> IdeaModel:
    try:
        idea = _evaluation(request).acknowledge(idea_id, criterion_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return _idea_response(idea)


@router.get("/ideas/{idea_id}/tracking", response_model=IdeaTrackingResponseModel)
def get_idea_tracking(idea_id: str, request: Request) -> IdeaTrackingResponseModel:
    """The hypothetical forward record, rebuilt from provider closes on every read."""
    try:
        result = _tracking(request).compute(idea_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return IdeaTrackingResponseModel(**result.to_dict())


@router.patch("/ideas/{idea_id}/tracking", response_model=IdeaTrackingResponseModel)
def update_idea_tracking(
    idea_id: str, payload: IdeaTrackingSettingsRequestModel, request: Request
) -> IdeaTrackingResponseModel:
    """Change the cost assumptions or the benchmark (journaled); returns the recomputed record."""
    try:
        _service(request).update_tracking_settings(idea_id, payload.to_domain())
        result = _tracking(request).compute(idea_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return IdeaTrackingResponseModel(**result.to_dict())


@router.get("/ideas/{idea_id}/export")
def export_idea(
    idea_id: str,
    request: Request,
    format: str = Query(default="md", pattern="^(md|json)$"),
) -> Response:
    service = _service(request)
    try:
        idea = service.get_idea(idea_id)
        tracking_result = None
        if idea.tracking is not None and idea.tracking.segments:
            try:
                tracking_result = _tracking(request).compute_for(idea, persist=False).to_dict()
            except Exception:  # noqa: BLE001 - la exportación sale igual, con el último titular guardado
                tracking_result = None
        if format == "json":
            content = json.dumps(
                service.export_json(idea_id, tracking_result=tracking_result), indent=2, ensure_ascii=False, allow_nan=False
            )
            media_type = "application/json; charset=utf-8"
        else:
            content = service.export_markdown(idea_id, tracking_result=tracking_result)
            media_type = "text/markdown; charset=utf-8"
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return Response(content=content, media_type=media_type, headers=_download_headers(idea, format))


def _download_headers(idea: Idea, extension: str) -> dict[str, str]:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", idea.title.strip()).strip("-._")[:80] or idea.idea_id
    return {"Content-Disposition": f'attachment; filename="idea-{stem}.{extension}"'}
