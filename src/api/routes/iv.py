from __future__ import annotations

import json
import math
import re

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import ValidationError

from src.api.schemas.iv import (
    IVSessionRequestModel,
    IVSessionStatusResponseModel,
    IVSurfaceResponseModel,
    IVUnderlyingHistoryResponseModel,
    IVSnapshotModel,
    IVSnapshotSurfaceModel,
    IVSnapshotSummaryModel,
    IVSnapshotListModel,
)
from src.application.iv_service import IVSurfaceRequest
from src.models.instruments import InstrumentReference


router = APIRouter(tags=["iv"])


def _validate_capture(surface: IVSurfaceResponseModel) -> None:
    if not re.fullmatch(r"[A-Z0-9.^-]{1,32}", surface.symbol):
        raise ValueError("Capture requires a normalized underlying symbol.")
    if not surface.snapshot_available or surface.points <= 0 or not surface.spot or surface.spot <= 0:
        raise ValueError("Load an available Options surface before capturing it.")
    if not 1 <= len(surface.expiries) <= 60 or not 1 <= len(surface.strikes) <= 1000:
        raise ValueError("Options capture has invalid expiry or strike dimensions.")
    if (len(set(surface.expiries)) != len(surface.expiries)
            or surface.strikes != sorted(set(surface.strikes))
            or any(not math.isfinite(s) or s <= 0 for s in surface.strikes)):
        raise ValueError("Options capture requires unique expiries and sorted positive strikes.")
    if (len(surface.iv_grid) != len(surface.expiries)
            or any(len(row) != len(surface.strikes) for row in surface.iv_grid)):
        raise ValueError("Options capture grid does not match its expiry and strike axes.")
    if surface.cell_sources and (len(surface.cell_sources) != len(surface.expiries)
            or any(len(row) != len(surface.strikes) for row in surface.cell_sources)):
        raise ValueError("Options capture cell sources do not match its grid.")
    if len(surface.contracts) > 5000 or len(surface.pairs) > 5000:
        raise ValueError("Options capture exceeds contract limits.")
    json.dumps(surface.model_dump(mode="json"), allow_nan=False)


@router.post("/iv/snapshots", response_model=IVSnapshotModel)
def capture_iv_snapshot(payload: IVSnapshotSurfaceModel, request: Request) -> IVSnapshotModel:
    try:
        _validate_capture(payload)
        record = request.app.state.runtime.iv_snapshot_store.save(payload.model_dump(mode="json"))
        return IVSnapshotModel.model_validate(record)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except OSError as error:
        raise HTTPException(503, "Could not save the Options capture. Check local storage and retry.") from error


@router.get("/iv/snapshots", response_model=IVSnapshotListModel)
def list_iv_snapshots(request: Request, symbol: str = Query(min_length=1, max_length=32)) -> IVSnapshotListModel:
    records, warnings = request.app.state.runtime.iv_snapshot_store.records()
    summaries = []
    for record in records:
        try:
            capture = IVSnapshotModel.model_validate(record)
            _validate_capture(capture.surface)
        except (ValidationError, ValueError, TypeError):
            warnings.append("An invalid Options capture was skipped; original file retained.")
            continue
        surface = capture.surface
        if surface.symbol == symbol.strip().upper():
            summaries.append(IVSnapshotSummaryModel(
                snapshot_id=capture.snapshot_id, captured_at=capture.captured_at,
                symbol=surface.symbol, timestamp=surface.timestamp,
                source_provider=surface.source_provider, freshness_label=surface.freshness_label,
                points=surface.points))
    summaries.sort(key=lambda row: row.captured_at.timestamp(), reverse=True)
    return IVSnapshotListModel(snapshots=summaries, warnings=warnings)


@router.get("/iv/snapshots/{snapshot_id}", response_model=IVSnapshotModel)
def read_iv_snapshot(snapshot_id: str, request: Request) -> IVSnapshotModel:
    try:
        result = IVSnapshotModel.model_validate(request.app.state.runtime.iv_snapshot_store.load(snapshot_id))
        _validate_capture(result.surface)
        return result
    except FileNotFoundError as error:
        raise HTTPException(404, "Options capture not found.") from error
    except (ValueError, TypeError, KeyError, OSError) as error:
        raise HTTPException(503, "Options capture is unreadable; original file retained.") from error


@router.get("/iv/surface", response_model=IVSurfaceResponseModel)
def iv_surface(
    request: Request,
    symbol: str = Query(default="SPY"),
    market_data_mode: str | None = Query(default=None),
    wait_seconds: float = Query(default=2.5, ge=0.5, le=90.0),
    depth_preset: str | None = Query(default=None),
    surface_model: str | None = Query(default=None),
) -> IVSurfaceResponseModel:
    runtime = request.app.state.runtime
    result = runtime.iv_service.get_surface(
        IVSurfaceRequest(
            symbol=symbol,
            market_data_mode=market_data_mode or runtime.market_data_mode,
            wait_seconds=wait_seconds,
            depth_preset=depth_preset or "standard",
            surface_model=surface_model or "linear",
        )
    )
    return IVSurfaceResponseModel.from_service_result(symbol=symbol, result=result)


@router.get("/iv/underlying-history", response_model=IVUnderlyingHistoryResponseModel)
def iv_underlying_history(
    request: Request,
    symbol: str = Query(default="SPY"),
    lookback_days: int = Query(default=252, ge=30, le=1260),
    force_refresh: bool = Query(default=False),
) -> IVUnderlyingHistoryResponseModel:
    runtime = request.app.state.runtime
    normalized_symbol = symbol.strip().upper() or "SPY"
    result = runtime.research_provider.load_instrument_history_result(
        InstrumentReference(symbol=normalized_symbol),
        lookback_days,
        bypass_cache=force_refresh,
    )
    return IVUnderlyingHistoryResponseModel.from_history_result(
        symbol=normalized_symbol,
        lookback_days=lookback_days,
        result=result,
    )


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
    start_result = runtime.iv_service.start_stream_session(
        payload.symbol,
        depth_preset=payload.depth_preset,
        surface_model=payload.surface_model,
    )
    return _iv_session_status(runtime, status_override=start_result.status, messages=start_result.messages)


@router.post("/iv/session/stop", response_model=IVSessionStatusResponseModel)
def stop_iv_session(request: Request) -> IVSessionStatusResponseModel:
    runtime = request.app.state.runtime
    runtime.iv_service.stop_stream()
    return _iv_session_status(runtime, status_override="Stopped")


def _iv_session_status(runtime, status_override: str | None = None, messages: list[str] | None = None) -> IVSessionStatusResponseModel:
    snapshot = runtime.iv_service.latest_snapshot()
    session_messages = [*(messages or []), *runtime.iv_service.drain_messages()]
    surface = (
        IVSurfaceResponseModel.from_service_result(
            symbol=runtime.iv_service.active_symbol() or "SPY",
            result=runtime.iv_service.get_surface(
                IVSurfaceRequest(
                    symbol=runtime.iv_service.active_symbol() or "SPY",
                    market_data_mode=runtime.iv_service.market_data_mode,
                    wait_seconds=0.5,
                    surface_model=runtime.iv_service.active_surface_model(),
                )
            )
            if snapshot is None and runtime.client.mock
            else _iv_result_from_snapshot(snapshot, runtime.iv_service.active_symbol() or "SPY", session_messages),
        )
    )
    return IVSessionStatusResponseModel(
        running=runtime.iv_service.is_running(),
        status_text=status_override or runtime.iv_service.status_text(),
        active_symbol=runtime.iv_service.active_symbol(),
        market_data_mode=runtime.iv_service.market_data_mode,
        surface=surface,
        messages=session_messages,
    )


def _iv_result_from_snapshot(snapshot, symbol: str, messages: list[str] | None = None):
    from src.application.iv_service import IVSurfaceResult

    if snapshot is None:
        return IVSurfaceResult(snapshot=None, messages=list(messages or []))
    return IVSurfaceResult(
        snapshot=snapshot,
        messages=list(messages or []),
        surface_model=snapshot.surface_model.model,
        surface_model_label=snapshot.surface_model.label,
        surface_model_status=snapshot.surface_model.status,
        surface_model_notes=list(snapshot.surface_model.notes),
    )
