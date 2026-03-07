from __future__ import annotations

from fastapi import APIRouter, Query, Request

from src.api.schemas.iv import IVSurfaceResponseModel
from src.application.iv_service import IVSurfaceRequest


router = APIRouter(tags=["iv"])


@router.get("/iv/surface", response_model=IVSurfaceResponseModel)
def iv_surface(
    request: Request,
    symbol: str = Query(default="SPY"),
    market_data_mode: str | None = Query(default=None),
    wait_seconds: float = Query(default=2.5, ge=0.5, le=10.0),
) -> IVSurfaceResponseModel:
    runtime = request.app.state.runtime
    result = runtime.iv_service.get_surface(
        IVSurfaceRequest(
            symbol=symbol,
            market_data_mode=market_data_mode or runtime.market_data_mode,
            wait_seconds=wait_seconds,
        )
    )
    return IVSurfaceResponseModel.from_service_result(symbol=symbol, result=result)
