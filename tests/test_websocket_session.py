"""Guardia de sesión para WebSocket (GammaWebSocketSessionMiddleware).

El middleware HTTP de sesión no ve los WebSocket, y CORS no se aplica a ellos: antes de esta
guardia, /maritime/live/ws aceptaba cualquier conexión. Estos tests usan el relay marítimo sin
AISSTREAM_API_KEY, que responde «unavailable» sin abrir ninguna conexión externa.
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api.main import create_app
from src.api.session_auth import (
    GAMMA_SESSION_HEADER,
    GAMMA_WS_SUBPROTOCOL,
    GAMMA_WS_TOKEN_PREFIX,
    WS_POLICY_VIOLATION,
)
from src.application.runtime import build_runtime

SESSION = "expected-session"
WS_PATH = "/maritime/live/ws"


def _token_subprotocol(token: str) -> str:
    encoded = base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{GAMMA_WS_TOKEN_PREFIX}{encoded}"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MARITIME_PROVIDER", "sample")
    monkeypatch.setenv("AISSTREAM_API_KEY", "")
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    # Sin la cabecera de sesión que conftest añade por defecto a cada TestClient.
    test_client = TestClient(create_app(runtime, session_token=SESSION), headers={"X-Test-No-Gamma-Session": "1"})
    try:
        yield test_client
    finally:
        runtime.shutdown()


def _assert_rejected(client: TestClient, **kwargs) -> None:
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(WS_PATH, **kwargs):
            pass
    assert excinfo.value.code == WS_POLICY_VIOLATION


def test_websocket_without_token_is_rejected(client):
    _assert_rejected(client)
    _assert_rejected(client, subprotocols=[GAMMA_WS_SUBPROTOCOL])


def test_websocket_with_wrong_token_is_rejected(client):
    _assert_rejected(client, headers={GAMMA_SESSION_HEADER: "wrong-session"})
    _assert_rejected(client, subprotocols=[GAMMA_WS_SUBPROTOCOL, _token_subprotocol("wrong-session")])
    _assert_rejected(client, subprotocols=[GAMMA_WS_SUBPROTOCOL, f"{GAMMA_WS_TOKEN_PREFIX}%%%"])


def test_websocket_from_foreign_origin_is_rejected_even_with_token(client):
    _assert_rejected(
        client,
        headers={"Origin": "https://evil.example"},
        subprotocols=[GAMMA_WS_SUBPROTOCOL, _token_subprotocol(SESSION)],
    )
    _assert_rejected(client, headers={"Origin": "null", GAMMA_SESSION_HEADER: SESSION})


@pytest.mark.parametrize("origin", ["http://127.0.0.1:5173", "tauri://localhost", "http://tauri.localhost"])
def test_browser_websocket_with_token_subprotocol_is_accepted(client, origin):
    with client.websocket_connect(
        WS_PATH,
        headers={"Origin": origin},
        subprotocols=[GAMMA_WS_SUBPROTOCOL, _token_subprotocol(SESSION)],
    ) as websocket:
        # El servidor elige el subprotocolo de sesión y nunca devuelve el que lleva el token.
        assert websocket.accepted_subprotocol == GAMMA_WS_SUBPROTOCOL
        payload = websocket.receive_json()

    # En demo el relay responde «unavailable» sin abrir AISstream; aquí solo importa el handshake.
    assert payload["status"] == "unavailable"


def test_non_browser_websocket_with_session_header_is_accepted(client):
    with client.websocket_connect(WS_PATH, headers={GAMMA_SESSION_HEADER: SESSION}) as websocket:
        assert websocket.accepted_subprotocol is None
        payload = websocket.receive_json()

    assert payload["status"] == "unavailable"


def test_token_subprotocol_accepts_tokens_with_any_characters(tmp_path, monkeypatch):
    monkeypatch.setenv("AISSTREAM_API_KEY", "")
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    token = "<dev-only token> ñ/+="
    client = TestClient(create_app(runtime, session_token=token), headers={"X-Test-No-Gamma-Session": "1"})
    try:
        with client.websocket_connect(WS_PATH, subprotocols=[GAMMA_WS_SUBPROTOCOL, _token_subprotocol(token)]) as websocket:
            assert websocket.receive_json()["status"] == "unavailable"
    finally:
        runtime.shutdown()


def test_http_session_boundary_is_unchanged(client):
    assert client.get("/health").status_code == 200
    assert client.get("/system/status").status_code == 401
    assert client.get("/system/status", headers={GAMMA_SESSION_HEADER: SESSION}).status_code == 200
