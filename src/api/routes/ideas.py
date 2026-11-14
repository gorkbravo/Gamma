"""``/ideas`` routes (Workstream 12, checkpoint I1).

Read and write local research records only. No route here evaluates
criteria, tracks prices, calls a market-data provider or touches a broker.
"""

from __future__ import annotations

import json
import re
from typing import NoReturn

from fastapi import APIRouter, HTTPException, Query, Request, Response

from src.api.schemas.ideas import (
    IdeaCreateRequestModel,
    IdeaDeleteResponseModel,
    IdeaEvidenceCreateRequestModel,
    IdeaEvidenceModel,
    IdeaJournalCreateRequestModel,
    IdeaListResponseModel,
    IdeaModel,
    IdeaPatchRequestModel,
    IdeaPinResponseModel,
)
from src.models.ideas import Idea, IdeaValidationError
from src.services.idea_store import IdeaConflictError, IdeaNotFoundError
from src.utils.time import now_utc

router = APIRouter(tags=["ideas"])


def _service(request: Request):
    return request.app.state.runtime.idea_service


def _idea_response(idea: Idea) -> IdeaModel:
    return IdeaModel.from_domain(idea, retrieved_at=now_utc())


def _raise(exc: Exception) -> NoReturn:
    if isinstance(exc, IdeaNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, IdeaConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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


@router.get("/ideas/{idea_id}/export")
def export_idea(
    idea_id: str,
    request: Request,
    format: str = Query(default="md", pattern="^(md|json)$"),
) -> Response:
    service = _service(request)
    try:
        idea = service.get_idea(idea_id)
        if format == "json":
            content = json.dumps(service.export_json(idea_id), indent=2, ensure_ascii=False, allow_nan=False)
            media_type = "application/json; charset=utf-8"
        else:
            content = service.export_markdown(idea_id)
            media_type = "text/markdown; charset=utf-8"
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return Response(content=content, media_type=media_type, headers=_download_headers(idea, format))


def _download_headers(idea: Idea, extension: str) -> dict[str, str]:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", idea.title.strip()).strip("-._")[:80] or idea.idea_id
    return {"Content-Disposition": f'attachment; filename="idea-{stem}.{extension}"'}
