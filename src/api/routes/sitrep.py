from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.schemas.sitrep import (
    SitrepFollowUpCreateRequestModel,
    SitrepFollowUpDeleteResponseModel,
    SitrepFollowUpListResponseModel,
    SitrepFollowUpModel,
    SitrepFollowUpUpdateRequestModel,
    SitrepWorkspaceResponseModel,
)
from src.application.sitrep_service import SITREP_SECTIONS, SitrepWorkspaceRequest
from src.models.sitrep import SitrepFollowUpCreateRequest, SitrepFollowUpUpdateRequest


router = APIRouter(tags=["sitrep"])


@router.get("/sitrep/workspace", response_model=SitrepWorkspaceResponseModel)
def sitrep_workspace(
    request: Request,
    sections: str = Query(
        default="",
        description=f"Optional comma-separated subset of {', '.join(SITREP_SECTIONS)}; empty loads all sections.",
    ),
    force_refresh: bool = Query(default=False),
) -> SitrepWorkspaceResponseModel:
    runtime = request.app.state.runtime
    requested = tuple(item.strip().lower() for item in sections.split(",") if item.strip()) or SITREP_SECTIONS
    result = runtime.sitrep_service.get_workspace(
        SitrepWorkspaceRequest(sections=requested, force_refresh=force_refresh)
    )
    return SitrepWorkspaceResponseModel.from_domain(result)


@router.get("/sitrep/follow-ups", response_model=SitrepFollowUpListResponseModel)
def list_sitrep_follow_ups(request: Request) -> SitrepFollowUpListResponseModel:
    runtime = request.app.state.runtime
    return SitrepFollowUpListResponseModel.from_domain(runtime.sitrep_service.list_follow_ups())


@router.post("/sitrep/follow-ups", response_model=SitrepFollowUpModel)
def create_sitrep_follow_up(
    payload: SitrepFollowUpCreateRequestModel,
    request: Request,
) -> SitrepFollowUpModel:
    runtime = request.app.state.runtime
    try:
        item = runtime.sitrep_service.create_follow_up(
            SitrepFollowUpCreateRequest(
                row_id=payload.row_id,
                title=payload.title,
                source=payload.source,
                tone=payload.tone,
                detail=payload.detail,
                meta=payload.meta,
                note=payload.note,
                handoff=payload.handoff,
                saved_at=payload.saved_at.replace(tzinfo=None) if payload.saved_at else None,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SitrepFollowUpModel.from_domain(item)


@router.patch("/sitrep/follow-ups/{item_id}", response_model=SitrepFollowUpModel)
def update_sitrep_follow_up(
    item_id: str,
    payload: SitrepFollowUpUpdateRequestModel,
    request: Request,
) -> SitrepFollowUpModel:
    runtime = request.app.state.runtime
    try:
        item = runtime.sitrep_service.update_follow_up(
            item_id,
            SitrepFollowUpUpdateRequest(note=payload.note, status=payload.status),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail=f"SITREP follow-up {item_id} was not found.")
    return SitrepFollowUpModel.from_domain(item)


@router.delete("/sitrep/follow-ups/{item_id}", response_model=SitrepFollowUpDeleteResponseModel)
def delete_sitrep_follow_up(item_id: str, request: Request) -> SitrepFollowUpDeleteResponseModel:
    runtime = request.app.state.runtime
    return SitrepFollowUpDeleteResponseModel(success=runtime.sitrep_service.delete_follow_up(item_id))
