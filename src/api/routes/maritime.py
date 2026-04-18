from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from src.api.schemas.maritime import (
    MaritimeTrackResponseModel,
    MaritimeTrackSnippetModel,
    MaritimeWorkspaceResponseModel,
)
from src.services.maritime_adapters import (
    AISSTREAM_DEFAULT_ENDPOINT,
    normalize_aisstream_position_message,
)
from src.utils.time import now_utc


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


@router.websocket("/maritime/live/ws")
async def maritime_live_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    api_key = (os.getenv("AISSTREAM_API_KEY", "") or "").strip()
    if not api_key:
        await websocket.send_json(
            {
                "type": "status",
                "status": "unavailable",
                "message": "AISSTREAM_API_KEY is not configured on the backend.",
            }
        )
        await websocket.close(code=1000)
        return

    try:
        import websockets
    except ImportError:
        await websocket.send_json(
            {
                "type": "status",
                "status": "unavailable",
                "message": "Python package 'websockets' is required for AISstream live collection.",
            }
        )
        await websocket.close(code=1011)
        return

    upstream = None
    upstream_recv_task: asyncio.Task | None = None
    client_recv_task: asyncio.Task | None = asyncio.create_task(websocket.receive_text())
    message_index = 0

    async def close_upstream() -> None:
        nonlocal upstream, upstream_recv_task
        if upstream_recv_task is not None:
            upstream_recv_task.cancel()
            upstream_recv_task = None
        if upstream is not None:
            try:
                await upstream.close()
            except Exception:
                pass
            upstream = None

    async def ensure_upstream():
        nonlocal upstream
        if upstream is not None:
            return upstream
        upstream = await websockets.connect(
            AISSTREAM_DEFAULT_ENDPOINT,
            open_timeout=10,
            ping_interval=20,
            ping_timeout=20,
        )
        await websocket.send_json({"type": "status", "status": "connected"})
        return upstream

    try:
        while True:
            tasks = [task for task in (client_recv_task, upstream_recv_task) if task is not None]
            if not tasks:
                break
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

            if client_recv_task in done:
                try:
                    raw = client_recv_task.result()
                except WebSocketDisconnect:
                    break
                client_recv_task = asyncio.create_task(websocket.receive_text())

                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "status", "status": "error", "message": "Invalid JSON message."})
                    continue

                action = str(message.get("type") or message.get("action") or "subscribe").strip().lower()
                if action in {"close", "suspend", "unsubscribe"}:
                    await close_upstream()
                    await websocket.send_json({"type": "status", "status": "suspended"})
                    continue

                box = _normalize_live_bounding_box(message)
                if box is None:
                    await websocket.send_json(
                        {"type": "status", "status": "error", "message": "A valid viewport bounding box is required."}
                    )
                    continue

                upstream_socket = await ensure_upstream()
                subscription = {
                    "APIKey": api_key,
                    "BoundingBoxes": [box],
                    "FilterMessageTypes": ["PositionReport"],
                }
                await upstream_socket.send(json.dumps(subscription))
                if upstream_recv_task is None or upstream_recv_task.done():
                    upstream_recv_task = asyncio.create_task(upstream_socket.recv())
                await websocket.send_json(
                    {
                        "type": "status",
                        "status": "subscribed",
                        "bounding_box": box,
                    }
                )

            if upstream_recv_task in done:
                try:
                    upstream_raw = upstream_recv_task.result()
                except Exception as exc:
                    await websocket.send_json(
                        {
                            "type": "status",
                            "status": "error",
                            "message": f"AISstream connection closed: {exc.__class__.__name__}.",
                        }
                    )
                    await close_upstream()
                    continue

                if upstream is not None:
                    upstream_recv_task = asyncio.create_task(upstream.recv())

                try:
                    payload = json.loads(upstream_raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                normalized = normalize_aisstream_position_message(payload, index=message_index, retrieved_at=now_utc())
                message_index += 1
                if normalized is None:
                    continue
                position, vessel = normalized
                await websocket.send_json(
                    {
                        "type": "position",
                        "position": _jsonable_dataclass(position),
                        "vessel": _jsonable_dataclass(vessel),
                    }
                )
    except WebSocketDisconnect:
        pass
    finally:
        if client_recv_task is not None:
            client_recv_task.cancel()
        await close_upstream()


def _normalize_live_bounding_box(message: dict[str, Any]) -> list[list[float]] | None:
    raw_box = message.get("bounding_box") or message.get("boundingBox")
    if raw_box is None:
        raw_boxes = message.get("BoundingBoxes")
        if isinstance(raw_boxes, list) and raw_boxes:
            raw_box = raw_boxes[0]
    if not (
        isinstance(raw_box, list)
        and len(raw_box) == 2
        and all(isinstance(point, list) and len(point) == 2 for point in raw_box)
    ):
        return None
    try:
        min_lat = float(raw_box[0][0])
        min_lon = float(raw_box[0][1])
        max_lat = float(raw_box[1][0])
        max_lon = float(raw_box[1][1])
    except (TypeError, ValueError):
        return None
    min_lat, max_lat = sorted((_clamp(min_lat, -90, 90), _clamp(max_lat, -90, 90)))
    min_lon, max_lon = sorted((_clamp(min_lon, -180, 180), _clamp(max_lon, -180, 180)))
    if min_lat == max_lat or min_lon == max_lon:
        return None
    return [[min_lat, min_lon], [max_lat, max_lon]]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _jsonable_dataclass(value):
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        return {key: _jsonable_dataclass(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable_dataclass(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value
