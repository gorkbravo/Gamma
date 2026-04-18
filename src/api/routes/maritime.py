from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.schemas.maritime import (
    MaritimeTrackResponseModel,
    MaritimeTrackSnippetModel,
    MaritimeWorkspaceResponseModel,
)


router = APIRouter(tags=["maritime"])


@router.get("/maritime/workspace", response_model=MaritimeWorkspaceResponseModel)
def maritime_workspace(
    request: Request,
    mode: str = Query(default="live_map"),
    force_refresh: bool = Query(default=False),
) -> MaritimeWorkspaceResponseModel:
    runtime = request.app.state.runtime
    result = runtime.maritime_service.get_workspace(mode=mode, force_refresh=force_refresh)
    return MaritimeWorkspaceResponseModel.from_domain(result)


@router.get("/maritime/vessels/{vessel_id}/track", response_model=MaritimeTrackResponseModel)
def maritime_vessel_track(
    vessel_id: str,
    request: Request,
    force_refresh: bool = Query(default=False),
) -> MaritimeTrackResponseModel:
    runtime = request.app.state.runtime
    track = runtime.maritime_service.get_vessel_track(vessel_id, force_refresh=force_refresh)
    if track is None:
        raise HTTPException(status_code=404, detail=f"Maritime vessel track not found: {vessel_id}")
    return MaritimeTrackResponseModel(
        vessel_id=vessel_id,
        track=MaritimeTrackSnippetModel.from_domain(track),
    )
