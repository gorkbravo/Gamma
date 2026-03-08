from __future__ import annotations

from fastapi import APIRouter, Query, Request

from src.api.schemas.iv import (
    IVSessionRequestModel,
    IVSessionStatusResponseModel,
    IVSurfaceResponseModel,
)
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


@router.get("/iv/session", response_model=IVSessionStatusResponseModel)
def iv_session_status(request: Request) -> IVSessionStatusResponseModel:
    runtime = request.app.state.runtime
    return _iv_session_status(runtime)


@router.post("/iv/session/start", response_model=IVSessionStatusResponseModel)
def start_iv_session(
    payload: IVSessionRequestModel,
    request: Request,
) -> IVSessionStatusResponseModel:
    runtime = request.app.state.runtime
    if payload.market_data_mode:
        runtime.set_market_data_mode(payload.market_data_mode)
    start_result = runtime.iv_service.start_stream_session(payload.symbol)
    return _iv_session_status(runtime, status_override=start_result.status, messages=start_result.messages)


@router.post("/iv/session/stop", response_model=IVSessionStatusResponseModel)
def stop_iv_session(request: Request) -> IVSessionStatusResponseModel:
    runtime = request.app.state.runtime
    runtime.iv_service.stop_stream()
    return _iv_session_status(runtime, status_override="Stopped")


def _iv_session_status(runtime, status_override: str | None = None, messages: list[str] | None = None) -> IVSessionStatusResponseModel:
    snapshot = runtime.iv_service.latest_snapshot()
    surface = (
        IVSurfaceResponseModel.from_service_result(
            symbol=runtime.iv_service.active_symbol() or "SPY",
            result=runtime.iv_service.get_surface(
                IVSurfaceRequest(
                    symbol=runtime.iv_service.active_symbol() or "SPY",
                    market_data_mode=runtime.iv_service.market_data_mode,
                    wait_seconds=0.5,
                )
            )
            if snapshot is None and runtime.client.mock
            else _iv_result_from_snapshot(snapshot, runtime.iv_service.active_symbol() or "SPY"),
        )
    )
    return IVSessionStatusResponseModel(
        running=runtime.iv_service.is_running(),
        status_text=status_override or runtime.iv_service.status_text(),
        active_symbol=runtime.iv_service.active_symbol(),
        market_data_mode=runtime.iv_service.market_data_mode,
        surface=surface,
        messages=list(messages or []),
    )


def _iv_result_from_snapshot(snapshot, symbol: str):
    from src.application.iv_service import IVSurfaceResult

    return IVSurfaceResult(snapshot=snapshot) if snapshot is not None else IVSurfaceResult(snapshot=None)
