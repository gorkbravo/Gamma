from __future__ import annotations

from fastapi import APIRouter, Query, Request

from src.api.schemas.sitrep import SitrepWorkspaceResponseModel
from src.application.sitrep_service import SITREP_SECTIONS, SitrepWorkspaceRequest


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
